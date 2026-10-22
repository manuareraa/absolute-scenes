"""The crew pipeline: Director -> Analyst -> Pundit -> Speech -> Verifier -> overlay contract."""

from __future__ import annotations

from typing import Any

from chalktalk_contracts import validate

from .analyst import Analyst
from .config import CrewConfig
from .director import Director, Moment
from .llm import FakeLLMClient, LLMClient
from .pundit import Pundit
from .script import render
from .speech import FakeSpeechClient, SpeechClient
from .tools import FakeAnalyticsTools, ToolClient
from .verifier import Verifier

LENSES = ("casual", "analyst", "newcomer")
SIDES = ("home", "away", "neutral")


def _centroid(geometry: dict[str, Any]) -> list[float] | None:
    pts = geometry.get("points")
    if not pts:
        return None
    return [
        round(sum(p[0] for p in pts) / len(pts), 2),
        round(sum(p[1] for p in pts) / len(pts), 2),
    ]


class Crew:
    def __init__(
        self,
        tools: ToolClient,
        llm: LLMClient,
        speech: SpeechClient,
        config: CrewConfig | None = None,
        director: Director | None = None,
    ) -> None:
        self.config = config or CrewConfig()
        self.director = director or Director()
        self.analyst = Analyst(tools)
        self.pundit = Pundit(llm)
        self.speech = speech
        self.verifier = Verifier(tools)

    def breakdown(
        self,
        moment: Moment,
        *,
        lens: str = "casual",
        side: str = "neutral",
        lang: str = "en-GB",
        surface: str = "broadcast",
    ) -> dict[str, Any]:
        results = self.analyst.analyse(moment, lens)
        draft = self.pundit.write(moment, results, lens=lens, side=side, lang=lang)
        rendered = render(draft.template, draft.values, lang=lang, voice=self.config.speech_voice)
        speech = self.speech.synthesize(rendered.ssml)

        cues = [{"cue_id": c, "offset_ms": speech.bookmarks[c]} for c in rendered.cue_order]
        offsets = {c["cue_id"]: c["offset_ms"] for c in cues}
        strokes = [
            {**s, "lead_ms": min(self.config.lead_ms, offsets[s["cue_id"]]), "duration_ms": 600}
            for s in draft.strokes
        ]
        script: dict[str, Any] = {
            "ssml": rendered.ssml,
            "text": rendered.text,
            "cues": cues,
            "words": [
                {"text": w.text, "offset_ms": w.offset_ms, "duration_ms": w.duration_ms}
                for w in speech.words
            ],
        }
        if speech.audio_url:
            script["audio_url"] = speech.audio_url
        target = _centroid(strokes[0]["geometry_m"]) if strokes else None
        overlay: dict[str, Any] = {
            "id": f"ov-{moment.id}-{lens}-{side}-{lang}",
            "stream_tc": None,
            "match_tc": moment.focus_t,
            "surface": surface,
            "claims": draft.claims,
            "strokes": strokes,
            "script": script,
            "camera": {
                "preset": "tactical" if lens == "analyst" else "broadcast",
                **({"target": target} if target else {}),
            },
            "lens": lens,
            "side": side,
            "lang": lang,
            "approval": {"state": "pending", "by": None, "at": None},
        }
        overlay = self.verifier.check(overlay)
        overlay["gate"]["scores"]["template_fallback"] = float(draft.fallback)
        validate("overlay", overlay)
        return overlay

    def run(
        self,
        events: list[dict[str, Any]],
        *,
        lenses: tuple[str, ...] = ("casual",),
        sides: tuple[str, ...] = ("neutral",),
        lang: str = "en-GB",
        surface: str = "broadcast",
    ) -> list[dict[str, Any]]:
        return [
            self.breakdown(m, lens=lens, side=side, lang=lang, surface=surface)
            for m in self.director.moments(events)
            for lens in lenses
            for side in sides
        ]


def fake_crew(config: CrewConfig | None = None) -> Crew:
    return Crew(FakeAnalyticsTools(), FakeLLMClient(), FakeSpeechClient(), config)


def crew_from_env(tools: ToolClient | None = None) -> Crew:
    """Build the crew the environment asks for (``CHALKTALK_CREW_BACKEND``, default ``fake``)."""
    config = CrewConfig.from_env()
    if config.backend == "fake":
        return Crew(tools or FakeAnalyticsTools(), FakeLLMClient(), FakeSpeechClient(), config)
    from .azure import AzureFoundryLLMClient, AzureSpeechClient

    config.require_azure()
    if tools is None:
        raise RuntimeError("azure backend needs a tool client (stream B's MCP server)")
    return Crew(tools, AzureFoundryLLMClient(config), AzureSpeechClient(config), config)
