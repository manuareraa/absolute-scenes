"""M9 auto-eventing: pitch tracks -> ``event`` contracts with ``source: "video"``.

Rules on top of possession:

- A person owns the ball when they are the nearest outfield person to it within
  ``OWN_R`` metres. Runs shorter than ``MIN_RUN`` frames are dropped.
- Between two possession runs, the ball was played. A release is fitted as a ballistic
  arc: the ball's image ray from the surveyed camera, and the release point at the
  owner's feet, make the 3D release velocity a small linear least-squares problem. This
  undoes the ground-plane error of an airborne ball.
- Release outcomes:
  - The arc crosses a goal line between the posts and under the bar: a shot. If the
    ball then goes in, a goal.
  - Next owner is a team-mate within ``PASS_MAX_S``: a pass.
  - A hard release in the team's own half: a clearance.
  - Next owner is on the other team: a tackle when the two were close, otherwise an
    interception (with the incomplete pass before it, if the ball travelled).
- When the ball jumps (``JUMP_M`` in one frame), the match restarted. If its last
  position was near the touch or goal line, that was a ``ball_out``. The next release
  from inside a goal area is a goal kick.
- Presses: an opponent within ``PRESS_R`` of the owner for ``PRESS_MIN`` frames.

Actors are track ids (``"T12"``): video sees shirts, not names. Each event carries a
confidence from how clean the evidence was. Which way each team attacks comes from where
its goalkeeper stands.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from chalktalk_core.geometry import FRAME_MS

from .pitch_tracks import PitchFrame

HALF_L, HALF_W = 52.5, 34.0
GOAL_HALF, BAR = 3.66, 2.44
GRAVITY = 9.81
OWN_R = 1.3
MIN_RUN = 3
TACKLE_R = 2.0
PRESS_R = 2.0
PRESS_MIN = 12
PASS_MAX_S = 3.0
CLEAR_SPEED = 16.0
CARRY_MIN_M = 3.0
JUMP_M = 6.0
LINE_NEAR = 2.5
FIT_FRAMES = 15
RELEASE_LOOKAHEAD = 5  # frames the ball may stay at the feet after a challenger is closer


@dataclass
class Run:
    owner: int
    team: str
    start: int
    end: int


def ball_path(
    frames: list[PitchFrame], max_gap: int = 6, held_gap: int = 50, held_m: float = 2.0
) -> np.ndarray:
    """(T, 2) ball ground positions with gaps filled linearly; NaN elsewhere.

    Short gaps are always filled. Longer ones (up to ``held_gap`` frames) are filled when
    the ball reappears within ``held_m`` of where it vanished: a detector loses the ball at
    a player's feet far more often than the ball actually travels and comes back.
    """
    xy = np.full((len(frames), 2), np.nan)
    for k, f in enumerate(frames):
        if f.ball is not None:
            xy[k] = f.ball["x"], f.ball["y"]
    ok = np.flatnonzero(~np.isnan(xy[:, 0]))
    for a, b in zip(ok[:-1], ok[1:], strict=True):
        d = np.hypot(*(xy[b] - xy[a]))
        short = b - a <= max_gap and d < JUMP_M * (b - a)
        if 1 < b - a and (short or (b - a <= held_gap and d < held_m)):
            w = np.linspace(0, 1, b - a + 1)[1:-1, None]
            xy[a + 1 : b] = xy[a] * (1 - w) + xy[b] * w
    return xy


def restarts(ball: np.ndarray) -> list[int]:
    """Frames whose ball position jumped from the previous seen one (a dead-ball reset)."""
    out = []
    last = None
    for k, b in enumerate(ball):
        if np.isnan(b[0]):
            continue
        if last is not None and np.hypot(*(b - ball[last])) > JUMP_M * min(k - last, 3):
            out.append(last)
        last = k
    return out


def ballistic_fit(
    ground: np.ndarray,
    times: np.ndarray,
    start: np.ndarray,
    cam: np.ndarray,
    obs_sigma: float = 0.05,
    start_sigma: float = 0.5,
    height_sigma: float = 0.15,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Release point (x, y, z) and velocity (vx, vy, vz) from ground-projected ball points.

    The ball at time t is B = S + v t - (0, 0, g t^2 / 2). Its ground projection G
    satisfies (G - C) (Cz - Bz) = (B - C) Cz per horizontal axis, which is linear in S
    and v. Height and distance along the camera ray are nearly degenerate over a short
    window, so the release point gets a prior: near ``start`` and near the ground.
    """
    ok = ~np.isnan(ground[:, 0])
    if ok.sum() < 4:
        return None
    G, t = ground[ok], times[ok]
    Cz = cam[2]
    drop = GRAVITY * t**2 / 2
    rows, rhs = [], []
    for ax in (0, 1):
        c = cam[ax]
        a = np.zeros((len(t), 6))
        a[:, ax] = -Cz
        a[:, 3 + ax] = -Cz * t
        a[:, 2] = -(G[:, ax] - c)
        a[:, 5] = -(G[:, ax] - c) * t
        rows.append(a / Cz)
        rhs.append((-c * Cz - (G[:, ax] - c) * (Cz + drop)) / Cz)
    prior = np.zeros((3, 6))
    w = np.array([obs_sigma / start_sigma, obs_sigma / start_sigma, obs_sigma / height_sigma])
    prior[[0, 1, 2], [0, 1, 2]] = w
    rows.append(prior)
    rhs.append(np.array([start[0], start[1], 0.0]) * w)
    x, *_ = np.linalg.lstsq(np.vstack(rows), np.concatenate(rhs), rcond=None)
    return x[:3], x[3:]


def arc_at_line(
    start: np.ndarray, v: np.ndarray, x_line: float
) -> tuple[float, float, float] | None:
    """(t, y, z) where the arc from 3D ``start`` crosses x = ``x_line``; None if never."""
    if abs(v[0]) < 1e-6:
        return None
    t = (x_line - start[0]) / v[0]
    if t <= 0:
        return None
    return t, start[1] + v[1] * t, start[2] + v[2] * t - GRAVITY * t**2 / 2


def owners(frames: list[PitchFrame], ball: np.ndarray) -> list[tuple[int, str] | None]:
    out: list[tuple[int, str] | None] = []
    for f, b in zip(frames, ball, strict=True):
        best = None
        if not np.isnan(b[0]):
            for p in f.people:
                if p.get("team") not in ("home", "away"):
                    continue
                d = np.hypot(p["x"] - b[0], p["y"] - b[1])
                if d <= OWN_R and (best is None or d < best[0]):
                    best = (d, p["id"], p["team"])
        out.append(best[1:] if best else None)
    return out


def runs(own: list[tuple[int, str] | None]) -> list[Run]:
    out: list[Run] = []
    k = 0
    while k < len(own):
        if own[k] is None:
            k += 1
            continue
        j = k
        while j + 1 < len(own) and own[j + 1] == own[k]:
            j += 1
        if j - k + 1 >= MIN_RUN:
            if out and out[-1].owner == own[k][0] and k - out[-1].end <= MIN_RUN:
                out[-1].end = j
            else:
                out.append(Run(own[k][0], own[k][1], k, j))
        k = j + 1
    return out


def attack_sign(frames: list[PitchFrame]) -> dict[str, float]:
    """+1 when a team attacks towards +x. From the goalkeepers' mean x."""
    xs: dict[str, list[float]] = {"home": [], "away": []}
    for f in frames:
        for p in f.people:
            if p.get("cls") == "goalkeeper" and p.get("team") in xs:
                xs[p["team"]].append(p["x"])
    sign = {t: -float(np.sign(np.mean(v)) or 1.0) for t, v in xs.items() if v}
    if len(sign) == 1:
        ((t, s),) = sign.items()
        sign["away" if t == "home" else "home"] = -s
    return {"home": sign.get("home", 1.0), "away": sign.get("away", -1.0)}


def _pos(f: PitchFrame, tid: int) -> tuple[float, float] | None:
    for p in f.people:
        if p["id"] == tid:
            return p["x"], p["y"]
    return None


def _xy(p) -> list[float]:
    return [round(float(p[0]), 2), round(float(p[1]), 2)]


def detect(
    frames: list[PitchFrame], start_ms: int, camera_position: tuple[float, float, float]
) -> list[dict]:
    """Events in the clip. ``start_ms`` is the match clock of frame index 0."""
    if not frames:
        return []
    T = len(frames)
    dt = FRAME_MS / 1000
    cam = np.asarray(camera_position, float)

    def t_of(k: float) -> int:
        k0 = int(np.clip(np.floor(k), 0, T - 1))
        return int(round(start_ms + (frames[k0].index + (k - k0)) * FRAME_MS))

    ball = ball_path(frames)
    resets = restarts(ball)
    rs = runs(owners(frames, ball))
    sign = attack_sign(frames)
    events: list[dict] = []

    def emit(k: float, kind: str, actors: list[int], team, conf: float, **attrs):
        ev = {
            "id": "",
            "t": t_of(k),
            "type": kind,
            "actors": [f"T{a}" for a in actors],
            "source": "video",
            "confidence": round(float(np.clip(conf, 0, 1)), 2),
            "attrs": {a: v for a, v in attrs.items() if v is not None},
        }
        if team in ("home", "away"):
            ev["team"] = team
        events.append(ev)

    def release(r: Run, until: int):
        """Fitted 3D release point and velocity for the ball leaving ``r``'s owner.

        The release is the last frame the ball is still at the owner's feet, which can be
        a few frames past the run's end when a challenger is marginally closer.
        """
        end = r.end
        for k in range(r.end + 1, min(r.end + 1 + RELEASE_LOOKAHEAD, until, T)):
            p = _pos(frames[k], r.owner)
            if p is None or np.isnan(ball[k, 0]) or np.hypot(*(ball[k] - p)) > OWN_R:
                break
            end = k
        s0 = ball[end]
        if np.isnan(s0[0]):
            s0 = np.asarray(_pos(frames[end], r.owner) or (np.nan, np.nan), float)
        hi = min(until, end + 1 + FIT_FRAMES, T)
        ks = np.arange(end + 1, hi)
        fit = ballistic_fit(ball[ks], (ks - end) * dt, s0, cam) if len(ks) else None
        if fit is None or np.isnan(s0[0]):
            return np.array([*s0, 0.0]), None
        return fit

    out_handled: set[int] = set()
    pending_restart = False
    for i, r in enumerate(rs):
        nxt = rs[i + 1] if i + 1 < len(rs) else None
        until = nxt.start if nxt else T
        reset = next((k for k in resets if r.end <= k < until), None)
        a, b = _pos(frames[r.start], r.owner), _pos(frames[r.end], r.owner)
        s_sign = sign.get(r.team, 1.0)

        if pending_restart and a is not None:
            pending_restart = False
            if abs(a[0]) > HALF_L - 6.5 and abs(a[1]) < 10.0:
                emit(r.end, "goal_kick", [r.owner], r.team, 0.75, at=_xy(a))
                a = b  # a goal kick is a dead ball, not a carry
        if a and b and np.hypot(b[0] - a[0], b[1] - a[1]) >= CARRY_MIN_M:
            conf = 0.6 + 0.3 * min(1.0, (r.end - r.start) / 25)
            emit(r.start, "carry", [r.owner], r.team, conf, start=_xy(a), end=_xy(b))
        _presses(frames, r, emit)

        start, v = release(r, reset + 1 if reset is not None else until)
        speed = float(np.linalg.norm(v)) if v is not None else 0.0
        shot = None
        if v is not None and v[0] * s_sign > 0:
            hit = arc_at_line(start, v, s_sign * HALF_L)
            if hit and hit[0] <= 2.5 and abs(hit[1]) <= GOAL_HALF + 2.0 and hit[2] <= BAR + 2.0:
                shot = hit
        gap_s = (until - r.end) * dt
        if shot is not None:
            on_target = abs(shot[1]) <= GOAL_HALF and 0 <= shot[2] <= BAR
            goal = on_target and (nxt is None or reset is not None)
            emit(
                r.end,
                "shot",
                [r.owner],
                r.team,
                0.8 if on_target else 0.6,
                start=_xy(start),
                end=[round(s_sign * HALF_L, 2), round(shot[1], 2), round(max(shot[2], 0.0), 2)],
                speed_ms=round(speed, 1),
                outcome="goal" if goal else None,
            )
            if goal:
                emit(r.end + shot[0] / dt, "goal", [r.owner], r.team, 0.7)
                if reset is not None:
                    out_handled.add(reset)
                continue
        elif (
            nxt is not None and nxt.team == r.team and nxt.owner != r.owner and gap_s <= PASS_MAX_S
        ):
            c = _pos(frames[nxt.start], nxt.owner) or start
            emit(
                r.end,
                "pass",
                [r.owner, nxt.owner],
                r.team,
                0.8,
                start=_xy(start),
                end=_xy(c),
                receiver=f"T{nxt.owner}",
                outcome="complete",
            )
        elif speed >= CLEAR_SPEED and start[0] * s_sign < 0:
            emit(r.end, "clearance", [r.owner], r.team, 0.6, start=_xy(start))
        elif nxt is not None and nxt.team != r.team and reset is None and gap_s > 0.3:
            c = _pos(frames[nxt.start], nxt.owner) or start
            emit(
                r.end,
                "pass",
                [r.owner],
                r.team,
                0.5,
                start=_xy(start),
                end=_xy(c),
                outcome="incomplete",
            )

        if reset is not None and reset not in out_handled:
            out_handled.add(reset)
            p = ball[reset]
            if HALF_L - abs(p[0]) <= LINE_NEAR or HALF_W - abs(p[1]) <= LINE_NEAR:
                emit(reset + 1, "ball_out", [], r.team, 0.75, at=_xy(p))
                pending_restart = True
            continue
        if nxt is not None and nxt.team != r.team:
            o2, n2 = _pos(frames[nxt.start], r.owner), _pos(frames[nxt.start], nxt.owner)
            close = o2 and n2 and np.hypot(o2[0] - n2[0], o2[1] - n2[1]) <= TACKLE_R
            if close and nxt.start - r.end <= 4:
                emit(nxt.start, "tackle", [nxt.owner, r.owner], nxt.team, 0.65, outcome="won")
            else:
                at = n2 or (ball[nxt.start] if not np.isnan(ball[nxt.start, 0]) else None)
                emit(
                    nxt.start,
                    "interception",
                    [nxt.owner],
                    nxt.team,
                    0.7,
                    at=_xy(at) if at is not None else None,
                )

    events.sort(key=lambda e: e["t"])
    for n, ev in enumerate(events):
        ev["id"] = f"v{n:05d}"
    return events


def _presses(frames: list[PitchFrame], r: Run, emit) -> None:
    """One press per opponent who stays within PRESS_R of the owner for PRESS_MIN frames."""
    streak: dict[int, int] = {}
    done: set[int] = set()
    for k in range(r.start, r.end + 1):
        o = _pos(frames[k], r.owner)
        if o is None:
            continue
        for p in frames[k].people:
            if p.get("team") not in ("home", "away") or p["team"] == r.team or p["id"] in done:
                continue
            d = np.hypot(p["x"] - o[0], p["y"] - o[1])
            streak[p["id"]] = streak.get(p["id"], 0) + 1 if d <= PRESS_R else 0
            if streak[p["id"]] >= PRESS_MIN:
                done.add(p["id"])
                emit(
                    k - PRESS_MIN + 1,
                    "press",
                    [p["id"], r.owner],
                    p["team"],
                    0.55,
                    distance_m=round(float(d), 2),
                )


def compare(
    video: list[dict],
    sim: list[dict],
    track_to_player: dict[int, str],
    tol_ms: int = 1000,
) -> dict:
    """Match video events to sim events by type within ``tol_ms``; report P/R and timing."""
    used: set[int] = set()
    matched = []
    for v in sorted(video, key=lambda e: -e["confidence"]):
        best = None
        for j, s in enumerate(sim):
            if j in used or s["type"] != v["type"]:
                continue
            dt_ms = abs(s["t"] - v["t"])
            if dt_ms <= tol_ms and (best is None or dt_ms < best[0]):
                best = (dt_ms, j)
        if best:
            used.add(best[1])
            s = sim[best[1]]
            actor_ok = None
            if v["actors"] and s["actors"]:
                actor_ok = track_to_player.get(int(v["actors"][0][1:])) == s["actors"][0]
            matched.append((v, s, best[0], actor_ok))
    types = sorted({e["type"] for e in sim} | {e["type"] for e in video})
    per_type = {}
    for t in types:
        per_type[t] = {
            "video": sum(e["type"] == t for e in video),
            "sim": sum(e["type"] == t for e in sim),
            "matched": sum(m[0]["type"] == t for m in matched),
        }
    actor_checks = [m[3] for m in matched if m[3] is not None]
    return {
        "video_events": len(video),
        "sim_events": len(sim),
        "matched": len(matched),
        "precision": round(len(matched) / max(len(video), 1), 3),
        "recall": round(len(matched) / max(len(sim), 1), 3),
        "timing_mae_ms": round(float(np.mean([m[2] for m in matched])), 1) if matched else None,
        "actor_accuracy": round(float(np.mean(actor_checks)), 3) if actor_checks else None,
        "per_type": per_type,
        "pairs": [
            {
                "video": m[0]["id"],
                "sim": m[1]["id"],
                "type": m[0]["type"],
                "dt_ms": m[2],
                "actor_ok": m[3],
            }
            for m in matched
        ],
    }
