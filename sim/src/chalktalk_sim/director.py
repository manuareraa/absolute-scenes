"""Synthetic match director: a seeded, tick-based simulation of a football match.

Each tick (40 ms) the director
1. sets a target point and speed cap for every player from the team shape (formation slots
   moved with the ball, compact out of possession, stretched in it), pressing, receiving
   runs and individual drift;
2. moves players toward their targets under speed, acceleration and deceleration limits;
3. moves the ball (dribbled, rolling, or in the air under gravity);
4. applies match logic: ball control and interceptions, tackles and fouls, the carrier's
   decision (carry, pass, shot, clearance), ball out of play and restarts, goals and kick-offs.

Every random draw comes from one ``numpy.random.Generator`` seeded by ``MatchConfig.seed``,
so the same config always yields the same match. Events carry ``source="sim"`` and
``confidence=1.0``: they are the ground truth that video detection is scored against.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from chalktalk_core.analytics import xg as xg_of
from chalktalk_core.geometry import (
    FRAME_MS,
    GOAL_HEIGHT,
    GOAL_WIDTH,
    HALF_LENGTH,
    HALF_WIDTH,
    attack_sign,
)

from .calibration import DEFAULT, Calibration
from .match import BOWNER, PBODY, PHEAD, PV, PX, PY, Match
from .teams import lineup

DT = FRAME_MS / 1000.0
TEAMS = ("home", "away")
GOAL_KICK_X = HALF_LENGTH - 5.5


@dataclass(frozen=True)
class Beat:
    """A scripted moment. ``goal``: the first shot by ``team`` at or after ``t_ms`` scores.
    ``var_check``: the first goal at or after ``t_ms`` goes to a VAR check (goal stands)."""

    t_ms: int
    kind: Literal["goal", "var_check"]
    team: str = "home"


@dataclass(frozen=True)
class MatchConfig:
    seed: int = 7
    half_minutes: float = 45.0
    periods: int = 2
    beats: tuple[Beat, ...] = ()
    calibration: Calibration = field(default=DEFAULT)


def simulate(config: MatchConfig) -> Match:
    return _Director(config).run()


class _Director:
    def __init__(self, config: MatchConfig):
        self.cfg = config
        self.cal = config.calibration
        self.rng = np.random.default_rng(config.seed)
        self.lineup = lineup()
        n = len(self.lineup)
        self.n = n
        self.team = np.array([{"home": 0, "away": 1, "ref": 2}[p.team] for p in self.lineup])
        self.ids = [p.id for p in self.lineup]
        self.is_gk = np.array([p.role == "GK" for p in self.lineup])
        self.is_fwd = np.array([p.depth >= 0.9 for p in self.lineup])
        self.is_def = np.array([p.depth <= -0.9 for p in self.lineup])
        self.depth = np.array([p.depth for p in self.lineup])
        self.width = np.array([p.width for p in self.lineup])
        cal = self.cal
        self.vmax = self.rng.normal(cal.vmax_mean, cal.vmax_sd, n).clip(7.0, 10.0)
        self.vmax[self.is_gk] = cal.vmax_keeper
        self.vmax[self.team == 2] = 7.0
        self.members = [np.flatnonzero(self.team == k) for k in (0, 1)]
        self.gk = [int(np.flatnonzero((self.team == k) & self.is_gk)[0]) for k in (0, 1)]
        self.ref = int(np.flatnonzero(self.team == 2)[0])

        self.pos = np.zeros((n, 2))
        self.vel = np.zeros((n, 2))
        self.head = np.zeros(n)
        self.wander = np.zeros((n, 2))
        self.block = [0.0, 0.0]
        self.ball = np.zeros(3)
        self.bvel = np.zeros(3)
        self.owner = -1
        self.poss = 0
        self.period = 1
        self.tick = 0
        self.state = "play"
        self.flight: dict[str, Any] | None = None
        self.restart: dict[str, Any] | None = None
        self.resume_t = 0
        self.kickoff_team = 0
        self.reception_t = 0
        self.carry_from: tuple[float, float] | None = None
        self.last_touch = 0
        self.run_until = np.zeros(n)
        self.run_x = np.zeros(n)
        self.cooldown = np.zeros(n)
        self.last_press = np.full(n, -1e9)
        self.score = [0, 0]
        self.beats = sorted(config.beats, key=lambda b: b.t_ms)
        self.used_beats: set[int] = set()
        self.events: list[dict[str, Any]] = []
        self.seq = 0

    # ------------------------------------------------------------------ helpers
    @property
    def t(self) -> int:
        return self.tick * FRAME_MS

    def sign(self, team: int) -> int:
        return attack_sign(TEAMS[team], self.period)

    def emit(self, type_: str, actors: list[int], team: int | None, **attrs: Any) -> dict:
        ev: dict[str, Any] = {
            "id": "",
            "t": self.t,
            "type": type_,
            "actors": [self.ids[a] for a in actors],
            "attrs": {k: v for k, v in attrs.items() if v is not None},
            "source": "sim",
            "confidence": 1.0,
            "_seq": self.seq,
        }
        if team is not None:
            ev["team"] = TEAMS[team]
        self.seq += 1
        self.events.append(ev)
        return ev

    def r2(self, x: float, y: float) -> list[float]:
        return [round(float(x), 2), round(float(y), 2)]

    def nearest(self, team: int, point: np.ndarray, exclude_gk: bool = True) -> int:
        idx = self.members[team]
        if exclude_gk:
            idx = idx[~self.is_gk[idx]]
        d = np.linalg.norm(self.pos[idx] - point[:2], axis=1)
        return int(idx[np.argmin(d)])

    def offside_line(self, att: int) -> float:
        """Offside line in the attacking team's coordinates (attack toward +x)."""
        s = self.sign(att)
        opp = self.members[1 - att]
        xs = np.sort(self.pos[opp, 0] * s)[::-1]
        return float(max(xs[1], self.ball[0] * s, 0.0))

    def beat_due(self, kind: str, team: int | None) -> int | None:
        for i, b in enumerate(self.beats):
            if i in self.used_beats or b.kind != kind or b.t_ms > self.t:
                continue
            if team is None or b.team == TEAMS[team]:
                return i
        return None

    # ------------------------------------------------------------------ setup
    def kickoff_layout(self, kicker: int) -> np.ndarray:
        tgt = np.zeros((self.n, 2))
        for k in (0, 1):
            s = self.sign(k)
            for i in self.members[k]:
                if self.is_gk[i]:
                    xn, y = -HALF_LENGTH + 3.0, 0.0
                else:
                    xn = min(-2.0, -14.0 + self.depth[i] * 11.0)
                    y = self.width[i] * 0.9
                    if k != kicker:
                        xn = min(xn, -10.0)
                tgt[i] = (xn * s, y)
        st = [i for i in self.members[kicker] if self.lineup[i].role in ("ST", "RS", "LS")]
        s = self.sign(kicker)
        tgt[st[0]] = (-0.4 * s, 0.3)
        if len(st) > 1:
            tgt[st[1]] = (-0.6 * s, -2.0)
        tgt[self.ref] = (-6.0, -12.0)
        return tgt

    def start_period(self, period: int, kicker: int) -> None:
        self.period = period
        self.pos = self.kickoff_layout(kicker)
        self.pos += self.rng.normal(0, 0.3, self.pos.shape)
        self.vel[:] = 0
        for k in (0, 1):
            self.head[self.members[k]] = 0.0 if self.sign(k) > 0 else 180.0
        self.ball[:] = 0
        self.bvel[:] = 0
        self.do_kickoff(kicker)

    def do_kickoff(self, kicker: int) -> None:
        self.state = "play"
        self.restart = None
        st = self.nearest(kicker, np.zeros(2))
        self.emit("kickoff", [st], kicker, period=self.period)
        self.poss = kicker
        self.set_owner(st)
        mates = [i for i in self.members[kicker] if i != st and not self.is_gk[i]]
        d = [np.linalg.norm(self.pos[i]) for i in mates]
        recv = mates[int(np.argsort(d)[1])]
        self.kick_pass(st, recv, restart="kickoff")

    # ------------------------------------------------------------------ targets
    def targets(self) -> tuple[np.ndarray, np.ndarray]:
        cal = self.cal
        tgt = np.zeros((self.n, 2))
        cap = self.vmax * cal.jog_speed_frac
        self.gain = np.full(self.n, 0.9)
        bx, by = float(self.ball[0]), float(self.ball[1])
        dead = self.state in ("goal", "kickoff")
        if dead:
            tgt = self.kickoff_layout(self.kickoff_team)
            cap = self.vmax * 0.45
        else:
            for k in (0, 1):
                s = self.sign(k)
                idx = self.members[k]
                bxn = bx * s
                in_poss = self.poss == k
                if in_poss:
                    c = float(np.clip(0.6 * bxn + 4.0, -22.0, 22.0))
                    depth, wscale = 1.0, cal.width_scale_in
                else:
                    c = float(np.clip(0.6 * bxn - 9.0, -34.0, 12.0))
                    depth, wscale = cal.compact_depth, cal.width_scale_out
                # The block follows the ball with a lag, not at ball speed.
                self.block[k] += (c - self.block[k]) * min(1.0, DT / cal.block_tau_s)
                c = self.block[k]
                xn = c + self.depth[idx] * cal.line_gap_m * depth
                xn = np.clip(xn, -HALF_LENGTH + 6.0, HALF_LENGTH - 4.0)
                y = self.width[idx] * wscale + by * cal.ball_side_shift
                if in_poss and self.state == "play":
                    line = self.offside_line(k)
                    running = self.run_until[idx] > self.t
                    xn = np.where(running, self.run_x[idx], np.minimum(xn, line - 0.4))
                tgt[idx, 0] = xn * s
                tgt[idx, 1] = y
                gk = self.gk[k]
                gxn = -HALF_LENGTH + 2.5 + 0.07 * (bxn + HALF_LENGTH)
                tgt[gk] = (gxn * s, float(np.clip(by * 0.15, -3.0, 3.0)))
            tgt += self.wander
            tgt[self.ref] = (bx * 0.8, float(np.clip(by - 13.0 * np.sign(by or 1.0), -30, 30)))
            self.ball_targets(tgt, cap)
        tgt[:, 0] = np.clip(tgt[:, 0], -HALF_LENGTH - 1.0, HALF_LENGTH + 1.0)
        tgt[:, 1] = np.clip(tgt[:, 1], -HALF_WIDTH - 1.0, HALF_WIDTH + 1.0)
        return tgt, cap

    def ball_targets(self, tgt: np.ndarray, cap: np.ndarray) -> None:
        cal = self.cal
        b = self.ball[:2]
        att, dfn = self.poss, 1 - self.poss
        if self.state == "restart" and self.restart is not None:
            tk = self.restart["taker"]
            tgt[tk] = self.restart["spot"]
            cap[tk] = self.vmax[tk] * 0.7
            self.gain[tk] = 4.0
            return
        if self.owner >= 0:
            c = self.owner
            s = self.sign(att)
            opp = self.members[dfn]
            d = np.linalg.norm(self.pos[opp] - self.pos[c], axis=1)
            near = opp[np.argmin(d)]
            away = self.pos[c] - self.pos[near]
            away /= np.linalg.norm(away) + 1e-9
            fwd = np.array([s, 0.0])
            heading = fwd + 0.6 * away * (d.min() < 6.0)
            heading /= np.linalg.norm(heading) + 1e-9
            dest = self.pos[c] + heading * 8.0
            dest[0] = np.clip(dest[0], -HALF_LENGTH + 3, HALF_LENGTH - 3)
            dest[1] = np.clip(dest[1], -HALF_WIDTH + 2, HALF_WIDTH - 2)
            tgt[c] = dest
            cap[c] = self.vmax[c] * cal.dribble_speed_frac
            self.gain[c] = 4.0
            # Press the carrier and cover behind the presser.
            order = opp[np.argsort(d)]
            presser = int(order[0]) if not self.is_gk[order[0]] else int(order[1])
            tgt[presser] = self.pos[c] + self.vel[c] * 0.3
            cap[presser] = self.vmax[presser] * 0.92
            self.gain[presser] = 4.0
            cover = int(order[1]) if order[1] != presser else int(order[2])
            if not self.is_gk[cover]:
                tgt[cover] = self.pos[c] - np.array([self.sign(att) * 6.0, 0.0])
                cap[cover] = self.vmax[cover] * 0.8
                self.gain[cover] = 4.0
            return
        if self.flight is not None:
            dest = np.array(self.flight["target"])
            if np.linalg.norm(self.bvel[:2]) < 3.0:
                dest = b.copy()
            recv = self.flight.get("receiver")
            if recv is not None:
                tgt[recv] = dest
                cap[recv] = self.vmax[recv]
                self.gain[recv] = 4.0
            else:
                ch = self.nearest(att, dest)
                tgt[ch] = dest
                cap[ch] = self.vmax[ch]
                self.gain[ch] = 4.0
            if self.flight["kind"] != "shot":
                ch = self.nearest(dfn, dest)
                tgt[ch] = dest
                cap[ch] = self.vmax[ch]
                self.gain[ch] = 4.0
            else:
                gk = self.gk[dfn]
                tgt[gk] = self.flight["keeper_to"]
                cap[gk] = self.vmax[gk]
                self.gain[gk] = 4.0
            return
        # Loose ball: the nearest player of each team chases it.
        for k in (0, 1):
            ch = self.nearest(k, b, exclude_gk=False)
            tgt[ch] = b
            cap[ch] = self.vmax[ch]
            self.gain[ch] = 4.0

    # ------------------------------------------------------------------ physics
    def move_players(self, tgt: np.ndarray, cap: np.ndarray) -> None:
        cal = self.cal
        d = tgt - self.pos
        dist = np.linalg.norm(d, axis=1)
        # Arrive behaviour with a small dead zone, so players at their slot stand or walk.
        speed = np.minimum(cap, np.maximum(dist - 0.8 / self.gain, 0.0) * self.gain)
        desired = d / (dist[:, None] + 1e-9) * speed[:, None]
        dv = desired - self.vel
        cur = np.linalg.norm(self.vel, axis=1)
        amax = np.where(speed > cur, cal.accel_max, cal.decel_max) * DT
        mag = np.linalg.norm(dv, axis=1)
        dv *= np.minimum(1.0, amax / (mag + 1e-9))[:, None]
        self.vel += dv
        self.pos += self.vel * DT
        self.pos[:, 0] = np.clip(self.pos[:, 0], -HALF_LENGTH - 3, HALF_LENGTH + 3)
        self.pos[:, 1] = np.clip(self.pos[:, 1], -HALF_WIDTH - 3, HALF_WIDTH + 3)
        sp = np.linalg.norm(self.vel, axis=1)
        moving = sp > 0.3
        self.head[moving] = np.degrees(np.arctan2(self.vel[moving, 1], self.vel[moving, 0]))
        # Individual drift around the slot (Ornstein-Uhlenbeck).
        theta = DT / cal.wander_tau_s
        sigma = cal.wander_m * math.sqrt(2 * theta)
        self.wander += -theta * self.wander + self.rng.normal(0, sigma, self.wander.shape)

    def move_ball(self) -> None:
        cal = self.cal
        if self.owner >= 0:
            c = self.owner
            sp = float(np.linalg.norm(self.vel[c]))
            if sp > 0.5:
                u = self.vel[c] / sp
            else:
                u = np.array([self.sign(int(self.team[c])), 0.0])
            self.ball[:2] = self.pos[c] + u * 0.55
            self.ball[2] = 0.0
            self.bvel[:2] = self.vel[c]
            self.bvel[2] = 0.0
            return
        if self.state in ("restart", "kickoff"):
            self.bvel[:] = 0
            return
        if self.ball[2] > 0 or self.bvel[2] > 0:
            self.bvel[2] -= cal.gravity * DT
            self.ball += self.bvel * DT
            if self.ball[2] <= 0:
                self.ball[2] = 0.0
                if self.bvel[2] < -2.0:
                    self.bvel[2] = -self.bvel[2] * 0.35
                    self.bvel[:2] *= 0.75
                else:
                    self.bvel[2] = 0.0
        else:
            sp = float(np.linalg.norm(self.bvel[:2]))
            if sp > 0:
                new = max(0.0, sp - cal.roll_decel * DT)
                self.bvel[:2] *= new / sp
            self.ball[:2] += self.bvel[:2] * DT
        if self.state == "goal":
            self.ball[0] = np.clip(self.ball[0], -HALF_LENGTH - 2.0, HALF_LENGTH + 2.0)
            if abs(self.ball[0]) >= HALF_LENGTH + 2.0:
                self.bvel[:] = 0

    # ------------------------------------------------------------------ actions
    def set_owner(self, k: int) -> None:
        self.owner = k
        self.flight = None
        self.poss = int(self.team[k])
        self.last_touch = self.poss
        self.reception_t = self.t
        self.carry_from = (float(self.pos[k, 0]), float(self.pos[k, 1]))

    def release(self) -> None:
        c = self.owner
        if c >= 0 and self.carry_from is not None:
            x0, y0 = self.carry_from
            length = math.hypot(self.pos[c, 0] - x0, self.pos[c, 1] - y0)
            if length >= 3.0:
                ev = self.emit(
                    "carry",
                    [c],
                    int(self.team[c]),
                    start=self.r2(x0, y0),
                    end=self.r2(*self.pos[c]),
                    length_m=round(length, 1),
                )
                ev["t"] = self.reception_t
        self.carry_from = None
        self.owner = -1

    def kick_pass(
        self, c: int, recv: int, restart: str | None = None, lofted: bool | None = None
    ) -> None:
        cal = self.cal
        team = int(self.team[c])
        d0 = float(np.linalg.norm(self.pos[recv] - self.pos[c]))
        lead = self.vel[recv] * (d0 / 15.0) * 0.6
        opp = self.members[1 - int(self.team[c])]
        pressed = np.min(np.linalg.norm(self.pos[opp] - self.pos[c], axis=1)) < cal.press_radius_m
        err = cal.pass_error_frac * d0 + (cal.pass_error_pressed_m if pressed else 0.0)
        if restart == "kickoff":
            err = 0.0
        target = self.pos[recv] + lead + self.rng.normal(0.0, err + 1e-9, 2)
        start = self.ball[:2].copy()
        vec = target - start
        d = float(np.linalg.norm(vec)) + 1e-9
        u = vec / d
        if lofted is None:
            lofted = d > cal.lofted_min_m and self.rng.random() < 0.6
        offside = False
        if restart not in ("throw_in", "goal_kick", "corner", "kickoff"):
            s = self.sign(team)
            line = self.offside_line(team)
            xr = self.pos[recv, 0] * s
            offside = bool(xr > line + 0.3 and xr > 0)
        self.release()
        if lofted:
            vh = cal.lofted_hspeed
            T = d / vh
            self.bvel[:2] = u * vh
            self.bvel[2] = cal.gravity * T / 2 * 0.8
            self.ball[2] = 0.05
        else:
            v0 = min(26.0, math.sqrt(cal.pass_arrival_speed**2 + 2 * cal.roll_decel * d))
            self.bvel[:2] = u * v0
            self.bvel[2] = 0.0
        ev = self.emit(
            "pass",
            [c, recv],
            team,
            start=self.r2(*start),
            end=self.r2(*target),
            length_m=round(d, 1),
            height="high" if lofted else "ground",
            receiver=self.ids[recv],
            restart=restart,
        )
        self.flight = {
            "kind": "pass",
            "kicker": c,
            "team": team,
            "receiver": recv,
            "target": target,
            "t0": self.t,
            "event": ev,
            "offside": offside,
        }
        self.last_touch = team
        self.poss = team

    def choose_pass(self, c: int, max_len: float = 50.0) -> tuple[int, float]:
        team = int(self.team[c])
        s = self.sign(team)
        opp = self.pos[self.members[1 - team]]
        line = self.offside_line(team)
        best, best_score = -1, -1e9
        p0 = self.pos[c]
        for j in self.members[team]:
            if j == c:
                continue
            pj = self.pos[j]
            seg = pj - p0
            d = float(np.linalg.norm(seg))
            if d < 5.0 or d > max_len:
                continue
            if self.is_gk[j] and not self.is_def[c]:
                continue
            proj = np.clip(((opp - p0) @ seg) / (d * d), 0.0, 1.0)
            closest = p0 + proj[:, None] * seg
            lane = float(np.min(np.linalg.norm(opp - closest, axis=1)))
            space = float(np.min(np.linalg.norm(opp - pj, axis=1)))
            progress = (pj[0] - p0[0]) * s / 20.0
            score = (
                1.2 * progress
                + 1.4 * min(lane / 4.0, 1.0)
                + 1.0 * min(space / 6.0, 1.0)
                - abs(d - 18.0) / 40.0
                + self.rng.gumbel() * 0.35
            )
            if pj[0] * s > line + 0.3 and pj[0] * s > 0 and self.rng.random() < 0.9:
                score -= 3.0
            if self.is_gk[j]:
                score -= 1.0
            if score > best_score:
                best, best_score = int(j), score
        return best, best_score

    def shoot(self, c: int, forced: bool) -> None:
        cal = self.cal
        team = int(self.team[c])
        s = self.sign(team)
        gx = s * HALF_LENGTH
        xg = xg_of(float(self.pos[c, 0]), float(self.pos[c, 1]), s)
        rng = self.rng
        if forced:
            outcome = "goal"
        else:
            on = rng.random() < 0.45
            p_goal = min(0.9, max(0.05, xg / 0.4))
            outcome = ("goal" if rng.random() < p_goal else "saved") if on else "off_target"
        side = 1.0 if rng.random() < 0.5 else -1.0
        if outcome == "goal":
            ty, tz = side * rng.uniform(1.6, GOAL_WIDTH / 2 - 0.4), rng.uniform(0.2, 2.1)
        elif outcome == "saved":
            ty, tz = rng.uniform(-2.6, 2.6), rng.uniform(0.2, 1.8)
        else:
            ty, tz = side * rng.uniform(GOAL_WIDTH / 2 + 0.6, 7.5), rng.uniform(0.3, 3.6)
        speed = float(np.clip(rng.normal(cal.shot_speed_mean, cal.shot_speed_sd), 15, 34))
        start = self.ball.copy()
        vec = np.array([gx - start[0], ty - start[1]])
        d = float(np.linalg.norm(vec))
        T = d / speed
        self.release()
        self.bvel[:2] = vec / d * speed
        self.bvel[2] = (tz + cal.gravity * T * T / 2) / T
        self.ball[2] = 0.05
        keeper_y = ty if outcome == "saved" else ty * 0.45
        ev = self.emit(
            "shot",
            [c],
            team,
            start=self.r2(start[0], start[1]),
            end=[round(gx, 2), round(ty, 2), round(tz, 2)],
            xg=round(xg, 3),
            speed_ms=round(speed, 1),
            outcome=outcome,
        )
        self.flight = {
            "kind": "shot",
            "kicker": c,
            "team": team,
            "receiver": None,
            "target": np.array([gx, ty]),
            "keeper_to": np.array([gx - s * 1.0, keeper_y]),
            "t0": self.t,
            "event": ev,
            "outcome": outcome,
        }
        self.last_touch = team

    def clear(self, c: int) -> None:
        team = int(self.team[c])
        s = self.sign(team)
        rng = self.rng
        target = np.array([s * rng.uniform(5, 30), rng.uniform(-28, 28)])
        start = self.ball[:2].copy()
        vec = target - start
        d = float(np.linalg.norm(vec))
        vh = 21.0
        T = d / vh
        self.release()
        self.bvel[:2] = vec / d * vh
        self.bvel[2] = self.cal.gravity * T / 2
        self.ball[2] = 0.05
        ev = self.emit("clearance", [c], team, start=self.r2(*start), end=self.r2(*target))
        self.flight = {
            "kind": "clear",
            "kicker": c,
            "team": team,
            "receiver": None,
            "target": target,
            "t0": self.t,
            "event": ev,
        }
        self.last_touch = team

    # ------------------------------------------------------------------ logic
    def decide(self) -> None:
        cal = self.cal
        c = self.owner
        team = int(self.team[c])
        s = self.sign(team)
        opp = self.members[1 - team]
        dmin = float(np.min(np.linalg.norm(self.pos[opp] - self.pos[c], axis=1)))
        pressed = dmin < cal.press_radius_m
        hold = (self.t - self.reception_t) / 1000.0
        if hold < 0.35:
            return
        rate = 1.0 / (cal.pressed_hold_s if pressed else cal.mean_hold_s)
        if self.rng.random() >= rate * DT:
            return
        xn = float(self.pos[c, 0]) * s
        beat = self.beat_due("goal", team)
        if xn > 18.0:
            xg = xg_of(float(self.pos[c, 0]), float(self.pos[c, 1]), s)
            boost = 0.5 if beat is not None and xn > 25.0 else 0.0
            if self.rng.random() < min(0.85, xg * 2.2 + boost):
                if beat is not None:
                    self.used_beats.add(beat)
                self.shoot(c, forced=beat is not None)
                return
        if self.is_def[c] and xn < -28.0 and pressed and self.rng.random() < 0.35:
            self.clear(c)
            return
        recv, score = self.choose_pass(c)
        if recv < 0 or (score < 0.6 and not pressed and self.rng.random() < 0.5):
            self.reception_t = self.t - 200
            return
        self.kick_pass(c, recv)

    def tackles(self) -> None:
        cal = self.cal
        c = self.owner
        team = int(self.team[c])
        opp = self.members[1 - team]
        d = np.linalg.norm(self.pos[opp] - self.pos[c], axis=1)
        closing = -np.sum((self.pos[opp] - self.pos[c]) * (self.vel[opp] - self.vel[c]), axis=1)
        closing /= d + 1e-9
        for k, dk, ck in zip(opp, d, closing, strict=True):
            if dk < cal.press_radius_m and ck > 1.0 and self.t - self.last_press[k] > 3000:
                self.last_press[k] = self.t
                self.emit("press", [int(k), c], 1 - team, distance_m=round(float(dk), 2))
        for k, dk in zip(opp, d, strict=True):
            if dk > cal.tackle_radius_m or self.cooldown[k] > self.t or self.is_gk[k]:
                continue
            if self.rng.random() >= cal.tackle_rate_hz * DT:
                continue
            self.cooldown[k] = self.t + 1500
            r = self.rng.random()
            if r < cal.foul_share:
                self.emit("foul", [int(k), c], 1 - team, at=self.r2(*self.pos[c]))
                if self.rng.random() < cal.card_share:
                    self.emit("card", [int(k)], 1 - team, colour="yellow")
                self.begin_restart("free_kick", team, self.pos[c].copy(), 4.0)
                return
            if r < cal.foul_share + cal.tackle_success:
                self.emit("tackle", [int(k), c], 1 - team, outcome="won")
                self.release()
                self.set_owner(int(k))
                return
            self.emit("dribble", [c, int(k)], team, outcome="beat")
            return

    def control(self) -> None:
        f = self.flight
        if f is None or self.ball[2] > 1.9:
            return
        if self.t - f["t0"] < 200:
            return
        if f["kind"] == "shot":
            return
        b = self.ball[:2]
        d = np.linalg.norm(self.pos - b, axis=1)
        d[self.ref] = 1e9
        if f["kicker"] >= 0 and self.t - f["t0"] < 500:
            d[f["kicker"]] = 1e9
        recv = f.get("receiver")
        order = np.argsort(d)
        if recv is not None and d[recv] < self.cal.control_radius_m:
            order = [recv, *[k for k in order if k != recv]]
        for k in order:
            k = int(k)
            if d[k] >= self.cal.control_radius_m:
                break
            same = int(self.team[k]) == f["team"]
            if not same and self.rng.random() >= self.cal.intercept_per_tick:
                continue
            ev = f["event"]
            if f["kind"] == "pass":
                if same and k == recv and f.get("offside"):
                    ev["attrs"]["outcome"] = "offside"
                    self.emit("offside", [k], f["team"], at=self.r2(*self.pos[k]))
                    self.begin_restart("free_kick", 1 - f["team"], self.pos[k].copy(), 4.0)
                    return
                ev["attrs"]["outcome"] = "complete" if same else "incomplete"
                if same and k != recv:
                    ev["attrs"]["receiver"] = self.ids[k]
            if not same:
                self.emit("interception", [k], int(self.team[k]), at=self.r2(*b))
            self.set_owner(k)
            return

    def check_shot(self) -> None:
        f = self.flight
        if f is None or f["kind"] != "shot":
            return
        team = f["team"]
        s = self.sign(team)
        xb = float(self.ball[0]) * s
        if f["outcome"] == "saved" and xb >= HALF_LENGTH - 1.2:
            gk = self.gk[1 - team]
            self.emit("save", [gk], 1 - team, at=self.r2(*self.ball[:2]))
            self.ball[2] = 0.0
            self.bvel[:] = 0
            self.set_owner(gk)
            return
        if xb >= HALF_LENGTH:
            in_goal = abs(self.ball[1]) < GOAL_WIDTH / 2 and self.ball[2] < GOAL_HEIGHT
            if in_goal and f["outcome"] == "goal":
                self.goal(f["kicker"], team)

    def goal(self, scorer: int, team: int) -> None:
        self.score[team] += 1
        self.flight = None
        self.emit(
            "goal",
            [scorer],
            team,
            score={"home": self.score[0], "away": self.score[1]},
        )
        self.bvel[:2] *= 0.3
        self.state = "goal"
        self.kickoff_team = 1 - team
        wait = 14000
        vb = self.beat_due("var_check", None)
        if vb is not None:
            self.used_beats.add(vb)
            self.pending = [
                (self.t + 3000, "var_check", scorer, team, {"reason": "possible offside"}),
                (self.t + 14000, "var_decision", scorer, team, {"decision": "goal_stands"}),
            ]
            wait = 22000
        self.resume_t = self.t + wait

    def out_of_play(self) -> None:
        x, y = float(self.ball[0]), float(self.ball[1])
        if abs(x) <= HALF_LENGTH and abs(y) <= HALF_WIDTH:
            return
        if self.state != "play":
            return
        f = self.flight
        if f is not None and f["kind"] == "pass" and "outcome" not in f["event"]["attrs"]:
            f["event"]["attrs"]["outcome"] = "out"
        last = self.last_touch
        self.release()
        self.flight = None
        self.emit("ball_out", [], last, at=self.r2(x, y))
        if abs(y) > HALF_WIDTH and abs(x) <= HALF_LENGTH:
            spot = np.array([x, math.copysign(HALF_WIDTH, y)])
            self.begin_restart("throw_in", 1 - last, spot, 3.0)
            return
        # Over the goal line: who attacks that end?
        end_sign = 1 if x > 0 else -1
        attacker = 0 if self.sign(0) == end_sign else 1
        if last == attacker:
            spot = np.array([end_sign * GOAL_KICK_X, math.copysign(4.0, y)])
            self.begin_restart("goal_kick", 1 - attacker, spot, 5.0)
        else:
            spot = np.array([end_sign * HALF_LENGTH, math.copysign(HALF_WIDTH, y)])
            self.begin_restart("corner", attacker, spot, 6.0)

    def begin_restart(self, kind: str, team: int, spot: np.ndarray, delay: float) -> None:
        self.release()
        self.flight = None
        self.state = "restart"
        self.poss = team
        spot = spot.copy()
        if kind not in ("corner", "throw_in"):
            spot[0] = np.clip(spot[0], -HALF_LENGTH + 1, HALF_LENGTH - 1)
            spot[1] = np.clip(spot[1], -HALF_WIDTH + 1, HALF_WIDTH - 1)
        taker = self.gk[team] if kind == "goal_kick" else self.nearest(team, spot)
        self.restart = {
            "kind": kind,
            "team": team,
            "spot": spot,
            "taker": taker,
            "ready_t": self.t + int(delay * 1000),
        }
        self.ball[:2] = spot
        self.ball[2] = 0.0
        self.bvel[:] = 0

    def take_restart(self) -> None:
        r = self.restart
        assert r is not None
        tk = r["taker"]
        if self.t < r["ready_t"] or np.linalg.norm(self.pos[tk] - r["spot"]) > 1.5:
            return
        self.state = "play"
        self.restart = None
        self.emit(r["kind"], [tk], r["team"], at=self.r2(*r["spot"]))
        self.set_owner(tk)
        self.ball[:2] = r["spot"]
        max_len = 25.0 if r["kind"] == "throw_in" else 60.0
        recv, _ = self.choose_pass(tk, max_len=max_len)
        if recv < 0:
            recv = self.nearest(r["team"], r["spot"])
        lofted = True if r["kind"] == "corner" else None
        self.kick_pass(tk, recv, restart=r["kind"], lofted=lofted)

    def runs(self) -> None:
        if self.state != "play" or self.owner < 0:
            return
        att = self.poss
        idx = self.members[att][self.is_fwd[self.members[att]]]
        line = self.offside_line(att)
        for i in idx:
            if self.run_until[i] < self.t and self.rng.random() < 0.25 * DT:
                self.run_until[i] = self.t + 2500
                self.run_x[i] = min(line + self.rng.uniform(6, 14), HALF_LENGTH - 8)

    def step(self) -> None:
        tgt, cap = self.targets()
        self.move_players(tgt, cap)
        self.move_ball()
        if self.state == "play":
            if self.owner >= 0:
                self.tackles()
                if self.state == "play" and self.owner >= 0:
                    self.decide()
            else:
                self.check_shot()
                if self.state == "play":
                    self.control()
            if self.state == "play":
                self.out_of_play()
            self.runs()
        elif self.state == "restart":
            self.take_restart()
        elif self.state == "goal":
            for p in list(getattr(self, "pending", [])):
                if self.t >= p[0]:
                    self.emit(p[1], [p[2]], p[3], **p[4])
                    self.pending.remove(p)
            if self.t >= self.resume_t - 6000:
                self.state = "kickoff"
                self.ball[:] = 0
                self.bvel[:] = 0
        elif self.state == "kickoff":
            if self.t >= self.resume_t:
                st = self.nearest(self.kickoff_team, np.zeros(2))
                self.pos[st] = (-0.4 * self.sign(self.kickoff_team), 0.3)
                self.do_kickoff(self.kickoff_team)

    # ------------------------------------------------------------------ run
    def run(self) -> Match:
        per = int(round(self.cfg.half_minutes * 60_000 / FRAME_MS))
        total = per * self.cfg.periods
        players = np.zeros((total, self.n, 5), dtype=np.float32)
        ball = np.zeros((total, 5), dtype=np.float32)
        period = np.zeros(total, dtype=np.int8)
        self.pending: list[tuple] = []
        for p in range(1, self.cfg.periods + 1):
            self.start_period(p, kicker=(p - 1) % 2)
            for _ in range(per):
                self.step()
                i = self.tick
                players[i, :, PX] = self.pos[:, 0]
                players[i, :, PY] = self.pos[:, 1]
                players[i, :, PV] = np.linalg.norm(self.vel, axis=1)
                players[i, :, PHEAD] = self.head
                to_ball = self.ball[:2] - self.pos
                players[i, :, PBODY] = np.degrees(np.arctan2(to_ball[:, 1], to_ball[:, 0]))
                if self.owner >= 0:
                    players[i, self.owner, PBODY] = self.head[self.owner]
                ball[i, :3] = self.ball
                ball[i, 3] = np.linalg.norm(self.bvel)
                ball[i, BOWNER] = self.owner
                period[i] = p
                self.tick += 1
            self.tick -= 1
            self.release()
            if self.flight is not None and self.flight["kind"] == "pass":
                self.flight["event"]["attrs"].setdefault("outcome", "incomplete")
            self.flight = None
            self.emit("period_end", [], None, period=p)
            self.tick += 1
        self.events.sort(key=lambda e: (e["t"], e["_seq"]))
        for n, ev in enumerate(self.events, 1):
            ev["id"] = f"e{n:05d}"
            del ev["_seq"]
        meta = {
            "half_minutes": self.cfg.half_minutes,
            "periods": self.cfg.periods,
            "score": {"home": self.score[0], "away": self.score[1]},
            "calibration": self.cal.to_dict(),
        }
        return Match(
            seed=self.cfg.seed,
            lineup=self.lineup,
            players=players,
            ball=ball,
            period=period,
            events=self.events,
            meta=meta,
        )
