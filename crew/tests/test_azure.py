"""Azure clients without the network: an injected transport for Foundry, pure helpers for Speech."""

import json

import pytest
from chalktalk_crew import CrewConfig, FakeLLMClient, FakeSpeechClient, crew_from_env
from chalktalk_crew.azure import (
    AzureCallError,
    AzureFoundryLLMClient,
    AzureSpeechClient,
    clean_template,
    names_previous,
    snap_bookmarks,
)
from chalktalk_crew.crew import Crew
from chalktalk_crew.speech import WordTiming
from chalktalk_crew.tools import FakeAnalyticsTools
from crew_events import counter_then_foul

ENV = {
    "CHALKTALK_CREW_BACKEND": "azure",
    "AZURE_OPENAI_ENDPOINT": "https://example.invalid/",
    "AZURE_OPENAI_DEPLOYMENT": "gpt-4.1-mini",
    "AZURE_OPENAI_API_KEY": "test-key-not-real",
    "AZURE_SPEECH_REGION": "koreacentral",
    "AZURE_SPEECH_KEY": "test-speech-key-not-real",
}


class Transport:
    """Records requests; answers like Azure OpenAI with whatever the fake writer would write."""

    def __init__(self, fail: list[int] | None = None) -> None:
        self.calls: list[dict] = []
        self.fail = list(fail or [])
        self.writer = FakeLLMClient()

    def __call__(self, url, headers, body):
        payload = json.loads(body)
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        if self.fail:
            raise AzureCallError(f"HTTP {self.fail.pop(0)}: busy")
        return {
            "choices": [{"message": {"content": f"```\n{self._template(payload)}\n```"}}],
            "usage": {"prompt_tokens": 400, "completion_tokens": 60},
        }

    def _template(self, payload):
        from chalktalk_crew.llm import Beat, DraftRequest

        req = json.loads(payload["messages"][1]["content"])
        beats = [Beat(**b) for b in req.pop("beats")]
        return self.writer.draft(DraftRequest(**req, beats=beats))


def test_config_reads_coordinator_env_names_and_hides_keys():
    cfg = CrewConfig.from_env(ENV)
    assert cfg.foundry_deployment == "gpt-4.1-mini" and cfg.speech_region == "koreacentral"
    assert cfg.max_tokens == 300
    cfg.require_azure()
    assert "not-real" not in repr(cfg)
    assert "not-real" not in repr(AzureFoundryLLMClient(cfg, post=Transport()))
    assert "not-real" not in repr(AzureSpeechClient(cfg))


def test_per_client_backend_override():
    cfg = CrewConfig.from_env({**ENV, "CHALKTALK_SPEECH_BACKEND": "fake"})
    assert (cfg.llm_backend, cfg.speech_backend) == ("azure", "fake")
    crew = crew_from_env(FakeAnalyticsTools(), cfg)
    assert isinstance(crew.pundit.llm, AzureFoundryLLMClient)
    assert isinstance(crew.speech, FakeSpeechClient)


def test_foundry_client_request_shape_usage_and_caps():
    cfg = CrewConfig.from_env({**ENV, "CHALKTALK_MAX_TOKENS": "200"})
    transport = Transport()
    llm = AzureFoundryLLMClient(cfg, post=transport)
    crew = Crew(FakeAnalyticsTools(), llm, FakeSpeechClient(), cfg)
    overlays = crew.run(counter_then_foul(), lenses=("casual",), sides=("home",))
    assert overlays and all(ov["gate"]["passed"] for ov in overlays)
    call = transport.calls[0]
    assert call["url"].startswith("https://example.invalid/openai/deployments/gpt-4.1-mini/")
    assert call["headers"]["api-key"] == "test-key-not-real"
    assert call["payload"]["max_tokens"] == 200
    assert llm.usage.calls == len(transport.calls)
    assert llm.usage.prompt_tokens == 400 * llm.usage.calls
    assert 0 < llm.usage.as_dict()["est_cost_usd"] < 0.001 * llm.usage.calls


def test_foundry_client_retries_throttling_only(monkeypatch):
    monkeypatch.setattr("chalktalk_crew.azure.time.sleep", lambda s: None)
    cfg = CrewConfig.from_env(ENV)
    ok = AzureFoundryLLMClient(cfg, post=Transport(fail=[429, 503]))
    crew = Crew(FakeAnalyticsTools(), ok, FakeSpeechClient(), cfg)
    assert crew.run(counter_then_foul(), lenses=("casual",), sides=("home",))
    bad = AzureFoundryLLMClient(cfg, post=Transport(fail=[401]))
    crew = Crew(FakeAnalyticsTools(), bad, FakeSpeechClient(), cfg)
    with pytest.raises(AzureCallError, match="401"):
        crew.run(counter_then_foul(), lenses=("casual",), sides=("home",))


def test_clean_template():
    assert clean_template("```text\nThe [[k1]]gap.\n```") == "The [[k1]]gap."
    assert clean_template('"The [[k1]]gap."') == "The [[k1]]gap."


def test_snap_bookmarks_by_time_never_reaches_back():
    words = [WordTiming("the", 200, 80), WordTiming("gap", 300, 200), WordTiming("is", 560, 90)]
    # S1: bookmarks fire ~12 ms before their word, or at the start of a pause before it.
    snapped = snap_bookmarks({"k1": 288, "k2": 240, "k3": 900}, words)
    assert snapped == {"k1": 300, "k2": 300, "k3": 900}


def test_snap_bookmarks_by_text_position():
    ssml = (
        "<speak><voice>Look, <bookmark mark='k1'/>the gap <bookmark mark='k2'/>is</voice></speak>"
    )
    words = [WordTiming("Look", 50, 200), WordTiming("the", 400, 80), WordTiming("gap", 490, 200)]
    words.append(WordTiming("is", 760, 90))
    offsets = [ssml.index(w.text) for w in words]
    snapped = snap_bookmarks({"k1": 260, "k2": 745}, words, ssml=ssml, text_offsets=offsets)
    assert snapped == {"k1": 400, "k2": 760}


def test_snap_bookmark_written_after_its_word_goes_back_to_it():
    # The writer sometimes ends a clause with the cue: "esas ocasiones [[k2]]." names "ocasiones".
    ssml = (
        "<speak><voice>Un espacio <bookmark mark='k1'/>. Esas ocasiones <bookmark mark='k2'/>."
        "</voice></speak>"
    )
    words = [WordTiming("Un", 50, 100), WordTiming("espacio", 160, 400)]
    words += [WordTiming("Esas", 900, 200), WordTiming("ocasiones", 1110, 800)]
    offsets = [ssml.index(w.text) for w in words]
    raw = {"k1": 570, "k2": 1915}
    assert snap_bookmarks(raw, words, ssml=ssml, text_offsets=offsets) == {"k1": 160, "k2": 1110}
    assert snap_bookmarks(raw, words, ssml=ssml) == {"k1": 160, "k2": 1110}  # by time
    assert names_previous(ssml, "k2") and not names_previous("a <bookmark mark='k1'/>b", "k1")


def test_speech_locale_from_voice():
    client = AzureSpeechClient(CrewConfig.from_env(ENV))
    ssml = "<speak version='1.0' xml:lang='en'><voice name='x'>Hi</voice></speak>"
    assert "xml:lang='en-GB'" in client._locale(ssml)
