"""Crew configuration, read from environment variables only. No keys live in code.

Keys come from the process environment (locally: ``set -a; . ~/.config/chalktalk/azure.env``)
and are kept out of ``repr`` so they never land in logs. ``CHALKTALK_*`` names win over the
``AZURE_*`` names the coordinator's env file uses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

Backend = Literal["fake", "azure"]
BACKENDS = ("fake", "azure")


def _backend(env: dict[str, str], name: str, default: str) -> Backend:
    value = (env.get(name) or default).strip().lower()
    if value not in BACKENDS:
        raise ValueError(f"{name} must be 'fake' or 'azure', got {value!r}")
    return value  # type: ignore[return-value]


def _first(env: dict[str, str], *names: str) -> str | None:
    for name in names:
        if env.get(name):
            return env[name]
    return None


@dataclass(frozen=True)
class CrewConfig:
    backend: Backend = "fake"
    llm_backend: Backend = "fake"
    speech_backend: Backend = "fake"
    foundry_endpoint: str | None = None
    foundry_deployment: str | None = None
    foundry_api_version: str = "2024-10-21"
    foundry_api_key: str | None = field(default=None, repr=False)
    max_tokens: int = 300
    speech_endpoint: str | None = None
    speech_region: str | None = None
    speech_key: str | None = field(default=None, repr=False)
    speech_voice: str = "en-GB-RyanNeural"
    lead_ms: int = 150

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> CrewConfig:
        env = dict(os.environ) if env is None else env
        backend = _backend(env, "CHALKTALK_CREW_BACKEND", "fake")
        return cls(
            backend=backend,
            llm_backend=_backend(env, "CHALKTALK_LLM_BACKEND", backend),
            speech_backend=_backend(env, "CHALKTALK_SPEECH_BACKEND", backend),
            foundry_endpoint=_first(env, "CHALKTALK_FOUNDRY_ENDPOINT", "AZURE_OPENAI_ENDPOINT"),
            foundry_deployment=_first(
                env, "CHALKTALK_FOUNDRY_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT"
            ),
            foundry_api_version=env.get("CHALKTALK_FOUNDRY_API_VERSION") or cls.foundry_api_version,
            foundry_api_key=env.get("AZURE_OPENAI_API_KEY") or None,
            max_tokens=int(env.get("CHALKTALK_MAX_TOKENS") or cls.max_tokens),
            speech_endpoint=env.get("CHALKTALK_SPEECH_ENDPOINT") or None,
            speech_region=_first(env, "CHALKTALK_SPEECH_REGION", "AZURE_SPEECH_REGION"),
            speech_key=env.get("AZURE_SPEECH_KEY") or None,
            speech_voice=env.get("CHALKTALK_SPEECH_VOICE") or cls.speech_voice,
            lead_ms=int(env.get("CHALKTALK_LEAD_MS") or cls.lead_ms),
        )

    def require_azure(self) -> None:
        """Raise naming every missing env var for the Azure clients this config selects."""
        need: list[tuple[str, str | None]] = []
        if self.llm_backend == "azure":
            need += [
                ("AZURE_OPENAI_ENDPOINT", self.foundry_endpoint),
                ("AZURE_OPENAI_DEPLOYMENT", self.foundry_deployment),
                ("AZURE_OPENAI_API_KEY", self.foundry_api_key),
            ]
        if self.speech_backend == "azure":
            need += [
                ("AZURE_SPEECH_REGION", self.speech_region or self.speech_endpoint),
                ("AZURE_SPEECH_KEY", self.speech_key),
            ]
        missing = [name for name, value in need if not value]
        if missing:
            raise RuntimeError("azure backend needs env vars: " + ", ".join(missing))
