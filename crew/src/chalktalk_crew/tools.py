"""Analyst tool client: the only source of numbers and drawable geometry.

The real tools are stream B's MCP server (deterministic numpy). Until it lands, the crew runs
against :class:`FakeAnalyticsTools`, which returns stable, clearly-fake outputs in the same shape.
Every tool output is ``{"value", "unit", "geometry", "provenance"}``; geometry is in pitch metres
(105 x 68, origin at the centre spot).
"""

from __future__ import annotations

import hashlib
import json
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

HALF_LENGTH = 52.5
HALF_WIDTH = 34.0


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def output_hash(output: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(output).encode()).hexdigest()


class ToolError(RuntimeError):
    """A tool could not answer for these args (e.g. nobody on the ball). The Analyst drops it."""


class ToolClient(Protocol):
    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ToolResult:
    id: str
    name: str
    args: dict[str, Any]
    output: dict[str, Any]
    output_hash: str = field(default="")

    @property
    def tool_call(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "args": self.args,
            "output_hash": self.output_hash,
        }


def call_tools(
    client: ToolClient, requests: list[tuple[str, dict[str, Any]]], *, prefix: str = "tc"
) -> list[ToolResult]:
    """Run tool calls in parallel (LLMCompiler style); results keep the request order.

    A call that raises ``ToolError`` is dropped; any other exception propagates.
    """
    if not requests:
        return []

    def run(req: tuple[str, dict[str, Any]]) -> dict[str, Any] | None:
        try:
            return client.call(req[0], req[1])
        except ToolError:
            return None

    with ThreadPoolExecutor(max_workers=min(4, len(requests))) as pool:
        outputs = list(pool.map(run, requests))
    kept = [(req, out) for req, out in zip(requests, outputs, strict=True) if out is not None]
    return [
        ToolResult(f"{prefix}{i + 1}", name, args, out, output_hash(out))
        for i, ((name, args), out) in enumerate(kept)
    ]


def _clamp_point(x: float, y: float) -> list[float]:
    return [
        round(max(-HALF_LENGTH, min(HALF_LENGTH, x)), 2),
        round(max(-HALF_WIDTH, min(HALF_WIDTH, y)), 2),
    ]


class FakeAnalyticsTools:
    """Deterministic stand-in for stream B's MCP tools. Outputs are seeded by (name, args).

    Values are placeholders for offline tests and demos of the pipeline, not match statistics.
    """

    NAMES = (
        "line_gap",
        "pitch_control",
        "pressing_intensity",
        "pass_options",
        "offside_line",
        "shape_compactness",
        "xg",
    )

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self.NAMES:
            raise KeyError(f"unknown tool {name!r}")
        self.calls.append((name, dict(args)))
        seed = int(hashlib.sha256(f"{name}|{canonical_json(args)}".encode()).hexdigest()[:12], 16)
        rng = random.Random(seed)
        out = getattr(self, f"_{name}")(rng, args)
        out["provenance"] = {"tool": name, "impl": "fake", "seed": seed}
        return out

    @staticmethod
    def _anchor(rng: random.Random) -> tuple[float, float]:
        return rng.uniform(-30, 30), rng.uniform(-25, 25)

    def _line_gap(self, rng: random.Random, args: dict[str, Any]) -> dict[str, Any]:
        x, y = self._anchor(rng)
        gap = round(rng.uniform(7.0, 16.0), 1)
        return {
            "value": gap,
            "unit": "m",
            "geometry": {
                "points": [_clamp_point(x, y), _clamp_point(x + gap, y + rng.uniform(-3, 3))]
            },
        }

    def _pitch_control(self, rng: random.Random, args: dict[str, Any]) -> dict[str, Any]:
        x, y = self._anchor(rng)
        pts = [_clamp_point(x + dx, y + dy) for dx, dy in ((-8, -6), (8, -6), (8, 6), (-8, 6))]
        return {"value": round(rng.uniform(40, 78)), "unit": "%", "geometry": {"points": pts}}

    def _pressing_intensity(self, rng: random.Random, args: dict[str, Any]) -> dict[str, Any]:
        player = str(args.get("player") or f"{(args.get('team') or 'h')[0]}{rng.randint(2, 11)}")
        return {
            "value": round(rng.uniform(30, 90)),
            "unit": "%",
            "geometry": {"player_id": player, "radius": 5.0},
        }

    def _pass_options(self, rng: random.Random, args: dict[str, Any]) -> dict[str, Any]:
        x, y = self._anchor(rng)
        end = _clamp_point(x + rng.uniform(12, 28), y + rng.uniform(-12, 12))
        return {
            "value": rng.randint(1, 5),
            "unit": "options",
            "geometry": {"points": [_clamp_point(x, y), end]},
        }

    def _offside_line(self, rng: random.Random, args: dict[str, Any]) -> dict[str, Any]:
        x = round(rng.uniform(10, 40), 1)
        return {
            "value": x,
            "unit": "m",
            "geometry": {"points": [[x, -HALF_WIDTH], [x, HALF_WIDTH]]},
        }

    def _shape_compactness(self, rng: random.Random, args: dict[str, Any]) -> dict[str, Any]:
        x, y = self._anchor(rng)
        w, h = rng.uniform(18, 32), rng.uniform(20, 40)
        pts = [_clamp_point(x + dx, y + dy) for dx, dy in ((0, 0), (w, 0), (w, h), (0, h))]
        return {"value": round(w * h), "unit": "m2", "geometry": {"points": pts}}

    def _xg(self, rng: random.Random, args: dict[str, Any]) -> dict[str, Any]:
        x, y = rng.uniform(30, 47), rng.uniform(-15, 15)
        return {
            "value": round(rng.uniform(0.03, 0.6), 2),
            "unit": "xG",
            "geometry": {"points": [_clamp_point(x, y), [HALF_LENGTH, 0.0]]},
        }
