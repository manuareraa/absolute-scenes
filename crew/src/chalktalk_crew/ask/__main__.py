"""``python -m chalktalk_crew.ask serve|ask|sync``.

- ``serve``: the HTTP service (``PORT``, default 8080).
- ``ask SHOW_ID MATCH_TC QUESTION``: one answer to stdout as NDJSON (``--out`` to save it).
- ``sync``: create the three ask agents on the Foundry project (manual, needs ``az login``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .server import create_app, crew_from_env


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="chalktalk_crew.ask")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    a = sub.add_parser("ask")
    a.add_argument("show_id")
    a.add_argument("match_tc", type=int)
    a.add_argument("question")
    a.add_argument("--lens", default="casual")
    a.add_argument("--side", default="neutral")
    a.add_argument("--lang", default="en-GB")
    a.add_argument("--out")
    sub.add_parser("sync")
    args = p.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run(
            create_app(crew_from_env()), host="0.0.0.0", port=int(os.environ.get("PORT", 8080))
        )
        return 0
    if args.cmd == "sync":
        from chalktalk_mcp.store import Store
        from chalktalk_mcp.tools import Tools

        from .agents import sync_agents
        from .toolbox import ToolBox

        box = ToolBox(Tools(Store()), "sim-1")
        model = os.environ.get("AZURE_OPENAI_DEPLOYMENT") or "gpt-4.1-mini"
        print(json.dumps(sync_agents(os.environ["AZURE_AI_PROJECT_ENDPOINT"], model, box)))
        return 0

    from .crew import AskRequest

    crew = crew_from_env()
    req = AskRequest(args.show_id, args.match_tc, args.question, args.lens, args.side, args.lang)
    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout  # noqa: SIM115
    try:
        for ev in crew.stream(req):
            out.write(json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n")
            out.flush()
    finally:
        if out is not sys.stdout:
            out.close()
    usage = getattr(crew.runner, "usage", None)
    if usage is not None:
        print(json.dumps({"usage": usage.as_dict()}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
