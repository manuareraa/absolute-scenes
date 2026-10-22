import pytest
from chalktalk_core.geometry import attack_sign, goal_centre, heading_deg, in_pitch, other_team


def test_attack_sign_swaps_each_period():
    assert attack_sign("home", 1) == 1 and attack_sign("away", 1) == -1
    assert attack_sign("home", 2) == -1 and attack_sign("away", 2) == 1
    with pytest.raises(ValueError):
        attack_sign("ref", 1)


def test_goal_and_heading():
    assert goal_centre("home", 1) == (52.5, 0.0)
    assert heading_deg(0, 1) == 90.0
    assert other_team("home") == "away"
    assert in_pitch(52.5, 34) and not in_pitch(53, 0)
