"""Box-score realism: pooled over a few seeds, the sim lands in published real-football ranges.

Sources for each range are in docs/notes/b-sim-realism.md and chalktalk_sim.stats.REFERENCE.
"""

import numpy as np
import pytest
from chalktalk_sim import MatchConfig, simulate
from chalktalk_sim.stats import REFERENCE, match_stats

SEEDS = (1, 2, 3)
HALF_MINUTES = 15.0


@pytest.fixture(scope="module")
def stats():
    return [
        match_stats(simulate(MatchConfig(seed=s, half_minutes=HALF_MINUTES)), press_step=10)
        for s in SEEDS
    ]


def pooled_per90(stats, f):
    minutes = sum(s["minutes"] for s in stats)
    return sum(f(s) for s in stats) * 90.0 / minutes


def inside(value, key):
    lo, hi = REFERENCE[key]
    assert lo <= value <= hi, f"{key} {value:.2f} outside {lo}-{hi}"


def test_shots_per_90(stats):
    inside(pooled_per90(stats, lambda s: s["shots"]), "shots_per90")


def test_xg_per_team_and_per_shot(stats):
    xg = pooled_per90(stats, lambda s: s["home"]["xg"] + s["away"]["xg"]) / 2
    inside(xg, "xg_per_team_per90")
    shots = sum(s["shots"] for s in stats)
    xg_total = sum(s["home"]["xg"] + s["away"]["xg"] for s in stats)
    inside(xg_total / shots, "xg_per_shot")


def test_ppda(stats):
    values = [s[t]["ppda"] for s in stats for t in ("home", "away") if s[t]["ppda"]]
    inside(float(np.median(values)), "ppda")


def test_pressing_intensity(stats):
    values = [s[t]["pressing"] for s in stats for t in ("home", "away")]
    inside(float(np.mean(values)), "pressing")


def test_pass_completion(stats):
    inside(float(np.mean([s["pass_completion"] for s in stats])), "pass_completion")
