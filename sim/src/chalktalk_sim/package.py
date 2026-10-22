"""Match package writer: the files the browser, the hub and the tools read.

Layout under ``<out>/<match_id>/``::

    manifest.json        match info, chunk index, score, event count
    events.json          all events (event.schema.json), sorted by t
    chunks/c00000.json.gz
                         gzip JSON array of frames (frame.schema.json), CHUNK_MS each

Chunks are streamed one at a time so a full match never sits in memory as JSON.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from chalktalk_core.geometry import FRAME_MS

from .match import Match, match_id

CHUNK_MS = 10_000
FORMAT_VERSION = 1


def _dump(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()


def write_package(match: Match, out: Path | str, chunk_ms: int = CHUNK_MS) -> Path:
    root = Path(out) / match_id(match.seed)
    chunks_dir = root / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    per = chunk_ms // FRAME_MS
    index = []
    for n, start in enumerate(range(0, match.n_frames, per)):
        stop = min(start + per, match.n_frames)
        name = f"chunks/c{n:05d}.json.gz"
        # mtime=0 keeps the bytes identical for identical matches.
        with gzip.GzipFile(root / name, "wb", mtime=0) as fh:
            fh.write(_dump(list(match.frames(start, stop))))
        index.append(
            {
                "file": name,
                "start_t": start * FRAME_MS,
                "end_t": (stop - 1) * FRAME_MS,
                "frames": stop - start,
            }
        )
    (root / "events.json").write_bytes(_dump(match.events))
    manifest = {
        "format": FORMAT_VERSION,
        **match.info(),
        "digest": match.digest(),
        "chunk_ms": chunk_ms,
        "chunks": index,
        "events": {"file": "events.json", "count": len(match.events)},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return root


def read_chunk(root: Path | str, file: str) -> list[dict[str, Any]]:
    with gzip.open(Path(root) / file, "rb") as fh:
        return json.loads(fh.read())
