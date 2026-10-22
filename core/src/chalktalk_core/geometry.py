"""Pitch geometry shared by sim, analytics and tools.

Pitch metres, origin at the centre spot, x along the long axis, y across (see
``contracts/schemas/frame.schema.json``). In period 1 home attacks +x.
"""

from __future__ import annotations

import math

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
HALF_LENGTH = PITCH_LENGTH / 2
HALF_WIDTH = PITCH_WIDTH / 2

GOAL_WIDTH = 7.32
GOAL_HEIGHT = 2.44
PENALTY_AREA_DEPTH = 16.5
PENALTY_AREA_WIDTH = 40.32
PENALTY_SPOT = 11.0
CENTRE_CIRCLE_RADIUS = 9.15

FPS = 25
FRAME_MS = 1000 // FPS


def attack_sign(team: str, period: int) -> int:
    """+1 if ``team`` attacks +x in ``period``, else -1. Teams swap ends each period."""
    home_plus = period % 2 == 1
    if team == "home":
        return 1 if home_plus else -1
    if team == "away":
        return -1 if home_plus else 1
    raise ValueError(f"no attacking direction for team {team!r}")


def other_team(team: str) -> str:
    return {"home": "away", "away": "home"}[team]


def goal_centre(attacking_team: str, period: int) -> tuple[float, float]:
    """Centre of the goal that ``attacking_team`` shoots at."""
    return (attack_sign(attacking_team, period) * HALF_LENGTH, 0.0)


def heading_deg(dx: float, dy: float) -> float:
    """Direction in degrees, 0 = +x, counter-clockwise, in [-180, 180]."""
    return math.degrees(math.atan2(dy, dx))


def in_pitch(x: float, y: float, margin: float = 0.0) -> bool:
    return abs(x) <= HALF_LENGTH + margin and abs(y) <= HALF_WIDTH + margin
