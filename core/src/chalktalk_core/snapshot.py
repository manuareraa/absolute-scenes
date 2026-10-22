"""Array view of one ``frame.schema.json`` document."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .geometry import attack_sign


@dataclass(frozen=True)
class Snapshot:
    t: int
    period: int
    ids: list[str]
    team: np.ndarray  # (N,) str: home, away, ref
    xy: np.ndarray  # (N, 2) metres
    vel: np.ndarray  # (N, 2) m/s, from speed and heading
    ball: np.ndarray  # (3,) x, y, z
    ball_v: float
    owner: str | None

    @classmethod
    def from_frame(cls, frame: dict[str, Any]) -> Snapshot:
        ps = frame["players"]
        heading = np.radians([p["heading"] for p in ps])
        speed = np.array([p["v"] for p in ps], dtype=float)
        b = frame["ball"]
        return cls(
            t=int(frame["t"]),
            period=int(frame["period"]),
            ids=[p["id"] for p in ps],
            team=np.array([p["team"] for p in ps]),
            xy=np.array([[p["x"], p["y"]] for p in ps], dtype=float),
            vel=np.stack([speed * np.cos(heading), speed * np.sin(heading)], axis=1),
            ball=np.array([b["x"], b["y"], b["z"]], dtype=float),
            ball_v=float(b["v"]),
            owner=b.get("owner"),
        )

    def index(self, player_id: str) -> int:
        try:
            return self.ids.index(player_id)
        except ValueError:
            raise KeyError(f"no player {player_id!r} at t={self.t}") from None

    def members(self, team: str) -> np.ndarray:
        return np.flatnonzero(self.team == team)

    def sign(self, team: str) -> int:
        return attack_sign(team, self.period)

    def owner_team(self) -> str | None:
        if self.owner is None:
            return None
        return str(self.team[self.index(self.owner)])

    def keeper(self, team: str) -> int:
        """The team's player deepest toward its own goal."""
        idx = self.members(team)
        return int(idx[np.argmin(self.xy[idx, 0] * self.sign(team))])

    def outfield(self, team: str) -> np.ndarray:
        idx = self.members(team)
        return idx[idx != self.keeper(team)]
