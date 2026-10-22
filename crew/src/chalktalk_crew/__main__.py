"""``python -m chalktalk_crew run``: generate and cache verified overlays for a seeded sim match.

Backends come from env (``CHALKTALK_CREW_BACKEND=azure`` plus the Azure keys); the default is
the fakes, which cost nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from .pipeline import RunLog, RunOptions, run


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--half-minutes", type=float, default=45.0)
    p.add_argument("--max-moments", type=int, default=6)
    p.add_argument("--lenses", default="casual", help="comma list: casual,analyst,newcomer")
    p.add_argument("--sides", default="home", help="comma list: home,away,neutral")
    p.add_argument("--lang", default="en-GB", help="comma list: en-GB,es-ES")
    p.add_argument("--cache", type=Path, default=Path(".chalktalk-cache"))
    p.add_argument("--budget-usd", type=float, default=0.25, help="stop generating past this")
    p.add_argument("--retry-rejected", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m chalktalk_crew")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="generate the missing overlays for one match")
    _common(p)
    p.add_argument(
        "--post",
        action="store_true",
        help="POST verified overlays to $CHALKTALK_EDGE_URL/api/overlay (secret from env)",
    )
    p = sub.add_parser("live", help="generate, then post each overlay as the live clock nears it")
    _common(p)
    p.add_argument("--ahead-s", type=float, default=8.0, help="post this long before the moment")
    args = parser.parse_args(argv)

    opts = RunOptions(
        seed=args.seed,
        half_minutes=args.half_minutes,
        max_moments=args.max_moments,
        lenses=tuple(args.lenses.split(",")),
        sides=tuple(args.sides.split(",")),
        lang=args.lang,
        cache=args.cache,
        budget_usd=args.budget_usd,
        retry_rejected=args.retry_rejected,
        post=getattr(args, "post", False),
    )
    log = run(opts)
    out = log.as_dict()
    if args.cmd == "live":
        out["watch"] = _live(opts, log, round(args.ahead_s * 1000))
    json.dump(out, sys.stdout, indent=2)
    print()
    return 0


def _live(opts: RunOptions, log: RunLog, ahead_ms: int) -> dict:
    """Check the edge serves this exact match, then follow its clock and post on time."""
    from dataclasses import asdict

    from .live import OverlayPoster, verified_overlays, watch, ws_clock

    poster = OverlayPoster.from_env()
    base = poster.url.removesuffix("/api/overlay")
    with urllib.request.urlopen(f"{base}/api/match/{log.match_id}", timeout=15) as resp:
        served = json.loads(resp.read()).get("digest")
    if served != log.digest:
        raise SystemExit(
            f"edge serves {log.match_id} digest {str(served)[:8]}, ours {log.digest[:8]}"
        )
    overlays = verified_overlays(opts.cache, log)
    return asdict(
        watch(ws_clock(base, log.match_id), overlays, poster, log.match_id, ahead_ms=ahead_ms)
    )


if __name__ == "__main__":
    raise SystemExit(main())
