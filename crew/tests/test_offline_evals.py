"""Crew output must pass the offline eval suite (evals/). Runs in CI via crew/tests."""

import sys
from pathlib import Path

from chalktalk_crew import FakeAnalyticsTools, fake_crew

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evals" / "src"))

from chalktalk_evals import run_suite  # noqa: E402


def test_fake_crew_passes_offline_evals():
    report = run_suite(fake_crew(), FakeAnalyticsTools())
    assert report["passed"], [r for r in report["rows"] if r["failures"]]
