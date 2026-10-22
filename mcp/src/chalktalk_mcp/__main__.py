"""``python -m chalktalk_mcp [--transport stdio|streamable-http] [--host H] [--port P]``."""

from __future__ import annotations

import argparse
import os

from .server import build_server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="chalktalk_mcp")
    ap.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = ap.parse_args(argv)
    server = build_server()
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run(
            "streamable-http",
            host=args.host,
            port=args.port,
            stateless_http=True,
            json_response=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
