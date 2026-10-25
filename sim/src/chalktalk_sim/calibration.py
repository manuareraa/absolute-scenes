"""Kinematic and behavioural parameters for the match director.

Started from published elite-football ranges, then tuned so the realism profile of a
generated match is close (KS distance) to the reference profile that ``chalktalk_sim.calibrate``
builds from IDSSE (Bassek et al. 2025, CC BY 4.0, data by DFL); see
``docs/notes/b-realism-report.md``. ``accel_max``/``decel_max`` are the sustained values the
movement model applies every tick, so they sit below the rare real peaks (about 6 m/s^2).
Real tracking data is used for calibration and the realism benchmark only; only quantile
summaries (``data/reference_profile.json``) are committed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class Calibration:
    # Player kinematics
    vmax_mean: float = 7.8  # m/s, outfield top speed, drawn per player
    vmax_sd: float = 0.54
    vmax_keeper: float = 7.2
    accel_max: float = 2.5  # m/s^2 when speeding up
    decel_max: float = 3.5  # m/s^2 when slowing down
    dribble_speed_frac: float = 0.72  # share of top speed while carrying the ball
    jog_speed_frac: float = 0.4  # share of top speed when holding shape
    wander_m: float = 1.2  # amplitude of individual drift around the shape slot
    wander_tau_s: float = 10.0
    arrive_gain: float = 0.35  # 1/s, how hard players close on their slot

    # Ball
    roll_decel: float = 2.4  # m/s^2 on the grass, bounce and drag folded in
    pass_arrival_speed: float = 7.0  # m/s target speed at the receiver
    lofted_min_m: float = 32.0  # passes longer than this are often lofted
    lofted_hspeed: float = 19.0  # m/s horizontal speed of a lofted ball
    shot_speed_mean: float = 25.0
    shot_speed_sd: float = 3.0
    gravity: float = 9.81
    control_radius_m: float = 1.2
    ball_gather_ms: float = 7.5  # how fast a controlled ball is drawn to the feet

    # Team shape
    line_gap_m: float = 17.0  # back line to midfield to attack, in possession
    compact_depth: float = 0.8  # depth scale out of possession
    width_scale_in: float = 0.92
    width_scale_out: float = 0.55
    ball_side_shift: float = 0.3
    block_tau_s: float = 1.8  # lag of the team block behind the ball

    # Decisions
    mean_hold_s: float = 2.0  # time on the ball before acting, unpressed
    pressed_hold_s: float = 0.7
    press_radius_m: float = 2.5
    tackle_radius_m: float = 1.3
    tackle_rate_hz: float = 0.35
    tackle_success: float = 0.45
    foul_share: float = 0.14
    card_share: float = 0.12
    intercept_per_tick: float = 0.15
    # A loose ball won below this speed is a recovery, not an interception (no event).
    interception_min_speed_ms: float = 8.0
    # Shots: chance to shoot when a shooting chance comes up is
    # min(xg, shot_xg_cap) * shot_appetite + boosts. The cap stops close-range chances
    # from crowding out the long shots real teams also take.
    shot_appetite: float = 1.4
    shot_xg_cap: float = 0.08
    shot_box_boost: float = 0.04
    shot_on_target: float = 0.45
    # A due scripted goal waits for a shot from at least this deep (metres past halfway).
    beat_shot_min_xn: float = 33.0
    beat_any_shot_s: float = 15.0  # after this long overdue, shoot from anywhere in range
    # A scripted goal comes from a real chance (xG at least this) unless it is this overdue.
    beat_goal_min_xg: float = 0.15
    beat_relax_s: float = 90.0
    # A goal sent to VAR is tight but onside: the last pass finds the receiver this close
    # behind the line (metres).
    var_margin_m: float = 0.3
    var_wait_s: float = 4.0  # how long the carrier shields the ball for that pass
    # Believable shots (docs/notes/b-believable-goals.md).
    max_shot_dist_m: float = 32.0  # no shots from further than this from goal centre
    min_shot_angle_rad: float = 0.12  # nor from angles tighter than this (about 7 degrees)
    keeper_depth_per_m: float = 0.1  # keeper's distance off his line per metre to the ball
    keeper_reach_m: float = 1.4  # a goal passes at least this far from the keeper's body
    keeper_save_reach_m: float = 1.0  # a save is made when the ball comes this close
    block_radius_m: float = 0.5  # a defender this close to a low shot blocks it
    shot_lane_margin_m: float = 1.0  # a scripted goal is aimed this far clear of defenders
    pass_error_frac: float = 0.04  # sd of the pass end point per metre of pass
    pass_error_pressed_m: float = 1.5

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> Calibration:
        known = {f.name for f in fields(cls)}
        return cls(**{k: float(v) for k, v in data.items() if k in known})


DEFAULT = Calibration()
