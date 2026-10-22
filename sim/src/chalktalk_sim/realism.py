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


def samples_from_arrays(
    xy: np.ndarray,
    speed: np.ndarray,
    team: np.ndarray,
    outfield: np.ndarray,
    owner: np.ndarray,
    period: np.ndarray,
    ball_speed: np.ndarray,
    pass_lengths: np.ndarray,
    dt: float,
    step: int = 5,
    shape_every: int = 25,
) -> dict[str, np.ndarray]:
    """Metric samples from tracking arrays; sim and calibration data share this code.

    ``xy`` (T, N, 2) metres and ``speed`` (T, N) m/s at interval ``dt``; ``team`` (N,) of
    home/away/ref; ``outfield`` (N,) bool; ``owner`` (T,) player index or -1; ``period`` (T,).
    NaN marks a player not on the pitch. Speeds and accelerations are sampled every
    ``step`` frames, shape and pressure every ``shape_every`` frames.
    """
    same_period = period[1:] == period[:-1]
    speed_of = speed[:, outfield]
    accel = (np.diff(speed_of, axis=0) / dt)[same_period][::step].ravel()
    lengths, widths, press = [], [], []
    for i in range(0, len(xy), shape_every):
        for k in ("home", "away"):
            idx = (team == k) & outfield
            xs, ys = xy[i, idx, 0], xy[i, idx, 1]
            if np.isfinite(xs).sum() >= 8:
                lengths.append(np.nanmax(xs) - np.nanmin(xs))
                widths.append(np.nanmax(ys) - np.nanmin(ys))
        o = int(owner[i])
        if o >= 0:
            opp = (team != team[o]) & (team != "ref")
            d = np.hypot(xy[i, opp, 0] - xy[i, o, 0], xy[i, opp, 1] - xy[i, o, 1])
            if np.isfinite(d).any():
                press.append(np.nanmin(d))
    return {
        "speed_ms": speed_of[::step].ravel(),
        "accel_ms2": accel,
        "team_length_m": np.array(lengths),
        "team_width_m": np.array(widths),
        "pressure_distance_m": np.array(press),
        "pass_length_m": np.asarray(pass_lengths, dtype=float),
        "ball_speed_ms": np.asarray(ball_speed)[::step],
    }


def samples(match: Match, step: int = 5) -> dict[str, np.ndarray]:
    """Raw samples per metric for a simulated match."""
    team = np.array([p.team for p in match.lineup])
    outfield = np.array([p.team != "ref" and p.role != "GK" for p in match.lineup])
    p = match.players
    passes = [e["attrs"]["length_m"] for e in match.events if e["type"] == "pass"]
    return samples_from_arrays(
        xy=p[:, :, [PX, PY]],
        speed=p[:, :, PV],
        team=team,
        outfield=outfield,
        owner=match.ball[:, BOWNER].astype(int),
        period=match.period,
        ball_speed=match.ball[:, 3],
        pass_lengths=np.array(passes, dtype=float),
        dt=DT,
        step=step,
    )


def summarise(raw: dict[str, np.ndarray]) -> dict[str, dict[str, Any]]:
    return {k: _summary(v) for k, v in raw.items()}


def profile(match: Match) -> dict[str, dict[str, Any]]:
    return summarise(samples(match))


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
