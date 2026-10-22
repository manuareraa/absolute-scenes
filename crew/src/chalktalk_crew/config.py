"""Crew configuration, read from environment variables only. No keys live in code.

Azure auth goes through the Azure CLI / managed identity (``DefaultAzureCredential``) once the
coordinator wires it; nothing here stores a secret.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Backend = Literal["fake", "azure"]


@dataclass(frozen=True)
class CrewConfig:
    backend: Backend = "fake"
    foundry_endpoint: str | None = None
    foundry_deployment: str | None = None
    speech_endpoint: str | None = None
    speech_region: str | None = None
    speech_voice: str = "en-GB-RyanNeural"
    lead_ms: int = 150

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> CrewConfig:
        env = dict(os.environ) if env is None else env
        backend = env.get("CHALKTALK_CREW_BACKEND", "fake").strip().lower()
        if backend not in ("fake", "azure"):
            raise ValueError(f"CHALKTALK_CREW_BACKEND must be 'fake' or 'azure', got {backend!r}")
        return cls(
            backend=backend,  # type: ignore[arg-type]
            foundry_endpoint=env.get("CHALKTALK_FOUNDRY_ENDPOINT") or None,
            foundry_deployment=env.get("CHALKTALK_FOUNDRY_DEPLOYMENT") or None,
            speech_endpoint=env.get("CHALKTALK_SPEECH_ENDPOINT") or None,
            speech_region=env.get("CHALKTALK_SPEECH_REGION") or None,
            speech_voice=env.get("CHALKTALK_SPEECH_VOICE") or cls.speech_voice,
            lead_ms=int(env.get("CHALKTALK_LEAD_MS") or cls.lead_ms),
        )

    def require_azure(self) -> None:
        missing = [
            name
            for name, value in (
                ("CHALKTALK_FOUNDRY_ENDPOINT", self.foundry_endpoint),
                ("CHALKTALK_FOUNDRY_DEPLOYMENT", self.foundry_deployment),
                (
                    "CHALKTALK_SPEECH_ENDPOINT or CHALKTALK_SPEECH_REGION",
                    self.speech_endpoint or self.speech_region,
                ),
            )
            if not value
        ]
        if missing:
            raise RuntimeError("azure backend needs env vars: " + ", ".join(missing))
