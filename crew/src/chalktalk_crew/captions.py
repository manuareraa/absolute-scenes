"""WebVTT captions from the TTS word timings, so captions match the voice word for word.

Word timings carry bare words (Azure joins a number and its unit); the script text gives them
back their punctuation. A caption line ends after a sentence or after ``max_words`` words. Each
language gets captions in its own words.
"""

from __future__ import annotations

import re
from typing import Any

STRIP = ".,;:!?\"'¡¿()"


def _ts(ms: int) -> str:
    h, rest = divmod(max(ms, 0), 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _punctuate(words: list[dict[str, Any]], text: str) -> list[str]:
    """Each timed word as written in the script (with its punctuation), when it can be found."""
    tokens, pos, out = text.split(), 0, []
    for word in words:
        bare = word["text"].strip(STRIP).lower()
        span = len(bare.split())  # Azure times "6 opciones" (number and unit) as one word
        for j in range(pos, min(pos + 4, len(tokens))):
            written = " ".join(tokens[j : j + span])
            if written.strip(STRIP).lower() == bare:
                out.append(written)
                pos = j + span
                break
        else:
            out.append(word["text"])
    return out


def phrases(
    words: list[dict[str, Any]], text: str = "", max_words: int = 7
) -> list[tuple[int, int, str]]:
    """``(start_ms, end_ms, line)`` per caption line."""
    shown = _punctuate(words, text)
    out: list[tuple[int, int, str]] = []
    start = 0
    for i, token in enumerate(shown):
        if re.search(r"[.!?;:]$", token) or i + 1 - start >= max_words or i + 1 == len(shown):
            first, last = words[start], words[i]
            end = last["offset_ms"] + last["duration_ms"]
            out.append((first["offset_ms"], end, " ".join(shown[start : i + 1])))
            start = i + 1
    return out


def webvtt(overlay: dict[str, Any]) -> str:
    script = overlay["script"]
    lines = ["WEBVTT", f"Language: {overlay['lang']}", ""]
    for n, (start, end, line) in enumerate(phrases(script.get("words") or [], script["text"]), 1):
        lines += [str(n), f"{_ts(start)} --> {_ts(end)}", line, ""]
    return "\n".join(lines)
