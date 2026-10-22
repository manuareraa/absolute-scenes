"""A generated match: compact arrays plus contract-shaped views."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from chalktalk_core.geometry import FRAME_MS

from .teams import CLUBS, Player

# Column order of ``Match.players``.
PX, PY, PV, PHEAD, PBODY = range(5)
# Column order of ``Match.ball``.
BX, BY, BZ, BV, BOWNER = range(5)


@dataclass
class Match:
    """Arrays are indexed [tick, ...]; one tick is ``FRAME_MS`` (40 ms, 25 fps).

    ``players``: float32 (T, N, 5) with x, y, speed, heading, body heading.
    ``ball``: float32 (T, 5) with x, y, z, speed and the owner's index (-1 for none).
    ``period``: int8 (T,).
    """

    seed: int
    lineup: list[Player]
    players: np.ndarray
    ball: np.ndarray
    period: np.ndarray
    events: list[dict[str, Any]]
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def n_frames(self) -> int:
        return int(self.period.shape[0])

    @property
    def duration_ms(self) -> int:
        return self.n_frames * FRAME_MS

    def tick(self, t_ms: int) -> int:
        """Index of the frame at or just before match time ``t_ms``."""
        return int(min(max(t_ms // FRAME_MS, 0), self.n_frames - 1))

    def frame(self, i: int) -> dict[str, Any]:
        """Frame ``i`` as a ``frame.schema.json`` document."""
        p = self.players[i]
        b = self.ball[i]
        owner = int(b[BOWNER])
        players = []
        for k, pl in enumerate(self.lineup):
            players.append(
                {
                    "id": pl.id,
                    "team": pl.team,
                    "x": round(float(p[k, PX]), 2),
                    "y": round(float(p[k, PY]), 2),
                    "v": round(float(p[k, PV]), 2),
                    "heading": round(float(p[k, PHEAD]), 1),
                    "body_heading": round(float(p[k, PBODY]), 1),
                }
            )
        return {
            "t": i * FRAME_MS,
            "period": int(self.period[i]),
            "ball": {
                "x": round(float(b[BX]), 2),
                "y": round(float(b[BY]), 2),
                "z": round(float(b[BZ]), 2),
                "v": round(float(b[BV]), 2),
                "owner": self.lineup[owner].id if owner >= 0 else None,
            },
            "players": players,
        }

    def frames(self, start: int = 0, stop: int | None = None, step: int = 1) -> Iterator[dict]:
        stop = self.n_frames if stop is None else min(stop, self.n_frames)
        for i in range(start, stop, step):
            yield self.frame(i)

    def events_between(self, start_t: int, end_t: int) -> list[dict[str, Any]]:
        return [e for e in self.events if start_t <= e["t"] <= end_t]

    def info(self) -> dict[str, Any]:
        teams = {}
        for key, club in CLUBS.items():
            teams[key] = {
                "name": club.name,
                "short": club.short,
                "formation": club.formation,
                "colours": list(club.colours),
                "players": [
                    {"id": p.id, "number": p.number, "name": p.name, "role": p.role}
                    for p in self.lineup
                    if p.team == key
                ],
            }
        return {
            "match_id": match_id(self.seed),
            "seed": self.seed,
            "fps": 1000 // FRAME_MS,
            "duration_ms": self.duration_ms,
            "teams": teams,
            "referee": [p.id for p in self.lineup if p.team == "ref"],
            **self.meta,
        }

    def digest(self) -> str:
        """sha256 over the arrays and events; equal digests mean identical matches."""
        h = hashlib.sha256()
        for arr in (self.players, self.ball, self.period):
            h.update(np.ascontiguousarray(arr).tobytes())
        h.update(json.dumps(self.events, sort_keys=True, separators=(",", ":")).encode())
        return h.hexdigest()


def match_id(seed: int) -> str:
    return f"sim-{seed}"
