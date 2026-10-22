"""Build ``show`` contracts (post-match drawn tactical shows) from overlays.

One show per (side, lens, lang); segments in match order, one chapter per overlay. Only overlays
that passed the Verifier gate go in, unless ``require_gate=False``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from chalktalk_contracts import validate

CHAPTER_TOPICS = {
    "line_gap": "The gap between the lines",
    "xg": "The chance",
    "offside_line": "The offside line",
    "pitch_control": "Who owned the space",
    "pressing_intensity": "The press",
    "pass_options": "The pass that was on",
    "shape_compactness": "The defensive block",
}


def match_minute(match_tc: int) -> int:
    return match_tc // 60_000 + 1


def chapter_title(overlay: dict[str, Any]) -> str:
    claims = overlay.get("claims") or []
    tool = claims[0]["tool_call"]["name"] if claims else ""
    topic = CHAPTER_TOPICS.get(tool, "The breakdown")
    return f"{match_minute(overlay['match_tc'])}' · {topic}"


def gate_passed(overlay: dict[str, Any]) -> bool:
    return bool((overlay.get("gate") or {}).get("passed"))


def build_show(
    overlays: list[dict[str, Any]],
    *,
    match_id: str,
    side: str,
    lens: str,
    lang: str,
    show_id: str | None = None,
    created_at: datetime | None = None,
    require_gate: bool = True,
) -> dict[str, Any]:
    """Assemble one show. Raises ``ValueError`` on a mixed batch or when nothing is usable."""
    for ov in overlays:
        if (ov["side"], ov["lens"], ov["lang"]) != (side, lens, lang):
            raise ValueError(
                f"overlay {ov['id']} is {ov['side']}/{ov['lens']}/{ov['lang']}, "
                f"not {side}/{lens}/{lang}"
            )
    usable = [ov for ov in overlays if gate_passed(ov) or not require_gate]
    if not usable:
        raise ValueError("no overlay passed the gate; a show needs at least one segment")

    segments = []
    for ov in sorted(usable, key=lambda o: (o["match_tc"], o["id"])):
        segment: dict[str, Any] = {
            "chapter_title": chapter_title(ov),
            "overlay": {**ov, "surface": "show", "stream_tc": None},
        }
        if audio := ov["script"].get("audio_url"):
            segment["audio_url"] = audio
        segments.append(segment)

    show: dict[str, Any] = {
        "id": show_id or f"show-{match_id}-{side}-{lens}-{lang}",
        "match_id": match_id,
        "side": side,
        "lens": lens,
        "lang": lang,
        "segments": segments,
    }
    if created_at is not None:
        if created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        show["created_at"] = created_at.isoformat()
    validate("show", show)
    return show


def build_shows(
    overlays: list[dict[str, Any]],
    *,
    match_id: str,
    created_at: datetime | None = None,
    require_gate: bool = True,
) -> list[dict[str, Any]]:
    """Fan-out: one show per (side, lens, lang) group that has at least one usable overlay."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for ov in overlays:
        groups[(ov["side"], ov["lens"], ov["lang"])].append(ov)
    shows = []
    for (side, lens, lang), group in sorted(groups.items()):
        if require_gate and not any(gate_passed(ov) for ov in group):
            continue
        shows.append(
            build_show(
                group,
                match_id=match_id,
                side=side,
                lens=lens,
                lang=lang,
                created_at=created_at,
                require_gate=require_gate,
            )
        )
    return shows
