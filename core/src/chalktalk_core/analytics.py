"""Deterministic match analytics over contract frames.

Every function returns a :class:`Result`: a value with its unit, the evidence window (match
ms) that backs it, drawable geometry in pitch metres (partial overlay strokes: ``shape`` and
``geometry_m``; the crew adds ids and cues) and details. A claim binds to one result through
its tool call; the Verifier re-runs the function and checks the value within tolerance.

Models (all reimplemented here, numpy only):
- time to intercept (TTI) with a reaction time and a top speed, turned into a probability by
  a logistic curve, after Spearman et al. (2017) and Bekkers (2025);
- pitch control as a softmax over TTI of every player to each grid cell;
- a parametric xG (distance and goal angle) and a parametric xT surface.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from .geometry import GOAL_WIDTH, HALF_LENGTH, HALF_WIDTH, other_team
from .snapshot import Snapshot

REACTION_S = 0.7
PLAYER_VMAX = 7.0
TTI_SIGMA = 0.45
PRESS_HORIZON_S = 1.5
CONTROL_TEMPERATURE_S = 0.35
PASS_SPEED = 15.0

Frame = dict[str, Any]


@dataclass
class Result:
    metric: str
    value: float | int | bool | str
    unit: str | None
    evidence_window: dict[str, int]
    geometry: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- helpers
def _snap(frame: Frame | Snapshot) -> Snapshot:
    return frame if isinstance(frame, Snapshot) else Snapshot.from_frame(frame)


def _window(t0: int, t1: int | None = None) -> dict[str, int]:
    return {"start_t": int(t0), "end_t": int(t0 if t1 is None else t1)}


def _pt(p: Sequence[float]) -> list[float]:
    return [round(float(p[0]), 2), round(float(p[1]), 2)]


def _logistic(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-math.pi / (math.sqrt(3.0) * TTI_SIGMA) * x))


def time_to_intercept(xy: np.ndarray, vel: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """(N players, M targets) seconds: keep running for the reaction time, then go straight
    to the target at top speed."""
    after = xy + vel * REACTION_S
    d = np.linalg.norm(after[:, None, :] - targets[None, :, :], axis=2)
    return REACTION_S + d / PLAYER_VMAX


def convex_hull(points: np.ndarray) -> np.ndarray:
    """Monotone chain; counter-clockwise hull without repeating the first point."""
    pts = sorted({(float(x), float(y)) for x, y in points})
    if len(pts) <= 2:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def polygon_area(poly: np.ndarray) -> float:
    if len(poly) < 3:
        return 0.0
    x, y = poly[:, 0], poly[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def _lines(s: Snapshot, team: str) -> list[np.ndarray]:
    """Split the outfield players into defence, midfield and attack lines at the two largest
    gaps along the attacking direction (at least 3 defenders, 2 midfielders, 1 forward)."""
    idx = s.outfield(team)
    xn = s.xy[idx, 0] * s.sign(team)
    order = idx[np.argsort(xn)]
    xs = np.sort(xn)
    n = len(xs)
    best, cut = -1.0, (min(4, n - 3), min(8, n - 1))
    for i in range(3, n - 2):
        for j in range(i + 2, n):
            g = (xs[i] - xs[i - 1]) + (xs[j] - xs[j - 1])
            if g > best:
                best, cut = g, (i, j)
    i, j = cut
    return [order[:i], order[i:j], order[j:]]


def _line_geometry(s: Snapshot, members: np.ndarray) -> dict[str, Any]:
    x = float(np.mean(s.xy[members, 0]))
    ys = s.xy[members, 1]
    return {"shape": "line", "geometry_m": {"points": [_pt((x, ys.min())), _pt((x, ys.max()))]}}


# --------------------------------------------------------------------------- shape
def team_shape(frame: Frame | Snapshot, team: str) -> Result:
    """Outfield hull area (compactness), width, length and the three line heights."""
    s = _snap(frame)
    idx = s.outfield(team)
    pts = s.xy[idx]
    hull = convex_hull(pts)
    lines = _lines(s, team)
    sign = s.sign(team)
    heights = [float(np.mean(s.xy[m, 0])) for m in lines]
    names = ("defence", "midfield", "attack")
    return Result(
        metric="team_shape",
        value=round(polygon_area(hull), 1),
        unit="m2",
        evidence_window=_window(s.t),
        geometry=[{"shape": "zone", "geometry_m": {"points": [_pt(p) for p in hull]}}]
        + [_line_geometry(s, m) for m in lines],
        details={
            "team": team,
            "width_m": round(float(np.ptp(pts[:, 1])), 2),
            "length_m": round(float(np.ptp(pts[:, 0])), 2),
            "line_x": {n: round(h, 2) for n, h in zip(names, heights, strict=True)},
            "line_players": {n: [s.ids[i] for i in m] for n, m in zip(names, lines, strict=True)},
            "gaps_m": {
                "defence_midfield": round((heights[1] - heights[0]) * sign, 2),
                "midfield_attack": round((heights[2] - heights[1]) * sign, 2),
            },
        },
    )


def line_gap(frame: Frame | Snapshot, team: str, between: str = "defence_midfield") -> Result:
    """Distance in metres between two of the team's lines along the pitch."""
    s = _snap(frame)
    shape = team_shape(s, team)
    if between not in shape.details["gaps_m"]:
        raise ValueError("between must be 'defence_midfield' or 'midfield_attack'")
    a, b = between.split("_")
    xa, xb = shape.details["line_x"][a], shape.details["line_x"][b]
    lines = shape.geometry[1:]
    pick = {"defence": lines[0], "midfield": lines[1], "attack": lines[2]}
    mid_y = float(np.mean(s.xy[s.outfield(team), 1]))
    return Result(
        metric="line_gap",
        value=shape.details["gaps_m"][between],
        unit="m",
        evidence_window=_window(s.t),
        geometry=[
            pick[a],
            pick[b],
            {"shape": "arrow", "geometry_m": {"points": [_pt((xa, mid_y)), _pt((xb, mid_y))]}},
        ],
        details={"team": team, "between": between, "from_x": xa, "to_x": xb},
    )


def distance_between(frame: Frame | Snapshot, a: str, b: str) -> Result:
    s = _snap(frame)
    pa, pb = s.xy[s.index(a)], s.xy[s.index(b)]
    return Result(
        metric="distance_between",
        value=round(float(np.linalg.norm(pa - pb)), 2),
        unit="m",
        evidence_window=_window(s.t),
        geometry=[{"shape": "line", "geometry_m": {"points": [_pt(pa), _pt(pb)]}}],
        details={"a": a, "b": b},
    )


# --------------------------------------------------------------------------- pressure
def pressure_on_ball(frame: Frame | Snapshot) -> Result:
    """Probability that at least one opponent reaches the ball carrier within 1.5 s."""
    s = _snap(frame)
    if s.owner is None:
        return Result("pressure_on_ball", 0.0, "prob", _window(s.t), details={"carrier": None})
    c = s.index(s.owner)
    team = str(s.team[c])
    opp = s.members(other_team(team))
    carrier_next = (s.xy[c] + s.vel[c] * REACTION_S)[None, :]
    tti = time_to_intercept(s.xy[opp], s.vel[opp], carrier_next)[:, 0]
    p = _logistic(PRESS_HORIZON_S - tti)
    pressure = float(1.0 - np.prod(1.0 - p))
    rel = s.xy[opp] - s.xy[c]
    d = np.linalg.norm(rel, axis=1)
    closing = -np.sum(rel * (s.vel[opp] - s.vel[c]), axis=1) / (d + 1e-9)
    order = np.argsort(-p)
    pressers = [
        {
            "id": s.ids[opp[k]],
            "distance_m": round(float(d[k]), 2),
            "closing_ms": round(float(closing[k]), 2),
            "p": round(float(p[k]), 3),
        }
        for k in order[:3]
    ]
    geometry = [
        {
            "shape": "ring",
            "geometry_m": {"points": [_pt(s.xy[c])], "radius": 3.0, "player_id": s.owner},
        }
    ]
    for k in order[:3]:
        if p[k] >= 0.2:
            geometry.append(
                {
                    "shape": "arrow",
                    "geometry_m": {
                        "points": [_pt(s.xy[opp[k]]), _pt(s.xy[c])],
                        "player_id": s.ids[opp[k]],
                    },
                }
            )
    return Result(
        metric="pressure_on_ball",
        value=round(pressure, 3),
        unit="prob",
        evidence_window=_window(s.t),
        geometry=geometry,
        details={"carrier": s.owner, "team": team, "pressers": pressers},
    )


def pressing_intensity(frames: Iterable[Frame], team: str) -> Result:
    """Mean pressure ``team`` puts on the opposing ball carrier over a window."""
    values, ts, peak = [], [], (0.0, None)
    for fr in frames:
        s = _snap(fr)
        ts.append(s.t)
        if s.owner_team() != other_team(team):
            continue
        v = float(pressure_on_ball(s).value)
        values.append(v)
        if v > peak[0]:
            peak = (v, s.t)
    if not ts:
        raise ValueError("empty window")
    mean = float(np.mean(values)) if values else 0.0
    return Result(
        metric="pressing_intensity",
        value=round(mean, 3),
        unit="prob",
        evidence_window=_window(min(ts), max(ts)),
        details={
            "team": team,
            "frames": len(ts),
            "frames_out_of_possession": len(values),
            "peak": round(peak[0], 3),
            "peak_t": peak[1],
        },
    )


# --------------------------------------------------------------------------- space
def _control_grid(s: Snapshot, team: str, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    gx, gy = np.meshgrid(xs, ys)
    cells = np.stack([gx.ravel(), gy.ravel()], axis=1)
    players = np.flatnonzero(s.team != "ref")
    tti = time_to_intercept(s.xy[players], s.vel[players], cells)
    w = np.exp(-(tti - tti.min(axis=0)) / CONTROL_TEMPERATURE_S)
    mine = s.team[players] == team
    p = w[mine].sum(axis=0) / w.sum(axis=0)
    return p.reshape(gy.shape)


def pitch_control(
    frame: Frame | Snapshot,
    team: str,
    zone: Sequence[float] | None = None,
    step_m: float = 2.0,
    include_grid: bool = False,
) -> Result:
    """Share of ``zone`` ([x0, y0, x1, y1], default the whole pitch) that ``team`` controls."""
    s = _snap(frame)
    x0, y0, x1, y1 = zone or (-HALF_LENGTH, -HALF_WIDTH, HALF_LENGTH, HALF_WIDTH)
    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    xs = np.arange(x0 + step_m / 2, x1, step_m)
    ys = np.arange(y0 + step_m / 2, y1, step_m)
    if xs.size == 0 or ys.size == 0:
        raise ValueError("zone smaller than one grid step")
    grid = _control_grid(s, team, xs, ys)
    details: dict[str, Any] = {"team": team, "zone": [x0, y0, x1, y1], "step_m": step_m}
    if include_grid:
        details["grid"] = {
            "x": [round(float(v), 2) for v in xs],
            "y": [round(float(v), 2) for v in ys],
            "p": np.round(grid, 2).tolist(),
        }
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return Result(
        metric="pitch_control",
        value=round(float(grid.mean()), 3),
        unit="share",
        evidence_window=_window(s.t),
        geometry=[{"shape": "zone", "geometry_m": {"points": [_pt(c) for c in corners]}}],
        details=details,
    )


def control_at(frame: Frame | Snapshot, team: str, x: float, y: float) -> Result:
    """Probability that ``team`` would win a ball played to (x, y) now."""
    s = _snap(frame)
    p = _control_grid(s, team, np.array([float(x)]), np.array([float(y)]))[0, 0]
    return Result(
        metric="control_at",
        value=round(float(p), 3),
        unit="prob",
        evidence_window=_window(s.t),
        geometry=[{"shape": "spotlight", "geometry_m": {"points": [_pt((x, y))], "radius": 3.0}}],
        details={"team": team, "x": x, "y": y},
    )


# --------------------------------------------------------------------------- value
def xg(x: float, y: float, attack_sign: int) -> float:
    """Expected goals of a shot from (x, y) at the goal at ``attack_sign`` * 52.5."""
    dx = attack_sign * HALF_LENGTH - x
    dist = math.hypot(dx, y)
    angle = math.atan2(GOAL_WIDTH * abs(dx), dx * dx + y * y - (GOAL_WIDTH / 2) ** 2)
    if angle < 0:
        angle += math.pi
    z = -1.1 - 0.105 * dist + 1.6 * angle
    return 1.0 / (1.0 + math.exp(-z))


def xt(x: float, y: float, attack_sign: int) -> float:
    """Parametric expected threat: chance the possession ends in a goal from here."""
    dx = attack_sign * HALF_LENGTH - x
    dist = math.hypot(dx, y)
    theta = math.atan2(abs(y), max(abs(dx), 1e-6))
    return 0.004 + 0.45 * math.exp(-dist / 9.5) * (0.6 + 0.4 * math.cos(theta))


def shot_xg(frame: Frame | Snapshot, player_id: str | None = None) -> Result:
    """xG of a shot by ``player_id`` (default the ball carrier) from where they stand."""
    s = _snap(frame)
    pid = player_id or s.owner
    if pid is None:
        raise ValueError("no player given and nobody has the ball")
    k = s.index(pid)
    team = str(s.team[k])
    sign = s.sign(team)
    x, y = s.xy[k]
    goal = (sign * HALF_LENGTH, 0.0)
    return Result(
        metric="shot_xg",
        value=round(xg(float(x), float(y), sign), 3),
        unit="xG",
        evidence_window=_window(s.t),
        geometry=[
            {"shape": "arrow", "geometry_m": {"points": [_pt((x, y)), _pt(goal)], "player_id": pid}}
        ],
        details={"player": pid, "team": team, "distance_m": round(math.hypot(goal[0] - x, y), 2)},
    )


def xt_added(team: str, period: int, start: Sequence[float], end: Sequence[float], t: int = 0):
    """Expected threat added by moving the ball from ``start`` to ``end``."""
    from .geometry import attack_sign

    sign = attack_sign(team, period)
    a, b = xt(start[0], start[1], sign), xt(end[0], end[1], sign)
    return Result(
        metric="xt_added",
        value=round(b - a, 4),
        unit="xT",
        evidence_window=_window(t),
        geometry=[{"shape": "arrow", "geometry_m": {"points": [_pt(start), _pt(end)]}}],
        details={"team": team, "xt_start": round(a, 4), "xt_end": round(b, 4)},
    )


# --------------------------------------------------------------------------- lines
def offside_line(frame: Frame | Snapshot, defending_team: str) -> Result:
    """The defending team's offside line and the attackers beyond it."""
    s = _snap(frame)
    attack = other_team(defending_team)
    sign = s.sign(attack)
    dfn = s.members(defending_team)
    xn = np.sort(s.xy[dfn, 0] * sign)[::-1]
    second_last = float(xn[1])
    line_n = max(second_last, float(s.ball[0]) * sign, 0.0)
    line_x = line_n * sign
    att = s.members(attack)
    beyond = [s.ids[i] for i in att if s.xy[i, 0] * sign > line_n and s.ids[i] != s.owner]
    return Result(
        metric="offside_line",
        value=round(line_x, 2),
        unit="m",
        evidence_window=_window(s.t),
        geometry=[
            {
                "shape": "offside_line",
                "geometry_m": {"points": [_pt((line_x, -HALF_WIDTH)), _pt((line_x, HALF_WIDTH))]},
            }
        ],
        details={
            "defending_team": defending_team,
            "second_last_defender_x": round(second_last * sign, 2),
            "attackers_beyond": beyond,
        },
    )


def pass_options(frame: Frame | Snapshot, max_len_m: float = 45.0) -> Result:
    """The carrier's teammates as pass options: interception risk of the lane, control at the
    receiver, xT gain and offside. The value is the number of safe options (risk < 0.35)."""
    s = _snap(frame)
    if s.owner is None:
        raise ValueError("nobody has the ball")
    c = s.index(s.owner)
    team = str(s.team[c])
    sign = s.sign(team)
    opp = s.members(other_team(team))
    off = set(offside_line(s, other_team(team)).details["attackers_beyond"])
    start = s.xy[c]
    options = []
    for j in s.members(team):
        if j == c:
            continue
        end = s.xy[j]
        length = float(np.linalg.norm(end - start))
        if length < 3.0 or length > max_len_m:
            continue
        samples = np.linspace(0.15, 1.0, 8)
        pts = start[None, :] + samples[:, None] * (end - start)[None, :]
        t_ball = samples * length / PASS_SPEED
        tti = time_to_intercept(s.xy[opp], s.vel[opp], pts)
        risk = float(np.max(_logistic(t_ball[None, :] - tti)))
        options.append(
            {
                "id": s.ids[j],
                "length_m": round(length, 2),
                "risk": round(risk, 3),
                "control": round(float(control_at(s, team, end[0], end[1]).value), 3),
                "xt_gain": round(xt(end[0], end[1], sign) - xt(start[0], start[1], sign), 4),
                "offside": s.ids[j] in off,
                "end": _pt(end),
            }
        )
    options.sort(key=lambda o: (o["risk"], o["id"]))
    safe = [o for o in options if o["risk"] < 0.35 and not o["offside"]]
    geometry = [
        {
            "shape": "pass_lane",
            "geometry_m": {"points": [_pt(start), o["end"]], "player_id": o["id"]},
            "style": {"variant": "open" if o in safe else "risky"},
        }
        for o in options[:6]
    ]
    return Result(
        metric="pass_options",
        value=len(safe),
        unit="count",
        evidence_window=_window(s.t),
        geometry=geometry,
        details={"carrier": s.owner, "team": team, "options": options},
    )


# --------------------------------------------------------------------------- speed
def ball_speed(frames: Iterable[Frame]) -> Result:
    """Top ball speed in the window, e.g. a shot."""
    best = (-1.0, 0, (0.0, 0.0))
    ts = []
    for fr in frames:
        ts.append(fr["t"])
        b = fr["ball"]
        if b["v"] > best[0]:
            best = (float(b["v"]), fr["t"], (b["x"], b["y"]))
    if not ts:
        raise ValueError("empty window")
    v, t, at = best
    return Result(
        metric="ball_speed",
        value=round(v, 2),
        unit="m/s",
        evidence_window=_window(min(ts), max(ts)),
        geometry=[
            {"shape": "label", "geometry_m": {"points": [_pt(at)], "text": f"{v * 3.6:.0f} km/h"}}
        ],
        details={"t": t, "kmh": round(v * 3.6, 1)},
    )


def player_run(frames: Iterable[Frame], player_id: str) -> Result:
    """Top speed and distance covered by one player over the window, with the path."""
    path, speeds, ts = [], [], []
    for fr in frames:
        p = next((q for q in fr["players"] if q["id"] == player_id), None)
        if p is None:
            raise KeyError(f"no player {player_id!r}")
        path.append((p["x"], p["y"]))
        speeds.append(p["v"])
        ts.append(fr["t"])
    if not ts:
        raise ValueError("empty window")
    arr = np.array(path)
    dist = float(np.sum(np.linalg.norm(np.diff(arr, axis=0), axis=1))) if len(arr) > 1 else 0.0
    stride = max(1, len(path) // 12)
    pts = [_pt(p) for p in path[::stride]]
    if pts[-1] != _pt(path[-1]):
        pts.append(_pt(path[-1]))
    return Result(
        metric="player_run",
        value=round(max(speeds), 2),
        unit="m/s",
        evidence_window=_window(min(ts), max(ts)),
        geometry=[{"shape": "run", "geometry_m": {"points": pts, "player_id": player_id}}],
        details={
            "player": player_id,
            "distance_m": round(dist, 2),
            "kmh": round(max(speeds) * 3.6, 1),
        },
    )
