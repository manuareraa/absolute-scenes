"""Pundit writer interface (a Foundry model deployment in production) and a deterministic fake.

The writer only phrases and orders. It receives typed beats (slot names, cue ids, what each
stroke shows) and returns a script template; it never sees coordinates and never writes digits.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from .tools import canonical_json


@dataclass(frozen=True)
class Beat:
    tool: str
    slot: str
    cue_id: str
    unit: str | None
    team_ref: str  # how to name the team the tool measured: "our", "their", "the home"


@dataclass(frozen=True)
class DraftRequest:
    lens: str
    side: str
    lang: str
    trigger: str
    beats: list[Beat]


# Stable prompt prefix (kept long and unchanged for prompt-cache hits on Foundry).
SYSTEM_PROMPT = """You are the Pundit in ChalkTalk, a tactical football analyst drawing on a pitch.
Write one short spoken breakdown from the beats you are given, in the requested language and lens.
Rules:
1. Never write a digit or a number word. Every number is a slot: write {slot} exactly where it goes.
2. Put each cue mark [[cue_id]] immediately before the word that names what is drawn. Use every cue
   exactly once, in the order that tells the story best.
3. Use only the beats given. Do not add facts, names, scores or statistics of your own.
4. Lens 'casual': plain, punchy, two or three sentences. Lens 'analyst': precise tactical terms.
   Lens 'newcomer': explain each idea in everyday words, no jargon.
5. Side 'home' or 'away': speak to that side's fans; 'neutral': no favourite.
Return only the script template text."""


def render_prompt(request: DraftRequest) -> list[dict[str, str]]:
    payload = {**asdict(request), "beats": [asdict(b) for b in request.beats]}
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": canonical_json(payload)},
    ]


class LLMClient(Protocol):
    def draft(self, request: DraftRequest) -> str: ...


# Per-tool phrasing for the fake writer: {team}, {slot} and {cue} are filled per beat.
_PHRASES: dict[str, dict[str, str]] = {
    "line_gap": {
        "casual": "Look at the [[{cue}]]gap between {team} lines, {{{slot}}} metres of grass.",
        "analyst": "{Team} midfield and back line split: the [[{cue}]]gap is {{{slot}}} metres.",
        "newcomer": "See this [[{cue}]]space between {team} two lines of players? "
        "It is {{{slot}}} metres wide, room for an attacker to receive.",
    },
    "pass_options": {
        "casual": "And the [[{cue}]]pass is on, one of {{{slot}}} options.",
        "analyst": "The carrier has {{{slot}}} forward options; the [[{cue}]]lane through is open.",
        "newcomer": "The player on the ball could pick {{{slot}}} passes; "
        "this [[{cue}]]pass is the "
        "dangerous one.",
    },
    "pitch_control": {
        "casual": "They own that [[{cue}]]zone, {{{slot}}} percent of it.",
        "analyst": "Pitch control in that [[{cue}]]zone sits at {{{slot}}} percent.",
        "newcomer": "This [[{cue}]]area is where they would win the ball first, {{{slot}}} percent "
        "of the time.",
    },
    "pressing_intensity": {
        "casual": "Then the [[{cue}]]press arrives, {{{slot}}} percent intensity.",
        "analyst": "The [[{cue}]]press: intensity on the carrier at {{{slot}}} percent.",
        "newcomer": "Watch the [[{cue}]]pressure: how hard they hunt the ball, {{{slot}}} percent "
        "of the maximum.",
    },
    "offside_line": {
        "casual": "The [[{cue}]]line was {{{slot}}} metres from halfway.",
        "analyst": "The last defender held the [[{cue}]]line at {{{slot}}} metres from halfway.",
        "newcomer": "This [[{cue}]]line marks the last defender, {{{slot}}} metres from halfway; "
        "past it you are offside.",
    },
    "shape_compactness": {
        "casual": "The [[{cue}]]block covered {{{slot}}} square metres.",
        "analyst": "The defensive [[{cue}]]block spans {{{slot}}} square metres.",
        "newcomer": "The [[{cue}]]shape the defenders make covers {{{slot}}} square metres; "
        "smaller is harder to play through.",
    },
    "xg": {
        "casual": "A [[{cue}]]chance worth {{{slot}}} expected goals.",
        "analyst": "The [[{cue}]]shot carried {{{slot}}} xG.",
        "newcomer": "From that [[{cue}]]spot, the chance was worth {{{slot}}} expected goals; "
        "a certain goal would score a full goal.",
    },
}


class FakeLLMClient:
    """Template writer that follows the system prompt's rules exactly. Deterministic."""

    def __init__(self) -> None:
        self.requests: list[DraftRequest] = []

    def draft(self, request: DraftRequest) -> str:
        self.requests.append(request)
        parts = []
        for beat in request.beats:
            phrase = _PHRASES[beat.tool][request.lens]
            parts.append(
                phrase.format(
                    cue=beat.cue_id,
                    slot=beat.slot,
                    team=beat.team_ref,
                    Team=beat.team_ref[:1].upper() + beat.team_ref[1:],
                )
            )
        return " ".join(parts)
