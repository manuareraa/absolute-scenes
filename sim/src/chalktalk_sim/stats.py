"""Match statistics a football analyst would sanity-check, with published reference ranges.

``match_stats`` summarises a generated match the way box scores do (shots, xG, pass
completion, PPDA, pressing), so tests can hold the sim inside real-football ranges and the
notes can show before/after numbers. See ``docs/notes/b-sim-realism.md`` for the sources.
"""

from __future__ import annotations

from typing import Any

from chalktalk_core import analytics as an
from chalktalk_core.geometry import HALF_LENGTH, PITCH_LENGTH, attack_sign

from .match import Match

TEAMS = ("home", "away")
# Defensive actions counted by PPDA (Trainor 2014): tackles, interceptions, challenges
# (a failed tackle, here a dribble that beats the defender) and fouls.
DEFENSIVE = {"tackle", "interception", "dribble", "foul"}
# PPDA counts the pressing team's actions in its attacking 60% of the pitch.
PPDA_ZONE_X = -HALF_LENGTH + 0.4 * PITCH_LENGTH  # in the pressing team's attacking frame

# Real-football reference ranges (sources in docs/notes/b-sim-realism.md).
REFERENCE = {
    "shots_per90": (20.0, 32.0),  # both teams; PL 25.3 (2022/23), 27.2 (2023/24)
    "xg_per_team_per90": (0.6, 2.4),
    "xg_per_shot": (0.07, 0.15),  # PL conversion 11.9% of shots (2023/24)
    "ppda": (6.0, 16.0),  # PL team range, about 8.6 (high press) to 15+ (low block)
    "pass_completion": (0.70, 0.90),
    # Team pressing intensity, as measured by the same core function on IDSSE (DFL) play.
    "pressing": (0.45, 0.70),
}


def _ball_xy(match: Match, t: int) -> tuple[float, float]:
    b = match.ball[match.tick(t)]
    return float(b[0]), float(b[1])


def ppda(match: Match, team: str) -> float | None:
    """Passes allowed per defensive action by ``team`` in its attacking 60% of the pitch."""
    opp = "away" if team == "home" else "home"
    passes = actions = 0
    for e in match.events:
        period = int(match.period[match.tick(e["t"])])
        s = attack_sign(team, period)
        if e["type"] == "pass" and e["team"] == opp and not e["attrs"].get("restart"):
            x = float(e["attrs"]["start"][0])
        elif e["type"] in DEFENSIVE:
            # A dribble event belongs to the carrier's team; the challenge is the defender's.
            by = opp if e["type"] == "dribble" else e["team"]
            if by != team:
                continue
            x = _ball_xy(match, e["t"])[0]
        else:
            continue
        if x * s < PPDA_ZONE_X:
            continue
        if e["type"] == "pass":
            passes += 1
        else:
            actions += 1
    return round(passes / actions, 2) if actions else None


def match_stats(match: Match, press_step: int = 5) -> dict[str, Any]:
    minutes = match.duration_ms / 60000.0
    per90 = 90.0 / minutes
    shots = [e for e in match.events if e["type"] == "shot"]
    passes = [e for e in match.events if e["type"] == "pass"]
    done = [p for p in passes if p["attrs"].get("outcome") == "complete"]
    out: dict[str, Any] = {
        "minutes": round(minutes, 1),
        "score": dict(match.meta.get("score", {})),
        "shots": len(shots),
        "shots_per90": round(len(shots) * per90, 1),
        "pass_completion": round(len(done) / len(passes), 3) if passes else None,
        "interceptions_per90": round(
            sum(e["type"] == "interception" for e in match.events) * per90, 1
        ),
        "goals": [
            {"t": e["t"], "team": e["team"], "scorer": e["actors"][0]}
            for e in match.events
            if e["type"] == "goal"
        ],
    }
    for team in TEAMS:
        mine = [e for e in shots if e["team"] == team]
        out[team] = {
            "shots": len(mine),
            "xg": round(sum(e["attrs"]["xg"] for e in mine), 2),
            "ppda": ppda(match, team),
            "pressing": an.pressing_intensity(match.frames(0, None, press_step), team).value,
        }
    goal_shots = [e["attrs"]["xg"] for e in shots if e["attrs"]["outcome"] == "goal"]
    out["xg_per_shot"] = (
        round(sum(e["attrs"]["xg"] for e in shots) / len(shots), 3) if shots else None
    )
    out["goal_shot_xg"] = goal_shots
    return out
