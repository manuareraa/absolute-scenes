"""``python -m chalktalk_crew run``: generate and cache verified overlays for a seeded sim match.

Backends come from env (``CHALKTALK_CREW_BACKEND=azure`` plus the Azure keys); the default is
the fakes, which cost nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import RunOptions, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m chalktalk_crew")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="generate the missing overlays for one match")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--half-minutes", type=float, default=45.0)
    p.add_argument("--max-moments", type=int, default=6)
    p.add_argument("--lenses", default="casual", help="comma list: casual,analyst,newcomer")
    p.add_argument("--sides", default="home", help="comma list: home,away,neutral")
    p.add_argument("--lang", default="en-GB")
    p.add_argument("--cache", type=Path, default=Path(".chalktalk-cache"))
    p.add_argument("--budget-usd", type=float, default=0.25, help="stop generating past this")
    p.add_argument("--retry-rejected", action="store_true")
    p.add_argument(
        "--post",
        action="store_true",
        help="POST verified overlays to $CHALKTALK_EDGE_URL/api/overlay (secret from env)",
    )
    args = parser.parse_args(argv)

    log = run(
        RunOptions(
            seed=args.seed,
            half_minutes=args.half_minutes,
            max_moments=args.max_moments,
            lenses=tuple(args.lenses.split(",")),
            sides=tuple(args.sides.split(",")),
            lang=args.lang,
            cache=args.cache,
            budget_usd=args.budget_usd,
            retry_rejected=args.retry_rejected,
            post=args.post,
        )
    )
    json.dump(log.as_dict(), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
