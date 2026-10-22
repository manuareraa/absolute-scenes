"""Live pipeline: POST verified overlays to the edge Worker's ``/api/overlay``.

The Worker (``workers/edge``) checks the ``x-chalktalk-secret`` header against its
``OVERLAY_SECRET`` and fans the overlay out to the match's viewers. The base URL and secret come
from env (``CHALKTALK_EDGE_URL``, ``CHALKTALK_OVERLAY_SECRET``); locally the URL is
``wrangler dev`` (``http://127.0.0.1:8787``) and the secret sits in ``workers/edge/.dev.vars``.
Only gated overlays are posted: the edge does a light shape check, the contract check is ours.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
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
