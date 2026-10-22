"""Verifier gate: re-runs every tool call and checks the overlay before it can air.

Checks (all code, no LLM):
- each claim's value matches a fresh re-run of its tool within ``tolerance`` -> ``verified``;
- every number spoken in the script is the formatted value of a claim (no ungrounded numbers);
- every stroke's geometry is exactly a tool output's geometry (coordinates never from the LLM);
- every stroke's cue exists and its start (``offset_ms - lead_ms``) is not before the audio.
"""

from __future__ import annotations

from typing import Any

from .script import NUMBER, format_value
from .tools import ToolClient, canonical_json, output_hash


def _value_ok(claimed: Any, fresh: Any, tolerance: float | None) -> bool:
    if isinstance(claimed, bool) or isinstance(fresh, bool) or tolerance is None:
        return claimed == fresh
    if isinstance(claimed, int | float) and isinstance(fresh, int | float):
        return abs(claimed - fresh) <= tolerance
    return claimed == fresh


def _rate(ok: int, total: int) -> float:
    return 1.0 if total == 0 else ok / total


class Verifier:
    def __init__(self, tools: ToolClient) -> None:
        self.tools = tools

    def check(self, overlay: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of ``overlay`` with ``claims[].verified`` and ``gate`` set."""
        ov = {**overlay, "claims": [dict(c) for c in overlay["claims"]]}
        fresh_geometry: dict[str, str] = {}
        verified = hash_ok = 0
        for claim in ov["claims"]:
            call = claim["tool_call"]
            try:
                out = self.tools.call(call["name"], call["args"])
            except Exception:  # a tool that fails on re-run cannot back a claim
                claim["verified"] = False
                continue
            claim["verified"] = _value_ok(claim["value"], out.get("value"), claim.get("tolerance"))
            verified += claim["verified"]
            hash_ok += output_hash(out) == call["output_hash"]
            fresh_geometry[claim["id"]] = canonical_json(out.get("geometry"))

        lang = ov.get("lang")
        spoken = {
            format_value(c["value"], c.get("unit"), lang) for c in ov["claims"] if c["verified"]
        }
        numbers = NUMBER.findall(ov["script"]["text"])
        grounded = sum(n in spoken for n in numbers)

        cues = {c["cue_id"]: c["offset_ms"] for c in ov["script"]["cues"]}
        geom_ok = cue_ok = 0
        for stroke in ov["strokes"]:
            geom = canonical_json(stroke["geometry_m"])
            geom_ok += any(fresh_geometry.get(cid) == geom for cid in stroke.get("claim_ids") or [])
            offset = cues.get(stroke["cue_id"])
            cue_ok += offset is not None and offset - stroke.get("lead_ms", 150) >= 0

        n_claims, n_strokes = len(ov["claims"]), len(ov["strokes"])
        scores = {
            "grounding_rate": _rate(grounded, len(numbers)),
            "unsupported_numbers": float(len(numbers) - grounded),
            "claim_verified_rate": _rate(verified, n_claims),
            "hash_match_rate": _rate(hash_ok, n_claims),
            "geometry_from_tools": _rate(geom_ok, n_strokes),
            "cue_integrity": _rate(cue_ok, n_strokes),
        }
        passed = (
            n_claims > 0
            and scores["grounding_rate"] == 1.0
            and scores["claim_verified_rate"] == 1.0
            and scores["geometry_from_tools"] == 1.0
            and scores["cue_integrity"] == 1.0
        )
        ov["gate"] = {"passed": passed, "scores": scores}
        return ov
