"""Camera calibration from pitch lines: per-frame pan, tilt and zoom.

The gantry position is surveyed once (it never moves during a broadcast); everything
else comes from the image. Each frame we find white line pixels on grass, build a
distance transform, and fit the aim point and field of view so the projected pitch
markings land on the lines. Frame 0 starts from a coarse grid search; later frames start
from the previous solution. Player boxes are masked out (white shorts look like lines).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from scipy.optimize import minimize

from .camera import Camera
from .render import pitch_lines

DT_CAP = 12.0
# The broadcast lens zoom range (degrees of horizontal field of view).
HFOV_RANGE = (18.0, 40.0)


def template_points(step: float = 0.5) -> np.ndarray:
    """Pitch markings sampled every ``step`` metres, as (N, 3) points on the ground."""
    out = []
    for pl in pitch_lines():
        for a, b in zip(pl[:-1], pl[1:], strict=True):
            n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
            t = np.linspace(0, 1, n, endpoint=False)[:, None]
            out.append(a + (b - a) * t)
    pts = np.concatenate(out)
    return np.column_stack([pts, np.zeros(len(pts))])


def line_mask(img: np.ndarray, boxes: np.ndarray | None = None) -> np.ndarray:
    """White, unsaturated pixels next to grass, with person boxes removed."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    grass = ((h > 35) & (h < 85) & (s > 60)).astype(np.uint8)
    near_grass = cv2.dilate(grass, np.ones((7, 7), np.uint8)) > 0
    white = (s < 70) & (v > 170)
    mask = (white & near_grass).astype(np.uint8)
    if boxes is not None:
        for x0, y0, x1, y1 in np.asarray(boxes, int).reshape(-1, 4):
            mask[max(0, y0 - 2) : y1 + 3, max(0, x0 - 2) : x1 + 3] = 0
    return mask


@dataclass
class PTZ:
    tx: float
    ty: float
    hfov: float

    def camera(self, position, width: int, height: int) -> Camera:
        return Camera(
            position=position,
            target=(self.tx, self.ty, 0.0),
            hfov_deg=self.hfov,
            width=width,
            height=height,
        )


class LineCalibrator:
    def __init__(self, position: tuple[float, float, float], width: int, height: int):
        self.position = position
        self.width = width
        self.height = height
        self.pts = template_points()
        self.prev: PTZ | None = None

    def _cost_fn(self, dt: np.ndarray):
        W, H = self.width, self.height
        pts_h = np.hstack([self.pts, np.ones((len(self.pts), 1))])

        def cost(theta: np.ndarray) -> float:
            tx, ty, hfov = theta
            if not (HFOV_RANGE[0] < hfov < HFOV_RANGE[1]):
                return 1e3
            P = PTZ(tx, ty, hfov).camera(self.position, W, H).P()
            q = pts_h @ P.T
            uv = q[:, :2] / q[:, 2:3]
            ok = (
                (q[:, 2] > 0)
                & (uv[:, 0] >= 0)
                & (uv[:, 0] < W - 1)
                & (uv[:, 1] >= 0)
                & (uv[:, 1] < H - 1)
            )
            n = int(ok.sum())
            if n < 40:
                return DT_CAP * 2
            u, v = uv[ok, 0], uv[ok, 1]
            u0, v0 = u.astype(int), v.astype(int)
            fu, fv = u - u0, v - v0
            d = (
                dt[v0, u0] * (1 - fu) * (1 - fv)
                + dt[v0, u0 + 1] * fu * (1 - fv)
                + dt[v0 + 1, u0] * (1 - fu) * fv
                + dt[v0 + 1, u0 + 1] * fu * fv
            )
            return float(d.mean())

        return cost

    def fit(self, img: np.ndarray, boxes: np.ndarray | None = None) -> tuple[PTZ, float]:
        """Fit one frame. Returns the PTZ and the mean line distance in pixels."""
        mask = line_mask(img, boxes)
        dt = cv2.distanceTransform((1 - mask).astype(np.uint8), cv2.DIST_L2, 3)
        dt = np.minimum(dt, DT_CAP).astype(np.float64)
        cost = self._cost_fn(dt)
        if self.prev is None:
            grid = [
                (tx, ty, f)
                for tx in np.arange(-40, 41, 3.0)
                for ty in np.arange(-10, 17, 3.0)
                for f in (20.0, 23.0, 26.0, 29.0, 33.0)
            ]
            costs = [cost(np.array(g)) for g in grid]
            starts = [np.array(grid[i]) for i in np.argsort(costs)[:5]]
        else:
            starts = [np.array([self.prev.tx, self.prev.ty, self.prev.hfov])]
        best = None
        for x0 in starts:
            res = minimize(
                cost,
                x0,
                method="Nelder-Mead",
                options={
                    "xatol": 1e-3,
                    "fatol": 1e-4,
                    "maxiter": 400,
                    "initial_simplex": _simplex(x0),
                },
            )
            if best is None or res.fun < best.fun:
                best = res
        ptz = PTZ(*map(float, best.x))
        self.prev = ptz
        return ptz, float(best.fun)


def _simplex(x0: np.ndarray) -> np.ndarray:
    steps = np.array([1.5, 1.5, 0.8])
    return np.vstack([x0] + [x0 + np.eye(3)[i] * steps[i] for i in range(3)])
