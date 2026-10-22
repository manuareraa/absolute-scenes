"""Speech client interface (Azure AI Speech in production) and a deterministic fake.

Contract: SSML in, word boundaries and bookmark offsets (ms on the audio clock) out. The cue
offset is the audio offset of the bookmark, i.e. the start of the word right after it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol
from xml.sax.saxutils import unescape

BOOKMARK = re.compile(r"<bookmark\s+mark=['\"]([^'\"]+)['\"]\s*/>")
TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class WordTiming:
    text: str
    offset_ms: int
    duration_ms: int


@dataclass(frozen=True)
class SpeechResult:
    words: list[WordTiming]
    bookmarks: dict[str, int]
    duration_ms: int
    audio: bytes | None = None
    audio_url: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


class SpeechClient(Protocol):
    def synthesize(self, ssml: str) -> SpeechResult: ...


class FakeSpeechClient:
    """Character-rate timing estimate (the plan's last-resort fallback), fully deterministic.

    No audio is produced. ``ms_per_char`` ~ 65 gives roughly 15 characters per second.
    """

    def __init__(
        self, ms_per_char: int = 65, word_gap_ms: int = 40, pause_ms: int = 220, start_ms: int = 120
    ) -> None:
        self.ms_per_char = ms_per_char
        self.word_gap_ms = word_gap_ms
        self.pause_ms = pause_ms
        self.start_ms = start_ms

    def synthesize(self, ssml: str) -> SpeechResult:
        marked = BOOKMARK.sub(lambda m: f" \x00{m.group(1)}\x00 ", ssml)
        plain = unescape(TAG.sub(" ", marked), {"&apos;": "'", "&quot;": '"'})
        words: list[WordTiming] = []
        bookmarks: dict[str, int] = {}
        pending: list[str] = []
        t = self.start_ms
        for token in plain.split():
            if token.startswith("\x00") and token.endswith("\x00"):
                pending.append(token.strip("\x00"))
                continue
            for mark in pending:
                bookmarks[mark] = t
            pending.clear()
            dur = self.ms_per_char * len(token.strip(".,;:!?"))
            words.append(WordTiming(token.strip(".,;:!?\"'"), t, dur))
            t += dur + self.word_gap_ms
            if token[-1] in ".,;:!?":
                t += self.pause_ms
        for mark in pending:  # a trailing bookmark lands at the end of audio
            bookmarks[mark] = t
        return SpeechResult(words=words, bookmarks=bookmarks, duration_ms=t)
