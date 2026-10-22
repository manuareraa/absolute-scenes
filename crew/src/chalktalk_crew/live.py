"""Live pipeline: POST verified overlays to the edge Worker's ``/api/overlay``.

The Worker (``workers/edge``) checks the ``x-chalktalk-secret`` header against its
``OVERLAY_SECRET`` and fans the overlay out to the match's viewers. The base URL and secret come
from env (``CHALKTALK_EDGE_URL``, ``CHALKTALK_OVERLAY_SECRET``); locally the URL is
``wrangler dev`` (``http://127.0.0.1:8787``) and the secret sits in ``workers/edge/.dev.vars``.
Only gated overlays are posted: the edge does a light shape check, the contract check is ours.

``watch`` follows the match clock (the ``MatchHub`` WebSocket, ``ws_clock``) and posts each
overlay ``ahead_ms`` before its ``match_tc``, so the producer console has it queued in time.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chalktalk_contracts import validate

SECRET_HEADER = "x-chalktalk-secret"
MAX_OVERLAY_BYTES = 256 * 1024  # the Worker's own limit

Post = Callable[[str, dict[str, str], bytes], tuple[int, str]]


class PostError(RuntimeError):
    pass


def _urllib_post(url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")
    except urllib.error.URLError as err:
        raise PostError(f"edge unreachable: {err.reason}") from err


class OverlayPoster:
    """Posts ``{match_id, overlay}`` with the shared-secret header; retries 429 and 5xx."""

    def __init__(
        self,
        base_url: str,
        secret: str,
        *,
        post: Post | None = None,
        retries: int = 2,
    ) -> None:
        if not (base_url and secret):
            raise RuntimeError("posting needs CHALKTALK_EDGE_URL and CHALKTALK_OVERLAY_SECRET")
        self.url = base_url.rstrip("/") + "/api/overlay"
        self._secret = secret
        self.post = post or _urllib_post
        self.retries = retries
        self.posted = 0

    def __repr__(self) -> str:
        return f"OverlayPoster(url={self.url!r})"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, **kw: Any) -> OverlayPoster:
        env = dict(os.environ) if env is None else env
        return cls(
            env.get("CHALKTALK_EDGE_URL") or "http://127.0.0.1:8787",
            env.get("CHALKTALK_OVERLAY_SECRET") or "",
            **kw,
        )

    def send(self, match_id: str, overlay: dict[str, Any]) -> dict[str, Any]:
        """POST one verified overlay; returns the Worker's JSON (``{ok, id, viewers}``)."""
        if not overlay.get("gate", {}).get("passed"):
            raise PostError(f"{overlay.get('id')}: not verified, never posted")
        validate("overlay", overlay)
        body = json.dumps({"match_id": match_id, "overlay": overlay}).encode()
        if len(body) > MAX_OVERLAY_BYTES:
            raise PostError(f"{overlay['id']}: {len(body)} bytes is over the edge limit")
        headers = {"Content-Type": "application/json", SECRET_HEADER: self._secret}
        for attempt in range(self.retries + 1):
            status, text = self.post(self.url, headers, body)
            if status == 200:
                self.posted += 1
                return json.loads(text)
            if (status != 429 and status < 500) or attempt == self.retries:
                raise PostError(f"HTTP {status}: {text[:200]}")
            time.sleep(0.5 * 2**attempt)
        raise AssertionError("unreachable")


def ws_clock(base_url: str, match_id: str, *, timeout_s: float = 30.0) -> Iterator[int]:
    """Match time (ms) from the hub's WebSocket: ``hello``, ``frames`` and ``clock`` messages.

    Joining counts as a viewer, so it starts (or resumes) the clock like any viewer does. Ends
    on ``end`` or when no message arrives for ``timeout_s`` (the clock was paused).
    """
    from websockets.sync.client import connect

    url = base_url.rstrip("/").replace("http", "ws", 1) + f"/ws/match/{match_id}"
    with connect(url, open_timeout=15, max_size=8 * 1024 * 1024) as ws:
        while True:
            try:
                msg = json.loads(ws.recv(timeout=timeout_s))
            except TimeoutError:
                return
            if msg.get("type") == "end":
                return
            clock = msg.get("clock")
            if isinstance(clock, dict) and isinstance(clock.get("t"), int | float):
                yield int(clock["t"])


def verified_overlays(cache: Path, log: Any) -> list[dict[str, Any]]:
    """The run's verified overlays (fresh and cached) from ``<cache>/<match_id>-<digest8>/``."""
    root = Path(cache) / f"{log.match_id}-{log.digest[:8]}" / "overlays"
    paths = (root / f"{oid}.json" for oid in [*log.generated, *log.cached])
    return [json.loads(p.read_text()) for p in paths if p.exists()]


@dataclass
class WatchLog:
    posted: dict[str, int] = field(default_factory=dict)  # overlay id -> clock t when posted
    missed: list[str] = field(default_factory=list)  # already past when the crew joined
    failed: dict[str, str] = field(default_factory=dict)
    last_t: int | None = None


def watch(
    clock: Iterable[int],
    overlays: list[dict[str, Any]],
    poster: OverlayPoster,
    match_id: str,
    *,
    ahead_ms: int = 8000,
    late_ms: int = 2000,
) -> WatchLog:
    """Post each overlay once the clock is within ``ahead_ms`` of its moment.

    Overlays whose moment is more than ``late_ms`` behind the clock are not posted (the moment
    has aired). A seek back re-arms nothing: each overlay is posted at most once per watch.
    """
    queue = sorted(overlays, key=lambda o: o["match_tc"])
    log = WatchLog()
    for t in clock:
        log.last_t = t
        while queue and queue[0]["match_tc"] - ahead_ms <= t:
            overlay = queue.pop(0)
            if overlay["match_tc"] + late_ms < t:
                log.missed.append(overlay["id"])
                continue
            try:
                poster.send(match_id, overlay)
                log.posted[overlay["id"]] = t
            except PostError as err:
                log.failed[overlay["id"]] = str(err)[:200]
        if not queue:
            break
    return log
