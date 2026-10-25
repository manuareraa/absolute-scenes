"""The Verifier: every number the Pundit speaks must be a tool's number, in its spoken form.

It reads the draft, finds each number, and accepts it only if it is the spoken value of a tool
call made for this answer ("6.4 m", "65%", "0.03 xG"). A wrong number is rejected with the
tool's own value as the reason, and the Pundit rewrites. Accepted numbers become claim slots,
so the overlay's claims and the spoken text can never disagree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..lang import get_lang
from .toolbox import Call

NUMBER = re.compile(r"(?<![A-Za-z_\d])\d+(?:[.,]\d+)?(?![\d_])")
CUE = re.compile(r"\[\[([A-Za-z0-9_-]+)\]\]")
# Numbers spelled out would slip past the check, so they are rejected and rewritten as digits.
SPELLED = re.compile(
    r"\b(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|per ?cent|veinte|"
    r"treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|por ciento)\b",
    re.IGNORECASE,
)
UNIT_WORDS = {"m": "m", "m2": "m²", "xG": "xG", "share": "%", "prob": "%"}


def say(value: Any, unit: str | None, lang: str) -> str:
    """The one spoken form of a tool value, with its unit ("6.4 m", "65%", "0.03 xG")."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return str(value)
    dec = get_lang(lang).decimal
    if unit in ("share", "prob"):
        return f"{round(value * 100)}%"
    if unit in ("xG", "xT"):
        return f"{value:.2f}".replace(".", dec) + f" {unit}"
    if unit == "m":
        return f"{value:.1f}".replace(".", dec) + " m"
    num = str(round(value)) if isinstance(value, float) else str(value)
    return num + (f" {UNIT_WORDS.get(unit, unit)}" if unit and unit not in ("ms",) else "")


def numbers_of(value: Any, unit: str | None, lang: str) -> set[str]:
    """Every acceptable way to speak the value: the canonical form, and whole metres."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return set()
    text = say(value, unit, lang)
    forms = {m.group(0) for m in NUMBER.finditer(text)}
    if unit in ("m", "m2"):
        forms.add(str(round(value)))
    return forms


@dataclass
class Finding:
    claim: str  # the clause as spoken
    ok: bool
    reason: str = ""
    call_id: str | None = None
    number: str = ""
    span: tuple[int, int] = (0, 0)


@dataclass
class Check:
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.findings)

    def feedback(self) -> str:
        return "; ".join(f.reason for f in self.findings if not f.ok)


STOP = re.compile(r"[.!?;](?=\s|$)")  # a sentence end, not the point in "7.9 m"


def _clause(text: str, start: int, end: int) -> str:
    left = max((m.end() for m in STOP.finditer(text, 0, start)), default=0)
    right = next((m.start() for m in STOP.finditer(text, end)), len(text))
    return " ".join(CUE.sub("", text[left:right]).split())[:200] or text[start:end]


def _to_float(num: str) -> float:
    return float(num.replace(",", "."))


def check(text: str, calls: list[Call], lang: str) -> Check:
    """Each number in ``text`` against the spoken values of ``calls`` (strings such as a
    formation are matched whole first, so '4-4-2' is not read as three numbers)."""
    result = Check()
    masked = CUE.sub(lambda m: " " * len(m.group(0)), text)
    for call in calls:
        value = call.out.get("value")
        if isinstance(value, str) and value and value in masked:
            i = masked.index(value)
            result.findings.append(
                Finding(
                    _clause(text, i, i + len(value)), True, "", call.id, value, (i, i + len(value))
                )
            )
            masked = masked[:i] + " " * len(value) + masked[i + len(value) :]
    for m in NUMBER.finditer(masked):
        num = m.group(0)
        owner = next(
            (c for c in calls if num in numbers_of(c.out.get("value"), c.out.get("unit"), lang)),
            None,
        )
        clause = _clause(text, m.start(), m.end())
        if owner:
            result.findings.append(Finding(clause, True, "", owner.id, num, m.span()))
            continue
        result.findings.append(
            Finding(clause, False, _reason(num, calls, lang), None, num, m.span())
        )
    for m in SPELLED.finditer(masked):
        result.findings.append(
            Finding(
                _clause(text, m.start(), m.end()),
                False,
                f"write '{m.group(0)}' as digits, exactly as the result's 'say' field",
                None,
                m.group(0),
                m.span(),
            )
        )
    result.findings.sort(key=lambda f: f.span)
    return result


def _reason(num: str, calls: list[Call], lang: str) -> str:
    numeric = [c for c in calls if isinstance(c.out.get("value"), int | float)]
    if not numeric:
        return f"no tool measured {num}"
    target = _to_float(num)

    def gap(c: Call) -> float:
        spoken = NUMBER.search(say(c.out["value"], c.out.get("unit"), lang))
        return abs(_to_float(spoken.group(0)) - target) if spoken else float("inf")

    best = min(numeric, key=gap)
    return f"{best.name} says {say(best.out['value'], best.out.get('unit'), lang)}, not {num}"[:200]
