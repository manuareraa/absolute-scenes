"""Azure clients behind the crew interfaces: a Foundry chat deployment and Azure AI Speech.

Selected by env var (``CHALKTALK_CREW_BACKEND=azure``, or per client ``CHALKTALK_LLM_BACKEND`` /
``CHALKTALK_SPEECH_BACKEND``). Tests and CI never construct these against the network: the
Foundry client takes an injectable ``post`` transport, and the Speech SDK is an optional extra
(``chalktalk-crew[azure]``) imported only when a synthesis runs.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import CrewConfig
from .llm import DraftRequest, render_prompt
from .speech import SpeechResult, WordTiming

# gpt-4.1-mini list prices, USD per 1M tokens (GlobalStandard). For run logs only.
PRICE_IN_PER_M = 0.40
PRICE_OUT_PER_M = 1.60

Post = Callable[[str, dict[str, str], bytes], dict[str, Any]]


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, usage: dict[str, Any]) -> None:
        self.calls += 1
        self.prompt_tokens += int(usage.get("prompt_tokens", 0))
        self.completion_tokens += int(usage.get("completion_tokens", 0))

    @property
    def cost_usd(self) -> float:
        return (
            self.prompt_tokens * PRICE_IN_PER_M + self.completion_tokens * PRICE_OUT_PER_M
        ) / 1e6

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "est_cost_usd": round(self.cost_usd, 6),
        }


class AzureCallError(RuntimeError):
    pass


def _urllib_post(url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:300]
        raise AzureCallError(f"HTTP {err.code}: {detail}") from err


FENCE = re.compile(r"^```[a-z]*\s*|\s*```$")


def clean_template(text: str) -> str:
    """Strip code fences and wrapping quotes a chat model sometimes adds."""
    text = FENCE.sub("", text.strip()).strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


class AzureFoundryLLMClient:
    """Pundit writer on an Azure OpenAI-compatible Foundry deployment (chat completions)."""

    def __init__(
        self,
        config: CrewConfig,
        *,
        post: Post | None = None,
        retries: int = 3,
        temperature: float = 0.4,
    ) -> None:
        if not (config.foundry_endpoint and config.foundry_deployment and config.foundry_api_key):
            raise RuntimeError(
                "Foundry needs AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_KEY"
            )
        self.url = (
            f"{config.foundry_endpoint.rstrip('/')}/openai/deployments/"
            f"{config.foundry_deployment}/chat/completions"
            f"?api-version={config.foundry_api_version}"
        )
        self._key = config.foundry_api_key
        self.max_tokens = config.max_tokens
        self.temperature = temperature
        self.retries = retries
        self.post = post or _urllib_post
        self.usage = Usage()

    def __repr__(self) -> str:
        return f"AzureFoundryLLMClient(url={self.url!r})"

    def draft(self, request: DraftRequest) -> str:
        body = json.dumps(
            {
                "messages": render_prompt(request),
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            }
        ).encode()
        headers = {"Content-Type": "application/json", "api-key": self._key or ""}
        for attempt in range(self.retries + 1):
            try:
                data = self.post(self.url, headers, body)
                break
            except AzureCallError as err:
                retryable = str(err).startswith(("HTTP 429", "HTTP 5"))
                if not retryable or attempt == self.retries:
                    raise
                time.sleep(2**attempt)
        self.usage.add(data.get("usage") or {})
        return clean_template(data["choices"][0]["message"]["content"] or "")


TICKS_PER_MS = 10_000  # the Speech SDK reports offsets in 100 ns ticks


def snap_bookmarks(
    raw: dict[str, int],
    words: list[WordTiming],
    *,
    ssml: str | None = None,
    text_offsets: list[int] | None = None,
) -> dict[str, int]:
    """Cue offset = start of the word the bookmark precedes.

    Exact when ``ssml`` and the words' SSML ``text_offsets`` are given: the first word after the
    bookmark tag. Otherwise the first word starting at or after the bookmark. Spike S1 found
    bookmarks fire 12 ms before their word, or at the start of a pause before it, never after;
    a wider early slack picks the previous short word (docs/notes/c-s1-word-timing.md).
    Bookmarks with no word after them keep their raw offset.
    """
    out: dict[str, int] = {}
    for mark, offset in raw.items():
        nxt: int | None = None
        pos = ssml.find(f"mark='{mark}'") if ssml is not None else -1
        if pos >= 0 and text_offsets is not None:
            after = [(t, w.offset_ms) for t, w in zip(text_offsets, words, strict=True) if t > pos]
            nxt = min(after)[1] if after else None
        else:
            nxt = next((w.offset_ms for w in words if w.offset_ms >= offset), None)
        out[mark] = offset if nxt is None else nxt
    return out


LANG_ATTR = re.compile(r"xml:lang='([a-z]{2})'")


class AzureSpeechClient:
    """Azure AI Speech TTS: MP3 audio, WordBoundary timings and bookmark offsets in ms."""

    def __init__(self, config: CrewConfig, *, snap: bool = True) -> None:
        if not ((config.speech_region or config.speech_endpoint) and config.speech_key):
            raise RuntimeError("Speech needs AZURE_SPEECH_REGION and AZURE_SPEECH_KEY")
        self.region = config.speech_region
        self.endpoint = config.speech_endpoint
        self._key = config.speech_key
        self.voice = config.speech_voice
        self.snap = snap
        self.characters = 0  # billed characters (F0 includes 0.5M a month)

    def __repr__(self) -> str:
        return f"AzureSpeechClient(region={self.region!r}, voice={self.voice!r})"

    def _locale(self, ssml: str) -> str:
        # Azure wants a full locale in xml:lang; take it from the voice name (en-GB-RyanNeural).
        locale = "-".join(self.voice.split("-")[:2])
        return LANG_ATTR.sub(f"xml:lang='{locale}'", ssml)

    def synthesize(self, ssml: str) -> SpeechResult:
        try:
            import azure.cognitiveservices.speech as sdk
        except ImportError as err:  # pragma: no cover - exercised only with the extra installed
            raise RuntimeError(
                "install the Speech SDK: uv run --with azure-cognitiveservices-speech ..."
            ) from err

        if self.endpoint:
            cfg = sdk.SpeechConfig(subscription=self._key, endpoint=self.endpoint)
        else:
            cfg = sdk.SpeechConfig(subscription=self._key, region=self.region)
        cfg.speech_synthesis_voice_name = self.voice
        cfg.set_speech_synthesis_output_format(
            sdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
        )
        synth = sdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
        timed: list[tuple[WordTiming, int]] = []  # (word, its SSML text offset)
        raw: dict[str, int] = {}

        def on_word(evt: Any) -> None:
            if evt.boundary_type == sdk.SpeechSynthesisBoundaryType.Word:
                word = WordTiming(
                    evt.text,
                    round(evt.audio_offset / TICKS_PER_MS),
                    round(evt.duration.total_seconds() * 1000),
                )
                timed.append((word, evt.text_offset))

        def on_mark(evt: Any) -> None:
            raw[evt.text] = round(evt.audio_offset / TICKS_PER_MS)

        synth.synthesis_word_boundary.connect(on_word)
        synth.bookmark_reached.connect(on_mark)
        ssml = self._locale(ssml)
        result = synth.speak_ssml_async(ssml).get()
        if result.reason != sdk.ResultReason.SynthesizingAudioCompleted:
            details = result.cancellation_details
            raise AzureCallError(f"speech failed: {details.reason} {details.error_details}")
        self.characters += len(re.sub(r"<[^>]+>", "", ssml))
        timed.sort(key=lambda wt: wt[0].offset_ms)
        words = [w for w, _ in timed]
        bookmarks = (
            snap_bookmarks(raw, words, ssml=ssml, text_offsets=[t for _, t in timed])
            if self.snap
            else dict(raw)
        )
        return SpeechResult(
            words=words,
            bookmarks=bookmarks,
            duration_ms=round(result.audio_duration.total_seconds() * 1000),
            audio=bytes(result.audio_data),
            extra={f"raw_{k}": str(v) for k, v in raw.items()},
        )
