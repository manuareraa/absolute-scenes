import pytest
from chalktalk_sim import Beat, MatchConfig, simulate


@pytest.fixture(scope="session")
def match():
    """A short two-half match with a scripted goal that goes to VAR."""
    beats = (Beat(30_000, "goal", "home"), Beat(30_000, "var_check"))
    return simulate(MatchConfig(seed=11, half_minutes=2.5, beats=beats))
