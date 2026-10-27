"""The crew on Foundry Agent Service (Microsoft Agent Framework), with the in-process crew as
fallback.

Four PromptAgents live in the Foundry project (``AZURE_AI_PROJECT_ENDPOINT``), all on the
``gpt-4.1-mini`` deployment: ``chalktalk-director``, ``chalktalk-analyst``, ``chalktalk-pundit``
and ``chalktalk-verifier``. ``sync_agents`` creates or updates their definitions (project
data-plane objects, not Azure resources; they cost nothing until run).

What each agent decides, and what stays deterministic:

- **Director** ranks the candidate moments the event rules found and may drop repeats. It can
  only choose among candidate ids; anything else falls back to all candidates in time order.
- **Analyst** drives the analytics tools through a local function tool, ``run_analytics``. The
  model picks which planned tool to call; the arguments (time, team, player) come from the
  moment, never from the model. Planned tools it skipped are called in-process.
- **Pundit** writes the script template (``llm.SYSTEM_PROMPT`` is its instructions).
- **Verifier** calls ``verify_overlay``, which re-runs every tool and computes the gate. The
  gate it returns is the one the overlay carries; the model only reports it.

So coordinates and numbers always come from tools, and the gate never depends on a model. Any
agent error (auth, network, a malformed answer) falls back to the in-process role and is logged
in ``AgentLog.fallbacks``. Tracing: Agent Framework emits OpenTelemetry spans for every agent
run and tool call; ``configure_tracing`` exports them to the project's Application Insights
when one is connected, so they show under Tracing in the Foundry portal.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from .analyst import Analyst, plan
from .azure import Usage, clean_template
from .director import Director, Moment
from .llm import SYSTEM_PROMPT, DraftRequest, render_prompt
from .tools import ToolClient, ToolResult, call_tools
from .verifier import Verifier

AGENT_PREFIX = "chalktalk-"
ROLES = ("director", "analyst", "pundit", "verifier")

DIRECTOR_INSTRUCTIONS = """You are the Director of Absolute Scenes, a football analysis crew.
You get candidate moments from a match as JSON: id, trigger, match time in ms, attacking side.
Choose which moments deserve an on-air tactical breakdown and rank them, most important first.
Goals and big chances first; drop a moment only if it repeats the same story as a better one.
Answer with JSON only: {"keep": ["<id>", ...]}, using ids exactly as given."""

ANALYST_INSTRUCTIONS = """You are the Analyst of Absolute Scenes, a football analysis crew.
You get a moment and the analytics tools planned for it. Call run_analytics once for each
planned tool, by name. Never invent numbers or coordinates; the tools measure everything.
After the calls, answer with one short line naming what the tools showed."""

VERIFIER_INSTRUCTIONS = """You are the Verifier of Absolute Scenes, a football analysis crew.
Call verify_overlay exactly once. It re-runs every analytics tool behind the overlay's claims
and scores grounding, numbers, geometry and cue timing. Answer with JSON only:
{"passed": true|false, "reason": "<one short sentence>"} matching what the tool returned."""

INSTRUCTIONS = {
    "director": DIRECTOR_INSTRUCTIONS,
    "analyst": ANALYST_INSTRUCTIONS,
    "pundit": SYSTEM_PROMPT,
    "verifier": VERIFIER_INSTRUCTIONS,
}

# JSON schemas of the local function tools, declared on the PromptAgent definitions so the
# service knows them; Agent Framework runs the matching Python function locally.
TOOL_SCHEMAS: dict[str, list[dict[str, Any]]] = {
    "director": [],
    "analyst": [
        {
            "name": "run_analytics",
            "description": "Run one planned analytics tool on the moment; returns its value "
            "and unit. Arguments come from the moment.",
            "parameters": {
                "type": "object",
                "properties": {"tool": {"type": "string", "description": "Planned tool name"}},
                "required": ["tool"],
                "additionalProperties": False,
            },
        }
    ],
    "pundit": [],
    "verifier": [
        {
            "name": "verify_overlay",
            "description": "Re-run the tools behind every claim and return the gate.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        }
    ],
}


def agent_name(role: str) -> str:
    return AGENT_PREFIX + role


@dataclass
class AgentLog:
    """What the hosted crew did: agent runs per role, fallbacks with reasons, token usage."""

    runs: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ROLES, 0))
    fallbacks: list[dict[str, str]] = field(default_factory=list)

    def fallback(self, role: str, reason: str) -> None:
        self.fallbacks.append({"role": role, "reason": reason[:200]})


class AgentRunner(Protocol):
    """Runs one crew agent on a prompt with local function tools; returns its final text."""

    def run(self, role: str, prompt: str, tools: Sequence[Callable[..., Any]] = ()) -> str: ...


class FoundryRunner:
    """Runs the crew's PromptAgents on Foundry Agent Service with Entra ID (``az login`` locally,
    managed identity on Azure). Each run is capped at ``max_tokens`` and its usage logged."""

    def __init__(
        self,
        project_endpoint: str,
        *,
        version: str = "1",
        max_tokens: int = 300,
        credential: Any = None,
    ) -> None:
        if not project_endpoint:
            raise RuntimeError("the foundry crew needs AZURE_AI_PROJECT_ENDPOINT")
        self.project_endpoint = project_endpoint
        # "2" pins every role; "pundit=2" pins one role and leaves the others at version 1.
        pairs = [p.split("=", 1) for p in version.split(",") if "=" in p]
        self.versions = {role.strip(): v.strip() for role, v in pairs}
        self.version = "1" if pairs else version
        self.max_tokens = max_tokens
        self._credential = credential
        self.usage = Usage()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, **kw: Any) -> FoundryRunner:
        env = dict(os.environ) if env is None else env
        return cls(
            env.get("AZURE_AI_PROJECT_ENDPOINT") or "",
            version=env.get("CHALKTALK_AGENT_VERSION") or "1",
            max_tokens=int(env.get("CHALKTALK_MAX_TOKENS") or 300),
            **kw,
        )

    def run(self, role: str, prompt: str, tools: Sequence[Callable[..., Any]] = ()) -> str:
        return asyncio.run(self._run(role, prompt, list(tools)))

    async def _run(self, role: str, prompt: str, tools: list[Callable[..., Any]]) -> str:
        from agent_framework.foundry import FoundryAgent
        from azure.identity.aio import DefaultAzureCredential

        credential = self._credential
        owned = credential is None
        if owned:  # az login locally, managed identity on Azure
            credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        try:
            agent = FoundryAgent(
                project_endpoint=self.project_endpoint,
                agent_name=agent_name(role),
                agent_version=self.versions.get(role, self.version),
                credential=credential,
                tools=tools or None,
            )
            response = await agent.run(prompt, options={"max_tokens": self.max_tokens})
        finally:
            if owned:
                await credential.close()
        usage = response.usage_details or {}
        self.usage.add(
            {
                "prompt_tokens": usage.get("input_token_count") or 0,
                "completion_tokens": usage.get("output_token_count") or 0,
            }
        )
        return response.text


def _json_answer(text: str) -> dict[str, Any]:
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    start, end = text.find("{"), text.rfind("}")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("answer is not a JSON object")
    return data


class HostedDirector(Director):
    def __init__(self, runner: AgentRunner, log: AgentLog, **kw: Any) -> None:
        super().__init__(**kw)
        self.runner, self.log = runner, log

    def moments(self, events: list[dict[str, Any]]) -> list[Moment]:
        candidates = super().moments(events)
        if len(candidates) < 2:
            return candidates
        brief = [
            {"id": m.id, "trigger": m.trigger, "t_ms": m.focus_t, "attacking": m.attacking}
            for m in candidates
        ]
        try:
            self.log.runs["director"] += 1
            keep = _json_answer(self.runner.run("director", json.dumps(brief)))["keep"]
            by_id = {m.id: m for m in candidates}
            chosen = [by_id[i] for i in dict.fromkeys(keep) if i in by_id]
            if not chosen or len(chosen) < len([i for i in keep if isinstance(i, str)]):
                raise ValueError(f"unknown moment ids in {keep!r}")
            return chosen
        except Exception as err:  # noqa: BLE001 - any agent failure means the in-process rules
            self.log.fallback("director", f"{type(err).__name__}: {err}")
            return candidates


class HostedAnalyst(Analyst):
    def __init__(self, tools: ToolClient, runner: AgentRunner, log: AgentLog) -> None:
        super().__init__(tools)
        self.runner, self.log = runner, log

    def analyse(self, moment: Moment, lens: str) -> list[ToolResult]:
        planned = dict(plan(moment, lens))
        got: dict[str, ToolResult] = {}

        def run_analytics(tool: str) -> str:
            """Run one planned analytics tool on the moment; returns its value and unit."""
            if tool not in planned:
                return json.dumps({"error": f"not planned; planned tools: {sorted(planned)}"})
            if tool not in got:
                results = call_tools(self.tools, [(tool, planned[tool])])
                if not results:
                    return json.dumps({"error": f"{tool} could not measure this moment"})
                got[tool] = results[0]
            out = got[tool].output
            return json.dumps({"tool": tool, "value": out.get("value"), "unit": out.get("unit")})

        prompt = json.dumps(
            {"moment": moment.id, "trigger": moment.trigger, "lens": lens, "planned": [*planned]}
        )
        failed = False
        try:
            self.log.runs["analyst"] += 1
            self.runner.run("analyst", prompt, [run_analytics])
        except Exception as err:  # noqa: BLE001
            failed = True
            self.log.fallback("analyst", f"{type(err).__name__}: {err}")
        missing = [(name, args) for name, args in planned.items() if name not in got]
        # an agent that ran but skipped tools (even all of them) is a fallback too; a failed run
        # is already counted once above
        if missing and not failed:
            self.log.fallback("analyst", "skipped " + ", ".join(n for n, _ in missing))
        got.update({r.name: r for r in call_tools(self.tools, missing)})
        # number the calls like call_tools does: plan order, after dropping failed tools
        kept = [got[name] for name in planned if name in got]
        return [replace(r, id=f"tc{i + 1}") for i, r in enumerate(kept)]


class HostedVerifier(Verifier):
    def __init__(self, tools: ToolClient, runner: AgentRunner, log: AgentLog) -> None:
        super().__init__(tools)
        self.runner, self.log = runner, log

    def check(self, overlay: dict[str, Any]) -> dict[str, Any]:
        checked: list[dict[str, Any]] = []

        def verify_overlay() -> str:
            """Re-run the tools behind every claim and return the gate."""
            if not checked:
                checked.append(Verifier.check(self, overlay))
            return json.dumps(checked[0]["gate"])

        try:
            self.log.runs["verifier"] += 1
            answer = _json_answer(self.runner.run("verifier", overlay["id"], [verify_overlay]))
            if checked and bool(answer.get("passed")) != checked[0]["gate"]["passed"]:
                self.log.fallback("verifier", "agent verdict disagreed with the gate")
        except Exception as err:  # noqa: BLE001
            self.log.fallback("verifier", f"{type(err).__name__}: {err}")
        return checked[0] if checked else Verifier.check(self, overlay)


class AgentLLMClient:
    """``LLMClient`` that runs the Pundit agent; same prompt payload as the direct client."""

    def __init__(self, runner: AgentRunner, log: AgentLog) -> None:
        self.runner, self.log = runner, log

    def draft(self, request: DraftRequest) -> str:
        self.log.runs["pundit"] += 1
        return clean_template(self.runner.run("pundit", render_prompt(request)[1]["content"]))


class FallbackLLMClient:
    """Tries the Pundit agent; on any error uses the in-process client for that draft."""

    def __init__(self, primary: AgentLLMClient, fallback: Any, usage: Usage | None = None) -> None:
        self.primary, self.fallback = primary, fallback
        self._usage = usage

    @property
    def usage(self) -> Usage | None:
        """Agent runs of every role plus the fallback client's own calls (the run's LLM cost)."""
        mine, theirs = self._usage, getattr(self.fallback, "usage", None)
        if mine is None or theirs is None:
            return mine or theirs
        return Usage(
            mine.calls + theirs.calls,
            mine.prompt_tokens + theirs.prompt_tokens,
            mine.completion_tokens + theirs.completion_tokens,
        )

    def draft(self, request: DraftRequest) -> str:
        try:
            return self.primary.draft(request)
        except Exception as err:  # noqa: BLE001
            self.primary.log.fallback("pundit", f"{type(err).__name__}: {err}")
            return self.fallback.draft(request)


def agent_definitions(model: str) -> dict[str, dict[str, Any]]:
    """The four PromptAgent definitions as plain dicts (what ``sync_agents`` sends)."""
    return {
        agent_name(role): {
            "kind": "prompt",
            "model": model,
            "instructions": INSTRUCTIONS[role],
            "tools": [{"type": "function", **t} for t in TOOL_SCHEMAS[role]],
        }
        for role in ROLES
    }


def sync_agents(project_endpoint: str, model: str, credential: Any = None) -> dict[str, str]:
    """Create a new version of each crew agent; returns ``{agent_name: version}``. Manual only."""
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
    from azure.identity import AzureCliCredential

    client = AIProjectClient(
        endpoint=project_endpoint, credential=credential or AzureCliCredential()
    )
    versions = {}
    for name, spec in agent_definitions(model).items():
        tools = [FunctionTool(**{k: v for k, v in t.items() if k != "type"}, strict=False)
                 for t in spec["tools"]]  # fmt: skip
        definition = PromptAgentDefinition(
            model=model, instructions=spec["instructions"], tools=tools or None
        )
        details = client.agents.create_version(
            name, definition=definition, description="Absolute Scenes crew: " + name
        )
        versions[name] = str(details.version)
    return versions


def configure_tracing(project_endpoint: str | None = None) -> str:
    """Turn on Agent Framework's OpenTelemetry spans. Exports to Application Insights when
    ``APPLICATIONINSIGHTS_CONNECTION_STRING`` is set or the project has one connected; otherwise
    spans stay local (``CHALKTALK_TRACE_CONSOLE=1`` prints them). Returns where they go."""
    from agent_framework.observability import configure_otel_providers

    conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn and project_endpoint:
        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import AzureCliCredential

            client = AIProjectClient(endpoint=project_endpoint, credential=AzureCliCredential())
            conn = client.telemetry.get_application_insights_connection_string()
        except Exception:  # noqa: BLE001 - no App Insights connected, or no rights to read it
            conn = None
    if conn:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor
        except ImportError:  # the [foundry] extra was installed without azure-monitor
            conn = None
        else:
            configure_azure_monitor(connection_string=conn)
            configure_otel_providers(service_name="chalktalk-crew")
            return "application-insights"
    console = os.environ.get("CHALKTALK_TRACE_CONSOLE") == "1"
    configure_otel_providers(service_name="chalktalk-crew", enable_console_exporters=console)
    return "console" if console else "local"


def host_on_foundry(crew: Any, runner: AgentRunner, usage: Usage | None = None) -> AgentLog:
    """Swap the crew's four roles for their Foundry agents, keeping each in-process role as the
    fallback. Returns the log the hosted roles write to (also set as ``crew.agent_log``)."""
    log = AgentLog()
    tools = crew.analyst.tools
    crew.director = HostedDirector(
        runner, log, lookback_ms=crew.director.lookback_ms, min_gap_ms=crew.director.min_gap_ms
    )
    crew.analyst = HostedAnalyst(tools, runner, log)
    crew.verifier = HostedVerifier(crew.verifier.tools, runner, log)
    crew.pundit.llm = FallbackLLMClient(AgentLLMClient(runner, log), crew.pundit.llm, usage)
    crew.agent_log = log
    return log


def main(argv: list[str] | None = None) -> int:
    """``python -m chalktalk_crew.foundry_agents sync|show``: manage the agent definitions."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="python -m chalktalk_crew.foundry_agents")
    parser.add_argument("cmd", choices=("sync", "show"))
    parser.add_argument(
        "--model", default=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
    )
    args = parser.parse_args(argv)
    if args.cmd == "show":
        json.dump(agent_definitions(args.model), sys.stdout, indent=2)
    else:
        endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT") or ""
        if not endpoint:
            raise SystemExit("set AZURE_AI_PROJECT_ENDPOINT")
        json.dump(sync_agents(endpoint, args.model), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
