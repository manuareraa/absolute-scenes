"""Give a Show fixture real audio: ``python -m chalktalk_crew voice-show``.

Crew chapters already have an MP3 in the crew cache (``pipeline.run`` with Azure Speech); it is
copied next to the fixture. Tool chapters (ghost, VAR) were timed by the fake speech client, so
their SSML is synthesized here, and the new bookmarks and word timings replace their cues and
words. Each SSML is synthesized once: results are cached under ``<cache root>/voiced/`` by the
hash of the SSML, so a re-run costs no Speech characters.

The input fixture is never changed. ``--out DIR`` gets ``DIR/<fixture name>.json`` and
``DIR/<fixture name>/audio/<overlay id>.mp3``: copied as is into ``web/public/fixtures/``, the
audio sits in the folder the web player resolves ``script.audio_url`` against
(``/fixtures/<show id>/``).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .azure import names_previous
from .speech import SpeechResult, WordTiming

STATIC_ASSET_CAP = 25 * 1024 * 1024  # Workers static assets: 25 MiB per file


@dataclass
class VoiceLog:
    copied: list[str] = field(default_factory=list)
    synthesized: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)  # same SSML as a chapter voiced before
    missing: list[str] = field(default_factory=list)  # crew chapter with no cached MP3
    cues_moved: int = 0  # cues written after their word, moved back onto it
    speech_characters: int = 0
    files: int = 0
    total_bytes: int = 0
    largest_bytes: int = 0
    cue_word_gap_max_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _cached(root: Path, key: str) -> SpeechResult | None:
    meta, mp3 = root / f"{key}.json", root / f"{key}.mp3"
    if not (meta.exists() and mp3.exists()):
        return None
    m = json.loads(meta.read_text())
    words = [WordTiming(w["text"], w["offset_ms"], w["duration_ms"]) for w in m["words"]]
    return SpeechResult(words, m["bookmarks"], m["duration_ms"], audio=mp3.read_bytes())


def _store(root: Path, key: str, r: SpeechResult) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{key}.mp3").write_bytes(r.audio or b"")
    words = [w.__dict__ for w in r.words]
    meta = {"words": words, "bookmarks": r.bookmarks, "duration_ms": r.duration_ms}
    (root / f"{key}.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def cue_word_gap_ms(overlay: dict[str, Any]) -> int:
    """Largest distance from a cue to its nearest word start (0 when every cue is snapped)."""
    starts = [w["offset_ms"] for w in overlay["script"].get("words") or []]
    gaps = [min(abs(c["offset_ms"] - s) for s in starts) for c in overlay["script"]["cues"]]
    return max(gaps, default=0) if starts else 0


def _norm(word: str) -> str:
    return word.strip(".,;:!?\"'¿¡()…").lower()


def resnap_trailing(overlay: dict[str, Any]) -> int:
    """Move each cue the writer put after its word (``names_previous``) onto that word's start.

    Works from the text, not the cue's current offset, so it is idempotent and also fixes
    overlays cached before ``snap_bookmarks`` learned this. Returns the number of cues moved.
    """
    script = overlay["script"]
    words = script.get("words") or []
    moved = 0
    for cue in script["cues"]:
        mark = cue["cue_id"]
        tag = re.search(rf"<bookmark mark='{re.escape(mark)}'\s*/>", script["ssml"])
        if not (tag and names_previous(script["ssml"], mark)):
            continue
        before = re.sub(r"<[^>]+>", " ", script["ssml"][: tag.start()])
        tokens = [t for t in (_norm(x) for x in before.split()) if t]
        if not tokens:
            continue
        nth = tokens.count(tokens[-1])  # the named word is the nth occurrence of its text
        hits = [w["offset_ms"] for w in words if _norm(w["text"]) == tokens[-1]]
        if len(hits) >= nth and cue["offset_ms"] != hits[nth - 1]:
            cue["offset_ms"] = hits[nth - 1]
            moved += 1
    return moved


def voice_overlay(overlay: dict[str, Any], r: SpeechResult, audio_url: str | None) -> None:
    """Retime ``overlay``'s script to the synthesized speech ``r``."""
    script = overlay["script"]
    script["cues"] = [
        {"cue_id": c["cue_id"], "offset_ms": r.bookmarks[c["cue_id"]]} for c in script["cues"]
    ]
    script["words"] = [
        {"text": w.text, "offset_ms": w.offset_ms, "duration_ms": w.duration_ms} for w in r.words
    ]
    if audio_url:
        script["audio_url"] = audio_url


def voice_show(fixture: dict[str, Any], crew_root: Path, out_dir: Path, speech: Any) -> VoiceLog:
    """Write audio for every chapter of every show into ``out_dir`` (``.../audio``) and point
    the fixture's overlays at it. ``crew_root`` is ``<cache>/<match_id>-<digest8>``."""
    log = VoiceLog()
    voiced = crew_root / "voiced"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}  # SSML hash -> audio_url already written
    for show in fixture["shows"]:
        for seg in show["segments"]:
            ov = seg["overlay"]
            oid, script = ov["id"], ov["script"]
            url = f"audio/{oid}.mp3"
            crew_mp3 = crew_root / "audio" / f"{oid}.mp3"
            if script.get("audio_url") and crew_mp3.exists():
                shutil.copyfile(crew_mp3, out_dir / f"{oid}.mp3")
                script["audio_url"] = url
                log.copied.append(oid)
            elif script.get("audio_url"):
                log.missing.append(oid)
                script.pop("audio_url")
                continue
            else:
                key = hashlib.sha256(script["ssml"].encode()).hexdigest()[:16]
                r = _cached(voiced, key)
                if r is None:
                    before = int(getattr(speech, "characters", 0))
                    r = speech.synthesize(script["ssml"])
                    log.speech_characters += int(getattr(speech, "characters", 0)) - before
                    _store(voiced, key, r)
                    log.synthesized.append(oid)
                if key in written:
                    url = written[key]
                    log.reused.append(oid)
                elif r.audio:
                    (out_dir / f"{oid}.mp3").write_bytes(r.audio)
                    written[key] = url
                voice_overlay(ov, r, url if r.audio else None)
            seg.pop("audio_url", None)  # the player prefers it over the script's
            log.cues_moved += resnap_trailing(ov)
            log.cue_word_gap_max_ms = max(log.cue_word_gap_max_ms, cue_word_gap_ms(ov))
    sizes = [f.stat().st_size for f in out_dir.glob("*.mp3")]
    log.files, log.total_bytes, log.largest_bytes = len(sizes), sum(sizes), max(sizes, default=0)
    return log


def main(args: Any) -> dict[str, Any]:  # pragma: no cover - manual, see the module docstring
    from chalktalk_sim import DEMO_BEATS, MatchConfig, simulate

    from .config import CrewConfig
    from .speech import FakeSpeechClient

    match = simulate(MatchConfig(seed=args.seed, half_minutes=args.half_minutes, beats=DEMO_BEATS))
    digest = match.digest()[:8]
    fixture = json.loads(args.fixture.read_text())
    crew_root = args.cache / f"{fixture['match_id']}-{digest}"
    if not (crew_root / "overlays").is_dir():
        raise SystemExit(f"no crew cache at {crew_root}")
    config = CrewConfig.from_env()
    speech: Any = FakeSpeechClient()
    if config.speech_backend == "azure":
        from .azure import AzureSpeechClient

        speech = AzureSpeechClient(config)
    out_json = args.out / args.fixture.name
    if out_json.resolve() == args.fixture.resolve():
        raise SystemExit("--out must not be the fixture's own folder")
    out_dir = out_json.with_suffix("") / "audio"
    log = voice_show(fixture, crew_root, out_dir, speech)
    if log.largest_bytes > STATIC_ASSET_CAP:
        raise SystemExit(f"an MP3 is over the 25 MiB static asset cap: {log.largest_bytes} B")
    out_json.write_text(json.dumps(fixture, separators=(",", ":")))
    report = {"fixture": str(out_json), "audio": str(out_dir), **log.as_dict()}
    if args.queue:  # the producer queue carries the same crew overlays: fix their cues too
        queue = json.loads(args.queue.read_text())
        report["queue_cues_moved"] = sum(resnap_trailing(o) for o in queue["overlays"])
        out_queue = args.out / args.queue.name
        if out_queue.resolve() == args.queue.resolve():
            raise SystemExit("--out must not be the queue's own folder")
        out_queue.write_text(json.dumps(queue, separators=(",", ":")))
        report["queue"] = str(out_queue)
    return report
