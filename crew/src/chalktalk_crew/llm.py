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
    meaning: str = ""  # what the number says and whose it is, in plain words (built by code)


@dataclass(frozen=True)
class DraftRequest:
    lens: str
    side: str
    lang: str
    trigger: str
    beats: list[Beat]
    feedback: str | None = None  # why the previous draft was rejected, for one repair attempt


# Stable prompt prefix (kept long and unchanged for prompt-cache hits on Foundry).
SYSTEM_PROMPT = """You are the Pundit of Absolute Scenes, a tactical analyst drawing on a pitch.
Write one short spoken breakdown from the beats you are given, in the requested language and lens.
Rules:
1. Never write a digit or a number word. Each beat has a "slot" name: write it in braces, like
   {gap_m}, exactly where its number goes, followed by its unit in words (metres, percent,
   expected goals). Every beat's slot appears exactly once.
2. Each beat has a "cue_id": write it in double brackets, like [[k1]], immediately before the
   noun that names what is drawn ("the [[k1]]gap", "this [[k2]]zone"), never before "the",
   "their" or "our". Every beat's cue appears exactly once, in the order that tells the story.
   The drawn noun per tool: xg "shot" or "chance"; line_gap "gap"; pitch_control "zone";
   pressing_intensity "press"; pass_options "pass"; offside_line "line"; shape_compactness "block".
   In Spanish (es-ES) use: xg "disparo" or "ocasión"; line_gap "hueco"; pitch_control "zona";
   pressing_intensity "presión"; pass_options "pase"; offside_line "línea";
   shape_compactness "bloque".
3. Never write tool or slot names as words (no "line_gap"); say what they mean in plain words.
4. Use only the beats given. Do not add facts, names, scores or statistics of your own.
5. Lens 'casual': plain, punchy, two or three sentences. Lens 'analyst': precise tactical terms.
   Lens 'newcomer': explain each idea in everyday words, no jargon.
6. Side 'home' or 'away': speak to that side's fans; 'neutral': no favourite.
7. If "feedback" is given, your previous draft broke a rule: fix exactly that.
8. Write every word in the requested language. In Spanish, no English words at all; "xG" is
   the only abbreviation allowed.
9. You never see the numbers, so never rate an xg chance: no "high", "big", "clear",
   "dangerous", "alta", "clara", "peligrosa". Say only what it was worth in expected goals.
10. Each beat has a "meaning": whose lines, zone or chance the number measures and which team
   is attacking. Follow it exactly. "team_ref" is how to name that team ("our", "their", "the
   home side's"). A gap or block belongs to the team that is defending: if that team is ours,
   it is a gap in OUR lines, a weakness for us; never say we exploited it or that it was in
   their lines. If the meaning says a share is under half, the other team holds most of it.
11. A template missing any [[kN]] mark is rejected: put every cue in before you answer.
Example. Beats: line_gap slot gap_m cue k1; pitch_control slot control_pct cue k2. Template:
Look at the [[k1]]gap between their lines, {gap_m} metres.
We hold {control_pct} percent of this [[k2]]zone.
Return only the script template text."""


def render_prompt(request: DraftRequest) -> list[dict[str, str]]:
    payload = {**asdict(request), "beats": [asdict(b) for b in request.beats]}
    if payload["feedback"] is None:
        del payload["feedback"]
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
        "It is {{{slot}}} metres deep, room for an attacker to receive.",
    },
    "pass_options": {
        "casual": "And the [[{cue}]]pass is on, one of {{{slot}}} options.",
        "analyst": "The carrier has {{{slot}}} forward options; the [[{cue}]]lane through is open.",
        "newcomer": "The player on the ball could pick {{{slot}}} passes; "
        "this [[{cue}]]pass is the "
        "dangerous one.",
    },
    "pitch_control": {
        "casual": "{Team} share of that [[{cue}]]zone: {{{slot}}} percent.",
        "analyst": "Pitch control in that [[{cue}]]zone sits at {{{slot}}} percent.",
        "newcomer": "In this [[{cue}]]area, {team} players would reach the ball first "
        "{{{slot}}} percent of the time.",
    },
    "pressing_intensity": {
        "casual": "Then the [[{cue}]]press arrives, {{{slot}}} percent intensity.",
        "analyst": "The [[{cue}]]press: intensity on the carrier at {{{slot}}} percent.",
        "newcomer": "Watch the [[{cue}]]pressure: how hard {team} players hunt the ball, "
        "{{{slot}}} percent of the maximum.",
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


# Spanish: {team} is the subject ("nuestro equipo", "el rival", "el equipo local").
_PHRASES_ES: dict[str, dict[str, str]] = {
    "line_gap": {
        "casual": "{Team} deja un [[{cue}]]hueco entre líneas de {{{slot}}} metros.",
        "analyst": "{Team} parte el bloque: el [[{cue}]]hueco entre mediocampo y defensa "
        "es de {{{slot}}} metros.",
        "newcomer": "{Team} deja este [[{cue}]]espacio entre sus dos líneas de jugadores, "
        "de {{{slot}}} metros; ahí un atacante puede recibir.",
    },
    "pass_options": {
        "casual": "{Team} tiene el [[{cue}]]pase, una de {{{slot}}} opciones.",
        "analyst": "{Team} suma {{{slot}}} opciones hacia delante; la [[{cue}]]línea de pase "
        "está abierta.",
        "newcomer": "{Team} podía elegir entre {{{slot}}} pases; este [[{cue}]]pase es el "
        "más peligroso.",
    },
    "pitch_control": {
        "casual": "{Team} manda en esa [[{cue}]]zona, el {{{slot}}} por ciento.",
        "analyst": "{Team} controla esa [[{cue}]]zona en un {{{slot}}} por ciento.",
        "newcomer": "En esta [[{cue}]]zona, {team} llegaría antes al balón el {{{slot}}} "
        "por ciento de las veces.",
    },
    "pressing_intensity": {
        "casual": "{Team} llega con la [[{cue}]]presión, al {{{slot}}} por ciento.",
        "analyst": "{Team} aprieta: la [[{cue}]]presión sobre el poseedor está al {{{slot}}} "
        "por ciento.",
        "newcomer": "Mira la [[{cue}]]presión: {team} persigue el balón al {{{slot}}} por ciento "
        "de su máximo.",
    },
    "offside_line": {
        "casual": "{Team} fija la [[{cue}]]línea a {{{slot}}} metros del centro del campo.",
        "analyst": "{Team} adelanta la [[{cue}]]línea del último defensor a {{{slot}}} metros "
        "del medio campo.",
        "newcomer": "Esta [[{cue}]]línea marca al último defensor, a {{{slot}}} metros del "
        "centro; si la pasas, estás en fuera de juego.",
    },
    "shape_compactness": {
        "casual": "{Team} cierra un [[{cue}]]bloque de {{{slot}}} metros cuadrados.",
        "analyst": "{Team} defiende con un [[{cue}]]bloque de {{{slot}}} metros cuadrados.",
        "newcomer": "La [[{cue}]]forma que hacen los defensores ocupa {{{slot}}} metros "
        "cuadrados; cuanto más pequeña, más difícil es atravesarla.",
    },
    "xg": {
        "casual": "{Team} tuvo una [[{cue}]]ocasión de {{{slot}}} goles esperados.",
        "analyst": "El [[{cue}]]disparo valía {{{slot}}} xG.",
        "newcomer": "Desde ese [[{cue}]]punto, la ocasión valía {{{slot}}} goles esperados; "
        "un gol seguro valdría un gol entero.",
    },
}
PHRASES_BY_LANG = {"en": _PHRASES, "es": _PHRASES_ES}


class FakeLLMClient:
    """Template writer that follows the system prompt's rules exactly. Deterministic."""

    def __init__(self) -> None:
        self.requests: list[DraftRequest] = []

    def draft(self, request: DraftRequest) -> str:
        self.requests.append(request)
        parts = []
        phrases = PHRASES_BY_LANG[request.lang.split("-")[0]]
        for beat in request.beats:
            phrase = phrases[beat.tool][request.lens]
            parts.append(
                phrase.format(
                    cue=beat.cue_id,
                    slot=beat.slot,
                    team=beat.team_ref,
                    Team=beat.team_ref[:1].upper() + beat.team_ref[1:],
                )
            )
        return " ".join(parts)
