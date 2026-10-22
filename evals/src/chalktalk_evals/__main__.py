"""Run the offline eval suite: ``uv run python -m chalktalk_evals [--out report.json]``.

Uses the crew the environment selects (``CHALKTALK_CREW_BACKEND``, default ``fake``). Exits 1
when any overlay misses a threshold.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chalktalk_crew import FakeAnalyticsTools, crew_from_env

from .harness import run_suite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chalktalk_evals")
    parser.add_argument("--out", type=Path, help="write the full JSON report here")
    args = parser.parse_args(argv)
    tools = FakeAnalyticsTools()
    report = run_suite(crew_from_env(tools), tools)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps({"passed": report["passed"], **report["summary"]}, indent=2))
    for row in report["rows"]:
        if row["failures"]:
            print(f"FAIL {row['overlay_id']}: {', '.join(row['failures'])}", file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
