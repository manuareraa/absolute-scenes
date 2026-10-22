import pytest
from chalktalk_mcp.store import Store
from chalktalk_sim import Beat, MatchConfig, simulate


@pytest.fixture(scope="session")
def match():
    beats = (Beat(30_000, "var_check"), Beat(30_000, "goal", "home"))
    return simulate(MatchConfig(seed=11, half_minutes=1.5, beats=beats))


@pytest.fixture()
def store(match):
    s = Store(packages=None, max_matches=2)
    s.put(match)
    return s


@pytest.fixture(scope="session")
def owned_t(match):
    """A time when a home player has the ball."""
    for i in range(100, match.n_frames, 5):
        f = match.frame(i)
        o = f["ball"]["owner"]
        if o and o.startswith("H"):
            return f["t"]
    raise AssertionError("no home possession")
