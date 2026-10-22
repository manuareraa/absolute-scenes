"""Build the web's show fixture from a crew cache (``python -m chalktalk_crew run``).

Shows come from ``chalktalk_postmatch.build_shows`` over the cached, gate-passed overlays.
Frames are the seeded sim match, cut to a window round each moment so the file stays small.
Audio stays where the crew wrote it; ``audio_url`` is relative to the fixture's folder.
With ``--queue`` it also writes the producer console's queue: every cached overlay (approval
untouched, rejected ones included) with the frame at each moment.

    uv run python web/scripts/show_fixture.py --cache .chalktalk-cache --half-minutes 6 \
        --out web/public/fixtures/show-sim-7.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from chalktalk_postmatch.show import build_shows
from chalktalk_sim import DEMO_BEATS, MatchConfig, simulate
from chalktalk_sim.match import FRAME_MS

PRE_MS = 4000
POST_MS = 1000
STEP = 2  # every other frame: 12.5 fps is plenty for the pre-roll


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--half-minutes", type=float, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--queue", type=Path)
    args = p.parse_args()

    match = simulate(MatchConfig(seed=args.seed, half_minutes=args.half_minutes, beats=DEMO_BEATS))
    digest = match.digest()[:8]
    roots = [d for d in args.cache.iterdir() if d.name.endswith(f"-{digest}")]
    if len(roots) != 1:
        raise SystemExit(f"no cache folder for digest {digest} in {args.cache}")
    root = roots[0]
    match_id = root.name.removesuffix(f"-{digest}")

    overlays = [json.loads(f.read_text()) for f in sorted((root / "overlays").glob("*.json"))]
    rejected = [json.loads(f.read_text()) for f in sorted((root / "rejected").glob("*.json"))]
    shows = build_shows(overlays, match_id=match_id)

    keep: set[int] = set()
    for t in {o["match_tc"] for o in overlays}:
        first = max(0, (t - PRE_MS) // FRAME_MS)
        keep.update(range(first, (t + POST_MS) // FRAME_MS + 1, STEP))
    frames = [match.frame(i) for i in sorted(keep) if i < match.n_frames]

    out = {"match_id": match_id, "fps": 1000 // FRAME_MS, "frames": frames, "shows": shows}
    args.out.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{args.out}: {len(shows)} shows, {len(frames)} frames, {args.out.stat().st_size} B")

    if args.queue:
        queued = overlays + rejected
        moments = sorted({o["match_tc"] for o in queued})
        q = {
            "match_id": match_id,
            "overlays": queued,
            "frames": [match.frame(match.tick(t)) for t in moments],
        }
        args.queue.write_text(json.dumps(q, separators=(",", ":")))
        print(f"{args.queue}: {len(queued)} overlays, {args.queue.stat().st_size} B")


if __name__ == "__main__":
    main()
