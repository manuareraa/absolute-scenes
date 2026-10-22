"""Fail if a branch changes paths outside its stream (see owners.toml).

Usage:
  python scripts/check_paths.py --branch stream/a-pitch --base origin/main   # CI
  python scripts/check_paths.py --branch stream/a-pitch --staged             # pre-commit
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = re.compile(
    r"^(?:stream/(?P<stream>[a-e])-[a-z0-9][a-z0-9._-]*|coord/[a-z0-9][a-z0-9._-]*)$"
)


def load_owners(path: Path = ROOT / "owners.toml") -> dict:
    return tomllib.loads(path.read_text())


def allowed_paths(branch: str, owners: dict) -> list[str]:
    m = BRANCH.match(branch)
    if not m:
        raise ValueError(
            f"branch {branch!r} must be stream/<a-e>-<slug> or coord/<slug> (see CLAUDE.md)"
        )
    if m.group("stream") is None:
        return owners["coord"]["paths"]
    return owners["streams"][m.group("stream")]["paths"] + owners.get("shared", [])


def violations(branch: str, files: list[str], owners: dict) -> list[str]:
    allowed = allowed_paths(branch, owners)
    if "*" in allowed:
        return []
    return [f for f in files if not any(f == p or f.startswith(p) for p in allowed)]


def changed_files(base: str | None, staged: bool) -> list[str]:
    if staged:
        cmd = ["git", "diff", "--cached", "--name-only"]
    else:
        cmd = ["git", "diff", "--name-only", f"{base}...HEAD"]
    out = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", required=True)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--base")
    group.add_argument("--staged", action="store_true")
    args = ap.parse_args(argv)
    try:
        bad = violations(args.branch, changed_files(args.base, args.staged), load_owners())
    except ValueError as e:
        print(f"check_paths: {e}", file=sys.stderr)
        return 1
    if bad:
        print(f"check_paths: {args.branch} may not change:", file=sys.stderr)
        for f in bad:
            print(f"  {f}", file=sys.stderr)
        print("Ask the owning stream or the coordinator (owners.toml).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
