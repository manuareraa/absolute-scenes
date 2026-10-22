"""Kinematic and behavioural parameters for the match director.

The defaults are set from published elite-football ranges (top speeds 8-10 m/s, peak
accelerations 3-5 m/s^2, ground passes 10-20 m/s). ``scripts`` in this package refit them
from IDSSE (Bassek et al. 2025, CC-BY 4.0, data by DFL) for calibration and the realism
benchmark only; no real tracking data is shipped.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class Calibration:
    # Player kinematics
    vmax_mean: float = 8.4  # m/s, outfield top speed, drawn per player
    vmax_sd: float = 0.45
    vmax_keeper: float = 7.2
    accel_max: float = 3.6  # m/s^2 when speeding up
    decel_max: float = 5.5  # m/s^2 when slowing down
    dribble_speed_frac: float = 0.72  # share of top speed while carrying the ball
    jog_speed_frac: float = 0.55  # share of top speed when holding shape
    wander_m: float = 2.2  # amplitude of individual drift around the shape slot
    wander_tau_s: float = 6.0

    # Ball
    roll_decel: float = 2.4  # m/s^2 on the grass, bounce and drag folded in
    pass_arrival_speed: float = 7.0  # m/s target speed at the receiver
    lofted_min_m: float = 32.0  # passes longer than this are often lofted
    lofted_hspeed: float = 19.0  # m/s horizontal speed of a lofted ball
    shot_speed_mean: float = 25.0
    shot_speed_sd: float = 3.0
    gravity: float = 9.81
    control_radius_m: float = 1.2

    # Team shape
    line_gap_m: float = 13.0  # back line to midfield to attack, in possession
    compact_depth: float = 0.78  # depth scale out of possession
    width_scale_in: float = 1.0
    width_scale_out: float = 0.72
    ball_side_shift: float = 0.3
    block_tau_s: float = 1.8  # lag of the team block behind the ball

    # Decisions
    mean_hold_s: float = 2.0  # time on the ball before acting, unpressed
    pressed_hold_s: float = 0.7
    press_radius_m: float = 3.0
    tackle_radius_m: float = 1.3
    tackle_rate_hz: float = 0.35
    tackle_success: float = 0.45
    foul_share: float = 0.14
    card_share: float = 0.12
    intercept_per_tick: float = 0.15
    pass_error_frac: float = 0.04  # sd of the pass end point per metre of pass
    pass_error_pressed_m: float = 1.5

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> Calibration:
        known = {f.name for f in fields(cls)}
        return cls(**{k: float(v) for k, v in data.items() if k in known})


DEFAULT = Calibration()
