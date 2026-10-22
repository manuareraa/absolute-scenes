import copy
import re

import pytest
from chalktalk_contracts import is_valid
from chalktalk_contracts.models.overlay_schema import Overlay
from chalktalk_crew import (
    LENSES,
    SIDES,
    Crew,
    CrewConfig,
    FakeAnalyticsTools,
    FakeLLMClient,
    FakeSpeechClient,
    Verifier,
    crew_from_env,
    fake_crew,
)
from chalktalk_crew.script import NUMBER, format_value
from crew_events import ALL, counter_then_foul, offside_run, shot_then_corner


@pytest.fixture(scope="module")
def overlays():
    crew = fake_crew()
    return [ov for f in ALL.values() for ov in crew.run(f(), lenses=LENSES, sides=SIDES)]


def test_one_overlay_per_moment_lens_side(overlays):
    assert len(overlays) == 3 * len(LENSES) * len(SIDES)
    assert len({ov["id"] for ov in overlays}) == len(overlays)


def test_overlays_match_contract(overlays):
    for ov in overlays:
        assert is_valid("overlay", ov)
        Overlay.model_validate(ov)


def test_all_fake_overlays_pass_gate(overlays):
    for ov in overlays:
        assert ov["gate"]["passed"], ov["gate"]
        assert all(c["verified"] is True for c in ov["claims"])
        assert ov["approval"]["state"] == "pending"


def test_every_number_comes_from_a_claim_with_a_tool_call(overlays):
    for ov in overlays:
        spoken = {format_value(c["value"], c["unit"]) for c in ov["claims"] if c["tool_call"]}
        numbers = NUMBER.findall(ov["script"]["text"])
        assert numbers, ov["script"]["text"]
        assert set(numbers) <= spoken


def test_strokes_bind_to_cues_and_start_before_their_word(overlays):
    for ov in overlays:
        cues = {c["cue_id"]: c["offset_ms"] for c in ov["script"]["cues"]}
        word_starts = {w["offset_ms"] for w in ov["script"]["words"]}
        for s in ov["strokes"]:
            assert s["cue_id"] in cues
            assert cues[s["cue_id"]] in word_starts  # bookmark sits on a word start
            assert cues[s["cue_id"]] - s["lead_ms"] >= 0
            assert s["claim_ids"]


def test_ssml_has_one_bookmark_per_cue(overlays):
    for ov in overlays:
        marks = re.findall(r"<bookmark mark='([^']+)'/>", ov["script"]["ssml"])
        assert sorted(marks) == sorted(c["cue_id"] for c in ov["script"]["cues"])


def test_cue_offsets_increase_in_speaking_order(overlays):
    for ov in overlays:
        offsets = [c["offset_ms"] for c in ov["script"]["cues"]]
        assert offsets == sorted(offsets)


def test_geometry_is_tool_geometry():
    tools = FakeAnalyticsTools()
    crew = Crew(tools, FakeLLMClient(), FakeSpeechClient())
    ov = crew.run(counter_then_foul(), lenses=("analyst",))[0]
    for s, c in zip(ov["strokes"], ov["claims"], strict=True):
        out = tools.call(c["tool_call"]["name"], c["tool_call"]["args"])
        assert s["geometry_m"] == out["geometry"]


def test_deterministic():
    a = fake_crew().run(shot_then_corner(), lenses=LENSES)
    b = fake_crew().run(shot_then_corner(), lenses=LENSES)
    assert a == b


def test_lens_changes_depth():
    crew = fake_crew()
    moment = crew.director.moments(counter_then_foul())[0]
    casual = crew.breakdown(moment, lens="casual")
    analyst = crew.breakdown(moment, lens="analyst")
    assert len(analyst["claims"]) > len(casual["claims"])
    assert analyst["camera"]["preset"] == "tactical"


def test_side_changes_framing():
    crew = fake_crew()
    moment = crew.director.moments(counter_then_foul())[0]  # home attack, away defends
    away = crew.breakdown(moment, side="away")["script"]["text"]
    home = crew.breakdown(moment, side="home")["script"]["text"]
    neutral = crew.breakdown(moment, side="neutral")["script"]["text"]
    assert "our lines" in away and "their lines" in home and "away side's" in neutral


def test_primary_tool_follows_trigger():
    crew = fake_crew()
    shot = crew.run(shot_then_corner())[0]
    offside = crew.run(offside_run())[0]
    assert shot["claims"][0]["tool_call"]["name"] == "xg"
    assert offside["claims"][0]["tool_call"]["name"] == "offside_line"
    assert offside["strokes"][0]["shape"] == "offside_line"


class LeakyLLM(FakeLLMClient):
    """Breaks the rules: writes its own number."""

    def draft(self, request):
        return super().draft(request) + " They ran 7 kilometres more."


def test_llm_free_number_falls_back_to_rule_writer():
    crew = Crew(FakeAnalyticsTools(), LeakyLLM(), FakeSpeechClient())
    ov = crew.run(counter_then_foul())[0]
    assert "7 kilometres" not in ov["script"]["text"]
    assert ov["gate"]["scores"]["template_fallback"] == 1.0
    assert ov["gate"]["passed"]


def _base():
    return fake_crew().run(counter_then_foul(), lenses=("analyst",))[0]


def test_verifier_flags_wrong_value():
    ov = copy.deepcopy(_base())
    ov["claims"][0]["value"] += 5
    checked = Verifier(FakeAnalyticsTools()).check(ov)
    assert checked["claims"][0]["verified"] is False
    assert not checked["gate"]["passed"]


def test_verifier_flags_ungrounded_number_in_text():
    ov = copy.deepcopy(_base())
    ov["script"]["text"] += " They won 9 duels."
    checked = Verifier(FakeAnalyticsTools()).check(ov)
    assert checked["gate"]["scores"]["unsupported_numbers"] == 1.0
    assert not checked["gate"]["passed"]


def test_verifier_flags_invented_geometry():
    ov = copy.deepcopy(_base())
    ov["strokes"][0]["geometry_m"] = {"points": [[0.0, 0.0], [10.0, 10.0]]}
    checked = Verifier(FakeAnalyticsTools()).check(ov)
    assert checked["gate"]["scores"]["geometry_from_tools"] < 1.0
    assert not checked["gate"]["passed"]


def test_verifier_flags_missing_cue():
    ov = copy.deepcopy(_base())
    ov["strokes"][0]["cue_id"] = "nope"
    assert not Verifier(FakeAnalyticsTools()).check(ov)["gate"]["passed"]


def test_verifier_within_tolerance_passes():
    ov = copy.deepcopy(_base())
    claim = ov["claims"][0]
    claim["value"] = round(claim["value"] + claim["tolerance"] / 2, 2)
    checked = Verifier(FakeAnalyticsTools()).check(ov)
    assert checked["claims"][0]["verified"] is True


def test_verifier_tool_error_unverifies():
    class Broken(FakeAnalyticsTools):
        def call(self, name, args):
            raise RuntimeError("down")

    checked = Verifier(Broken()).check(copy.deepcopy(_base()))
    assert not any(c["verified"] for c in checked["claims"])


def test_lead_clamped_when_cue_is_first_word():
    class Instant(FakeSpeechClient):
        def __init__(self):
            super().__init__(start_ms=0)

    crew = Crew(FakeAnalyticsTools(), FakeLLMClient(), Instant(), CrewConfig(lead_ms=300))
    ov = crew.run(shot_then_corner())[0]
    for s in ov["strokes"]:
        cue = next(c for c in ov["script"]["cues"] if c["cue_id"] == s["cue_id"])
        assert cue["offset_ms"] - s["lead_ms"] >= 0
    assert ov["gate"]["passed"]


def test_config_from_env():
    cfg = CrewConfig.from_env({"CHALKTALK_CREW_BACKEND": "azure", "CHALKTALK_LEAD_MS": "200"})
    assert cfg.backend == cfg.llm_backend == cfg.speech_backend == "azure"
    assert cfg.lead_ms == 200
    with pytest.raises(RuntimeError, match="AZURE_OPENAI_ENDPOINT.*AZURE_SPEECH_KEY"):
        cfg.require_azure()
    with pytest.raises(ValueError):
        CrewConfig.from_env({"CHALKTALK_CREW_BACKEND": "cloud"})
    assert CrewConfig.from_env({}).backend == "fake"


def test_crew_from_env_defaults_to_fake(monkeypatch):
    for k in ("CHALKTALK_CREW_BACKEND", "CHALKTALK_LLM_BACKEND", "CHALKTALK_SPEECH_BACKEND"):
        monkeypatch.delenv(k, raising=False)
    crew = crew_from_env()
    assert crew.run(counter_then_foul())[0]["gate"]["passed"]
