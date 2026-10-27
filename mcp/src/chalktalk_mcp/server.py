"""MCP server exposing the Analyst's tools (``mcp`` SDK 2.x ``MCPServer``)."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import __version__
from .store import Store, UnknownMatch
from .tools import TOOL_NAMES, Tools

INSTRUCTIONS = """\
Deterministic football analytics over synthetic Absolute Scenes matches (ids like 'sim-7').
Pitch coordinates are metres, origin at the centre, x along the 105 m length, y across the
68 m width; times are match milliseconds. Player ids: 'H01'..'H11' home, 'A01'..'A11' away.
Every result carries an evidence_window, drawable geometry and a tool_call with output_hash:
copy the tool_call into the claim. Never invent coordinates: draw only returned geometry.
Use 'verify' to re-run a tool_call and check a claim's value within tolerance."""

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


def _guard(fn):
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        try:
            return fn(*args, **kwargs)
        except (UnknownMatch, KeyError, ValueError, TypeError) as exc:
            msg = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
            raise ToolError(str(msg)) from exc

    return wrapper


def build_server(store: Store | None = None) -> MCPServer:
    tools = Tools(store or Store())
    server = MCPServer(name="chalktalk-analyst", version=__version__, instructions=INSTRUCTIONS)
    for name in TOOL_NAMES:
        server.add_tool(_guard(getattr(tools, name)), name=name, annotations=READ_ONLY)

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "version": __version__})

    return server
