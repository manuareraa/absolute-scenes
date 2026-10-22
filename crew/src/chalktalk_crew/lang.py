"""Languages the crew speaks: a neural voice, the decimal mark and how to name a team, per locale.

Each language gets its own script, SSML (``xml:lang`` and voice) and bookmarks: the Pundit
writes in the language, ``script.render`` marks the cues, and the TTS voice for that locale
returns the bookmark offsets. Numbers are spoken in the locale's form (``8,2`` in Spanish), and
the verifier matches them in that same form.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Lang:
    voice: str  # Azure neural voice, available on Speech F0
    decimal: str
    ours: str
    theirs: str
    neutral: str  # "{team}" is "home" or "away"
    teams: tuple[str, str]  # how "home" and "away" are said


LANGS: dict[str, Lang] = {
    "en-GB": Lang("en-GB-RyanNeural", ".", "our", "their", "the {team} side's", ("home", "away")),
    "es-ES": Lang("es-ES-AlvaroNeural", ",", "nuestro equipo", "el rival", "el equipo {team}",
                  ("local", "visitante")),
}  # fmt: skip
DEFAULT_LANG = "en-GB"


class UnsupportedLanguage(ValueError):
    pass


def get_lang(code: str | None) -> Lang:
    """The language for a BCP 47 tag; a bare ``es`` or an unknown region picks the first match."""
    code = code or DEFAULT_LANG
    if code in LANGS:
        return LANGS[code]
    base = code.split("-")[0].lower()
    for tag, lang in LANGS.items():
        if tag.split("-")[0] == base:
            return lang
    raise UnsupportedLanguage(f"no voice for {code!r}; supported: {', '.join(LANGS)}")


def team_ref(side: str, team: str, lang: str | None = None) -> str:
    """How the script names the team a tool measured, for the fans of ``side``."""
    spec = get_lang(lang)
    if side == "neutral":
        return spec.neutral.format(team=spec.teams[0] if team == "home" else spec.teams[1])
    return spec.ours if side == team else spec.theirs


def voice_for(lang: str | None, default: str | None = None) -> str:
    """The configured voice when it speaks ``lang`` (an override), else the language's own."""
    spec = get_lang(lang)
    if default and default.split("-")[0] == spec.voice.split("-")[0]:
        return default
    return spec.voice
