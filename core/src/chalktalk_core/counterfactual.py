"""'What should they have done?': move named players and re-measure the same frame.

The Tactician (an LLM) proposes a change as structured offsets for named players, in the
player's own terms (metres back towards their goal, infield towards the middle, towards the
ball), never as coordinates. This module turns the offsets into positions, swaps them into the
frame and re-runs pitch control, the line gap, pressure on the ball and OBSO for the moved
team, before and after. The Critic accepts the change only if these numbers improve.

xG here depends on the shot location only, so moving defenders cannot change it; OBSO (the
chance of scoring from the next action, which uses pitch control) is the threat measure that
does respond to positions.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from . import analytics as an
from .geometry import HALF_LENGTH, HALF_WIDTH, other_team

MAX_MOVES = 3
MAX_SHIFT_M = 10.0
ZONE_M = (30.0, 24.0)  # length x width of the zone around the ball
EPS = {"pitch_control": 0.005, "line_gap_m": 0.1, "pressure": 0.005, "obso": 0.0005}

Frame = dict[str, Any]


def _offset(s: Any, k: int, team: str, move: dict[str, Any]) -> np.ndarray:
    """The move as a vector in metres, capped at ``MAX_SHIFT_M``."""
    back = np.array([-s.sign(team), 0.0])
    y = float(s.xy[k][1])
    infield = np.array([0.0, -math.copysign(1.0, y) if abs(y) > 0.5 else 0.0])
    to_ball = np.asarray(s.ball[:2], dtype=float) - s.xy[k]
    norm = float(np.linalg.norm(to_ball))
    to_ball = to_ball / norm if norm > 1e-6 else np.zeros(2)
    vec = (
        float(move.get("back_m", 0.0)) * back
        + float(move.get("infield_m", 0.0)) * infield
        + float(move.get("to_ball_m", 0.0)) * to_ball
    )
    length = float(np.linalg.norm(vec))
    if length > MAX_SHIFT_M:
        vec *= MAX_SHIFT_M / length
    return vec


def _metrics(frame: Frame, team: str) -> dict[str, float | None]:
    """From ``team``'s view. None when a metric does not apply (e.g. pressure in possession)."""
    s = an._snap(frame)
    bx, by = float(s.ball[0]), float(s.ball[1])
    dx, dy = ZONE_M[0] / 2, ZONE_M[1] / 2
    zone = [
        max(-HALF_LENGTH, bx - dx),
        max(-HALF_WIDTH, by - dy),
        min(HALF_LENGTH, bx + dx),
        min(HALF_WIDTH, by + dy),
    ]
    out: dict[str, float | None] = {
        "pitch_control": float(an.pitch_control(s, team, zone=zone).value),
        "line_gap_m": None,
        "pressure": None,
        "obso": None,
    }
    try:
        out["line_gap_m"] = float(an.line_gap(s, team).value)
    except ValueError:
        pass
    on_ball = s.owner_team()
    if on_ball == other_team(team):
        out["pressure"] = float(an.pressure_on_ball(s).value)
        out["obso"] = float(an.obso(s, on_ball).value)
    elif on_ball == team:
        out["obso"] = float(an.obso(s, team).value)
    return out


def _better(name: str, before: float, after: float, in_possession: bool) -> int:
    """+1 if the change helps the moved team, -1 if it hurts, 0 within noise."""
    diff = after - before
    if abs(diff) <= EPS[name]:
        return 0
    lower_is_better = name == "line_gap_m" or (name == "obso" and not in_possession)
    return 1 if (diff < 0) == lower_is_better else -1


def what_if(frame: Frame, team: str, moves: Sequence[dict[str, Any]]) -> an.Result:
    """Move ``team``'s named players by structured offsets and re-measure the frame.

    Each move is ``{player_id, back_m, infield_m, to_ball_m}`` (metres, negative for the
    opposite way; at most ``MAX_SHIFT_M`` in total). The value is the number of metrics that
    improved minus those that got worse, from ``team``'s view."""
    if team not in ("home", "away"):
        raise ValueError("team must be 'home' or 'away'")
    if not moves or len(moves) > MAX_MOVES:
        raise ValueError(f"give 1..{MAX_MOVES} moves")
    s = an._snap(frame)
    changed = copy.deepcopy(frame)
    by_id = {p["id"]: p for p in changed["players"]}
    geometry: list[dict[str, Any]] = []
    applied = []
    for move in moves:
        pid = str(move.get("player_id"))
        k = s.index(pid)  # KeyError for an unknown player
        if str(s.team[k]) != team:
            raise ValueError(f"{pid} does not play for {team}")
        if any(a["player_id"] == pid for a in applied):
            raise ValueError(f"{pid} moved twice")
        start = s.xy[k].astype(float)
        end = start + _offset(s, k, team, move)
        end = np.array(
            [np.clip(end[0], -HALF_LENGTH, HALF_LENGTH), np.clip(end[1], -HALF_WIDTH, HALF_WIDTH)]
        )
        by_id[pid]["x"], by_id[pid]["y"] = float(end[0]), float(end[1])
        if changed["ball"].get("owner") == pid:
            changed["ball"]["x"], changed["ball"]["y"] = float(end[0]), float(end[1])
        shift = round(float(np.linalg.norm(end - start)), 2)
        applied.append(
            {"player_id": pid, "from": an._pt(start), "to": an._pt(end), "shift_m": shift}
        )
        geometry.append(
            {
                "shape": "ghost_path",
                "geometry_m": {"points": [an._pt(start), an._pt(end)], "player_id": pid},
                "style": {"color": "ghost", "dash": True},
            }
        )
        geometry.append({"shape": "ring", "geometry_m": {"points": [an._pt(end)], "radius": 1.5}})
    before, after = _metrics(frame, team), _metrics(changed, team)
    in_possession = s.owner_team() == team
    metrics: dict[str, dict[str, Any]] = {}
    net = 0
    for name in before:
        b, a = before[name], after[name]
        if b is None or a is None:
            continue
        better = _better(name, b, a, in_possession)
        net += better
        metrics[name] = {"before": round(b, 4), "after": round(a, 4), "better": better}
    return an.Result(
        metric="what_if",
        value=net,
        unit="metrics",
        evidence_window=an._window(s.t),
        geometry=geometry,
        details={
            "team": team,
            "in_possession": in_possession,
            "moves": applied,
            "metrics": metrics,
            "improved": sorted(n for n, m in metrics.items() if m["better"] > 0),
            "worse": sorted(n for n, m in metrics.items() if m["better"] < 0),
        },
    )
