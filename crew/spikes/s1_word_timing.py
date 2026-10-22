"""Spike S1: how well do SSML bookmarks line up with WordBoundary word starts on Azure Speech?

For each cue we take the raw bookmark offset (``bookmark_reached``) and the start of the word the
bookmark actually precedes, found by text position (``WordBoundary.text_offset`` into the SSML),
then report the gap. It also checks how often snapping by time ("the first word starting at or after
the bookmark, minus some slack") picks that same word.

Live and manual only (it calls Azure Speech F0, free tier). Run from the repo root:

    set -a; . ~/.config/chalktalk/azure.env; set +a
    uv run --with azure-cognitiveservices-speech python crew/spikes/s1_word_timing.py

Prints a JSON summary; the numbers are copied into docs/notes/c-s1-word-timing.md.
"""

from __future__ import annotations

import json
import math
import os
import re
import statistics
import sys

import azure.cognitiveservices.speech as sdk

TICKS_PER_MS = 10_000
SLACKS = (0, 20, 100)  # time-based snapping candidates, ms of slack before the bookmark
VOICES = ("en-GB-RyanNeural", "en-US-AndrewNeural")

# Synthetic pundit lines in the crew's template style; [[kN]] marks become bookmarks. 20 cues.
LINES = [
    "Look at the [[k1]]gap between their lines, 12.9 metres of grass, and the [[k2]]pass is on.",
    "Their back four hold the [[k3]]line at 31.4 metres; the [[k4]]runner starts on the shoulder.",
    "Then the [[k5]]press arrives, three players closing, and the [[k6]]lane through the middle "
    "shuts.",
    "Pitch control in that [[k7]]zone sits at 74 percent, so the [[k8]]switch is the answer.",
    "The defensive [[k9]]block spans 812 square metres, compact, and the [[k10]]overload on the "
    "left is ignored.",
    "A [[k11]]chance worth 0.31 expected goals from the [[k12]]edge of the box.",
    "Watch the [[k13]]full-back push up; behind him, [[k14]]space opens for the winger.",
    "The [[k15]]holding midfielder drops between the centre-backs, and the [[k16]]shape becomes a "
    "back three.",
    "Their [[k17]]striker drifts wide, dragging a defender, and the [[k18]]channel opens.",
    "From the [[k19]]corner, a near-post run, and the [[k20]]header lands on target.",
]
CUE = re.compile(r"\[\[(k\d+)\]\]")


def to_ssml(line: str, voice: str) -> str:
    locale = "-".join(voice.split("-")[:2])
    body = CUE.sub(lambda m: f"<bookmark mark='{m.group(1)}'/>", line)
    return (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{locale}'>"
        f"<voice name='{voice}'>{body}</voice></speak>"
    )


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def run(voice: str) -> list[dict]:
    cfg = sdk.SpeechConfig(
        subscription=os.environ["AZURE_SPEECH_KEY"], region=os.environ["AZURE_SPEECH_REGION"]
    )
    cfg.speech_synthesis_voice_name = voice
    cfg.set_speech_synthesis_output_format(
        sdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
    )
    rows = []
    for line in LINES:
        ssml = to_ssml(line, voice)
        synth = sdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
        words: list[tuple[int, int, str]] = []  # (ssml text offset, audio ms, text)
        marks: dict[str, int] = {}
        synth.synthesis_word_boundary.connect(
            lambda e, w=words: (
                e.boundary_type == sdk.SpeechSynthesisBoundaryType.Word
                and w.append((e.text_offset, round(e.audio_offset / TICKS_PER_MS), e.text))
            )
        )
        synth.bookmark_reached.connect(
            lambda e, m=marks: m.__setitem__(e.text, round(e.audio_offset / TICKS_PER_MS))
        )
        result = synth.speak_ssml_async(ssml).get()
        if result.reason != sdk.ResultReason.SynthesizingAudioCompleted:
            raise SystemExit(f"speech failed: {result.cancellation_details.error_details}")
        words.sort(key=lambda w: w[1])
        for mark, b in marks.items():
            pos = ssml.index(f"mark='{mark}'")
            true = min((w for w in words if w[0] > pos), key=lambda w: w[0])
            by_time = {
                slack: next((w for w in words if w[1] >= b - slack), None) for slack in SLACKS
            }
            rows.append(
                {
                    "voice": voice,
                    "cue": mark,
                    "word": true[2],
                    "bookmark_ms": b,
                    "word_start_ms": true[1],
                    "delta_ms": true[1] - b,
                    **{
                        f"snap_{slack}ms_ok": w is not None and w[0] == true[0]
                        for slack, w in by_time.items()
                    },
                }
            )
    return rows


def summary(rows: list[dict]) -> dict:
    deltas = [r["delta_ms"] for r in rows]
    abs_d = [abs(d) for d in deltas]
    return {
        "cues": len(rows),
        "median_abs_ms": statistics.median(abs_d),
        "p95_abs_ms": p95(abs_d),
        "max_abs_ms": max(abs_d),
        "median_signed_ms": statistics.median(deltas),
        "min_signed_ms": min(deltas),
        **{f"snap_{s}ms_correct": sum(r[f"snap_{s}ms_ok"] for r in rows) for s in SLACKS},
    }


def main() -> None:
    voices = sys.argv[1:] or list(VOICES)
    all_rows = []
    out = {}
    for voice in voices:
        rows = run(voice)
        all_rows += rows
        out[voice] = summary(rows)
    out["all"] = summary(all_rows)
    out["worst"] = sorted(all_rows, key=lambda r: -abs(r["delta_ms"]))[:3]
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
