"""The MCP tools for one match, as function tools the live crew may call in any order.

``ToolBox`` binds ``match_id`` (the viewer's show decides it, never the model), counts calls
against a hard cap, reports every call as a ``tool`` event and keeps each full result, so
claims and strokes are built from tool outputs only. The JSON schemas the agents see are
derived from the MCP tool signatures, so the two never drift apart.
"""

from __future__ import annotations

import inspect
import json
import time
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from chalktalk_mcp.tools import TOOL_NAMES

# Not offered to the Analyst: the match is fixed, and what_if belongs to the Critic.
HIDDEN = ("list_matches", "what_if", "verify", "evidence")
MOVES_SCHEMA = {
    "type": "array",
    "maxItems": 3,
    "items": {
        "type": "object",
        "properties": {
            "player_id": {"type": "string", "description": "e.g. 'A04'"},
            "back_m": {"type": "number", "description": "metres towards their own goal"},
            "infield_m": {"type": "number", "description": "metres towards the middle"},
            "to_ball_m": {"type": "number", "description": "metres towards the ball"},
        },
        "required": ["player_id"],
        "additionalProperties": False,
    },
}
MAX_RESULT_CHARS = 700


class ToolCapReached(RuntimeError):
    pass


def _json_type(hint: Any) -> dict[str, Any]:
    origin = typing.get_origin(hint)
    args = [a for a in typing.get_args(hint) if a is not type(None)]
    if origin in (typing.Union, types.UnionType):
        if len(args) == 1:
            return _json_type(args[0])
        return {"anyOf": [_json_type(a) for a in args]}
    if origin is list:
        return {"type": "array", "items": _json_type(args[0]) if args else {}}
    if origin is dict or hint is dict:
        return {"type": "object"}
    return {
        int: {"type": "integer"},
        float: {"type": "number"},
        str: {"type": "string"},
        bool: {"type": "boolean"},
    }.get(hint, {})


def tool_schema(fn: Callable[..., Any], name: str) -> dict[str, Any]:
    """``{name, description, parameters}`` for one MCP tool, without ``match_id``."""
    hints = typing.get_type_hints(fn)
    props: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in inspect.signature(fn).parameters.items():
        if pname in ("self", "match_id"):
            continue
        props[pname] = MOVES_SCHEMA if pname == "moves" else _json_type(hints.get(pname))
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    doc = " ".join((inspect.getdoc(fn) or name).split())
    return {
        "name": name,
        "description": doc[:1000],
        "parameters": {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
    }


def summarise(out: dict[str, Any]) -> str:
    """One line for the control-room strip, e.g. 'line_gap 6.4 m'."""
    value, unit = out.get("value"), out.get("unit")
    metric = out.get("metric") or out.get("tool_call", {}).get("name", "")
    if isinstance(value, float):
        value = round(value, 3)
    text = f"{metric} {value}" + (f" {unit}" if unit else "")
    return text[:200]


def compact(out: dict[str, Any]) -> str:
    """What the model reads back: the number, its unit and a trimmed slice of the details."""
    body = {
        "call_id": out["tool_call"]["id"],
        "metric": out.get("metric"),
        "value": out.get("value"),
        "unit": out.get("unit"),
        "details": out.get("details"),
    }
    text = json.dumps(body, separators=(",", ":"), default=str)
    return text if len(text) <= MAX_RESULT_CHARS else text[: MAX_RESULT_CHARS - 3] + "..."


@dataclass
class Call:
    name: str
    args: dict[str, Any]
    out: dict[str, Any]
    ms: int

    @property
    def id(self) -> str:
        return self.out["tool_call"]["id"]


class ToolBox:
    def __init__(
        self,
        tools: Any,
        match_id: str,
        *,
        max_calls: int = 8,
        on_call: Callable[[Call], None] | None = None,
        names: tuple[str, ...] = TOOL_NAMES,
    ) -> None:
        self.tools = tools
        self.match_id = match_id
        self.max_calls = max_calls
        self.on_call = on_call
        # what_if is the Critic's; it may land in the MCP tools after TOOL_NAMES is read.
        self.available = tuple(n for n in dict.fromkeys((*names, "what_if")) if hasattr(tools, n))
        self.calls: list[Call] = []

    def offered(self) -> tuple[str, ...]:
        return tuple(n for n in self.available if n not in HIDDEN)

    def schemas(self, names: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        return [tool_schema(getattr(type(self.tools), n), n) for n in names or self.offered()]

    def call(self, name: str, args: dict[str, Any]) -> Call:
        """Run one tool; raises ``ToolCapReached`` past the cap, or the tool's own error."""
        if name not in self.available:
            raise KeyError(f"unknown tool {name!r}")
        if len(self.calls) >= self.max_calls:
            raise ToolCapReached(f"tool call cap ({self.max_calls}) reached")
        args = {k: v for k, v in args.items() if k != "match_id"}
        start = time.monotonic()
        out = getattr(self.tools, name)(self.match_id, **args)
        call = Call(name, args, out, int((time.monotonic() - start) * 1000))
        self.calls.append(call)
        if self.on_call:
            self.on_call(call)
        return call

    def rerun(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Re-run a sealed tool call for the gate (not counted, not reported)."""
        args = {k: v for k, v in tool_call["args"].items() if k != "match_id"}
        return getattr(self.tools, tool_call["name"])(self.match_id, **args)

    def by_id(self, call_id: str) -> Call | None:
        return next((c for c in self.calls if c.id == call_id), None)

    def runner(self, name: str) -> Callable[..., str]:
        """``fn(**kwargs) -> str`` for the model: the compact result, or an error it can read."""

        def run(**kwargs: Any) -> str:
            try:
                return compact(self.call(name, kwargs).out)
            except ToolCapReached as err:
                return json.dumps({"error": f"{err}; answer with what you have"})
            except (KeyError, ValueError, TypeError) as err:
                return json.dumps({"error": f"{name}: {err}"[:300]})

        return run

    def function_tools(self) -> list[Any]:
        """The offered tools as Agent Framework ``FunctionTool``s (lazy import)."""
        from agent_framework import FunctionTool

        return [
            FunctionTool(
                name=s["name"],
                description=s["description"],
                func=self.runner(s["name"]),
                input_model=s["parameters"],
            )
            for s in self.schemas()
        ]
