"""The end-to-end pipeline on a short seeded sim with the real analytics and fake LLM/Speech."""

import json
from dataclasses import replace

import pytest
from chalktalk_contracts import validate
from chalktalk_crew import CrewConfig, FakeLLMClient, FakeSpeechClient
from chalktalk_crew.__main__ import main
from chalktalk_crew.azure import AzureCallError, AzureSpeechClient
from chalktalk_crew.core_tools import CoreToolClient
from chalktalk_crew.pipeline import RunOptions, run
from chalktalk_crew.tools import ToolError, call_tools
from chalktalk_mcp.store import Store
from chalktalk_mcp.tools import Tools
from chalktalk_sim import DEMO_BEATS, MatchConfig, simulate

HALF = 3.0


class CountingLLM(FakeLLMClient):
    def __init__(self) -> None:
        super().__init__()
        self.n = 0

    def draft(self, request):
        self.n += 1
        return super().draft(request)


class Mp3Speech(FakeSpeechClient):
    def synthesize(self, ssml):
        return replace(super().synthesize(ssml), audio=b"ID3fake")


@pytest.fixture(scope="module")
def core():
    match = simulate(MatchConfig(seed=7, half_minutes=HALF, beats=DEMO_BEATS))
    store = Store(half_minutes=HALF)
    src = store.put(match)
    return CoreToolClient(Tools(store), src.match_id)


def test_core_tools_answer_from_the_real_analytics(core):
    out = core.call("line_gap", {"t": 60000, "team": "home"})
    assert out["unit"] == "m" and out["shape"] in ("arrow", "line")
    assert out["provenance"]["tool_call"]["name"] == "line_gap"
    assert out == core.call("line_gap", {"t": 60000, "team": "home"})  # deterministic
    press = core.call("pressing_intensity", {"t": 60000, "team": "away"})
    assert press["unit"] == "%" and 0 <= press["value"] <= 100 and press["shape"] == "ring"


def test_tool_errors_are_dropped_not_raised(core):
    class Flaky:
        def call(self, name, args):
            if name == "xg":
                raise ToolError("nobody has the ball")
            return core.call(name, args)

    results = call_tools(Flaky(), [("xg", {"t": 0}), ("line_gap", {"t": 60000, "team": "home"})])
    assert [r.name for r in results] == ["line_gap"] and results[0].id == "tc1"


def test_pipeline_writes_verified_overlays_audio_and_cues_then_caches(tmp_path):
    opts = RunOptions(seed=7, half_minutes=HALF, max_moments=3, sides=("home", "away"))
    opts.cache = tmp_path
    llm = CountingLLM()
    log = run(opts, config=CrewConfig(), llm=llm, speech=Mp3Speech())
    assert log.generated and not log.rejected
    root = tmp_path / f"{log.match_id}-{log.digest[:8]}"
    for oid in log.generated:
        overlay = json.loads((root / "overlays" / f"{oid}.json").read_text())
        validate("overlay", overlay)
        assert overlay["gate"]["passed"]
        assert overlay["script"]["audio_url"] == f"audio/{oid}.mp3"
        assert (root / "audio" / f"{oid}.mp3").read_bytes() == b"ID3fake"
        cues = json.loads((root / "cues" / f"{oid}.json").read_text())
        assert [c["cue_id"] for c in cues] == [c["cue_id"] for c in overlay["script"]["cues"]]
        assert all(c["word"] and c["stroke_start_ms"] >= 0 for c in cues)
    calls = llm.n
    again = run(opts, config=CrewConfig(), llm=llm, speech=Mp3Speech())
    assert llm.n == calls  # nothing regenerated
    assert sorted(again.cached) == sorted(log.generated) and not again.generated
    assert len(list((root / "runs").glob("*.json"))) >= 1


def test_budget_guard_stops_generation(tmp_path):
    opts = RunOptions(seed=7, half_minutes=HALF, max_moments=2, budget_usd=0.0, cache=tmp_path)
    log = run(opts, config=CrewConfig(), llm=CountingLLM(), speech=FakeSpeechClient())
    assert not log.generated and log.skipped and log.stopped.startswith("budget")


def test_cli_prints_the_run_log(tmp_path, capsys):
    argv = ["run", "--half-minutes", str(HALF), "--max-moments", "1", "--cache", str(tmp_path)]
    assert main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["match_id"] == "sim-7" and "llm" in out and "est_cost_usd" in out


def test_speech_retries_throttling_only(monkeypatch):
    monkeypatch.setattr("chalktalk_crew.azure.time.sleep", lambda s: None)
    cfg = CrewConfig(speech_region="koreacentral", speech_key="test-not-real")
    client = AzureSpeechClient(cfg)
    errors = [AzureCallError("speech failed: Error TooManyRequests busy")]

    def once(ssml):
        if errors:
            raise errors.pop(0)
        return "ok"

    client._synthesize_once = once
    assert client.synthesize("<speak/>") == "ok"
    client._synthesize_once = lambda s: (_ for _ in ()).throw(AzureCallError("speech failed: 401"))
    with pytest.raises(AzureCallError, match="401"):
        client.synthesize("<speak/>")


def test_template_check_rejects_raw_names_and_unspoken_slots():
    from chalktalk_crew.script import TemplateError, check_template

    with pytest.raises(TemplateError, match="raw name"):
        check_template("Our [[k1]]line_gap holds {gap_m} metres.", {"gap_m"}, {"k1"})
    with pytest.raises(TemplateError, match="never spoken"):
        check_template("Look at the [[k1]]gap.", {"gap_m"}, {"k1"})
    check_template("Look at the [[k1]]gap, {gap_m} metres.", {"gap_m"}, {"k1"})


def test_failed_azure_calls_are_logged_and_left_uncached(tmp_path):
    class Down(FakeSpeechClient):
        def synthesize(self, ssml):
            raise AzureCallError("speech failed: ServiceTimeout")

    opts = RunOptions(seed=7, half_minutes=HALF, max_moments=1, cache=tmp_path)
    log = run(opts, config=CrewConfig(), llm=CountingLLM(), speech=Down())
    assert log.failed and not log.generated
    assert not list(tmp_path.glob("*/overlays/*.json"))


def test_pundit_repairs_a_broken_draft_once_before_falling_back(core):
    from chalktalk_crew.crew import Crew

    class DropsACue(CountingLLM):
        def draft(self, request):
            good = super().draft(request)
            return good if request.feedback else good.replace("[[k1]]", "")

    llm = DropsACue()
    crew = Crew(core, llm, FakeSpeechClient())
    match = simulate(MatchConfig(seed=7, half_minutes=HALF, beats=DEMO_BEATS))
    overlay = crew.breakdown(crew.director.moments(match.events)[0], lens="casual", side="home")
    assert llm.n == 2 and overlay["gate"]["scores"]["template_fallback"] == 0.0


def test_fix_slot_names():
    from chalktalk_crew.script import fix_slot_names

    assert fix_slot_names("{xG} and {gap_m}", {"xg", "gap_m"}) == "{xg} and {gap_m}"
    assert fix_slot_names("{options} and {gap_m}", {"pass_options", "gap_m"}) == (
        "{pass_options} and {gap_m}"
    )
    assert fix_slot_names("{a} {b}", {"x", "y"}) == "{a} {b}"  # ambiguous: left for the check


def test_cue_before_a_number_is_rejected():
    from chalktalk_crew.script import TemplateError, check_template

    with pytest.raises(TemplateError, match="drawn noun"):
        check_template("The press is at [[k1]]{press_pct} percent.", {"press_pct"}, {"k1"})
