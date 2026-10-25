"""Make the show's board match what the pundit says (`show_fixture.py` runs this on every build).

- **Gap chapters draw both lines.** B's ``line_gap`` returns the team's two lines and the arrow
  between them; the crew keeps only the arrow, so "the gap between their lines" showed a lone
  arrow. The tool is re-run (same value and arrow as the claim) and its two lines are drawn on the
  arrow's cue.
- **VAR chapters hold on the pass.** ``var_offside`` measures at the moment of the pass (its
  evidence window starts there), not at the shot. The VAR meta gets ``play_t`` so the board shows
  the line, the second-last defender, the passer and the receiver where the tool measured them.
- **A shot that scored is titled a goal**, not "The chance", since the score changes on screen.

Run on a built fixture:

    uv run python web/scripts/show_refine.py --half-minutes 5 web/public/fixtures/show-sim-7.json
    uv run python web/scripts/show_refine.py --half-minutes 5 --queue \
        web/public/fixtures/queue-sim-7.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from chalktalk_sim import DEMO_BEATS, MatchConfig, simulate
from chalktalk_sim.match import FRAME_MS
from tool_overlays import tools

PRE_MS = 4000
POST_MS = 1000
STEP = 2
GOAL_WITHIN_MS = 3000
TOPIC_CHANCE = "The chance"
TOPIC_GOAL = "Goal"


def _gap_lines(t, overlay: dict[str, Any], match_id: str, strict: bool = True) -> None:
    """Add the ``line_gap`` tool's two lines before each gap arrow, on the arrow's cue.

    ``strict``: a re-run that differs from its claim stops the build. The producer queue keeps
    rejected overlays, whose numbers may be the reason they were rejected, so there such an arrow
    is left as it is."""
    claims = {c["id"]: c for c in overlay["claims"]}
    strokes = []
    for s in overlay["strokes"]:
        c = next((claims[i] for i in s.get("claim_ids", []) if i in claims), None)
        tc = c["tool_call"] if c else None
        if s["shape"] == "arrow" and tc and tc["name"] == "line_gap":
            if any(x["id"].startswith(f"{s['id']}-line") for x in overlay["strokes"]):
                strokes.append(s)
                continue
            args = tc["args"]
            r = t.line_gap(match_id, int(args["t"]), args["team"])
            arrow = next(g for g in r["geometry"] if g["shape"] == "arrow")
            same_arrow = arrow["geometry_m"]["points"] == s["geometry_m"]["points"]
            if (r["value"] != c["value"] or not same_arrow) and not strict:
                strokes.append(s)
                continue
            if r["value"] != c["value"] or not same_arrow:
                raise SystemExit(f"{overlay['id']}: line_gap re-run does not match its claim")
            lines = [g for g in r["geometry"] if g["shape"] == "line"]
            for i, g in enumerate(lines):
                strokes.append(
                    {
                        "id": f"{s['id']}-line{i + 1}",
                        "claim_ids": s["claim_ids"],
                        "cue_id": s["cue_id"],
                        "lead_ms": s.get("lead_ms", 0),
                        "duration_ms": s.get("duration_ms", 600),
                        "shape": "line",
                        "geometry_m": g["geometry_m"],
                        "style": {"color": "chalk", "dash": True},
                    }
                )
        strokes.append(s)
    overlay["strokes"] = strokes


def _goal_title(seg: dict[str, Any], goals: list[dict[str, Any]]) -> None:
    ov = seg["overlay"]
    xg = next((c for c in ov["claims"] if c["tool_call"]["name"] == "xg"), None)
    if not xg or TOPIC_CHANCE not in seg["chapter_title"]:
        return
    shot_t = int(xg["tool_call"]["args"]["t"])
    team = xg["tool_call"]["args"].get("team")
    if any(0 <= g["t"] - shot_t <= GOAL_WITHIN_MS and g.get("team") == team for g in goals):
        seg["chapter_title"] = seg["chapter_title"].replace(TOPIC_CHANCE, TOPIC_GOAL)


def refine(fx: dict[str, Any], half_minutes: float, seed: int = 7) -> dict[str, Any]:
    match = simulate(MatchConfig(seed=seed, half_minutes=half_minutes, beats=DEMO_BEATS))
    t = tools(half_minutes, match.digest()[:8])
    match_id = fx["match_id"]
    goals = [e for e in t.store.get(match_id).events() if e["type"] == "goal"]
    for show in fx["shows"]:
        for seg in show["segments"]:
            _gap_lines(t, seg["overlay"], match_id)
            _goal_title(seg, goals)
    # The evidence panel replays the same geometry the chapter drew.
    for e in (fx.get("evidence") or {}).values():
        if e["tool"] == "line_gap" and not any(g["shape"] == "line" for g in e["geometry"]):
            r = t.line_gap(match_id, int(e["args"]["t"]), e["args"]["team"])
            e["geometry"] = [
                {**g, "style": {"color": "chalk", "dash": g["shape"] == "line"}}
                if g["shape"] == "line"
                else {**g, "style": {"color": "chalk"}}
                for g in r["geometry"]
            ]
    keep = {f["t"] for f in fx["frames"]}
    add = []
    for h, meta in (fx.get("var") or {}).items():
        ev = fx["evidence"][h]
        r = t.var_offside(match_id, int(ev["args"]["t"]), ev["args"]["player_id"])
        if r["tool_call"]["output_hash"] != h:
            raise SystemExit("var_offside re-run does not match its claim")
        meta["play_t"] = int(r["evidence_window"]["start_t"])
        first = max(0, (meta["play_t"] - PRE_MS) // FRAME_MS)
        for i in range(first, (meta["play_t"] + POST_MS) // FRAME_MS + 1, STEP):
            f = match.frame(i)
            if f["t"] not in keep:
                keep.add(f["t"])
                add.append(f)
    fx["frames"] = sorted(fx["frames"] + add, key=lambda f: f["t"])
    return fx


def refine_queue(q: dict[str, Any], half_minutes: float, seed: int = 7) -> dict[str, Any]:
    """The producer console's queue: the same gap lines, so it shows what the show would draw."""
    match = simulate(MatchConfig(seed=seed, half_minutes=half_minutes, beats=DEMO_BEATS))
    t = tools(half_minutes, match.digest()[:8])
    for o in q["overlays"]:
        _gap_lines(t, o, q["match_id"], strict=False)
    return q


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--half-minutes", type=float, required=True)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--queue", action="store_true", help="the file is the producer queue")
    p.add_argument("fixture", type=Path)
    args = p.parse_args()
    if args.queue:
        q = refine_queue(json.loads(args.fixture.read_text()), args.half_minutes, args.seed)
        args.fixture.write_text(json.dumps(q, separators=(",", ":")))
        print(f"{args.fixture}: refined, {len(q['overlays'])} overlays")
        return
    fx = refine(json.loads(args.fixture.read_text()), args.half_minutes, args.seed)
    args.fixture.write_text(json.dumps(fx, separators=(",", ":")))
    print(f"{args.fixture}: refined, {len(fx['frames'])} frames, {args.fixture.stat().st_size} B")


if __name__ == "__main__":
    main()
