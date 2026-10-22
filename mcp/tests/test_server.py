import anyio
from chalktalk_mcp.server import build_server

from mcp import Client


def test_mcp_round_trip(store, owned_t):
    server = build_server(store)

    async def run():
        async with Client(server) as client:
            listed = await client.list_tools()
            names = {t.name for t in listed.tools}
            ok = await client.call_tool("pressure", {"match_id": "sim-11", "t": owned_t})
            bad = await client.call_tool("match_info", {"match_id": "nope"})
            return names, ok, bad

    names, ok, bad = anyio.run(run)
    assert {"pressure", "pitch_control", "verify", "events"} <= names
    assert not ok.is_error
    body = ok.structured_content
    assert body["tool_call"]["output_hash"].startswith("sha256:")
    assert bad.is_error
