"""Multi-object tracking metrics: HOTA (as in TrackEval), CLEAR MOTA and IDF1.

Input is a list of frames; each frame holds ground-truth ids, tracker ids and a
similarity matrix (gt x tracker) in [0, 1]. Similarity is box IoU in the image, or a
GS-HOTA-style localisation score in pitch metres (``pitch_similarity``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

ALPHAS = np.arange(0.05, 0.96, 0.05)
EPS = np.finfo(float).eps


@dataclass
class FrameData:
    gt_ids: np.ndarray  # (G,) int
    tr_ids: np.ndarray  # (T,) int
    sim: np.ndarray  # (G, T) float


def box_iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU between (G, 4) and (T, 4) boxes as x0, y0, x1, y1."""
    a = np.asarray(a, float).reshape(-1, 4)
    b = np.asarray(b, float).reshape(-1, 4)
    ix0 = np.maximum(a[:, None, 0], b[None, :, 0])
    iy0 = np.maximum(a[:, None, 1], b[None, :, 1])
    ix1 = np.minimum(a[:, None, 2], b[None, :, 2])
    iy1 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(ix1 - ix0, 0, None) * np.clip(iy1 - iy0, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / np.maximum(union, EPS), 0.0)


def pitch_similarity(gt_xy: np.ndarray, tr_xy: np.ndarray, tau: float = 5.0) -> np.ndarray:
    """GS-HOTA localisation: exp(ln(0.05) d^2 / tau^2), so 5 m apart scores 0.05."""
    gt_xy = np.asarray(gt_xy, float).reshape(-1, 2)
    tr_xy = np.asarray(tr_xy, float).reshape(-1, 2)
    d2 = ((gt_xy[:, None, :] - tr_xy[None, :, :]) ** 2).sum(-1)
    return np.exp(np.log(0.05) * d2 / tau**2)


def _remap(frames: list[FrameData]) -> tuple[list[FrameData], int, int]:
    gts = sorted({int(i) for f in frames for i in f.gt_ids})
    trs = sorted({int(i) for f in frames for i in f.tr_ids})
    gm = {g: k for k, g in enumerate(gts)}
    tm = {t: k for k, t in enumerate(trs)}
    out = [
        FrameData(
            np.array([gm[int(i)] for i in f.gt_ids], int),
            np.array([tm[int(i)] for i in f.tr_ids], int),
            np.asarray(f.sim, float).reshape(len(f.gt_ids), len(f.tr_ids)),
        )
        for f in frames
    ]
    return out, len(gts), len(trs)


def hota(frames: list[FrameData]) -> dict[str, float]:
    frames, ng, nt = _remap(frames)
    gt_count = np.zeros(ng)
    tr_count = np.zeros(nt)
    potential = np.zeros((ng, nt))
    n_gt_dets = n_tr_dets = 0
    for f in frames:
        n_gt_dets += len(f.gt_ids)
        n_tr_dets += len(f.tr_ids)
        gt_count[f.gt_ids] += 1
        tr_count[f.tr_ids] += 1
        if f.sim.size:
            denom = f.sim.sum(0)[None, :] + f.sim.sum(1)[:, None] - f.sim
            potential[np.ix_(f.gt_ids, f.tr_ids)] += np.where(
                denom > EPS, f.sim / np.maximum(denom, EPS), 0
            )
    gas = potential / np.maximum(gt_count[:, None] + tr_count[None, :] - potential, EPS)

    tp = np.zeros(len(ALPHAS))
    matches = np.zeros((len(ALPHAS), ng, nt))
    loc = np.zeros(len(ALPHAS))
    for f in frames:
        if not f.sim.size:
            continue
        score = gas[np.ix_(f.gt_ids, f.tr_ids)] * f.sim
        r, c = linear_sum_assignment(-score)
        for a, alpha in enumerate(ALPHAS):
            ok = f.sim[r, c] >= alpha - EPS
            rr, cc = r[ok], c[ok]
            tp[a] += ok.sum()
            loc[a] += f.sim[rr, cc].sum()
            matches[a, f.gt_ids[rr], f.tr_ids[cc]] += 1
    fn = n_gt_dets - tp
    fp = n_tr_dets - tp
    det_a = tp / np.maximum(tp + fn + fp, EPS)
    ass_a = np.zeros(len(ALPHAS))
    for a in range(len(ALPHAS)):
        m = matches[a]
        a_score = m / np.maximum(gt_count[:, None] + tr_count[None, :] - m, EPS)
        ass_a[a] = (m * a_score).sum() / max(tp[a], 1)
    h = np.sqrt(det_a * ass_a)
    loc_a = loc / np.maximum(tp, EPS)
    return {
        "HOTA": float(h.mean()),
        "DetA": float(det_a.mean()),
        "AssA": float(ass_a.mean()),
        "LocA": float(loc_a.mean()),
        "HOTA(0)": float(h[0]),
    }


def clear_and_id(frames: list[FrameData], threshold: float = 0.5) -> dict[str, float]:
    """CLEAR MOT (MOTA, MOTP, ID switches) and identity metrics (IDF1) at one threshold."""
    frames, ng, nt = _remap(frames)
    n_gt = n_tr = tp = fp = fn = idsw = 0
    sim_sum = 0.0
    prev_match = np.full(ng, -1)
    last_match = np.full(ng, -1)
    pair_hits = np.zeros((ng, nt))
    gt_count = np.zeros(ng)
    tr_count = np.zeros(nt)
    for f in frames:
        n_gt += len(f.gt_ids)
        n_tr += len(f.tr_ids)
        gt_count[f.gt_ids] += 1
        tr_count[f.tr_ids] += 1
        if f.sim.size:
            pair_hits[np.ix_(f.gt_ids, f.tr_ids)] += f.sim >= threshold - EPS
        cur = np.full(ng, -1)
        if f.sim.size:
            keep = (prev_match[f.gt_ids][:, None] == f.tr_ids[None, :]).astype(float)
            score = 1000 * keep + f.sim
            score[f.sim < threshold - EPS] = 0
            r, c = linear_sum_assignment(-score)
            ok = score[r, c] > 0
            r, c = r[ok], c[ok]
            g, t = f.gt_ids[r], f.tr_ids[c]
            idsw += int(((last_match[g] >= 0) & (last_match[g] != t)).sum())
            last_match[g] = t
            cur[g] = t
            tp += len(r)
            sim_sum += float(f.sim[r, c].sum())
        prev_match = cur
    fn = n_gt - tp
    fp = n_tr - tp
    # IDF1: one global gt-to-track assignment.
    if pair_hits.size:
        fn_mat = gt_count[:, None] - pair_hits
        fp_mat = tr_count[None, :] - pair_hits
        cost = np.zeros((ng + nt, nt + ng))
        cost[:ng, :nt] = fn_mat + fp_mat
        cost[:ng, nt:] = 1e9
        cost[np.arange(ng), nt + np.arange(ng)] = gt_count
        cost[ng:, :nt] = 1e9
        cost[ng + np.arange(nt), np.arange(nt)] = tr_count
        r, c = linear_sum_assignment(cost)
        idfn = sum(cost[i, j] for i, j in zip(r, c, strict=True) if i < ng and j >= nt)
        idfp = sum(cost[i, j] for i, j in zip(r, c, strict=True) if i >= ng and j < nt)
        matched = [(i, j) for i, j in zip(r, c, strict=True) if i < ng and j < nt]
        idfn += sum(fn_mat[i, j] for i, j in matched)
        idfp += sum(fp_mat[i, j] for i, j in matched)
        idtp = n_gt - idfn
    else:
        idtp, idfn, idfp = 0, n_gt, n_tr
    return {
        "MOTA": 1 - (fn + fp + idsw) / max(n_gt, 1),
        "MOTP": sim_sum / max(tp, 1),
        "IDF1": 2 * idtp / max(n_gt + n_tr, 1),
        "IDSW": float(idsw),
        "TP": float(tp),
        "FP": float(fp),
        "FN": float(fn),
        "Recall": tp / max(n_gt, 1),
        "Precision": tp / max(n_tr, 1),
        "GT_IDs": float(ng),
        "Track_IDs": float(nt),
    }
