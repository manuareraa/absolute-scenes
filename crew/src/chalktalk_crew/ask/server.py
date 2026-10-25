"""``POST /ask``: the live crew over HTTP, streamed as NDJSON AskEvents.

Body: ``{show_id, match_tc, question, lens, side, lang}``. Each line is one AskEvent
(``contracts/schemas/ask-event.schema.json``). ``GET /ask/audio/{key}`` serves answer audio
when Speech returns bytes rather than a URL; ``GET /healthz`` is the container probe.

With ``CHALKTALK_ASK_SECRET`` set, ``/ask`` and ``/ask/audio`` need the same value in
``x-chalktalk-secret`` (the edge Worker's ``ASK_BACKEND_SECRET``); ``/healthz`` stays open.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .crew import AskCrew, AskRequest

MAX_AUDIO = 64


class AudioStore:
    """The last ``MAX_AUDIO`` answers' MP3s in memory (answers are cached per moment anyway)."""

    def __init__(self, prefix: str = "/ask/audio/", *, inline: bool = False) -> None:
        self.prefix = prefix
        self.inline = inline
        self.clips: OrderedDict[str, bytes] = OrderedDict()

    def __call__(self, key: str, audio: bytes) -> str:
        if self.inline:
            # Behind the edge Worker the browser can't reach /ask/audio, so the clip rides in
            # the overlay event itself (an answer is ~20 s of MP3, well under 100 kB).
            return "data:audio/mpeg;base64," + base64.b64encode(audio).decode()
        self.clips[key] = audio
        while len(self.clips) > MAX_AUDIO:
            self.clips.popitem(last=False)
        return self.prefix + key


def create_app(
    crew: AskCrew, audio: AudioStore | None = None, *, secret: str | None = None
) -> Starlette:
    if audio is None:
        audio = crew.audio_store if isinstance(crew.audio_store, AudioStore) else AudioStore()
    if crew.audio_store is None:
        crew.audio_store = audio

    def allowed(request: Request) -> bool:
        if not secret:
            return True
        given = request.headers.get("x-chalktalk-secret", "")
        return hmac.compare_digest(given.encode(), secret.encode())

    async def ask(request: Request) -> Response:
        if not allowed(request):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        try:
            body: Any = await request.json()
            req = AskRequest.from_json(body)
            req.match_id  # noqa: B018 - validates the show id
        except (ValueError, KeyError, TypeError) as err:
            return JSONResponse({"error": str(err)[:200]}, status_code=400)

        def lines() -> Iterator[bytes]:
            for ev in crew.stream(req):
                yield (json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n").encode()

        return StreamingResponse(
            lines(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    async def clip(request: Request) -> Response:
        if not allowed(request):
            return Response(status_code=403)
        data = audio.clips.get(request.path_params["key"])
        if data is None:
            return Response(status_code=404)
        return Response(data, media_type="audio/mpeg")

    async def healthz(_: Request) -> Response:
        return JSONResponse({"ok": True, "asks": crew.stats.asks})

    return Starlette(
        routes=[
            Route("/ask", ask, methods=["POST"]),
            Route("/ask/audio/{key}", clip, methods=["GET"]),
            Route("/healthz", healthz, methods=["GET"]),
        ]
    )


def crew_from_env(env: dict[str, str] | None = None) -> AskCrew:
    """``CHALKTALK_ASK_BACKEND=azure`` for Foundry agents, Azure Speech and Content Safety;
    anything else (the default) runs the fakes, so a bare container never spends tokens.
    ``CHALKTALK_ASK_PRELOAD=sim-7`` builds those matches at start-up, before the first ask."""
    from chalktalk_mcp.store import Store
    from chalktalk_mcp.tools import Tools

    env = dict(os.environ) if env is None else env
    tools = Tools(Store())
    if env.get("CHALKTALK_ASK_BACKEND") == "azure":
        from ..azure import AzureSpeechClient
        from ..config import CrewConfig
        from ..foundry_agents import FoundryRunner, configure_tracing
        from .agents import FoundryAskRunner
        from .safety import AzureContentSafety

        configure_tracing(env.get("AZURE_AI_PROJECT_ENDPOINT"))
        runner = FoundryAskRunner(FoundryRunner.from_env(env))
        speech = AzureSpeechClient(CrewConfig.from_env(env))
        crew = AskCrew(tools, runner, speech, AzureContentSafety.from_env(env))
    else:
        from ..speech import FakeSpeechClient
        from .agents import FakeAskRunner
        from .safety import FakeSafety

        crew = AskCrew(tools, FakeAskRunner(), FakeSpeechClient(), FakeSafety())
    crew.audio_store = AudioStore(inline=env.get("CHALKTALK_ASK_AUDIO", "inline") == "inline")
    for match_id in filter(None, env.get("CHALKTALK_ASK_PRELOAD", "").split(",")):
        crew.warm(match_id.strip())
    return crew
