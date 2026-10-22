"""The Analyst's tools backed by the real analytics (``chalktalk_mcp.tools.Tools``, in-process).

Maps each crew tool name to an MCP tool on one match and reshapes the answer into the crew's
tool output: one value and unit, one drawable stroke (``shape`` + ``geometry``), the evidence
window, and the MCP ``tool_call`` under ``provenance``. Every number and coordinate comes from
the MCP tool; this module only picks and rescales (shares become percent).
"""

from __future__ import annotations

from typing import Any

from .tools import HALF_LENGTH, HALF_WIDTH, ToolError

SCAN_BACK_MS = 3000  # how far back to look for a ball carrier
SCAN_STEP_MS = 200
PRESS_WINDOW_MS = 5000
CONTROL_ZONE_M = (30.0, 24.0)  # length x width of the zone around the ball
PRESS_RING_M = 4.0


def _pick(geometry: list[dict[str, Any]], *shapes: str) -> dict[str, Any]:
    for shape in shapes:
        for item in geometry:
            if item["shape"] == shape:
                return item
    raise ToolError(f"no {'/'.join(shapes)} geometry in the tool output")


def _clamp(x: float, y: float) -> list[float]:
    return [
        round(max(-HALF_LENGTH, min(HALF_LENGTH, x)), 2),
        round(max(-HALF_WIDTH, min(HALF_WIDTH, y)), 2),
    ]


class CoreToolClient:
    """``ToolClient`` over the real analytics for one match (deterministic, so re-runs verify)."""

    NAMES = (
        "line_gap",
        "pitch_control",
        "pressing_intensity",
        "pass_options",
        "offside_line",
        "shape_compactness",
        "xg",
    )

    def __init__(self, tools: Any, match_id: str) -> None:
        self.tools = tools
        self.match_id = match_id
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self.NAMES:
            raise KeyError(f"unknown tool {name!r}")
        self.calls.append((name, dict(args)))
        try:
            out, mcp = getattr(self, f"_{name}")(int(args["t"]), args)
        except (ValueError, KeyError) as err:
            raise ToolError(f"{name}: {err}") from err
        out.setdefault("evidence_window", mcp["evidence_window"])
        out["provenance"] = {"impl": "chalktalk_core", "tool_call": mcp["tool_call"]}
        return out

    # ------------------------------------------------------------------ helpers
    def _frame(self, t: int) -> dict[str, Any]:
        return self.tools.frame(self.match_id, t)["details"]["frame"]

    def _carrier_t(self, t: int) -> int:
        """The latest time at or before ``t`` (within SCAN_BACK_MS) when someone has the ball."""
        for back in range(0, SCAN_BACK_MS + 1, SCAN_STEP_MS):
            if self._frame(t - back)["ball"]["owner"]:
                return t - back
        raise ToolError(f"nobody has the ball in the {SCAN_BACK_MS} ms before t={t}")

    @staticmethod
    def _stroke(item: dict[str, Any], value: Any, unit: str) -> dict[str, Any]:
        return {
            "value": value,
            "unit": unit,
            "shape": item["shape"],
            "geometry": item["geometry_m"],
        }

    # ------------------------------------------------------------------ tools
    def _line_gap(self, t: int, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        r = self.tools.line_gap(self.match_id, t, args["team"])
        return self._stroke(_pick(r["geometry"], "arrow", "line"), r["value"], "m"), r

    def _shape_compactness(self, t: int, args: dict[str, Any]):
        r = self.tools.team_shape(self.match_id, t, args["team"])
        return self._stroke(_pick(r["geometry"], "zone"), round(r["value"]), "m2"), r

    def _offside_line(self, t: int, args: dict[str, Any]):
        r = self.tools.offside_line(self.match_id, t, args["team"])
        item = _pick(r["geometry"], "offside_line")
        return self._stroke(item, round(abs(item["geometry_m"]["points"][0][0]), 1), "m"), r

    def _pitch_control(self, t: int, args: dict[str, Any]):
        ball = self._frame(t)["ball"]
        dx, dy = CONTROL_ZONE_M[0] / 2, CONTROL_ZONE_M[1] / 2
        x0, y0 = _clamp(ball["x"] - dx, ball["y"] - dy)
        x1, y1 = _clamp(ball["x"] + dx, ball["y"] + dy)
        r = self.tools.pitch_control(self.match_id, t, args["team"], zone=[x0, y0, x1, y1])
        return self._stroke(_pick(r["geometry"], "zone"), round(r["value"] * 100), "%"), r

    def _pressing_intensity(self, t: int, args: dict[str, Any]):
        r = self.tools.pressing_intensity(self.match_id, t - PRESS_WINDOW_MS, t, args["team"])
        ball = self._frame(t)["ball"]
        geometry: dict[str, Any] = {
            "points": [_clamp(ball["x"], ball["y"])],
            "radius": PRESS_RING_M,
        }
        if ball["owner"]:
            geometry["player_id"] = ball["owner"]
        out = {"value": round(r["value"] * 100), "unit": "%", "shape": "ring", "geometry": geometry}
        return out, r

    def _pass_options(self, t: int, args: dict[str, Any]):
        r = self.tools.pass_options(self.match_id, self._carrier_t(t))
        lanes = [g for g in r["geometry"] if g["shape"] in ("pass_lane", "arrow")]
        if not lanes:
            raise ToolError("the carrier has no pass options")
        return self._stroke(lanes[0], len(lanes), "options"), r

    def _xg(self, t: int, args: dict[str, Any]):
        player = args.get("player")
        if player is None:
            r = self.tools.shot_xg(self.match_id, self._carrier_t(t))
        else:
            r = self.tools.shot_xg(self.match_id, t, player)
        return self._stroke(_pick(r["geometry"], "arrow", "line"), round(r["value"], 2), "xG"), r
