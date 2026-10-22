"""Azure adapters for the crew interfaces. Not wired yet: credentials arrive via the Azure CLI.

Both classes take only a :class:`CrewConfig` built from env vars; auth will use
``DefaultAzureCredential`` (Azure CLI locally, managed identity on Azure). They fail loudly
instead of silently falling back to the fakes.
"""

from __future__ import annotations

from .config import CrewConfig
from .llm import DraftRequest
from .speech import SpeechResult

_NOT_WIRED = (
    "Azure {what} is not wired yet (M4). Use CHALKTALK_CREW_BACKEND=fake; "
    "see docs/notes/c-azure-wiring.md."
)


class AzureFoundryLLMClient:
    """Pundit writer on a Foundry model deployment (``CHALKTALK_FOUNDRY_*``)."""

    def __init__(self, config: CrewConfig) -> None:
        self.endpoint = config.foundry_endpoint
        self.deployment = config.foundry_deployment

    def draft(self, request: DraftRequest) -> str:
        raise NotImplementedError(_NOT_WIRED.format(what="Foundry"))


class AzureSpeechClient:
    """Azure AI Speech TTS with SSML bookmarks and word boundaries (``CHALKTALK_SPEECH_*``)."""

    def __init__(self, config: CrewConfig) -> None:
        self.endpoint = config.speech_endpoint
        self.region = config.speech_region
        self.voice = config.speech_voice

    def synthesize(self, ssml: str) -> SpeechResult:
        raise NotImplementedError(_NOT_WIRED.format(what="Speech"))
