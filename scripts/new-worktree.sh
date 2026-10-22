#!/usr/bin/env bash
# Create a worktree for a stream branch next to the main checkout, from the latest main.
# Usage: scripts/new-worktree.sh stream/a-pitch-render
set -euo pipefail
branch=${1:?usage: new-worktree.sh <stream/x-slug|coord/slug>}
main=$(cd "$(git rev-parse --git-common-dir)/.." && pwd -P)
dir="$main/../repo-worktrees/${branch//\//-}"
git -C "$main" config core.hooksPath .githooks
git -C "$main" fetch -q origin main
git -C "$main" worktree add "$dir" -b "$branch" origin/main
echo "$dir"
echo "Next: cd \"$dir\" && uv sync && npm ci"
