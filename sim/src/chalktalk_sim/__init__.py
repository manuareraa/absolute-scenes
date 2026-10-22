"""ChalkTalk synthetic match director: seeded 25 fps tracking and events for fictional clubs."""

from .calibration import Calibration
from .director import Beat, MatchConfig, simulate
from .match import Match, match_id
from .package import write_package

__version__ = "0.1.0"

__all__ = ["Beat", "Calibration", "Match", "MatchConfig", "match_id", "simulate", "write_package"]
