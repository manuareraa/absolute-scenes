"""Score pitch tracks against the renderer's ground truth (``frames.jsonl``).

People whose visible fraction is under ``MIN_VISIBLE`` are "don't care": they are not
counted as misses, and a tracker box on one of them is not counted as a false positive
(the MOTChallenge convention for heavily occluded people).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from .camera import image_to_pitch
from .mot import FrameData, box_iou, clear_and_id, hota, pitch_similarity
from .pitch_tracks import PitchFrame
from .render import kit_key

MIN_VISIBLE = 0.3
BALL_HIT_PX = 8.0


def _gt_people(fr: dict):
    keep, ignore = [], []
    for p in fr["players"]:
        if not p["bbox"] or p["visible"] <= 0:
            continue
        (keep if p["visible"] >= MIN_VISIBLE else ignore).append(p)
    return keep, ignore


def _drop_on_ignored(people: list[dict], keep: list[dict], ignore: list[dict]) -> list[dict]:
    if not people or not ignore:
        return people
    boxes = [p["box"] for p in people]
    iou_ign = box_iou(boxes, [g["bbox"] for g in ignore]).max(1)
    iou_keep = box_iou(boxes, [g["bbox"] for g in keep]).max(1) if keep else np.zeros(len(people))
    return [p for p, a, b in zip(people, iou_ign, iou_keep, strict=True) if not (a >= 0.5 > b)]


def _calib_error(H_gt: np.ndarray, H_fit: np.ndarray, w: int, h: int) -> float:
    """Mean ground distance (m) between the two homographies over on-pitch image points."""
    u, v = np.meshgrid(np.linspace(0, w - 1, 16), np.linspace(h * 0.25, h - 1, 9))
    uv = np.column_stack([u.ravel(), v.ravel()])
    a = image_to_pitch(H_gt, uv)
    on = (np.abs(a[:, 0]) <= 52.5) & (np.abs(a[:, 1]) <= 34)
    if not on.any():
        return float("nan")
    b = image_to_pitch(H_fit, uv[on])
    return float(np.linalg.norm(a[on] - b, axis=1).mean())


def evaluate(truth_frames: list[dict], pred: list[PitchFrame], width: int, height: int) -> dict:
    gid: dict[str, int] = {}
    img_frames, pitch_frames = [], []
    kit_right = kit_total = 0
    pos_err, calib_err = [], []
    ball_gt = ball_hit = ball_pred = 0
    ball_err = []
    for fr, pf in zip(truth_frames, pred, strict=False):
        keep, ignore = _gt_people(fr)
        people = _drop_on_ignored(pf.people, keep, ignore)
        g_ids = np.array([gid.setdefault(g["id"], len(gid)) for g in keep], int)
        t_ids = np.array([p["id"] for p in people], int)
        iou = box_iou([g["bbox"] for g in keep], [p["box"] for p in people])
        img_frames.append(FrameData(g_ids, t_ids, iou))
        psim = pitch_similarity(
            [[g["x"], g["y"]] for g in keep], [[p["x"], p["y"]] for p in people]
        )
        pitch_frames.append(FrameData(g_ids, t_ids, psim))
        if iou.size:
            r, c = linear_sum_assignment(-iou)
            for i, j in zip(r, c, strict=True):
                if iou[i, j] < 0.5:
                    continue
                g, p = keep[i], people[j]
                kit_total += 1
                kit_right += p.get("track_kit") == kit_key(g["team"], g["role"])
                pos_err.append(np.hypot(p["x"] - g["x"], p["y"] - g["y"]))
        calib_err.append(_calib_error(np.array(fr["H"]), np.array(pf.H), width, height))

        b = fr["ball"]
        ball_pred += pf.ball is not None
        if b["bbox"] and b["visible"] >= 0.5:
            ball_gt += 1
            if pf.ball is not None:
                gc = np.array(
                    [(b["bbox"][0] + b["bbox"][2]) / 2, (b["bbox"][1] + b["bbox"][3]) / 2]
                )
                pb = pf.ball["box"]
                pc = np.array([(pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2])
                if np.linalg.norm(gc - pc) <= BALL_HIT_PX * width / 1280:
                    ball_hit += 1
                    if b["z"] < 0.5:
                        ball_err.append(np.hypot(pf.ball["x"] - b["x"], pf.ball["y"] - b["y"]))

    img_h = hota(img_frames)
    img_c = clear_and_id(img_frames)
    pitch_h = hota(pitch_frames)
    pitch_c = clear_and_id(pitch_frames, threshold=pitch_similarity([[0, 0]], [[1, 0]])[0, 0])
    ce = np.array([e for e in calib_err if np.isfinite(e)])
    return {
        "frames": len(img_frames),
        "people_image": {**_r(img_h), **_r(img_c)},
        "people_pitch": {
            **_r(pitch_h),
            "MOTA@1m": _r1(pitch_c["MOTA"]),
            "IDF1@1m": _r1(pitch_c["IDF1"]),
        },
        "position_error_m": _stats(pos_err),
        "calibration_error_m": _stats(ce),
        "kit_accuracy": _r1(kit_right / max(kit_total, 1)),
        "ball": {
            "gt_frames": ball_gt,
            "pred_frames": ball_pred,
            "recall": _r1(ball_hit / max(ball_gt, 1)),
            "precision": _r1(ball_hit / max(ball_pred, 1)),
            "ground_error_m": _stats(ball_err),
        },
    }


def _r1(v: float) -> float:
    return round(float(v), 4)


def _r(d: dict) -> dict:
    return {k: _r1(v) for k, v in d.items()}


def _stats(v) -> dict:
    v = np.asarray(v, float)
    if not v.size:
        return {"n": 0}
    return {
        "n": int(v.size),
        "mean": _r1(v.mean()),
        "median": _r1(np.median(v)),
        "p95": _r1(np.percentile(v, 95)),
    }
