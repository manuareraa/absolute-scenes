"""The crew hosted as Foundry agents, with a scripted stand-in for Agent Service (no Azure)."""

import json

import pytest
from chalktalk_crew.analyst import plan
from chalktalk_crew.azure import Usage
from chalktalk_crew.crew import crew_from_env, fake_crew
from chalktalk_crew.foundry_agents import (
    ROLES,
    TOOL_SCHEMAS,
    AgentLog,
    FoundryRunner,
    agent_definitions,
    host_on_foundry,
)
from chalktalk_crew.llm import SYSTEM_PROMPT, Beat, DraftRequest, FakeLLMClient
from chalktalk_crew.pipeline import RunOptions, run
from chalktalk_crew.tools import FakeAnalyticsTools


class ScriptedService:
    """Answers like the four PromptAgents would: calls the local tools it is handed."""

    def __init__(self, *, keep=None, skip_tools=(), verdict=None, fail=()):
        self.calls: list[str] = []
        self.keep, self.skip_tools, self.verdict, self.fail = keep, set(skip_tools), verdict, fail
        self.writer = FakeLLMClient()

    def run(self, role, prompt, tools=()):
        self.calls.append(role)
        if role in self.fail:
            raise RuntimeError("PermissionDenied: agents/read")
        if role == "director":
            ids = [m["id"] for m in json.loads(prompt)]
            return json.dumps({"keep": self.keep(ids) if self.keep else ids})
        if role == "analyst":
            (run_analytics,) = tools
            for name in json.loads(prompt)["planned"]:
                if name not in self.skip_tools:
                    run_analytics(tool=name)
            return "Done."
        if role == "verifier":
            (verify_overlay,) = tools
            gate = json.loads(verify_overlay())
            passed = gate["passed"] if self.verdict is None else self.verdict
            return "```json\n" + json.dumps({"passed": passed, "reason": "ok"}) + "\n```"
        payload = json.loads(prompt)
        beats = [Beat(**b) for b in payload.pop("beats")]
        return self.writer.draft(DraftRequest(**payload, beats=beats))


EVENTS = [
    {"id": "e1", "t": 30_000, "type": "pass", "team": "home", "player": "h7"},
    {"id": "e2", "t": 40_000, "type": "shot", "team": "home", "player": "h9"},
    {"id": "e3", "t": 41_000, "type": "goal", "team": "home", "player": "h9"},
    {"id": "e4", "t": 90_000, "type": "pass", "team": "away", "player": "a4"},
    {"id": "e5", "t": 100_000, "type": "shot", "team": "away", "player": "a9"},
    {"id": "e6", "t": 101_000, "type": "save", "team": "home", "player": "h1"},
    {"id": "e7", "t": 102_000, "type": "corner", "team": "away"},
]


def hosted(service):
    crew = fake_crew()
    log = host_on_foundry(crew, service)
    return crew, log


def test_hosted_crew_matches_the_in_process_crew():
    service = ScriptedService()
    crew, log = hosted(service)
    local = fake_crew().run(EVENTS, lenses=("casual", "analyst"))
    got = crew.run(EVENTS, lenses=("casual", "analyst"))
    assert got == local and all(o["gate"]["passed"] for o in got)
    assert not log.fallbacks
    assert log.runs["director"] == 1 and log.runs["pundit"] == len(got)
    assert log.runs["analyst"] == log.runs["verifier"] == len(got)


def test_director_ranks_but_cannot_invent_moments():
    crew, log = hosted(ScriptedService(keep=lambda ids: ids[::-1]))
    ids = [m.id for m in crew.director.moments(EVENTS)]
    assert ids == [m.id for m in fake_crew().director.moments(EVENTS)][::-1]
    crew, log = hosted(ScriptedService(keep=lambda ids: [*ids, "m-made-up"]))
    assert len(crew.director.moments(EVENTS)) == len(ids)
    assert log.fallbacks[0]["role"] == "director" and "m-made-up" in log.fallbacks[0]["reason"]


def test_analyst_tools_the_agent_skipped_run_in_process():
    crew, log = hosted(ScriptedService(skip_tools={"line_gap"}))
    moment = crew.director.moments(EVENTS)[0]
    results = crew.analyst.analyse(moment, "casual")
    local = fake_crew().analyst.analyse(moment, "casual")
    assert [r.name for r in results] == [r.name for r in local]
    assert [r.output for r in results] == [r.output for r in local]
    assert log.fallbacks == [{"role": "analyst", "reason": "skipped line_gap"}]


def test_an_analyst_that_calls_no_tools_counts_as_a_fallback():
    service = ScriptedService()
    crew, log = hosted(service)
    moment = crew.director.moments(EVENTS)[0]
    service.skip_tools = {name for name, _ in plan(moment, "casual")}
    results = crew.analyst.analyse(moment, "casual")
    assert [r.name for r in results] == [
        r.name for r in fake_crew().analyst.analyse(moment, "casual")
    ]
    assert [f["role"] for f in log.fallbacks] == ["analyst"]
    assert log.fallbacks[0]["reason"].startswith("skipped ")


def test_the_gate_comes_from_the_tool_not_the_agent():
    crew, log = hosted(ScriptedService(verdict=False))
    overlay = crew.run(EVENTS)[0]
    assert overlay["gate"]["passed"]  # the agent said fail; the tool's gate stands
    assert {"role": "verifier", "reason": "agent verdict disagreed with the gate"} in log.fallbacks


def test_every_role_falls_back_when_agent_service_is_down():
    service = ScriptedService(fail=ROLES)
    crew, log = hosted(service)
    assert crew.run(EVENTS) == fake_crew().run(EVENTS)
    assert {f["role"] for f in log.fallbacks} == set(ROLES)
    assert all("PermissionDenied" in f["reason"] for f in log.fallbacks)


def test_usage_adds_agent_and_fallback_calls():
    crew = fake_crew()
    usage = Usage(calls=2, prompt_tokens=1000, completion_tokens=100)
    host_on_foundry(crew, ScriptedService(), usage)
    assert crew.pundit.llm.usage.calls == 2  # the fake fallback has no usage of its own


def test_pipeline_logs_agent_runs(tmp_path, monkeypatch):
    import chalktalk_crew.pipeline as pipeline

    def hosted_from_env(tools, config):
        crew = crew_from_env(tools, config, env={})
        host_on_foundry(crew, ScriptedService(fail=("director",)))
        return crew

    monkeypatch.setattr(pipeline, "crew_from_env", hosted_from_env)
    log = run(RunOptions(seed=7, half_minutes=3.0, max_moments=1, cache=tmp_path))
    assert log.generated and log.agents["runs"]["pundit"] == 1
    assert [f["role"] for f in log.agents["fallbacks"]] == ["director"]


def test_crew_from_env_selects_agents():
    assert not hasattr(crew_from_env(FakeAnalyticsTools(), env={}), "agent_log")
    with pytest.raises(ValueError, match="CHALKTALK_AGENTS"):
        crew_from_env(FakeAnalyticsTools(), env={"CHALKTALK_AGENTS": "cloud"})
    with pytest.raises(RuntimeError, match="AZURE_AI_PROJECT_ENDPOINT"):
        FoundryRunner.from_env({})
    runner = FoundryRunner.from_env(
        {
            "AZURE_AI_PROJECT_ENDPOINT": "https://x.invalid/api/projects/p",
            "CHALKTALK_MAX_TOKENS": "50",
        }
    )
    assert runner.max_tokens == 50 and runner.version == "1"


def test_agent_definitions_declare_the_local_tools():
    defs = agent_definitions("gpt-4.1-mini")
    assert sorted(defs) == [f"chalktalk-{r}" for r in sorted(ROLES)]
    assert defs["chalktalk-pundit"]["instructions"] == SYSTEM_PROMPT
    assert [t["name"] for t in defs["chalktalk-analyst"]["tools"]] == ["run_analytics"]
    assert [t["name"] for t in defs["chalktalk-verifier"]["tools"]] == ["verify_overlay"]
    assert all(d["model"] == "gpt-4.1-mini" for d in defs.values())
    assert not TOOL_SCHEMAS["director"] and isinstance(AgentLog().runs, dict)


def test_agent_version_per_role():
    from chalktalk_crew.foundry_agents import FoundryRunner

    r = FoundryRunner.from_env(
        {"AZURE_AI_PROJECT_ENDPOINT": "x", "CHALKTALK_AGENT_VERSION": "pundit=2"}
    )
    assert (r.versions.get("pundit", r.version), r.versions.get("director", r.version)) == (
        "2",
        "1",
    )
    r = FoundryRunner.from_env({"AZURE_AI_PROJECT_ENDPOINT": "x", "CHALKTALK_AGENT_VERSION": "3"})
    assert r.versions.get("pundit", r.version) == "3"
