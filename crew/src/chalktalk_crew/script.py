"""Script templates: the Pundit writes text with slots and cue marks, code fills the numbers.

Template grammar (what the LLM must emit):
- ``{slot}``  a claim value, filled by code from the tool result (the LLM never writes digits);
- ``[[cue]]`` a drawing cue, placed right before the word that names the stroke.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.sax.saxutils import escape

TOKEN = re.compile(r"\[\[([A-Za-z0-9_-]+)\]\]|\{([A-Za-z0-9_]+)\}")
NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")


def format_value(value: float | int | str | bool, unit: str | None) -> str:
    """The one spoken form of a claim value; the verifier and evals match against it."""
    if isinstance(value, bool) or isinstance(value, str):
        return str(value)
    if unit == "xG":
        return f"{value:.2f}"
    if unit in ("m",):
        return f"{value:.1f}"
    return str(round(value))


class TemplateError(ValueError):
    pass


@dataclass(frozen=True)
class Rendered:
    text: str
    ssml: str
    cue_order: list[str]


def check_template(template: str, slots: set[str], cues: set[str]) -> None:
    """Reject templates with free digits, unknown slots, or missing/duplicate cues."""
    bare = TOKEN.sub(" ", template)
    if NUMBER.search(bare):
        raise TemplateError(f"template has a number outside a slot: {bare!r}")
    seen_cues = [m.group(1) for m in TOKEN.finditer(template) if m.group(1)]
    seen_slots = {m.group(2) for m in TOKEN.finditer(template) if m.group(2)}
    if unknown := seen_slots - slots:
        raise TemplateError(f"unknown slots {sorted(unknown)}")
    if sorted(seen_cues) != sorted(cues):
        raise TemplateError(f"cues {seen_cues} must be exactly {sorted(cues)}, once each")


def render(template: str, values: dict[str, str], *, lang: str, voice: str) -> Rendered:
    text_parts: list[str] = []
    ssml_parts: list[str] = []
    cue_order: list[str] = []
    pos = 0
    for m in TOKEN.finditer(template):
        chunk = template[pos : m.start()]
        text_parts.append(chunk)
        ssml_parts.append(escape(chunk))
        if m.group(1):
            cue_order.append(m.group(1))
            ssml_parts.append(f"<bookmark mark='{m.group(1)}'/>")
        else:
            text_parts.append(values[m.group(2)])
            ssml_parts.append(escape(values[m.group(2)]))
        pos = m.end()
    text_parts.append(template[pos:])
    ssml_parts.append(escape(template[pos:]))
    text = re.sub(r"\s+", " ", "".join(text_parts)).strip()
    body = re.sub(r"\s+", " ", "".join(ssml_parts)).strip()
    ssml = (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{lang}'>"
        f"<voice name='{voice}'>{body}</voice></speak>"
    )
    return Rendered(text, ssml, cue_order)
