"""Spike S5, GPU half: RF-DETR-S detections + ByteTrack -> ``tracks.jsonl``.

Runs in the separate GPU venv (see ``requirements.txt``), never in CI:

    ~/.cache/chalktalk/vision-gpu/bin/python vision/gpu/run_s5.py \\
        --video scripts/render/out/demo/clip.mp4 --out scripts/render/out/demo/tracks.jsonl

Each line is ``{frame, people: [{id, box, score}], balls: [{box, score}]}`` with boxes in
image pixels (x1, y1, x2, y2). The CPU half (``python -m chalktalk_vision.s5 --tracks``)
calibrates, classifies kits and projects to pitch metres. A ``*.stats.json`` next to the
output records throughput and peak GPU memory.
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path

import numpy as np
import supervision as sv
import torch
from rfdetr import RFDETRSmall
from trackers import ByteTrackTracker

warnings.filterwarnings("ignore")

# COCO ids as RF-DETR reports them (91-slot COCO numbering).
PERSON, BALL = 1, 37


def batches(video: Path, size: int, limit: int | None):
    buf = []
    for i, bgr in enumerate(sv.get_video_frames_generator(str(video))):
        if limit is not None and i >= limit:
            break
        buf.append(np.ascontiguousarray(bgr[:, :, ::-1]))
        if len(buf) == size:
            yield buf
            buf = []
    if buf:
        yield buf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--resolution", type=int, default=768, help="square input, multiple of 32")
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--fps", type=float, default=25.0)
    ap.add_argument("--person-th", type=float, default=0.15, help="lowest box fed to ByteTrack")
    ap.add_argument("--ball-th", type=float, default=0.1)
    ap.add_argument("--fp32", action="store_true")
    ap.add_argument("--max-frames", type=int)
    args = ap.parse_args()

    model = RFDETRSmall(resolution=args.resolution)
    if not args.fp32:
        model.inference(compile=False, batch_size=args.batch, dtype=torch.float16, inplace=True)
    tracker = ByteTrackTracker(
        lost_track_buffer=int(args.fps * 2),
        frame_rate=args.fps,
        track_activation_threshold=0.5,
        minimum_consecutive_frames=3,
        high_conf_det_threshold=0.5,
    )

    torch.cuda.reset_peak_memory_stats()
    n = 0
    t_det = 0.0
    t0 = time.perf_counter()
    with args.out.open("w") as out:
        for frames in batches(args.video, args.batch, args.max_frames):
            t = time.perf_counter()
            dets = model.predict(frames, threshold=min(args.person_th, args.ball_th))
            torch.cuda.synchronize()
            t_det += time.perf_counter() - t
            if not isinstance(dets, list):
                dets = [dets]
            for d in dets:
                people = d[(d.class_id == PERSON) & (d.confidence >= args.person_th)]
                people = tracker.update(people)
                ball = d[(d.class_id == BALL) & (d.confidence >= args.ball_th)]
                rec = {
                    "frame": n,
                    "people": [
                        {
                            "id": int(tid),
                            "box": [round(float(v), 1) for v in box],
                            "score": round(float(s), 3),
                        }
                        for box, s, tid in zip(
                            people.xyxy, people.confidence, people.tracker_id, strict=True
                        )
                        if tid is not None and tid >= 0
                    ],
                    "balls": [
                        {"box": [round(float(v), 1) for v in box], "score": round(float(s), 3)}
                        for box, s in sorted(
                            zip(ball.xyxy, ball.confidence, strict=True), key=lambda x: -x[1]
                        )[:3]
                    ],
                }
                out.write(json.dumps(rec) + "\n")
                n += 1
    total = time.perf_counter() - t0
    stats = {
        "model": "rf-detr-small (COCO)",
        "resolution": args.resolution,
        "dtype": "fp32" if args.fp32 else "fp16",
        "batch": args.batch,
        "frames": n,
        "detector_fps": round(n / t_det, 1),
        "end_to_end_fps": round(n / total, 1),
        "peak_gpu_mb": round(torch.cuda.max_memory_allocated() / 2**20),
        "gpu": torch.cuda.get_device_name(0),
    }
    args.out.with_suffix(".stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
