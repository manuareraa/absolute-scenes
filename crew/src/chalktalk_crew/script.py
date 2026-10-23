"""Script templates: the Pundit writes text with slots and cue marks, code fills the numbers.

Template grammar (what the LLM must emit):
- ``{slot}``  a claim value, filled by code from the tool result (the LLM never writes digits);
- ``[[cue]]`` a drawing cue, placed right before the word that names the stroke.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.sax.saxutils import escape

from .lang import get_lang

TOKEN = re.compile(r"\[\[([A-Za-z0-9_-]+)\]\]|\{([A-Za-z0-9_]+)\}")
NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?")  # 0.42, or 0,42 in Spanish


def format_value(value: float | int | str | bool, unit: str | None, lang: str | None = None) -> str:
    """The one spoken form of a claim value; the verifier and evals match against it."""
    if isinstance(value, bool) or isinstance(value, str):
        return str(value)
    if unit == "xG":
        text = f"{value:.2f}"
    elif unit in ("m",):
        text = f"{value:.1f}"
    else:
        return str(round(value))
    return text.replace(".", get_lang(lang).decimal)


IDENTIFIER = re.compile(r"\b[A-Za-z]+_[A-Za-z_]+\b")  # tool or slot names like line_gap
# English drawn nouns from the prompt's list; a Spanish script must name the stroke in Spanish.
ENGLISH_NOUNS = frozenset({"shot", "chance", "gap", "zone", "press", "pass", "line", "block"})
CUED_WORD = re.compile(r"\[\[[A-Za-z0-9_-]+\]\]\s*([^\W\d_]+)")
# Words that rate a chance. The writer never sees the xG value, so it must not judge it.
RATING_WORDS = re.compile(
    r"\b(high|big|huge|great|good|golden|clear|dangerous|real|alta|gran|grande|enorme|clara|"
    r"buena|peligros[ao]s?|ocasionaza)\b",
    re.IGNORECASE,
)


class TemplateError(ValueError):
    pass


@dataclass(frozen=True)
class Rendered:
    text: str
    ssml: str
    cue_order: list[str]


def fix_slot_names(template: str, slots: set[str]) -> str:
    """Repair misspelt slot names ({xG} for {xg}): by case, else the single unknown -> unspoken."""
    used = {m.group(2) for m in TOKEN.finditer(template) if m.group(2)}
    lower = {s.lower(): s for s in slots}
    fixes = {u: lower[u.lower()] for u in used - slots if u.lower() in lower}
    unknown = used - slots - set(fixes)
    unspoken = slots - used - set(fixes.values())
    if len(unknown) == 1 and len(unspoken) == 1:
        fixes[unknown.pop()] = unspoken.pop()
    for wrong, right in fixes.items():
        template = template.replace("{" + wrong + "}", "{" + right + "}")
    return template


def check_template(
    template: str,
    slots: set[str],
    cues: set[str],
    *,
    lang: str = "en-GB",
    xg_slot: str | None = None,
) -> None:
    """Reject free digits, raw names, unknown or unspoken slots, and missing or repeated cues.

    Spanish scripts must name drawn things in Spanish, and the sentence that speaks ``xg_slot``
    must not rate the chance ("high", "peligroso"): the number says how good it was.
    """
    bare = TOKEN.sub(" ", template)
    if NUMBER.search(bare):
        raise TemplateError(f"template has a number outside a slot: {bare!r}")
    if ident := IDENTIFIER.search(bare):
        raise TemplateError(f"template speaks a raw name {ident.group(0)!r}")
    seen_cues = [m.group(1) for m in TOKEN.finditer(template) if m.group(1)]
    seen_slots = {m.group(2) for m in TOKEN.finditer(template) if m.group(2)}
    if unknown := seen_slots - slots:
        raise TemplateError(f"unknown slots {sorted(unknown)}")
    if unspoken := slots - seen_slots:
        raise TemplateError(f"slots {sorted(unspoken)} are never spoken")
    if re.search(r"\]\]\s*\{", template):
        raise TemplateError("a cue must sit before the drawn noun, not before a number slot")
    if sorted(seen_cues) != sorted(cues):
        raise TemplateError(f"cues {seen_cues} must be exactly {sorted(cues)}, once each")
    if lang.startswith("es"):
        english = [w for w in CUED_WORD.findall(template) if w.lower() in ENGLISH_NOUNS]
        if english:
            raise TemplateError(f"write the drawn nouns in Spanish, not {english}")
    if xg_slot and f"{{{xg_slot}}}" in template:
        for sentence in re.split(r"(?<=[.!?;])\s+", template):
            if f"{{{xg_slot}}}" in sentence and (word := RATING_WORDS.search(sentence)):
                raise TemplateError(
                    f"do not rate the chance ({word.group(0)!r}); just give its expected goals"
                )


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
