"""Render a broadcast-angle clip of a seeded synthetic match, with exact ground truth.

    uv run python scripts/render/render_clip.py --out scripts/render/out/demo

Writes into ``--out`` (git-ignored by default):
  clip.mp4        H.264 video (needs ffmpeg on PATH; ``--no-video`` skips it)
  truth.json      clip metadata, lineup, kits
  frames.jsonl    per frame: camera P, pitch-to-image homography H, every person's pitch
                  position, pixel box and visible fraction, the ball
  gt.txt          MOTChallenge-style boxes (frame, id, x, y, w, h, 1, class, visibility)
  events.json     the simulator's events inside the window (the auto-eventing truth)
  preview.jpg     the middle frame

CPU only. The default window holds a home goal (seed 7, 10-minute halves, demo beats).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
from chalktalk_core.geometry import FRAME_MS
from chalktalk_sim.director import DEMO_BEATS, MatchConfig, simulate
from chalktalk_vision.render import ClipSpec, Renderer

BALL_ID = 100
CLASSES = {"player": 1, "goalkeeper": 2, "referee": 3, "ball": 4}


def person_class(team: str, role: str) -> int:
    if team == "ref":
        return CLASSES["referee"]
    return CLASSES["goalkeeper"] if role == "GK" else CLASSES["player"]


def _ffmpeg(out: Path, w: int, h: int, fps: int) -> subprocess.Popen:
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
    ]  # fmt: skip
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="render_clip")
    ap.add_argument("--out", type=Path, default=Path("scripts/render/out/demo"))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--half-minutes", type=float, default=10.0)
    ap.add_argument("--no-demo", action="store_true", help="drop the scripted demo beats")
    ap.add_argument("--start", type=float, default=225.0, help="window start, match seconds")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--no-video", action="store_true")
    args = ap.parse_args(argv)

    beats = () if args.no_demo else DEMO_BEATS
    match = simulate(MatchConfig(seed=args.seed, half_minutes=args.half_minutes, beats=beats))
    spec = ClipSpec(
        start_ms=int(args.start * 1000),
        seconds=args.seconds,
        width=args.width,
        height=args.height,
        seed=args.seed,
    )
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    fps = 1000 // FRAME_MS
    video = None
    if not args.no_video:
        if not shutil.which("ffmpeg"):
            print("ffmpeg not found; use --no-video", file=sys.stderr)
            return 2
        video = _ffmpeg(out / "clip.mp4", spec.width, spec.height, fps)

    renderer = Renderer(match, spec)
    ids = {p.id: k + 1 for k, p in enumerate(match.lineup)}
    t0 = time.perf_counter()
    end_ms = spec.start_ms
    mid = spec.n_frames // 2
    with (out / "frames.jsonl").open("w") as fj, (out / "gt.txt").open("w") as gt:
        for fr in renderer.frames():
            if video:
                video.stdin.write(fr.image.tobytes())
            if fr.index == mid:
                cv2.imwrite(str(out / "preview.jpg"), fr.image, [cv2.IMWRITE_JPEG_QUALITY, 90])
            fj.write(json.dumps(fr.truth, separators=(",", ":")) + "\n")
            n = fr.index + 1
            for p in fr.truth["players"]:
                if p["bbox"] and p["visible"] > 0:
                    x0, y0, x1, y1 = p["bbox"]
                    cls = person_class(p["team"], p["role"])
                    row = [n, ids[p["id"]], x0, y0, x1 - x0, y1 - y0, 1, cls, p["visible"]]
                    gt.write(
                        ",".join(f"{v:.1f}" if isinstance(v, float) else str(v) for v in row) + "\n"
                    )
            b = fr.truth["ball"]
            if b["bbox"] and b["visible"] > 0:
                x0, y0, x1, y1 = b["bbox"]
                row = [n, BALL_ID, x0, y0, x1 - x0, y1 - y0, 1, CLASSES["ball"], b["visible"]]
                gt.write(
                    ",".join(f"{v:.1f}" if isinstance(v, float) else str(v) for v in row) + "\n"
                )
            end_ms = fr.t
    if video:
        video.stdin.close()
        video.wait()
    elapsed = time.perf_counter() - t0

    info = match.info()
    truth = {
        "match_id": info["match_id"],
        "seed": args.seed,
        "half_minutes": args.half_minutes,
        "demo_beats": not args.no_demo,
        "digest": match.digest(),
        "start_ms": spec.start_ms,
        "end_ms": end_ms,
        "fps": fps,
        "n_frames": spec.n_frames,
        "width": spec.width,
        "height": spec.height,
        "camera": {"position": spec.camera_pos, "base_hfov_deg": spec.hfov_deg},
        "classes": CLASSES,
        "ball_track_id": BALL_ID,
        "track_ids": ids,
        "lineup": [
            {"id": p.id, "team": p.team, "role": p.role, "number": p.number} for p in match.lineup
        ],
        "teams": {k: {"colours": v["colours"]} for k, v in info["teams"].items()},
        "render_seconds": round(elapsed, 1),
    }
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    events = match.events_between(spec.start_ms, end_ms)
    (out / "events.json").write_text(json.dumps(events, indent=1))
    print(
        json.dumps(
            {
                "out": str(out),
                "frames": spec.n_frames,
                "events": len(events),
                "render_fps": round(spec.n_frames / elapsed, 1),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
