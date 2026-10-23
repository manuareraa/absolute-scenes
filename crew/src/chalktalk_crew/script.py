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
    r"\b(high|big|huge|great|good|golden|clear|dangerous|danger|threat\w*|real|alta|gran|grande|"
    r"enorme|clara|buena|peligros[ao]s?|peligro|amenaz\w*|ocasionaza)\b",
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


# The words that can name each tool's stroke, for putting back a cue the writer left out.
DRAWN_NOUNS: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "line_gap": ("gap", "gaps", "space", "hole"),
        "pitch_control": ("zone", "area", "space", "territory"),
        "pressing_intensity": ("press", "pressure", "pressing"),
        "pass_options": ("pass", "passes", "lane", "lanes", "options"),
        "offside_line": ("line",),
        "shape_compactness": ("block", "shape"),
        "xg": ("shot", "chance", "strike", "effort"),
    },
    "es": {
        "line_gap": ("hueco", "espacio", "pasillo"),
        "pitch_control": ("zona", "área", "espacio", "terreno"),
        "pressing_intensity": ("presión", "presiona", "pressing"),
        "pass_options": ("pase", "pases", "línea", "opciones"),
        "offside_line": ("línea",),
        "shape_compactness": ("bloque", "forma", "dibujo"),
        "xg": ("disparo", "ocasión", "tiro", "remate"),
    },
}
SENTENCE = re.compile(r"[^.!?;]+[.!?;]*")


def fix_cues(template: str, beats: list[tuple[str, str, str]], lang: str) -> str:
    """Put back cue marks the writer left out: before the first word naming the beat's stroke in
    the sentence that speaks its slot (else anywhere). ``beats`` are (tool, slot, cue_id)."""
    nouns = DRAWN_NOUNS[lang.split("-")[0]]
    for tool, slot, cue in beats:
        if f"[[{cue}]]" in template:
            continue
        word = re.compile(
            r"(?<![\w\]])(" + "|".join(map(re.escape, nouns.get(tool, ()))) + r")\b", re.I
        )
        spans = [m.span() for m in SENTENCE.finditer(template) if f"{{{slot}}}" in m.group(0)]
        for a, b in [*spans, (0, len(template))]:
            if m := word.search(template, a, b):
                template = template[: m.start()] + f"[[{cue}]]" + template[m.start() :]
                break
    return template


# Possessives that put a measured gap or block on the wrong team, per (lang, team_ref kind).
SHAPE_WORDS = r"(?:own\s+)?(?:lines?|defen\w*|back\s+(?:line|four|five)|block|shape|midfield)"
WRONG_TEAM = {
    ("en", "ours"): re.compile(
        rf"\b(?:their\s+{SHAPE_WORDS}|we(?:'ve)?\s+(?:\w+\s+)?exploit\w*)", re.I
    ),
    ("en", "theirs"): re.compile(rf"\bour\s+{SHAPE_WORDS}", re.I),
    ("es", "ours"): re.compile(
        r"\b(?:aprovechamos|sus\s+líneas|su\s+defensa|líneas\s+del\s+rival|defensa\s+rival)", re.I
    ),
    ("es", "theirs"): re.compile(r"\bnuestr[oa]s?\s+(?:líneas?|defensa|bloque|zaga)", re.I),
}
# A line gap is the depth between two lines, so it is never "wide".
GAP_WIDTH = re.compile(r"\b(wide|width|across|de\s+ancho|de\s+anchura)\b", re.IGNORECASE)
MAJORITY = re.compile(
    r"\b(?:in\s+favou?r|dominat\w*|own(?:s|ed)?\s+(?:the|this|that)|controls?\s+most|"
    r"a\s+favor|domin\w*)",
    re.I,
)


def check_perspective(template: str, beats: list[dict[str, str]], lang: str) -> None:
    """Reject sentences that give a measured gap or block to the wrong team, or call a minority
    share a majority. ``beats``: tool, slot, ours ("ours"/"theirs"/"neutral"), minority ("1")."""
    base = lang.split("-")[0]
    for b in beats:
        said = [m.group(0) for m in SENTENCE.finditer(template) if f"{{{b['slot']}}}" in m.group(0)]
        for sentence in said:
            wrong = WRONG_TEAM.get((base, b["ours"]))
            if b["tool"] in ("line_gap", "shape_compactness") and wrong:
                if hit := wrong.search(sentence):
                    whose = "our own" if b["ours"] == "ours" else "the other team's"
                    raise TemplateError(
                        f"the {b['tool'].split('_')[0]} is in {whose} defensive shape; "
                        f"{hit.group(0)!r} gives it to the wrong team"
                    )
            if b["tool"] == "line_gap" and (hit := GAP_WIDTH.search(sentence)):
                raise TemplateError(
                    f"the gap is the distance between two lines, so {hit.group(0)!r} is wrong: "
                    "say how far apart or how deep it is"
                )
            if b.get("minority") and (hit := MAJORITY.search(sentence)):
                raise TemplateError(
                    f"that share is under half, so {hit.group(0)!r} is wrong: the other team "
                    "holds most of the zone"
                )


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
    # A cue mark before a full stop leaves "goals ." in the text; close the gap.
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    body = re.sub(r"\s+", " ", "".join(ssml_parts)).strip()
    ssml = (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{lang}'>"
        f"<voice name='{voice}'>{body}</voice></speak>"
    )
    return Rendered(text, ssml, cue_order)
