"""Absolute Scenes crew: Director, Analyst, Pundit, Speech and Verifier, making overlays."""

from .config import CrewConfig
from .crew import LENSES, SIDES, Crew, crew_from_env, fake_crew
from .director import Director, Moment
from .llm import DraftRequest, FakeLLMClient, LLMClient
from .speech import FakeSpeechClient, SpeechClient, SpeechResult
from .tools import FakeAnalyticsTools, ToolClient
from .verifier import Verifier

__version__ = "0.0.0"

__all__ = [
    "LENSES",
    "SIDES",
    "Crew",
    "CrewConfig",
    "Director",
    "DraftRequest",
    "FakeAnalyticsTools",
    "FakeLLMClient",
    "FakeSpeechClient",
    "LLMClient",
    "Moment",
    "SpeechClient",
    "SpeechResult",
    "ToolClient",
    "Verifier",
    "crew_from_env",
    "fake_crew",
]
