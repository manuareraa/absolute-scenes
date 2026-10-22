"""Headless broadcast-angle renderer for a synthetic match, with exact ground truth.

CPU only (numpy + OpenCV). The pitch, stand and boards are textures warped through the
camera; players are drawn as shaded figures with a running gait, sorted back to front.
Every frame comes with the camera matrix, the pitch-to-image homography and each person's
pitch position and pixel box, so detection, tracking and events can be scored exactly.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from chalktalk_core.geometry import (
    CENTRE_CIRCLE_RADIUS,
    FRAME_MS,
    GOAL_HEIGHT,
    GOAL_WIDTH,
    HALF_LENGTH,
    HALF_WIDTH,
    PENALTY_AREA_DEPTH,
    PENALTY_AREA_WIDTH,
    PENALTY_SPOT,
)
from chalktalk_sim.match import BOWNER, BX, BY, BZ, PBODY, PHEAD, PV, PX, PY, Match

from .camera import Camera

PERSON_HEIGHT = 1.8
BALL_RADIUS = 0.11
GOAL_AREA_DEPTH = 5.5
GOAL_AREA_WIDTH = 18.32
LINE_WIDTH = 0.12

# Ground texture extent (metres) and resolution.
TEX_X = (-62.5, 62.5)
TEX_Y = (-40.0, 38.0)
TEX_PPM = 20

# Kits (BGR). Goalkeepers and the referee get their own colours, as on TV.
_HEX = {
    "home": ("#1f4fa8", "#ffffff", "#1f4fa8"),
    "away": ("#c8102e", "#111111", "#c8102e"),
    "home_gk": ("#e84393", "#222222", "#e84393"),
    "away_gk": ("#7d3cb5", "#222222", "#7d3cb5"),
    "ref": ("#f1e43c", "#111111", "#111111"),
}
SKIN = [(160, 190, 230), (120, 160, 205), (90, 120, 170), (60, 85, 125), (45, 60, 95)]
HAIR = [(20, 20, 25), (30, 45, 70), (60, 90, 130), (110, 150, 190), (40, 40, 40)]


def _bgr(hexcode: str) -> tuple[int, int, int]:
    h = hexcode.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)


def _shade(c: tuple[int, int, int], k: float) -> tuple[int, int, int]:
    return tuple(int(min(255, max(0, v * k))) for v in c)  # type: ignore[return-value]


def kit_key(team: str, role: str) -> str:
    if team == "ref":
        return "ref"
    return f"{team}_gk" if role == "GK" else team


@dataclass(frozen=True)
class ClipSpec:
    start_ms: int
    seconds: float = 30.0
    width: int = 1280
    height: int = 720
    hfov_deg: float = 27.0
    camera_pos: tuple[float, float, float] = (0.0, -62.0, 22.0)
    seed: int = 0

    @property
    def n_frames(self) -> int:
        return int(round(self.seconds * 1000 / FRAME_MS))


@dataclass
class RenderedFrame:
    index: int
    t: int
    image: np.ndarray
    truth: dict[str, Any] = field(default_factory=dict)


# --- textures -------------------------------------------------------------------------


def _tex_from_world(x: float, y: float) -> tuple[float, float]:
    return ((x - TEX_X[0]) * TEX_PPM, (TEX_Y[1] - y) * TEX_PPM)


def _world_to_tex() -> np.ndarray:
    s = TEX_PPM
    return np.array([[s, 0, -TEX_X[0] * s], [0, -s, TEX_Y[1] * s], [0, 0, 1]], dtype=np.float64)


def pitch_lines() -> list[np.ndarray]:
    """Pitch markings as polylines in metres (also the template for calibration)."""
    L, W = HALF_LENGTH, HALF_WIDTH
    lines: list[np.ndarray] = [
        np.array([[-L, -W], [L, -W], [L, W], [-L, W], [-L, -W]]),
        np.array([[0, -W], [0, W]]),
    ]
    a = np.linspace(0, 2 * math.pi, 73)
    lines.append(np.stack([CENTRE_CIRCLE_RADIUS * np.cos(a), CENTRE_CIRCLE_RADIUS * np.sin(a)], 1))
    for s in (-1, 1):
        for depth, width in (
            (PENALTY_AREA_DEPTH, PENALTY_AREA_WIDTH),
            (GOAL_AREA_DEPTH, GOAL_AREA_WIDTH),
        ):
            x0, x1, hw = s * L, s * (L - depth), width / 2
            lines.append(np.array([[x0, -hw], [x1, -hw], [x1, hw], [x0, hw]]))
        # Penalty arc: the part of the 9.15 m circle round the spot outside the box.
        spot = s * (L - PENALTY_SPOT)
        lim = math.acos((PENALTY_AREA_DEPTH - PENALTY_SPOT) / CENTRE_CIRCLE_RADIUS)
        a = np.linspace(-lim, lim, 25)
        lines.append(
            np.stack(
                [spot - s * CENTRE_CIRCLE_RADIUS * np.cos(a), CENTRE_CIRCLE_RADIUS * np.sin(a)], 1
            )
        )
        for sy in (-1, 1):
            a = np.linspace(0, math.pi / 2, 7)
            lines.append(np.stack([s * (L - np.cos(a)), sy * (W - np.sin(a))], 1))
    return lines


def ground_texture(rng: np.random.Generator) -> np.ndarray:
    w = int((TEX_X[1] - TEX_X[0]) * TEX_PPM)
    h = int((TEX_Y[1] - TEX_Y[0]) * TEX_PPM)
    xs = np.linspace(TEX_X[0], TEX_X[1], w)
    stripe = (np.floor((xs + HALF_LENGTH) / (2 * HALF_LENGTH / 18)) % 2).astype(np.float32)
    base = np.array([58, 128, 62], np.float32)  # BGR grass
    tex = np.empty((h, w, 3), np.float32)
    tex[:] = base
    tex *= (1.0 + 0.09 * stripe)[None, :, None]
    noise = cv2.resize(rng.normal(0, 1, (h // 40, w // 40)).astype(np.float32), (w, h))
    fine = rng.normal(0, 1, (h, w)).astype(np.float32)
    tex *= (1.0 + 0.04 * noise + 0.025 * fine)[:, :, None]
    # Outside the playing area the grass is plain and a little darker.
    ox0, oy0 = _tex_from_world(-HALF_LENGTH - 2, HALF_WIDTH + 2)
    ox1, oy1 = _tex_from_world(HALF_LENGTH + 2, -HALF_WIDTH - 2)
    mask = np.ones((h, w), bool)
    mask[int(oy0) : int(oy1), int(ox0) : int(ox1)] = False
    tex[mask] *= 0.93
    tex = np.clip(tex, 0, 255).astype(np.uint8)
    lw = max(1, int(round(LINE_WIDTH * TEX_PPM)))
    white = (232, 238, 236)
    sh = 16  # fixed-point shift for sub-pixel lines
    for pl in pitch_lines():
        pts = np.array([_tex_from_world(x, y) for x, y in pl]) * (1 << sh)
        cv2.polylines(tex, [pts.astype(np.int32)], False, white, lw, cv2.LINE_AA, sh)
    for x in (-(HALF_LENGTH - PENALTY_SPOT), 0.0, HALF_LENGTH - PENALTY_SPOT):
        cx, cy = _tex_from_world(x, 0)
        cv2.circle(tex, (int(cx), int(cy)), int(0.2 * TEX_PPM), white, -1, cv2.LINE_AA)
    return tex


def crowd_texture(rng: np.random.Generator, w: int = 1600, h: int = 400) -> np.ndarray:
    cell = 4
    gw, gh = w // cell, h // cell
    palette = np.array(
        [(40, 40, 48), (30, 30, 140), (150, 60, 30), (200, 200, 200), (60, 120, 200), (90, 90, 90)],
        np.uint8,
    )
    idx = rng.choice(len(palette), size=(gh, gw), p=[0.35, 0.15, 0.15, 0.1, 0.1, 0.15])
    small = palette[idx].astype(np.float32) * rng.uniform(0.6, 1.1, (gh, gw, 1))
    rows = (np.arange(gh) % 3 == 0)[:, None, None]
    small = np.where(rows, small * 0.45, small)
    tex = cv2.resize(small.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
    return cv2.GaussianBlur(tex, (3, 3), 0)


def boards_texture(w: int = 2200, h: int = 18) -> np.ndarray:
    # Plain generic panels; no brands or marks.
    colours = [(150, 70, 20), (30, 30, 30), (20, 120, 200), (200, 200, 200), (40, 90, 40)]
    tex = np.zeros((h, w, 3), np.uint8)
    panel = 110
    for i in range(0, w, panel):
        c = colours[(i // panel) % len(colours)]
        tex[:, i : i + panel] = c
        cv2.rectangle(tex, (i + 20, 5), (i + panel - 20, h - 6), _shade(c, 1.6), -1)
    return tex


# --- renderer ------------------------------------------------------------------------


class Renderer:
    """Renders a window of a ``Match`` from the main broadcast camera."""

    def __init__(self, match: Match, spec: ClipSpec):
        self.match = match
        self.spec = spec
        rng = np.random.default_rng(spec.seed)
        self.ground = ground_texture(rng)
        self.crowd = crowd_texture(rng)
        self.boards = boards_texture()
        self.n = len(match.lineup)
        self.phase = rng.uniform(0, 2 * math.pi, self.n)
        self.looks = []
        for p in match.lineup:
            k = zlib.crc32(p.id.encode())
            self.looks.append((SKIN[k % len(SKIN)], HAIR[(k // 7) % len(HAIR)]))
        self.kits = [tuple(_bgr(c) for c in _HEX[kit_key(p.team, p.role)]) for p in match.lineup]
        self.start = match.tick(spec.start_ms)
        self._cam_xy = self._warm_camera()
        self.noise_rng = np.random.default_rng(spec.seed + 1)

    # Camera operator: follows the ball with critically smoothed pan and a slight zoom.
    def _aim(self, i: int) -> tuple[float, float]:
        b = self.match.ball[i]
        return float(np.clip(b[BX] * 0.9, -36, 36)), float(np.clip(b[BY] * 0.45 + 4, -10, 16))

    def _warm_camera(self) -> np.ndarray:
        i0 = max(0, self.start - 75)
        xy = np.array(self._aim(i0))
        for i in range(i0, self.start):
            xy += 0.05 * (np.array(self._aim(i)) - xy)
        return xy

    def camera(self) -> Camera:
        tx, ty = self._cam_xy
        zoom = 1.0 - 0.06 * (1 - min(abs(tx) / 36, 1))
        return Camera(
            position=self.spec.camera_pos,
            target=(tx, ty, 0.0),
            hfov_deg=self.spec.hfov_deg * zoom,
            width=self.spec.width,
            height=self.spec.height,
        )

    def frames(self) -> Iterator[RenderedFrame]:
        for k in range(self.spec.n_frames):
            i = min(self.start + k, self.match.n_frames - 1)
            self._cam_xy += 0.05 * (np.array(self._aim(i)) - self._cam_xy)
            yield self.render(k, i)

    def render(self, k: int, i: int) -> RenderedFrame:
        cam = self.camera()
        W, H = cam.width, cam.height
        img = np.empty((H, W, 3), np.uint8)
        grad = np.linspace(25, 55, H, dtype=np.float32)[:, None]
        img[:] = np.stack([grad + 5, grad, grad - 5], -1).astype(np.uint8)
        for s in (-1, 1):  # end stands behind the goals, then the main stand opposite
            x0, x1 = s * 58.0, s * 90.0
            self._warp_plane(
                img, cam, self.crowd, [(x1, 75, 26), (x1, -75, 26), (x0, -45, 0.5), (x0, 45, 0.5)]
            )
        self._warp_plane(
            img, cam, self.crowd, [(-80, 75, 26), (80, 75, 26), (80, 39, 0.5), (-80, 39, 0.5)]
        )
        Hg = cam.ground_homography()
        Ht = Hg @ np.linalg.inv(_world_to_tex())
        cv2.warpPerspective(
            self.ground,
            Ht,
            (W, H),
            dst=img,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_TRANSPARENT,
        )
        y_b = HALF_WIDTH + 1.5
        self._warp_plane(
            img, cam, self.boards, [(-55, y_b, 0.9), (55, y_b, 0.9), (55, y_b, 0), (-55, y_b, 0)]
        )
        for s in (-1, 1):
            self._goal(img, cam, s)
        truth = self._people(img, cam, i)
        img = cv2.GaussianBlur(img, (0, 0), 0.6)
        img = cv2.add(img, self.noise_rng.integers(0, 4, img.shape, dtype=np.uint8))
        truth.update(
            t=int(i * FRAME_MS),
            frame=k,
            period=int(self.match.period[i]),
            P=np.round(cam.P(), 6).tolist(),
            H=np.round(Hg / Hg[2, 2], 9).tolist(),
        )
        return RenderedFrame(index=k, t=int(i * FRAME_MS), image=img, truth=truth)

    def _warp_plane(self, img: np.ndarray, cam: Camera, tex: np.ndarray, corners: list) -> None:
        """Warp a texture onto a world quad; corners run TL, TR, BR, BL of the texture."""
        uv, depth = cam.project(np.array(corners, np.float64))
        if (depth <= 0.5).any():
            return
        h, w = tex.shape[:2]
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        M = cv2.getPerspectiveTransform(src, uv.astype(np.float32))
        cv2.warpPerspective(
            tex,
            M,
            (cam.width, cam.height),
            dst=img,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_TRANSPARENT,
        )

    def _goal(self, img: np.ndarray, cam: Camera, s: int) -> None:
        gx, hw = s * HALF_LENGTH, GOAL_WIDTH / 2
        back = gx + s * 2.0
        net = []
        for z in np.linspace(0, GOAL_HEIGHT, 6):
            net.append([(gx, -hw, z), (back, -hw, z * 0.6), (back, hw, z * 0.6), (gx, hw, z)])
        for y in np.linspace(-hw, hw, 9):
            net.append([(back, y, 0), (back, y, GOAL_HEIGHT * 0.6), (gx, y, GOAL_HEIGHT)])
        for pl in net:
            uv, d = cam.project(np.array(pl))
            if (d > 0).all():
                cv2.polylines(
                    img, [np.round(uv).astype(np.int32)], False, (190, 195, 195), 1, cv2.LINE_AA
                )
        frame = np.array([(gx, -hw, 0), (gx, -hw, GOAL_HEIGHT), (gx, hw, GOAL_HEIGHT), (gx, hw, 0)])
        uv, d = cam.project(frame)
        if (d > 0).all():
            px = max(2, int(round(cam.focal * 0.12 / d.mean())))
            cv2.polylines(
                img, [np.round(uv).astype(np.int32)], False, (245, 248, 248), px, cv2.LINE_AA
            )

    def _people(self, img: np.ndarray, cam: Camera, i: int) -> dict[str, Any]:
        m = self.match
        P = m.players[i]
        right = cam.R()[0]
        feet = np.column_stack([P[:, PX], P[:, PY], np.zeros(self.n)])
        heads = feet + [0, 0, PERSON_HEIGHT]
        uv_f, d_f = cam.project(feet)
        uv_h, _ = cam.project(heads)
        dt = FRAME_MS / 1000
        self.phase += 2 * math.pi * P[:, PV] * dt / 2.1
        # Ball (drawn in depth order with the players).
        b = m.ball[i]
        uv_b, d_b = cam.project(np.array([[b[BX], b[BY], b[BZ] + BALL_RADIUS], [b[BX], b[BY], 0]]))
        items = [(float(d_f[j]), j) for j in range(self.n)] + [(float(d_b[0]), -1)]
        boxes: dict[int, list[float]] = {}
        ball_box = None
        for _, j in sorted(items, reverse=True):
            if j < 0:
                ball_box = self._ball(img, cam, uv_b, d_b)
                continue
            if d_f[j] <= 0:
                continue
            heading = math.radians(float(P[j, PHEAD]))
            lateral = float(np.dot(right[:2], [math.cos(heading), math.sin(heading)]))
            facing = math.radians(float(P[j, PBODY]))
            to_cam = float(np.dot([math.cos(facing), math.sin(facing)], [0, -1]))
            boxes[j] = self._figure(img, uv_f[j], uv_h[j], j, float(P[j, PV]), lateral, to_cam)
        players = []
        for j, pl in enumerate(m.lineup):
            box = boxes.get(j)
            vis = _visible_fraction(box, cam.width, cam.height) if box else 0.0
            players.append(
                {
                    "id": pl.id,
                    "team": pl.team,
                    "role": pl.role,
                    "x": round(float(P[j, PX]), 3),
                    "y": round(float(P[j, PY]), 3),
                    "bbox": [round(v, 1) for v in box] if box else None,
                    "visible": round(vis, 3),
                }
            )
        owner = int(b[BOWNER])
        return {
            "players": players,
            "ball": {
                "x": round(float(b[BX]), 3),
                "y": round(float(b[BY]), 3),
                "z": round(float(b[BZ]), 3),
                "owner": m.lineup[owner].id if owner >= 0 else None,
                "bbox": [round(v, 1) for v in ball_box] if ball_box else None,
                "visible": round(_visible_fraction(ball_box, cam.width, cam.height), 3)
                if ball_box
                else 0.0,
            },
        }

    def _ball(
        self, img: np.ndarray, cam: Camera, uv: np.ndarray, d: np.ndarray
    ) -> list[float] | None:
        if d[0] <= 0:
            return None
        r = max(1.6, cam.focal * BALL_RADIUS / d[0])
        sx, sy = uv[1]
        _shadow(img, (sx, sy), (r * 1.2 + 1, max(1.0, r * 0.4)), 0.35)
        cx, cy = uv[0]
        sh = 4
        c = (int(cx * 16), int(cy * 16))
        cv2.circle(img, c, int(r * 16), (240, 240, 240), -1, cv2.LINE_AA, sh)
        cv2.circle(
            img,
            (int((cx + r * 0.25) * 16), int((cy + r * 0.25) * 16)),
            int(r * 0.45 * 16),
            (70, 70, 70),
            -1,
            cv2.LINE_AA,
            sh,
        )
        return [cx - r, cy - r, cx + r, cy + r]

    def _figure(
        self,
        img: np.ndarray,
        foot: np.ndarray,
        head: np.ndarray,
        j: int,
        v: float,
        lateral: float,
        to_cam: float,
    ) -> list[float]:
        up = head - foot
        h = float(np.linalg.norm(up))
        up /= h
        side = np.array([-up[1], up[0]])
        if side[0] < 0:
            side = -side
        upv = up  # unit vector from the feet to the head in the image

        def pt(a: float, b: float) -> np.ndarray:
            """a: metres-ish to the right, b: fraction of height above the feet."""
            return foot + side * a * h + upv * b * h

        shirt, shorts, socks = self.kits[j]
        skin, hair = self.looks[j]
        ph = self.phase[j]
        amp = min(v / 6.0, 1.0) * 0.17
        swing = math.sin(ph) * amp * lateral
        lift = max(0.0, math.cos(ph)) * amp * 0.25
        lift2 = max(0.0, -math.cos(ph)) * amp * 0.25
        knee_fwd = 0.03 * (1 if lateral >= 0 else -1) * min(v / 6.0, 1.0)
        th = max(1, int(round(0.075 * h)))
        sh = 4

        def poly(pts: list[np.ndarray], colour, closed=True) -> None:
            arr = (np.array(pts) * 16).astype(np.int32)
            if closed:
                cv2.fillPoly(img, [arr], colour, cv2.LINE_AA, sh)
            else:
                cv2.polylines(img, [arr], False, colour, th, cv2.LINE_AA, sh)

        # Shadow.
        _shadow(img, foot, (max(2.0, 0.2 * h), max(1.0, 0.05 * h)), 0.3)

        legs = [(-0.045, swing, lift), (0.045, -swing, lift2)]
        pts_all = []
        for k, (hx, sw, lf) in enumerate(legs):
            hip = pt(hx, 0.47)
            knee = pt(hx + sw * 0.5 + knee_fwd, 0.25 + lf * 0.5)
            ankle = pt(hx * 1.3 + sw, 0.03 + lf)
            shade = 0.85 if k == 0 else 1.0
            poly([hip, knee], _shade(skin, shade), closed=False)
            poly([knee, ankle], _shade(socks, shade), closed=False)
            boot = ankle + side * 0.035 * h * (1 if lateral >= 0 else -1)
            cv2.line(
                img,
                tuple((ankle * 16).astype(int)),
                tuple((boot * 16).astype(int)),
                (25, 25, 25),
                th,
                cv2.LINE_AA,
                sh,
            )
            pts_all += [ankle, boot, knee]
        # Shorts and shirt.
        poly([pt(-0.075, 0.55), pt(0.075, 0.55), pt(0.085, 0.42), pt(-0.085, 0.42)], shorts)
        torso = [pt(-0.085, 0.555), pt(0.085, 0.555), pt(0.11, 0.81), pt(-0.11, 0.81)]
        poly(torso, shirt)
        poly([pt(0.02, 0.56), pt(0.085, 0.56), pt(0.11, 0.80), pt(0.04, 0.80)], _shade(shirt, 0.8))
        # Arms swing against the legs.
        for s, sw in ((-1, -swing), (1, swing)):
            sho = pt(s * 0.115, 0.79)
            elb = pt(s * 0.14 + sw * 0.3, 0.64)
            hand = pt(s * 0.13 + sw * 0.6, 0.5)
            poly([sho, elb], shirt, closed=False)
            poly([elb, hand], skin, closed=False)
            pts_all += [hand, sho]
        # Neck and head; the face shows when the player faces the camera.
        r = 0.062 * h
        c = pt(0.0, 0.91)
        cv2.circle(img, tuple((c * 16).astype(int)), int(r * 16), skin, -1, cv2.LINE_AA, sh)
        hair_c = c + upv * r * (0.35 if to_cam > 0 else 0.1)
        cv2.circle(
            img, tuple((hair_c * 16).astype(int)), int(r * 0.85 * 16), hair, -1, cv2.LINE_AA, sh
        )
        pts_all += [c + upv * r, c - side * r, c + side * r, pt(-0.12, 0.8), pt(0.12, 0.8)]
        arr = np.array(pts_all)
        x0, y0 = arr.min(0)
        x1, y1 = arr.max(0)
        return [float(x0) - 1, float(y0) - 1, float(x1) + 1, float(max(y1, foot[1])) + 1]


def _shadow(img: np.ndarray, centre, axes, alpha: float) -> None:
    """Darken an ellipse on the ground, touching only its bounding box."""
    cx, cy = centre
    ax, ay = int(math.ceil(axes[0])), int(math.ceil(axes[1]))
    x0, y0 = max(0, int(cx) - ax - 1), max(0, int(cy) - ay - 1)
    x1, y1 = min(img.shape[1], int(cx) + ax + 2), min(img.shape[0], int(cy) + ay + 2)
    if x1 <= x0 or y1 <= y0:
        return
    mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.ellipse(mask, (int(cx) - x0, int(cy) - y0), (ax, ay), 0, 0, 360, 255, -1, cv2.LINE_AA)
    roi = img[y0:y1, x0:x1].astype(np.float32)
    roi *= 1 - alpha * (mask.astype(np.float32) / 255)[:, :, None]
    img[y0:y1, x0:x1] = roi.astype(np.uint8)


def _visible_fraction(box: list[float] | None, w: int, h: int) -> float:
    if not box:
        return 0.0
    x0, y0, x1, y1 = box
    area = max(1e-6, (x1 - x0) * (y1 - y0))
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    return max(0.0, cx1 - cx0) * max(0.0, cy1 - cy0) / area
