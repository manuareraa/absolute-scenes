"""M8 'ghost': where a player should have been.

Deterministic, no learning: the player's slot is their average offset from the centroid of
their outfield teammates over a baseline window (their place in the team shape). Through the
moment the ghost starts where the real player was and steers to the slot as the team moves,
under a top speed and an acceleration limit. Swapping the ghost in for the real player, we
re-run pitch control, OBSO and pressing on the same frames and report the differences.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from . import analytics as an
from .geometry import HALF_LENGTH, HALF_WIDTH, other_team
from .snapshot import Snapshot

GHOST_VMAX = 7.0
GHOST_ACCEL = 4.0
ARRIVE_GAIN = 1.2  # 1/s: desired speed per metre still to go
MAX_SAMPLES = 8

Frame = dict[str, Any]


def _teammates(s: Snapshot, team: str, player_id: str) -> np.ndarray:
    idx = s.outfield(team)
    return idx[[s.ids[i] != player_id for i in idx]]


def slot_offset(frames: Sequence[Frame | Snapshot], player_id: str) -> np.ndarray:
    """The player's mean offset (m) from the centroid of their outfield teammates."""
    if not frames:
        raise ValueError("empty baseline")
    total = np.zeros(2)
    for f in frames:
        s = an._snap(f)
        k = s.index(player_id)
        total += s.xy[k] - s.xy[_teammates(s, str(s.team[k]), player_id)].mean(axis=0)
    return total / len(frames)


def ghost_track(
    frames: Sequence[Frame | Snapshot], player_id: str, offset: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Real positions, slot positions, ghost positions and ghost velocities, one per frame."""
    snaps = [an._snap(f) for f in frames]
    k0 = snaps[0].index(player_id)
    team = str(snaps[0].team[k0])
    real = np.array([s.xy[s.index(player_id)] for s in snaps])
    slot = np.array([s.xy[_teammates(s, team, player_id)].mean(axis=0) + offset for s in snaps])
    slot[:, 0] = np.clip(slot[:, 0], -HALF_LENGTH, HALF_LENGTH)
    slot[:, 1] = np.clip(slot[:, 1], -HALF_WIDTH, HALF_WIDTH)
    pos = real[0].copy()
    vel = snaps[0].vel[k0].copy()
    track, vels = [pos.copy()], [vel.copy()]
    for prev, s, target in zip(snaps, snaps[1:], slot[1:], strict=False):
        dt = (s.t - prev.t) / 1000.0
        if dt <= 0:
            raise ValueError("frames must be in time order")
        want = (target - pos) * ARRIVE_GAIN
        speed = float(np.linalg.norm(want))
        if speed > GHOST_VMAX:
            want *= GHOST_VMAX / speed
        dv = want - vel
        step = float(np.linalg.norm(dv))
        if step > GHOST_ACCEL * dt:
            dv *= GHOST_ACCEL * dt / step
        vel = vel + dv
        pos = pos + vel * dt
        track.append(pos.copy())
        vels.append(vel.copy())
    return real, slot, np.array(track), np.array(vels)


def _swap(frame: Frame, player_id: str, xy: np.ndarray, vel: np.ndarray) -> Frame:
    out = copy.deepcopy(frame)
    for p in out["players"]:
        if p["id"] == player_id:
            p["x"], p["y"] = float(xy[0]), float(xy[1])
            p["v"] = float(np.linalg.norm(vel))
            p["heading"] = math.degrees(math.atan2(vel[1], vel[0]))
    if out["ball"].get("owner") == player_id:
        out["ball"]["x"], out["ball"]["y"] = float(xy[0]), float(xy[1])
    return out


def _metrics(frame: Frame, team: str) -> dict[str, float | None]:
    """From ``team``'s view: pitch control, net OBSO (own when on the ball, minus the
    opponent's when not) and pressure on the opposing carrier (None while in possession)."""
    s = an._snap(frame)
    on_ball = s.owner_team()
    pc = float(an.pitch_control(s, team).value)
    if on_ball is None:
        return {"pitch_control": pc, "obso": None, "pressing": None}
    o = float(an.obso(s, on_ball).value)
    pressing = float(an.pressure_on_ball(s).value) if on_ball == other_team(team) else None
    return {"pitch_control": pc, "obso": o if on_ball == team else -o, "pressing": pressing}


def _mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return float(np.mean(vals)) if vals else None


def _thin(points: np.ndarray, n: int = 13) -> list[list[float]]:
    stride = max(1, len(points) // (n - 1))
    pts = [an._pt(p) for p in points[::stride]]
    if pts[-1] != an._pt(points[-1]):
        pts.append(an._pt(points[-1]))
    return pts


def ghost(
    frames: Sequence[Frame],
    player_id: str,
    baseline: Sequence[Frame] | None = None,
) -> an.Result:
    """Where ``player_id`` should have been over ``frames`` (their slot in the team shape,
    learned from ``baseline``, default the same frames), and what it would have changed.
    The value is the distance (m) between the real player and the ghost at the end."""
    frames = list(frames)
    if len(frames) < 2:
        raise ValueError("the window needs at least two frames")
    offset = slot_offset(list(baseline) if baseline else frames, player_id)
    real, slot, track, vels = ghost_track(frames, player_id, offset)
    first = an._snap(frames[0])
    team = str(first.team[first.index(player_id)])
    picks = sorted(set(np.linspace(0, len(frames) - 1, min(len(frames), MAX_SAMPLES)).astype(int)))
    real_m = [_metrics(frames[k], team) for k in picks]
    ghost_m = [_metrics(_swap(frames[k], player_id, track[k], vels[k]), team) for k in picks]
    deltas: dict[str, float | None] = {}
    means: dict[str, dict[str, float | None]] = {"real": {}, "ghost": {}}
    for key in ("pitch_control", "obso", "pressing"):
        r = _mean([m[key] for m in real_m])
        g = _mean([m[key] for m in ghost_m])
        means["real"][key] = None if r is None else round(r, 4)
        means["ghost"][key] = None if g is None else round(g, 4)
        deltas[key] = None if r is None or g is None else round(g - r, 4)
    gap = np.linalg.norm(track - real, axis=1)
    end_real, end_ghost = real[-1], track[-1]
    geometry = [
        # The path's last point is the expected position; the web tethers the real player to it.
        {
            "shape": "ghost_path",
            "geometry_m": {"points": _thin(track), "player_id": player_id},
            "style": {"color": "ghost", "dash": True},
        },
        {"shape": "run", "geometry_m": {"points": _thin(real), "player_id": player_id}},
        {"shape": "ring", "geometry_m": {"points": [an._pt(end_ghost)], "radius": 1.5}},
    ]
    return an.Result(
        metric="ghost",
        value=round(float(gap[-1]), 2),
        unit="m",
        evidence_window=an._window(first.t, an._snap(frames[-1]).t),
        geometry=geometry,
        details={
            "player": player_id,
            "team": team,
            "slot_offset_m": an._pt(offset),
            "slot_end": an._pt(slot[-1]),
            "ghost_end": an._pt(end_ghost),
            "real_end": an._pt(end_real),
            "max_gap_m": round(float(gap.max()), 2),
            "deltas": deltas,
            "means": means,
            "samples": len(picks),
        },
    )
