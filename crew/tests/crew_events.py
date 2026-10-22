"""Synthetic test events (fictional player ids, no real clubs or players)."""


def ev(i, t, type_, team=None, actors=(), **attrs):
    e = {
        "id": f"e{i}",
        "t": t,
        "type": type_,
        "actors": list(actors),
        "source": "sim",
        "confidence": 1.0,
    }
    if team:
        e["team"] = team
    if attrs:
        e["attrs"] = attrs
    return e


def counter_then_foul():
    return [
        ev(1, 600_000, "pass", "home", ["h4"]),
        ev(2, 602_400, "carry", "home", ["h8"]),
        ev(3, 604_100, "pass", "home", ["h8"]),
        ev(4, 605_000, "press", "away", ["a6"]),
        ev(5, 605_600, "foul", "away", ["a6", "h10"]),
    ]


def shot_then_corner():
    return [
        ev(1, 1_830_000, "pass", "away", ["a3"]),
        ev(2, 1_832_200, "shot", "away", ["a9"]),
        ev(3, 1_832_900, "save", "home", ["h1"]),
        ev(4, 1_833_500, "corner", "away", ["a7"]),
    ]


def offside_run():
    return [
        ev(1, 2_400_000, "pass", "home", ["h6"]),
        ev(2, 2_401_200, "offside", "home", ["h11"]),
    ]


ALL = {
    "counter_then_foul": counter_then_foul,
    "shot_then_corner": shot_then_corner,
    "offside_run": offside_run,
}
