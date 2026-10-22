"""Pinhole broadcast camera in pitch metres.

World axes follow ``frame.schema.json``: origin at the centre spot, x along the long axis,
y across, z up. Image axes: u right, v down. The main broadcast camera sits on a gantry
behind the -y touchline and pans and tilts to follow play.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Camera:
    position: tuple[float, float, float]
    target: tuple[float, float, float]
    hfov_deg: float
    width: int = 1280
    height: int = 720

    @property
    def focal(self) -> float:
        return (self.width / 2) / math.tan(math.radians(self.hfov_deg) / 2)

    def K(self) -> np.ndarray:
        f = self.focal
        return np.array(
            [[f, 0, self.width / 2], [0, f, self.height / 2], [0, 0, 1]], dtype=np.float64
        )

    def R(self) -> np.ndarray:
        """World-to-camera rotation (rows: camera right, down, forward). No roll."""
        c = np.asarray(self.position, dtype=np.float64)
        fwd = np.asarray(self.target, dtype=np.float64) - c
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        down = np.cross(fwd, right)
        return np.stack([right, down, fwd])

    def P(self) -> np.ndarray:
        """3x4 projection matrix."""
        R = self.R()
        t = -R @ np.asarray(self.position, dtype=np.float64)
        return self.K() @ np.hstack([R, t[:, None]])

    def ground_homography(self) -> np.ndarray:
        """3x3 homography from pitch (x, y, z=0) to image pixels."""
        P = self.P()
        return P[:, [0, 1, 3]]

    def project(self, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Project (N, 3) world points. Returns (N, 2) pixels and (N,) depth in metres."""
        pts = np.atleast_2d(np.asarray(pts, dtype=np.float64))
        h = np.hstack([pts, np.ones((len(pts), 1))]) @ self.P().T
        depth = h[:, 2]
        return h[:, :2] / depth[:, None], depth


def image_to_pitch(H_pitch_to_img: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Map (N, 2) image pixels on the ground plane to pitch metres."""
    uv = np.atleast_2d(np.asarray(uv, dtype=np.float64))
    h = np.hstack([uv, np.ones((len(uv), 1))]) @ np.linalg.inv(H_pitch_to_img).T
    return h[:, :2] / h[:, 2:3]
