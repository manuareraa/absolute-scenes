"""Rule-based Director: picks the moments worth a breakdown from the event stream.

A moment is a stoppage (the release point) plus the play that led to it (what gets explained).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STOPPAGES = frozenset(
    {
        "foul", "card", "goal", "offside", "ball_out", "throw_in", "goal_kick", "corner",
        "free_kick", "penalty", "substitution", "var_decision", "period_end",
    }
)  # fmt: skip
ON_BALL = frozenset({"pass", "carry", "dribble", "shot", "save", "tackle", "interception", "press"})


@dataclass(frozen=True)
class Moment:
    id: str
    t: int  # stoppage time: when the breakdown can air
    focus_t: int  # the play being explained
    trigger: str
    attacking: str  # "home" | "away"
    focus_player: str | None
    window: tuple[int, int]
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def defending(self) -> str:
        return "away" if self.attacking == "home" else "home"


class Director:
    def __init__(self, lookback_ms: int = 12_000, min_gap_ms: int = 20_000) -> None:
        self.lookback_ms = lookback_ms
        self.min_gap_ms = min_gap_ms

    def moments(self, events: list[dict[str, Any]]) -> list[Moment]:
        ordered = sorted(events, key=lambda e: (e["t"], e["id"]))
        out: list[Moment] = []
        last_t = -self.min_gap_ms
        for i, ev in enumerate(ordered):
            if ev["type"] not in STOPPAGES or ev["t"] - last_t < self.min_gap_ms:
                continue
            start = max(0, ev["t"] - self.lookback_ms)
            window = [e for e in ordered[: i + 1] if e["t"] >= start]
            play = [e for e in window if e["type"] in ON_BALL and e.get("team")]
            if not play:
                continue
            focus = play[-1]
            # The side in possession: the team of the last pass/carry/shot in the window.
            attackers = [e for e in play if e["type"] in ("pass", "carry", "dribble", "shot")]
            attacking = (attackers[-1] if attackers else focus)["team"]
            out.append(
                Moment(
                    id=f"m{ev['t']}",
                    t=ev["t"],
                    focus_t=focus["t"],
                    trigger=ev["type"],
                    attacking=attacking,
                    focus_player=(focus.get("actors") or [None])[0],
                    window=(start, ev["t"]),
                    events=window,
                )
            )
            last_t = ev["t"]
        return out
