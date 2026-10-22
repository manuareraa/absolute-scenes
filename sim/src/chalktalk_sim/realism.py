"""Realism report: distributions of a generated match, compared by KS distance.

A profile is a dict ``metric -> quantile summary`` (101 quantiles), small enough to commit
and to compare against a reference profile built the same way from calibration data.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from chalktalk_core.geometry import FRAME_MS

from .match import BOWNER, PV, PX, PY, Match

QUANTILES = np.linspace(0.0, 1.0, 101)
DT = FRAME_MS / 1000.0


def _summary(sample: np.ndarray) -> dict[str, Any]:
    sample = np.asarray(sample, dtype=np.float64)
    sample = sample[np.isfinite(sample)]
    return {
        "n": int(sample.size),
        "mean": round(float(sample.mean()), 4) if sample.size else None,
        "q": [round(float(v), 4) for v in np.quantile(sample, QUANTILES)] if sample.size else [],
    }


def samples(match: Match, step: int = 5) -> dict[str, np.ndarray]:
    """Raw samples per metric. Speeds and accelerations are taken every ``step`` frames."""
    team = np.array([p.team for p in match.lineup])
    outfield = np.array([p.team != "ref" and p.role != "GK" for p in match.lineup])
    p = match.players
    same_period = match.period[1:] == match.period[:-1]
    speed = p[::step][:, outfield, PV].ravel()
    dv = np.diff(p[:, outfield, PV], axis=0)[same_period] / DT
    accel = dv[::step].ravel()

    lengths, widths, press = [], [], []
    for i in range(0, match.n_frames, 25):
        for k in ("home", "away"):
            idx = (team == k) & outfield
            xs, ys = p[i, idx, PX], p[i, idx, PY]
            lengths.append(xs.max() - xs.min())
            widths.append(ys.max() - ys.min())
        owner = int(match.ball[i, BOWNER])
        if owner >= 0:
            opp = (team != team[owner]) & (team != "ref")
            d = np.hypot(p[i, opp, PX] - p[i, owner, PX], p[i, opp, PY] - p[i, owner, PY])
            press.append(d.min())
    passes = [e["attrs"]["length_m"] for e in match.events if e["type"] == "pass"]
    ball_speed = match.ball[::step, 3]
    return {
        "speed_ms": speed,
        "accel_ms2": accel,
        "team_length_m": np.array(lengths),
        "team_width_m": np.array(widths),
        "pressure_distance_m": np.array(press),
        "pass_length_m": np.array(passes, dtype=float),
        "ball_speed_ms": ball_speed,
    }


def profile(match: Match) -> dict[str, dict[str, Any]]:
    return {k: _summary(v) for k, v in samples(match).items()}


def ks_from_quantiles(a: list[float], b: list[float]) -> float:
    """KS distance between two distributions given as equal-probability quantile lists."""
    qa, qb = np.asarray(a), np.asarray(b)
    if qa.size == 0 or qb.size == 0:
        return float("nan")
    grid = np.union1d(qa, qb)
    pa = np.linspace(0.0, 1.0, qa.size)
    pb = np.linspace(0.0, 1.0, qb.size)
    fa = np.interp(grid, qa, pa, left=0.0, right=1.0)
    fb = np.interp(grid, qb, pb, left=0.0, right=1.0)
    return float(np.max(np.abs(fa - fb)))


def compare(sim: dict[str, dict], ref: dict[str, dict]) -> dict[str, dict[str, Any]]:
    out = {}
    for metric in sorted(set(sim) & set(ref)):
        s, r = sim[metric], ref[metric]
        out[metric] = {
            "ks": round(ks_from_quantiles(s["q"], r["q"]), 4),
            "sim_median": s["q"][50] if s["q"] else None,
            "ref_median": r["q"][50] if r["q"] else None,
        }
    return out
