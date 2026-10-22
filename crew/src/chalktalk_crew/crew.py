"""The crew pipeline: Director -> Analyst -> Pundit -> Speech -> Verifier -> overlay contract."""

from __future__ import annotations

import os
from typing import Any

from chalktalk_contracts import validate

from .analyst import Analyst
from .config import CrewConfig
from .director import Director, Moment
from .lang import voice_for
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


class NoEvidence(RuntimeError):
    """Every tool the lens asked for failed, so there is nothing grounded to say."""


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
        if not results:
            raise NoEvidence(f"no tool could explain moment {moment.id} for lens {lens}")
        draft = self.pundit.write(moment, results, lens=lens, side=side, lang=lang)
        voice = voice_for(lang, self.config.speech_voice)
        rendered = render(draft.template, draft.values, lang=lang, voice=voice)
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


def crew_from_env(
    tools: ToolClient | None = None,
    config: CrewConfig | None = None,
    env: dict[str, str] | None = None,
) -> Crew:
    """Build the crew the environment asks for. ``CHALKTALK_CREW_BACKEND`` (default ``fake``)
    sets both clients; ``CHALKTALK_LLM_BACKEND`` / ``CHALKTALK_SPEECH_BACKEND`` override each.
    ``CHALKTALK_AGENTS=foundry`` runs the four roles as Foundry agents, with the clients above
    as their fallback (``foundry_agents``)."""
    env = dict(os.environ) if env is None else env
    config = config or CrewConfig.from_env(env)
    config.require_azure()
    llm: LLMClient = FakeLLMClient()
    speech: SpeechClient = FakeSpeechClient()
    if "azure" in (config.llm_backend, config.speech_backend):
        from .azure import AzureFoundryLLMClient, AzureSpeechClient

        if config.llm_backend == "azure":
            llm = AzureFoundryLLMClient(config)
        if config.speech_backend == "azure":
            speech = AzureSpeechClient(config)
    crew = Crew(tools or FakeAnalyticsTools(), llm, speech, config)
    agents = (env.get("CHALKTALK_AGENTS") or "local").strip().lower()
    if agents == "foundry":
        from .foundry_agents import FoundryRunner, configure_tracing, host_on_foundry

        runner = FoundryRunner.from_env(env)
        configure_tracing(runner.project_endpoint)
        host_on_foundry(crew, runner, runner.usage)
    elif agents != "local":
        raise ValueError(f"CHALKTALK_AGENTS must be 'local' or 'foundry', got {agents!r}")
    return crew
