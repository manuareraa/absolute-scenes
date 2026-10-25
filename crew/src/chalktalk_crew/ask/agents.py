"""The live crew's three Foundry agents, their instructions, and a scripted fake.

- ``ask-analyst`` picks which MCP tools to call (open tool choice, no fixed sequence).
- ``ask-pundit`` answers the viewer in a few spoken sentences, quoting tool numbers only.
- ``ask-tactician`` proposes a position change as offsets for named players (never coordinates).

The Director, Verifier and Critic are code: they route, check numbers and re-run tools. Every
prompt carries its facts as JSON after a ``DATA:`` line, so the fake can read them too.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Protocol

from .toolbox import ToolBox

ROLES = ("ask-analyst", "ask-pundit", "ask-tactician")

INSTRUCTIONS = {
    "ask-analyst": (
        "You are the Analyst in a football broadcast crew. A viewer paused the match and asked a "
        "question. Call the tools that measure what the question is about, at the paused time t "
        "(ms) unless a window is needed. Pick tools yourself: usually 2 to 4 calls, never more "
        "than 5. Use the team and player ids given in DATA. Then reply with one short line "
        "naming what you found. Never invent numbers."
    ),
    "ask-pundit": (
        "You are the Pundit. Answer the viewer's question in 1 to 3 short spoken sentences (at "
        "most 60 words), entirely in the language given, football terms included (in Spanish: "
        "'fuera de juego', 'control del espacio', 'presión', never the English words). Quote "
        "only numbers from RESULTS, written exactly as their 'say' field, in digits, and name "
        "each number with its own 'label', never another: a share of pitch control is not "
        "pressure. If the question asks about something listed in 'not_measured', say briefly "
        "that it could not be measured and why, then give what RESULTS did measure. Right "
        "before the word that names what is drawn, put the result's cue mark, e.g. 'the "
        "[[tc_line_gap_ab12]] gap is 6.4 m' or 'el [[tc_line_gap_ab12]] hueco es de 6,4 m'. "
        "The mark is silent: the sentence must read correctly with it removed, so never use it "
        "in place of a word. Use 'events' and 'ball_owner' to say what happened, translating "
        "event names. Never say there is no data or ask the viewer for more: describe what the "
        "tools found. Speak from the viewer's side when one is given. If FEEDBACK is present, "
        "fix exactly what it says. Plain text only."
    ),
    "ask-tactician": (
        "You are the Tactician. Propose one realistic positional change for one team that "
        "would have helped at this moment, for 1 to 3 named players from DATA. Reply with JSON "
        'only: {"team": "home"|"away", "proposal": "<under 20 words>", "moves": [{"player_id": '
        '"A04", "back_m": 0, "infield_m": 0, "to_ball_m": 0}]}. Offsets are metres in the '
        "player's own terms (negative for the other way), at most 8 m per player. Never give "
        "coordinates. If FEEDBACK is present, propose something different."
    ),
}


class AskRunner(Protocol):
    """Runs one agent; the Analyst also gets the match's ``ToolBox`` to call tools through."""

    def run(self, role: str, prompt: str, toolbox: ToolBox | None = None) -> str: ...


def data_block(data: dict[str, Any]) -> str:
    return "DATA: " + json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str)


def read_data(prompt: str) -> dict[str, Any]:
    line = next(ln for ln in prompt.splitlines() if ln.startswith("DATA: "))
    return json.loads(line.removeprefix("DATA: "))


class FoundryAskRunner:
    """Adapts the crew's ``FoundryRunner`` (Foundry Agent Service via Agent Framework)."""

    def __init__(self, runner: Any) -> None:
        self.runner = runner

    @property
    def usage(self) -> Any:
        return self.runner.usage

    def run(self, role: str, prompt: str, toolbox: ToolBox | None = None) -> str:
        tools = toolbox.function_tools() if toolbox else ()
        return self.runner.run(role, prompt, tools)


def agent_definitions(model: str, toolbox: ToolBox) -> dict[str, dict[str, Any]]:
    """PromptAgent definitions; the Analyst declares every offered tool (Foundry only sends
    function tools that the named agent's definition declares)."""
    return {
        f"chalktalk-{role}": {
            "kind": "prompt",
            "model": model,
            "instructions": INSTRUCTIONS[role],
            "tools": [{"type": "function", **s} for s in toolbox.schemas()]
            if role == "ask-analyst"
            else [],
        }
        for role in ROLES
    }


def sync_agents(
    project_endpoint: str, model: str, toolbox: ToolBox, credential: Any = None
) -> dict[str, str]:
    """Create a new version of each ask agent (data-plane objects, not Azure resources)."""
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
    from azure.identity import AzureCliCredential

    client = AIProjectClient(
        endpoint=project_endpoint, credential=credential or AzureCliCredential()
    )
    versions = {}
    for name, spec in agent_definitions(model, toolbox).items():
        tools = [
            FunctionTool(**{k: v for k, v in t.items() if k != "type"}, strict=False)
            for t in spec["tools"]
        ]
        definition = PromptAgentDefinition(
            model=model, instructions=spec["instructions"], tools=tools or None
        )
        details = client.agents.create_version(
            name, definition=definition, description="ChalkTalk live crew: " + name
        )
        versions[name] = str(details.version)
    return versions


# --- the scripted fake ------------------------------------------------------------------------

KEYWORDS: list[tuple[str, str]] = [
    (r"gap|space between|hueco|espacio", "line_gap"),
    (r"control|dominat|domin", "pitch_control"),
    (r"press|presión|presion", "pressure"),
    (r"shot|chance|score|xg|disparo|ocasión|ocasion|gol", "shot_xg"),
    (r"shape|compact|forma", "team_shape"),
    (r"formation|formación|formacion", "formation"),
    (r"offside|fuera de juego", "offside_line"),
]


def default_plan(question: str, ctx: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Tools a question obviously needs; the fake Analyst's choice and the fallback plan."""
    t, attacking, defending = ctx["t"], ctx["attacking"], ctx["defending"]
    args = {
        "line_gap": {"t": t, "team": defending},
        "pitch_control": {"t": t, "team": attacking},
        "pressure": {"t": t},
        "shot_xg": {"t": t},
        "team_shape": {"t": t, "team": defending},
        "formation": {"t": t, "team": defending},
        "offside_line": {"t": t, "defending_team": defending},
    }
    picked = [name for pat, name in KEYWORDS if re.search(pat, question, re.IGNORECASE)]
    names = list(dict.fromkeys(picked))[:3] or ["line_gap", "pitch_control"]
    return [(n, args[n]) for n in names]


class FakeAskRunner:
    """Deterministic agents for tests and CI. ``wrong_first`` makes the Pundit's first draft
    misquote a number, so the Verifier's reject-and-rewrite loop runs."""

    def __init__(self, *, wrong_first: bool = False, tactic: Callable[..., Any] | None = None):
        self.wrong_first = wrong_first
        self.tactic = tactic
        self.calls: list[str] = []

    def run(self, role: str, prompt: str, toolbox: ToolBox | None = None) -> str:
        self.calls.append(role)
        data = read_data(prompt)
        if role == "ask-analyst":
            assert toolbox is not None
            for name, args in default_plan(data["question"], data):
                toolbox.runner(name)(**args)
            return "Measured " + ", ".join(c.name for c in toolbox.calls)
        if role == "ask-pundit":
            return self._pundit(data)
        if role == "ask-tactician":
            return json.dumps(self.tactic(data) if self.tactic else self._tactic(data))
        raise KeyError(role)

    def _pundit(self, data: dict[str, Any]) -> str:
        parts = []
        for i, r in enumerate(data["results"]):
            say = r["say"]
            if self.wrong_first and "feedback" not in data and i == 0:
                say = re.sub(r"\d+", lambda m: str(int(m.group(0)) + 3), say, count=1)
            parts.append(f"The [[{r['call_id']}]] {r['label']} is {say}.")
        return " ".join(parts) or "Nothing stands out here."

    def _tactic(self, data: dict[str, Any]) -> dict[str, Any]:
        team = data["defending"]
        nearest = [p for p in data["players"] if p["team"] == team][:2]
        tried = bool(data.get("feedback"))
        moves = [
            {"player_id": p["id"], "back_m": 0.0 if tried else 3.0, "to_ball_m": 4.0}
            for p in nearest
        ]
        return {"team": team, "proposal": "nearest defenders close the ball down", "moves": moves}
