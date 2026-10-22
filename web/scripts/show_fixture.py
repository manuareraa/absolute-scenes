"""Build the web's show fixture from a crew cache (``python -m chalktalk_crew run``).

Shows come from ``chalktalk_postmatch.build_shows`` over the cached, gate-passed overlays.
Frames are the seeded sim match, cut to a window round each moment so the file stays small.
Each show also gets a ghost chapter built from B's ``ghost`` tool and a VAR chapter from its
``var_offside`` tool (``tool_overlays.py``), and every claim its evidence (B's ``evidence`` tool)
with the frames to replay it when tapped. Where B's ``half_time`` and ``catch_up`` tools exist,
their "moments that decided it" go in ``summaries``, each moment with its replay.
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
from tool_overlays import evidence_map, ghost_overlay, summary, tools, var_overlay

PRE_MS = 4000
POST_MS = 1000
STEP = 2  # every other frame: 12.5 fps is plenty for the pre-roll
REPLAY_STEP = 5  # evidence replays: 5 fps, the web eases between frames


GHOST_TITLE = "Where they should have been"
VAR_TITLE = "VAR check: offside?"
CATCH_UP_T = 600_000  # "you joined late": the catch-up as of 10:00 of the 12-minute demo match


def add_chapter(shows: list[dict], best: dict, title: str) -> None:
    """``best`` as a chapter of every show (its lens, side and language), in match order."""
    for show in shows:
        g = {**best, "lens": show["lens"], "side": show["side"], "lang": show["lang"]}
        g["id"] = f"{best['id'].rsplit('-', 1)[0]}-{show['lens']}-{show['side']}"
        seg = {"chapter_title": title, "overlay": g}
        segs = show["segments"]
        at = next((i for i, x in enumerate(segs) if x["overlay"]["match_tc"] > g["match_tc"]), None)
        segs.insert(len(segs) if at is None else at, seg)


def add_ghost_chapters(shows: list[dict], t, overlays: list[dict]) -> None:
    """One ghost chapter per show, at the crew moment where a player's drift mattered most,
    placed in match order among the show's chapters."""
    moments = sorted({o["match_tc"] for o in overlays})
    ghosts = [ghost_overlay(t, m) for m in moments]
    best = max(ghosts, key=lambda g: abs(g["claims"][1]["value"]) * 100 + g["claims"][0]["value"])
    add_chapter(shows, best, GHOST_TITLE)


def add_var_chapters(shows: list[dict], t) -> dict[str, dict]:
    """A VAR chapter for every goal VAR checked; returns each one's VAR meta by claim hash."""
    out = {}
    evs = t.store.get("sim-7").events()
    checked = {e["actors"][0] for e in evs if e["type"] == "var_check"}
    for goal in (e for e in evs if e["type"] == "goal" and e["actors"][0] in checked):
        if not any(c["type"] == "var_check" and 0 <= c["t"] - goal["t"] <= 10_000 for c in evs):
            continue
        ov, meta = var_overlay(t, goal)
        add_chapter(shows, ov, VAR_TITLE)
        out[ov["claims"][0]["tool_call"]["output_hash"]] = meta
    return out


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
    t = tools(args.half_minutes, digest)
    add_ghost_chapters(shows, t, overlays)
    var = add_var_chapters(shows, t)
    evidence = evidence_map(t, [g["overlay"] for s in shows for g in s["segments"]])
    summaries = {}
    if hasattr(t, "half_time"):  # B's #27
        summaries = {
            "half_time": summary(t, "half_time"),
            "catch_up": summary(t, "catch_up", CATCH_UP_T),
        }
    replays = [e for e in evidence.values()]
    replays += [m["replay"] for x in summaries.values() for m in x["moments"]]

    keep: set[int] = set()
    for t in {o["match_tc"] for o in overlays}:
        first = max(0, (t - PRE_MS) // FRAME_MS)
        keep.update(range(first, (t + POST_MS) // FRAME_MS + 1, STEP))
    for t in {g["overlay"]["match_tc"] for s in shows for g in s["segments"]}:
        first = max(0, (t - PRE_MS) // FRAME_MS)
        keep.update(range(first, (t + POST_MS) // FRAME_MS + 1, STEP))
    for e in replays:
        r = e["replay"]
        keep.update(range(r["start_t"] // FRAME_MS, r["end_t"] // FRAME_MS + 1, REPLAY_STEP))
    frames = [match.frame(i) for i in sorted(keep) if i < match.n_frames]

    out = {
        "match_id": match_id,
        "fps": 1000 // FRAME_MS,
        "frames": frames,
        "shows": shows,
        "evidence": evidence,
        "var": var,
        "summaries": summaries,
    }
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
