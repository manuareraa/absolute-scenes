"""Pundit: turns typed tool results into claims, a stroke plan and a script template.

Claims, values and geometry are built by code from tool outputs; the LLM only writes the template
(phrasing and order) around slots and cue marks.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import partial
from typing import Any

from .analyst import TOOL_SPECS
from .director import Moment
from .lang import team_ref
from .llm import Beat, DraftRequest, FakeLLMClient, LLMClient
from .script import (
    TemplateError,
    check_perspective,
    check_template,
    fix_cues,
    fix_slot_names,
    format_value,
)
from .tools import ToolResult

# What each tool's number says, for the writer; {who} is the team the tool measured.
MEANINGS = {
    "line_gap": "the gap between the midfield line and the back line of {who}, who are "
    "defending. It is space for the attacking team, a weakness in {whose} shape",
    "shape_compactness": "the area covered by the defensive block of {who}, who are defending",
    "pressing_intensity": "how hard {who}, defending, press the player on the ball",
    "offside_line": "the offside line held by the last defender of {who}",
    "pitch_control": "the share of the zone around the ball that {who}, attacking, would reach "
    "first; it is {half} half",
    "pass_options": "how many forward passes the player on the ball for {who} could choose",
    "xg": "what the chance {who} created was worth in expected goals",
}


def whose(side: str, team: str) -> tuple[str, str]:
    """(who, whose) for a meaning: our team, the opponents, or the home/away side."""
    if side == "neutral":
        return f"the {team} side", f"the {team} side's"
    return ("our own team", "our own") if side == team else ("the opponents", "the opponents'")


def beat_meaning(tool: str, side: str, team: str, value: object) -> str:
    who, own = whose(side, team)
    half = "under" if isinstance(value, int | float) and value < 50 else "over"
    return MEANINGS[tool].format(who=who, whose=own, half=half)


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
        sides: list[dict[str, str]] = []
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
            value = res.output["value"]
            beats.append(
                Beat(
                    res.name,
                    spec.slot,
                    cue_id,
                    res.output.get("unit"),
                    team_ref(side, team, lang),
                    beat_meaning(res.name, side, team, value),
                )
            )
            minority = res.name == "pitch_control" and isinstance(value, int | float) and value < 50
            sides.append(
                {
                    "tool": res.name,
                    "slot": spec.slot,
                    "ours": "neutral"
                    if side == "neutral"
                    else "ours"
                    if side == team
                    else "theirs",
                    "minority": "1" if minority else "",
                }
            )
            values[spec.slot] = format_value(res.output["value"], res.output.get("unit"), lang)

        request = DraftRequest(lens=lens, side=side, lang=lang, trigger=moment.trigger, beats=beats)
        slots = {b.slot for b in beats}
        cues = {b.cue_id for b in beats}
        xg_slot = TOOL_SPECS["xg"].slot if any(b.tool == "xg" for b in beats) else None
        check_rules = partial(check_template, slots=slots, cues=cues, lang=lang, xg_slot=xg_slot)
        marks = [(b.tool, b.slot, b.cue_id) for b in beats]

        def tidy(text: str) -> str:
            """Fix misspelt slots and put back lost cue marks, then apply every rule."""
            text = fix_cues(fix_slot_names(text, slots), marks, lang)
            check_rules(text)
            check_perspective(text, sides, lang)
            return text

        fallback = False
        try:
            template = tidy(self.llm.draft(request))
        except TemplateError as err:
            try:  # one repair attempt, told exactly which rule broke
                template = tidy(self.llm.draft(replace(request, feedback=str(err))))
            except TemplateError:
                # Still broken (a free number, a lost cue): use the rule-based writer.
                template, fallback = self._fallback.draft(request), True
                check_rules(template)
        return Draft(claims, strokes, template, values, fallback)
