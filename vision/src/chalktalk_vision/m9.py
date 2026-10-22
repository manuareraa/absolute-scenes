"""M9 runner: pitch tracks -> video events, compared with the simulator's events.

    uv run python -m chalktalk_vision.m9 --clip scripts/render/out/demo \\
        --pitch-tracks scripts/render/out/demo/pitch_tracks_detector.jsonl

Writes ``events_video_<tag>.json`` (``event`` contracts, ``source: "video"``) and
``m9_report_<tag>.json`` next to the pitch tracks, ``<tag>`` being ``detector`` or
``oracle``. Track ids are mapped to player ids only for scoring, by majority box overlap
with the ground truth.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from scipy.optimize import linear_sum_assignment

from .events import compare, detect
from .mot import box_iou
from .pitch_tracks import PitchFrame, read_pitch_tracks

# Events no camera can see: they come from officials and the clock, not the pitch.
NOT_VISUAL = {"var_check", "var_decision", "substitution", "period_end", "card"}


def track_to_player(truth_frames: list[dict], pitch: list[PitchFrame]) -> dict[int, str]:
    votes: dict[int, Counter] = defaultdict(Counter)
    for fr, pf in zip(truth_frames, pitch, strict=False):
        gt = [p for p in fr["players"] if p["bbox"]]
        if not gt or not pf.people:
            continue
        iou = box_iou([p["bbox"] for p in gt], [p["box"] for p in pf.people])
        r, c = linear_sum_assignment(-iou)
        for i, j in zip(r, c, strict=True):
            if iou[i, j] >= 0.5:
                votes[pf.people[j]["id"]][gt[i]["id"]] += 1
    return {tid: v.most_common(1)[0][0] for tid, v in votes.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="chalktalk_vision.m9")
    ap.add_argument("--clip", type=Path, required=True, help="renderer output folder")
    ap.add_argument("--pitch-tracks", type=Path, required=True)
    ap.add_argument("--tol-ms", type=int, default=1000)
    args = ap.parse_args(argv)
    clip: Path = args.clip
    truth = json.loads((clip / "truth.json").read_text())
    with (clip / "frames.jsonl").open() as f:
        truth_frames = [json.loads(line) for line in f]
    sim = json.loads((clip / "events.json").read_text())
    pitch = read_pitch_tracks(args.pitch_tracks)

    video = detect(pitch, truth["start_ms"], tuple(truth["camera"]["position"]))
    out = args.pitch_tracks.parent
    tag = args.pitch_tracks.stem.removeprefix("pitch_tracks_")
    (out / f"events_video_{tag}.json").write_text(json.dumps(video, indent=1))
    mapping = track_to_player(truth_frames, pitch)
    visual = [e for e in sim if e["type"] not in NOT_VISUAL]
    report = {
        "pitch_tracks": args.pitch_tracks.name,
        "all_sim_events": compare(video, sim, mapping, args.tol_ms),
        "visual_sim_events": compare(video, visual, mapping, args.tol_ms),
    }
    (out / f"m9_report_{tag}.json").write_text(json.dumps(report, indent=1))
    for e in video:
        print(e["t"], e["type"], e["actors"], e.get("team"), e["confidence"])
    summary = {
        k: {m: v[m] for m in ("precision", "recall", "timing_mae_ms", "actor_accuracy")}
        for k, v in report.items()
        if isinstance(v, dict)
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
