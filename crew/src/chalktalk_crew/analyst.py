"""Analyst: chooses which tools explain a moment for a lens, then calls them in parallel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .director import Moment
from .tools import ToolClient, ToolResult, call_tools


@dataclass(frozen=True)
class ToolSpec:
    shape: str  # stroke shape in the overlay vocabulary
    slot: str  # script slot name for the value
    tolerance: float  # verifier tolerance on re-run (absolute)
    measures: str  # "attacking" | "defending": whose numbers these are


TOOL_SPECS: dict[str, ToolSpec] = {
    "line_gap": ToolSpec("pass_lane", "gap_m", 0.5, "defending"),
    "pass_options": ToolSpec("arrow", "pass_options", 0.0, "attacking"),
    "pitch_control": ToolSpec("zone", "control_pct", 2.0, "attacking"),
    "pressing_intensity": ToolSpec("ring", "pressers", 0.0, "defending"),
    "offside_line": ToolSpec("offside_line", "line_x_m", 0.2, "defending"),
    "shape_compactness": ToolSpec("zone", "block_m2", 10.0, "defending"),
    "xg": ToolSpec("arrow", "xg", 0.01, "attacking"),
}

LENS_TOOLS: dict[str, tuple[list[str], int]] = {
    "casual": (["line_gap", "pass_options"], 2),
    "newcomer": (["line_gap", "shape_compactness"], 2),
    "analyst": (["line_gap", "pitch_control", "pressing_intensity", "pass_options"], 4),
}


def primary_tool(moment: Moment) -> str:
    if moment.trigger == "offside":
        return "offside_line"
    if moment.trigger == "goal" or any(e["type"] in ("shot", "save") for e in moment.events):
        return "xg"
    return "line_gap"


def tool_args(name: str, moment: Moment) -> dict[str, Any]:
    team = moment.attacking if TOOL_SPECS[name].measures == "attacking" else moment.defending
    args: dict[str, Any] = {"t": moment.focus_t, "team": team}
    if name in ("pass_options", "pressing_intensity", "xg") and moment.focus_player:
        args["player"] = moment.focus_player
    return args


def plan(moment: Moment, lens: str) -> list[tuple[str, dict[str, Any]]]:
    extras, cap = LENS_TOOLS[lens]
    names = list(dict.fromkeys([primary_tool(moment), *extras]))[:cap]
    return [(name, tool_args(name, moment)) for name in names]


class Analyst:
    def __init__(self, tools: ToolClient) -> None:
        self.tools = tools

    def analyse(self, moment: Moment, lens: str) -> list[ToolResult]:
        return call_tools(self.tools, plan(moment, lens))
