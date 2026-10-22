"""Spike S5, CPU half: tracks.jsonl -> pitch tracks -> scores against ground truth.

    uv run python -m chalktalk_vision.s5 --clip scripts/render/out/demo \\
        --tracks scripts/render/out/demo/tracks.jsonl

``--oracle`` builds the tracks from the ground-truth boxes instead, which isolates the
CPU stage (calibration, kits, projection) from detector and tracker errors.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .evaluate import evaluate
from .pitch_tracks import read_tracks, to_pitch, video_frames, write_pitch_tracks


def oracle_tracks(truth_frames: list[dict], track_ids: dict[str, int]) -> list[dict]:
    out = []
    for k, fr in enumerate(truth_frames):
        people = [
            {"id": track_ids[p["id"]], "box": p["bbox"], "score": 1.0}
            for p in fr["players"]
            if p["bbox"] and p["visible"] >= 0.3
        ]
        b = fr["ball"]
        balls = [{"box": b["bbox"], "score": 1.0}] if b["bbox"] and b["visible"] >= 0.5 else []
        out.append({"frame": k, "people": people, "balls": balls})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="chalktalk_vision.s5")
    ap.add_argument("--clip", type=Path, required=True, help="renderer output folder")
    ap.add_argument("--tracks", type=Path, help="GPU stage output (tracks.jsonl)")
    ap.add_argument("--oracle", action="store_true", help="use ground-truth boxes as tracks")
    ap.add_argument("--out", type=Path, help="defaults to the clip folder")
    args = ap.parse_args(argv)
    clip: Path = args.clip
    out: Path = args.out or clip
    truth = json.loads((clip / "truth.json").read_text())
    with (clip / "frames.jsonl").open() as f:
        truth_frames = [json.loads(line) for line in f]
    if args.oracle:
        tracks, tag = oracle_tracks(truth_frames, truth["track_ids"]), "oracle"
    elif args.tracks:
        tracks, tag = read_tracks(args.tracks), "detector"
    else:
        ap.error("pass --tracks or --oracle")

    t0 = time.perf_counter()
    pitch = to_pitch(
        video_frames(clip / "clip.mp4"),
        tracks,
        tuple(truth["camera"]["position"]),
        truth["width"],
        truth["height"],
    )
    cpu_s = time.perf_counter() - t0
    write_pitch_tracks(out / f"pitch_tracks_{tag}.jsonl", pitch)
    metrics = evaluate(truth_frames, pitch, truth["width"], truth["height"])
    metrics["cpu_stage_fps"] = round(len(pitch) / cpu_s, 1)
    metrics["tracks"] = tag
    (out / f"metrics_{tag}.json").write_text(json.dumps(metrics, indent=1))
    print(json.dumps(metrics, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
