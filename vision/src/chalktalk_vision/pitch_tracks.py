"""CPU stage: image tracks -> pitch tracks in metres, with team and role.

Input is what the GPU stage writes (``tracks.jsonl``): per frame, tracked person boxes and
ball candidates in pixels. For each frame we fit the camera from the pitch lines (person
boxes masked out), read each person's shirt colour, and project the bottom-centre of the
box (the feet) onto the ground plane. Each track then takes its majority kit, which gives
its team and its class (player, goalkeeper or referee).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .calib import LineCalibrator
from .camera import image_to_pitch
from .kits import KIT_LABELS, classify, shirt_colour, vote


@dataclass
class PitchFrame:
    index: int
    ptz: tuple[float, float, float]
    calib_cost: float
    H: list[list[float]]
    people: list[dict] = field(default_factory=list)
    ball: dict | None = None


def read_tracks(path: Path) -> list[dict]:
    with Path(path).open() as f:
        return [json.loads(line) for line in f if line.strip()]


def video_frames(path: Path) -> Iterator[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    try:
        while True:
            ok, img = cap.read()
            if not ok:
                return
            yield img
    finally:
        cap.release()


def _feet(box) -> tuple[float, float]:
    x0, _, x1, y1 = box
    return (x0 + x1) / 2, y1


# Ball gating, in pixels at 1280 wide. A COCO detector also fires, weakly, on the penalty
# and centre spots, so a weak candidate is only taken near where the ball just was.
GATE_PX, GATE_STEP_PX, GATE_MAX_PX = 40.0, 12.0, 160.0
SHORT_GAP = 6
WEAK, REACQUIRE = 0.3, 0.35


def pick_balls(tracks: list[dict], width: int) -> list[dict | None]:
    """One ball candidate per frame (or None), chosen for continuity with the last one."""
    s = width / 1280
    out: list[dict | None] = []
    last: tuple[np.ndarray, int] | None = None
    for k, tr in enumerate(tracks):
        cands = tr.get("balls", [])
        pick = None
        if last is not None:
            gap = k - last[1]
            r = min(GATE_PX + GATE_STEP_PX * (gap - 1), GATE_MAX_PX) * s
            near = [
                c
                for c in cands
                if np.hypot(*(np.array(_feet(c["box"])) - last[0])) <= r
                and (gap <= SHORT_GAP or c["score"] >= WEAK)
            ]
            if near:
                pick = max(near, key=lambda c: c["score"])
        if pick is None:
            strong = [c for c in cands if c["score"] >= REACQUIRE]
            pick = max(strong, key=lambda c: c["score"]) if strong else None
        if pick is not None:
            last = (np.array(_feet(pick["box"])), k)
        out.append(pick)
    return out


def to_pitch(
    images: Iterable[np.ndarray],
    tracks: list[dict],
    camera_position: tuple[float, float, float],
    width: int,
    height: int,
) -> list[PitchFrame]:
    """Calibrate every frame, project people and the ball, and label each track's kit."""
    cal = LineCalibrator(camera_position, width, height)
    picks = pick_balls(tracks, width)
    out: list[PitchFrame] = []
    kit_votes: dict[int, list[str | None]] = defaultdict(list)
    for img, tr in zip(images, tracks, strict=False):
        people = tr.get("people", [])
        boxes = np.array([p["box"] for p in people], float).reshape(-1, 4)
        ptz, cost = cal.fit(img, boxes)
        H = ptz.camera(camera_position, width, height).ground_homography()
        pf = PitchFrame(tr["frame"], (ptz.tx, ptz.ty, ptz.hfov), cost, H.tolist())
        if len(people):
            xy = image_to_pitch(H, np.array([_feet(p["box"]) for p in people]))
            for p, (x, y) in zip(people, xy, strict=True):
                kit, kconf = classify(shirt_colour(img, p["box"]))
                kit_votes[p["id"]].append(kit)
                pf.people.append(
                    {
                        "id": p["id"],
                        "box": p["box"],
                        "score": p.get("score", 1.0),
                        "x": float(x),
                        "y": float(y),
                        "kit": kit,
                        "kit_conf": kconf,
                    }
                )
        b = picks[len(out)] if len(out) < len(picks) else None
        if b is not None:
            (bx, by) = image_to_pitch(H, np.array([_feet(b["box"])]))[0]
            pf.ball = {"box": b["box"], "score": b["score"], "x": float(bx), "y": float(by)}
        out.append(pf)
    labels = {tid: vote(v) for tid, v in kit_votes.items()}
    for pf in out:
        for p in pf.people:
            kit, share = labels[p["id"]]
            team, cls = KIT_LABELS[kit] if kit else (None, "player")
            p.update(team=team, cls=cls, track_kit=kit, track_kit_share=share)
    return out


def write_pitch_tracks(path: Path, frames: list[PitchFrame]) -> None:
    with Path(path).open("w") as f:
        for pf in frames:
            f.write(json.dumps(pf.__dict__, separators=(",", ":")) + "\n")


def read_pitch_tracks(path: Path) -> list[PitchFrame]:
    with Path(path).open() as f:
        return [PitchFrame(**json.loads(line)) for line in f if line.strip()]
