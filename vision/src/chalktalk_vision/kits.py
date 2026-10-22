"""Team and role from shirt colour.

The broadcaster knows both kits, the goalkeepers' kits and the referee's before kick-off,
so each person box is labelled by its nearest shirt colour in Lab space. A track takes
the majority label over its frames.
"""

from __future__ import annotations

from collections import Counter

import cv2
import numpy as np

from .render import _HEX, _bgr

# kit key -> (team, class)
KIT_LABELS = {
    "home": ("home", "player"),
    "away": ("away", "player"),
    "home_gk": ("home", "goalkeeper"),
    "away_gk": ("away", "goalkeeper"),
    "ref": ("ref", "referee"),
}


def _lab(bgr: np.ndarray) -> np.ndarray:
    px = np.asarray(bgr, np.uint8).reshape(-1, 1, 3)
    return cv2.cvtColor(px, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)


KIT_KEYS = list(KIT_LABELS)
KIT_LAB = _lab(np.array([_bgr(_HEX[k][0]) for k in KIT_KEYS]))


def shirt_colour(img: np.ndarray, box) -> np.ndarray | None:
    """Median BGR of non-grass pixels in the torso band of a person box."""
    x0, y0, x1, y1 = (float(v) for v in box)
    h, w = y1 - y0, x1 - x0
    if h < 6 or w < 3:
        return None
    ty0, ty1 = int(y0 + 0.18 * h), int(y0 + 0.42 * h)
    tx0, tx1 = int(x0 + 0.25 * w), int(np.ceil(x1 - 0.25 * w))
    H, W = img.shape[:2]
    crop = img[max(0, ty0) : min(H, ty1), max(0, tx0) : min(W, tx1)]
    if crop.size == 0:
        return None
    px = crop.reshape(-1, 3)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    grass = (hsv[:, 0] > 35) & (hsv[:, 0] < 85) & (hsv[:, 1] > 60) & (hsv[:, 2] < 200)
    keep = px[~grass]
    if len(keep) < 3:
        return None
    return np.median(keep, axis=0)


def classify(colour: np.ndarray | None) -> tuple[str | None, float]:
    """Nearest kit key and a confidence from the margin to the runner-up."""
    if colour is None:
        return None, 0.0
    d = np.linalg.norm(KIT_LAB - _lab(colour)[0], axis=1)
    order = np.argsort(d)
    best, second = d[order[0]], d[order[1]]
    conf = float(np.clip((second - best) / max(second, 1e-6), 0, 1))
    return KIT_KEYS[order[0]], conf


def vote(labels: list[str | None]) -> tuple[str | None, float]:
    seen = [k for k in labels if k]
    if not seen:
        return None, 0.0
    key, n = Counter(seen).most_common(1)[0]
    return key, n / len(seen)
