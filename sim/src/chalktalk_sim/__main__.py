"""Command line: ``python -m chalktalk_sim generate|realism``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .director import DEMO_BEATS, MatchConfig, simulate
from .package import write_package
from .realism import compare, profile


def _config(args: argparse.Namespace) -> MatchConfig:
    beats = DEMO_BEATS if args.demo else ()
    return MatchConfig(seed=args.seed, half_minutes=args.half_minutes, beats=beats)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="chalktalk_sim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("generate", "realism"):
        p = sub.add_parser(name)
        p.add_argument("--seed", type=int, default=7)
        p.add_argument("--half-minutes", type=float, default=45.0)
        p.add_argument("--demo", action="store_true", help="add the scripted demo beats")
    sub.choices["generate"].add_argument("--out", type=Path, required=True)
    sub.choices["realism"].add_argument("--reference", type=Path, help="reference profile JSON")
    args = ap.parse_args(argv)

    match = simulate(_config(args))
    if args.cmd == "generate":
        root = write_package(match, args.out)
        print(json.dumps({"package": str(root), "score": match.meta["score"]}))
        return 0
    prof = profile(match)
    if args.reference:
        report = compare(prof, json.loads(args.reference.read_text())["metrics"])
    else:
        report = {k: {"median": v["q"][50], "n": v["n"]} for k, v in prof.items()}
    json.dump(report, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
