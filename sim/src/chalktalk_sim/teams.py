"""Fictional clubs, rosters and formations. No real club or player names."""

from __future__ import annotations

from dataclasses import dataclass

# Slots are (role, depth offset in metres from the team block centre, y in metres) for a
# team attacking +x. The keeper's x is absolute and handled separately.
FORMATIONS: dict[str, list[tuple[str, float, float]]] = {
    "4-3-3": [
        ("GK", 0.0, 0.0),
        ("RB", -1.0, -24.0),
        ("RCB", -1.0, -8.5),
        ("LCB", -1.0, 8.5),
        ("LB", -1.0, 24.0),
        ("RCM", 0.0, -14.0),
        ("CM", -0.2, 0.0),
        ("LCM", 0.0, 14.0),
        ("RW", 1.0, -22.0),
        ("ST", 1.15, 0.0),
        ("LW", 1.0, 22.0),
    ],
    "4-4-2": [
        ("GK", 0.0, 0.0),
        ("RB", -1.0, -24.0),
        ("RCB", -1.0, -8.5),
        ("LCB", -1.0, 8.5),
        ("LB", -1.0, 24.0),
        ("RM", 0.0, -22.0),
        ("RCM", 0.0, -7.5),
        ("LCM", 0.0, 7.5),
        ("LM", 0.0, 22.0),
        ("RS", 1.0, -7.0),
        ("LS", 1.0, 7.0),
    ],
}

SHIRTS = [1, 2, 5, 4, 3, 8, 6, 10, 7, 9, 11]


@dataclass(frozen=True)
class Player:
    id: str
    team: str
    number: int
    name: str
    role: str
    depth: float
    width: float


@dataclass(frozen=True)
class Club:
    key: str
    name: str
    short: str
    formation: str
    colours: tuple[str, str]
    surnames: tuple[str, ...]


CLUBS: dict[str, Club] = {
    "home": Club(
        key="home",
        name="Northbridge Rovers",
        short="NBR",
        formation="4-3-3",
        colours=("#1f4fa8", "#ffffff"),
        surnames=(
            "Varnell",
            "Okonde",
            "Thrane",
            "Mallory",
            "Ferreiro",
            "Kessick",
            "Dunmore",
            "Asante-Byrne",
            "Lindqvar",
            "Corrow",
            "Pemberly",
        ),
    ),
    "away": Club(
        key="away",
        name="Saltmere Athletic",
        short="SAL",
        formation="4-4-2",
        colours=("#c8102e", "#111111"),
        surnames=(
            "Hollin",
            "Brackwell",
            "Ndiave",
            "Ostrander",
            "Quillon",
            "Tavish",
            "Merriden",
            "Rocasta",
            "Elvane",
            "Sorrell",
            "Achterby",
        ),
    ),
}


def roster(team: str) -> list[Player]:
    club = CLUBS[team]
    prefix = "H" if team == "home" else "A"
    out = []
    for i, (role, depth, width) in enumerate(FORMATIONS[club.formation]):
        number = SHIRTS[i]
        out.append(
            Player(
                id=f"{prefix}{number:02d}",
                team=team,
                number=number,
                name=club.surnames[i],
                role=role,
                depth=depth,
                width=width,
            )
        )
    return out


REFEREE = Player(id="REF", team="ref", number=0, name="Referee", role="REF", depth=0, width=0)


def lineup() -> list[Player]:
    """Home 11, away 11, then the referee. Index order is the director's array order."""
    return [*roster("home"), *roster("away"), REFEREE]
