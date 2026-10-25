"""Azure AI Content Safety on the viewer's question: Prompt Shields, then a harm-category check.

The ``chalktalk-foundry`` AIServices resource serves Content Safety on its own endpoint (no new
resource): ``POST {endpoint}/contentsafety/text:shieldPrompt`` and ``text:analyze``. Tests use
``FakeSafety``; the Azure client takes an injectable ``post`` transport like the other clients.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

API_VERSION = "2024-09-01"
MAX_SEVERITY = 2  # 0 safe, 2 low, 4 medium, 6 high: refuse at medium and above
MAX_QUESTION_CHARS = 300

Post = Callable[[str, dict[str, str], bytes], dict[str, Any]]


@dataclass(frozen=True)
class SafetyResult:
    ok: bool
    reason: str = ""
    check: str = ""  # which check refused: length, prompt_shield, harm


class SafetyClient(Protocol):
    def check(self, text: str) -> SafetyResult: ...


def _length(text: str) -> SafetyResult | None:
    if not text.strip():
        return SafetyResult(False, "Ask a question about this moment.", "length")
    if len(text) > MAX_QUESTION_CHARS:
        return SafetyResult(False, "That question is too long; keep it short.", "length")
    return None


ATTACK = re.compile(
    r"ignore (all |the )?(previous|above|prior) instructions|system prompt|you are now|jailbreak",
    re.IGNORECASE,
)
HARM = re.compile(r"\b(kill|hate|bomb)\b", re.IGNORECASE)


class FakeSafety:
    """Deterministic stand-in: a few patterns for prompt attacks and harm."""

    def __init__(self) -> None:
        self.calls = 0

    def check(self, text: str) -> SafetyResult:
        self.calls += 1
        if short := _length(text):
            return short
        if ATTACK.search(text):
            return SafetyResult(False, REFUSE_ATTACK, "prompt_shield")
        if HARM.search(text):
            return SafetyResult(False, REFUSE_HARM, "harm")
        return SafetyResult(True)


REFUSE_ATTACK = "I can only talk about the football on screen."
REFUSE_HARM = "I can't answer that one. Ask me about the play instead."


def _urllib_post(url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"content safety HTTP {err.code}: {detail}") from err


def content_safety_endpoint(env: dict[str, str]) -> str:
    """``CHALKTALK_CONTENT_SAFETY_ENDPOINT``, else the AIServices endpoint the OpenAI one names."""
    if env.get("CHALKTALK_CONTENT_SAFETY_ENDPOINT"):
        return env["CHALKTALK_CONTENT_SAFETY_ENDPOINT"].rstrip("/")
    base = (env.get("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
    return base.replace(".openai.azure.com", ".cognitiveservices.azure.com")


class AzureContentSafety:
    """Prompt Shields (user prompt attack) and text analysis (hate, sexual, violence, self-harm).
    Any service error fails closed: the question is refused, never sent to the crew unchecked."""

    def __init__(self, endpoint: str, key: str, *, post: Post | None = None) -> None:
        if not (endpoint and key):
            raise RuntimeError("content safety needs an endpoint and AZURE_OPENAI_API_KEY")
        self.endpoint = endpoint.rstrip("/")
        self._key = key
        self.post = post or _urllib_post
        self.calls = 0

    def __repr__(self) -> str:
        return f"AzureContentSafety(endpoint={self.endpoint!r})"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, **kw: Any) -> AzureContentSafety:
        env = dict(os.environ) if env is None else env
        return cls(content_safety_endpoint(env), env.get("AZURE_OPENAI_API_KEY") or "", **kw)

    def _call(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        url = f"{self.endpoint}/contentsafety/text:{op}?api-version={API_VERSION}"
        headers = {"Content-Type": "application/json", "Ocp-Apim-Subscription-Key": self._key}
        return self.post(url, headers, json.dumps(payload).encode())

    def check(self, text: str) -> SafetyResult:
        if short := _length(text):
            return short
        try:
            shield = self._call("shieldPrompt", {"userPrompt": text, "documents": []})
            if shield.get("userPromptAnalysis", {}).get("attackDetected"):
                return SafetyResult(False, REFUSE_ATTACK, "prompt_shield")
            harm = self._call("analyze", {"text": text, "outputType": "FourSeverityLevels"})
        except Exception as err:  # noqa: BLE001 - fail closed
            return SafetyResult(
                False, "The safety check is unavailable; try again.", f"error: {err}"
            )
        worst = max((c.get("severity") or 0 for c in harm.get("categoriesAnalysis", [])), default=0)
        if worst > MAX_SEVERITY:
            return SafetyResult(False, REFUSE_HARM, "harm")
        return SafetyResult(True)
