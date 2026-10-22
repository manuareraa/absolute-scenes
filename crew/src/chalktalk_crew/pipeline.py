"""End to end: seeded sim match -> Director -> real analytics -> crew -> Verifier -> cache.

Each (moment, lens, side, lang) is generated once. Verified overlays, their MP3, cue sheet and
WebVTT captions land under ``<cache>/<match_id>-<digest8>/``; a moment already in
``overlays/`` (or in ``rejected/``, unless retried) is never sent to Foundry or Speech again.
Every run writes a log with token counts and an estimated cost to ``runs/``. With a poster
(``--post``), every verified overlay of the run, fresh or cached, is also POSTed to the edge
Worker (``live.py``).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any

from chalktalk_contracts import validate

from .azure import AzureCallError
from .captions import webvtt
from .config import CrewConfig
from .core_tools import CoreToolClient
from .crew import Crew, NoEvidence, crew_from_env


@dataclass
class RunOptions:
    seed: int = 7
    half_minutes: float = 45.0
    max_moments: int = 6
    lenses: tuple[str, ...] = ("casual",)
    sides: tuple[str, ...] = ("home",)
    lang: str = "en-GB"  # comma list for several languages: "en-GB,es-ES"
    cache: Path = Path(".chalktalk-cache")
    budget_usd: float = 0.25
    retry_rejected: bool = False
    post: bool = False


@dataclass
class RunLog:
    match_id: str
    digest: str
    started: str
    generated: list[str] = field(default_factory=list)
    cached: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    llm: dict[str, Any] = field(default_factory=dict)
    speech_characters: int = 0
    est_cost_usd: float = 0.0
    stopped: str | None = None
    posted: list[str] = field(default_factory=list)
    post_failed: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def overlay_id(moment_id: str, lens: str, side: str, lang: str) -> str:
    return f"ov-{moment_id}-{lens}-{side}-{lang}"


def cue_sheet(overlay: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per cue: when it is spoken, the word it lands on and when its stroke starts."""
    words = overlay["script"].get("words") or []
    strokes = {s["cue_id"]: s for s in overlay["strokes"]}
    rows = []
    for cue in overlay["script"]["cues"]:
        word = next((w["text"] for w in words if w["offset_ms"] >= cue["offset_ms"]), None)
        stroke = strokes.get(cue["cue_id"])
        rows.append(
            {
                "cue_id": cue["cue_id"],
                "offset_ms": cue["offset_ms"],
                "word": word,
                "stroke_id": stroke and stroke["id"],
                "shape": stroke and stroke["shape"],
                "stroke_start_ms": stroke and cue["offset_ms"] - stroke.get("lead_ms", 150),
            }
        )
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _usage(crew: Crew) -> tuple[dict[str, Any], int, float]:
    usage = getattr(crew.pundit.llm, "usage", None)
    llm = usage.as_dict() if usage else {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
    chars = int(getattr(crew.speech, "characters", 0))
    return llm, chars, float(llm.get("est_cost_usd", 0.0))  # Speech F0 is free


def _post(poster: Any, log: RunLog, oid: str, overlay: dict[str, Any]) -> None:
    from .live import PostError

    try:
        poster.send(log.match_id, overlay)
        log.posted.append(oid)
    except PostError as err:  # the overlay stays cached; a re-run with --post sends it again
        log.post_failed[oid] = str(err)[:200]


def run(
    opts: RunOptions,
    *,
    config: CrewConfig | None = None,
    llm: Any = None,
    speech: Any = None,
    poster: Any = None,
) -> RunLog:
    """Generate the missing overlays for one match. ``llm``/``speech``/``poster`` override the
    env clients; the poster is used only when ``opts.post`` is set."""
    from chalktalk_mcp.store import Store
    from chalktalk_mcp.tools import Tools
    from chalktalk_sim import DEMO_BEATS, MatchConfig, simulate

    match = simulate(MatchConfig(seed=opts.seed, half_minutes=opts.half_minutes, beats=DEMO_BEATS))
    store = Store(half_minutes=opts.half_minutes)
    source = store.put(match)
    digest = match.digest()
    tools = CoreToolClient(Tools(store), source.match_id)
    crew = crew_from_env(tools, config)
    if llm is not None:
        crew.pundit.llm = llm
    tap = AudioTap(speech if speech is not None else crew.speech)
    crew.speech = tap

    if opts.post and poster is None:
        from .live import OverlayPoster

        poster = OverlayPoster.from_env()
    root = Path(opts.cache) / f"{source.match_id}-{digest[:8]}"
    log = RunLog(source.match_id, digest, time.strftime("%Y-%m-%dT%H:%M:%S"))
    moments = crew.director.moments(match.events)[: opts.max_moments]
    for moment in moments:
        for lens in opts.lenses:
            for side, lang in product(opts.sides, opts.lang.split(",")):
                oid = overlay_id(moment.id, lens, side, lang)
                done = root / "overlays" / f"{oid}.json"
                bad = root / "rejected" / f"{oid}.json"
                if done.exists() or (bad.exists() and not opts.retry_rejected):
                    log.cached.append(oid)
                    if done.exists() and opts.post:
                        _post(poster, log, oid, json.loads(done.read_text()))
                    continue
                spent = _usage(crew)[2]
                if spent >= opts.budget_usd:
                    log.stopped = f"budget: ${spent:.4f} >= ${opts.budget_usd}"
                    log.skipped.append(oid)
                    continue
                tap.audio = None
                try:
                    overlay = crew.breakdown(moment, lens=lens, side=side, lang=lang)
                except NoEvidence:
                    log.skipped.append(oid)
                    continue
                except AzureCallError as err:  # not cached, so the next run tries it again
                    log.failed[oid] = str(err)[:200]
                    continue
                if not overlay["gate"]["passed"]:
                    _write_json(bad, overlay)
                    log.rejected.append(oid)
                    continue
                if tap.audio:
                    mp3 = root / "audio" / f"{oid}.mp3"
                    mp3.parent.mkdir(parents=True, exist_ok=True)
                    mp3.write_bytes(tap.audio)
                    overlay["script"]["audio_url"] = f"audio/{oid}.mp3"
                    validate("overlay", overlay)
                _write_json(root / "cues" / f"{oid}.json", cue_sheet(overlay))
                (root / "captions").mkdir(exist_ok=True)
                (root / "captions" / f"{oid}.vtt").write_text(webvtt(overlay))
                _write_json(done, overlay)
                bad.unlink(missing_ok=True)
                log.generated.append(oid)
                if opts.post:
                    _post(poster, log, oid, overlay)

    log.llm, log.speech_characters, log.est_cost_usd = _usage(crew)
    _write_json(root / "runs" / f"{log.started.replace(':', '')}.json", log.as_dict())
    return log


class AudioTap:
    """Wraps a speech client and keeps the last MP3, which the overlay itself does not carry."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.audio: bytes | None = None

    def synthesize(self, ssml: str) -> Any:
        result = self.inner.synthesize(ssml)
        self.audio = result.audio
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)
