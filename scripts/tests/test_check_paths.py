import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "check_paths", Path(__file__).resolve().parents[1] / "check_paths.py"
)
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)
OWNERS = cp.load_owners()


def test_stream_may_touch_own_and_shared_paths():
    files = ["web/src/App.tsx", "package-lock.json", "docs/notes/a.md"]
    assert cp.violations("stream/a-pitch", files, OWNERS) == []


def test_stream_may_not_touch_other_streams():
    files = ["web/src/App.tsx", "sim/src/x.py", "contracts/schemas/frame.schema.json"]
    assert cp.violations("stream/a-pitch", files, OWNERS) == [
        "sim/src/x.py",
        "contracts/schemas/frame.schema.json",
    ]


def test_coordinator_may_touch_anything():
    assert cp.violations("coord/m0-skeleton", ["contracts/x", "web/y"], OWNERS) == []


@pytest.mark.parametrize("branch", ["main", "claude/foo", "stream/z-x", "stream/a", "feature/x"])
def test_bad_branch_names_rejected(branch):
    with pytest.raises(ValueError):
        cp.allowed_paths(branch, OWNERS)


def test_every_stream_owns_disjoint_paths():
    seen = {}
    for key, s in OWNERS["streams"].items():
        for p in s["paths"]:
            for other, owner in seen.items():
                assert not (p.startswith(other) or other.startswith(p)), (key, owner, p)
            seen[p] = key
