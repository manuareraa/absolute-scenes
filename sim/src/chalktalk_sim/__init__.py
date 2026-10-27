"""Absolute Scenes synthetic match director: seeded 25 fps tracking and events, fictional clubs."""

from .calibration import Calibration
from .director import DEMO_BEATS, Beat, MatchConfig, config_from_meta, simulate
from .match import Match, match_id
from .package import write_package

__version__ = "0.1.0"

__all__ = [
    "DEMO_BEATS",
    "Beat",
    "Calibration",
    "Match",
    "MatchConfig",
    "config_from_meta",
    "match_id",
    "simulate",
    "write_package",
]
