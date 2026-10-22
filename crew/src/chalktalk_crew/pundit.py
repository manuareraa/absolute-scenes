"""Pundit: turns typed tool results into claims, a stroke plan and a script template.

Claims, values and geometry are built by code from tool outputs; the LLM only writes the template
(phrasing and order) around slots and cue marks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .analyst import TOOL_SPECS
from .director import Moment
from .llm import Beat, DraftRequest, FakeLLMClient, LLMClient
from .script import TemplateError, check_template, format_value
from .tools import ToolResult


def team_ref(side: str, team: str) -> str:
    if side == "neutral":
        return f"the {team} side's"
    return "our" if side == team else "their"


@dataclass(frozen=True)
class Draft:
    claims: list[dict[str, Any]]
    strokes: list[dict[str, Any]]
    template: str
    values: dict[str, str]
    fallback: bool


class Pundit:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self._fallback = FakeLLMClient()

    def write(
        self, moment: Moment, results: list[ToolResult], *, lens: str, side: str, lang: str
    ) -> Draft:
        claims: list[dict[str, Any]] = []
        strokes: list[dict[str, Any]] = []
        beats: list[Beat] = []
        values: dict[str, str] = {}
        for i, res in enumerate(results, start=1):
            spec = TOOL_SPECS[res.name]
            team = res.args.get("team", moment.attacking)
            claim_id, cue_id = f"c{i}", f"k{i}"
            claims.append(
                {
                    "id": claim_id,
                    "text_slot": spec.slot,
                    "value": res.output["value"],
                    "unit": res.output.get("unit"),
                    "tool_call": res.tool_call,
                    "evidence_window": res.output.get("evidence_window")
                    or {"start_t": moment.window[0], "end_t": moment.window[1]},
                    "tolerance": spec.tolerance,
                    "verified": None,
                }
            )
            strokes.append(
                {
                    "id": f"s{i}",
                    "shape": res.output.get("shape", spec.shape),
                    "geometry_m": res.output["geometry"],
                    "style": {"color": team if spec.measures == "attacking" else "chalk"},
                    "cue_id": cue_id,
                    "claim_ids": [claim_id],
                }
            )
            beats.append(
                Beat(res.name, spec.slot, cue_id, res.output.get("unit"), team_ref(side, team))
            )
            values[spec.slot] = format_value(res.output["value"], res.output.get("unit"))

        request = DraftRequest(lens=lens, side=side, lang=lang, trigger=moment.trigger, beats=beats)
        slots = {b.slot for b in beats}
        cues = {b.cue_id for b in beats}
        template = self.llm.draft(request)
        fallback = False
        try:
            check_template(template, slots, cues)
        except TemplateError:
            # The model broke the rules (a free number, a lost cue): use the rule-based writer.
            template, fallback = self._fallback.draft(request), True
            check_template(template, slots, cues)
        return Draft(claims, strokes, template, values, fallback)
