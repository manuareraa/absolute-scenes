"""Half-time and catch-up summaries: the moments that decided a stretch of play, and the
numbers behind it.

Deterministic, from the event log alone: each candidate moment gets a weight (goals first,
then red cards, then shots by xG, offsides near goal), the top ``n`` are returned in match
order, each with an evidence window, drawable geometry and the drill-down tool calls that
back it. Team stats are counted over the same window.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from . import analytics as an

TEAMS = ("home", "away")
PRE_MS = 8000  # evidence starts this long before a moment (the build-up)
POST_MS = 3000
LINK_MS = 25_000  # a VAR check or decision this soon after a goal belongs to it
SHOT_TO_GOAL_MS = 3000
POSSESSION_CAP_MS = 10_000  # longest gap credited to one on-ball event
ON_BALL = {
    "pass",
    "carry",
    "dribble",
    "shot",
    "clearance",
    "kickoff",
    "free_kick",
    "corner",
    "throw_in",
    "goal_kick",
    "penalty",
}

Event = dict[str, Any]


def _in(e: Event, start: int, end: int) -> bool:
    return start <= e["t"] <= end


def _score_before(events: Sequence[Event], t: int) -> dict[str, int]:
    score = {"home": 0, "away": 0}
    for e in events:
        if e["type"] == "goal" and e["t"] < t:
            score = dict(e["attrs"]["score"])
    return score


def _outcome(shot: Event, events: Sequence[Event]) -> str:
    """A shot's outcome, trusting goal events: a shot logged as "goal" that no goal event
    follows (the ball was cut out in flight) counts as blocked."""
    out = str(shot.get("attrs", {}).get("outcome", "shot"))
    if out != "goal":
        return out
    scored = any(
        e["type"] == "goal"
        and e.get("team") == shot.get("team")
        and 0 <= e["t"] - shot["t"] <= SHOT_TO_GOAL_MS
        for e in events
    )
    return "goal" if scored else "blocked"


def team_stats(events: Sequence[Event], start: int, end: int) -> dict[str, dict[str, Any]]:
    """Per team over [start, end]: goals, shots, on target, xG, passes (completed/attempted),
    pass accuracy, possession (time from each on-ball event to the next, capped at 10 s),
    offsides, fouls and cards."""
    stats = {
        t: {
            "goals": 0,
            "shots": 0,
            "on_target": 0,
            "xg": 0.0,
            "passes": 0,
            "passes_completed": 0,
            "offsides": 0,
            "fouls": 0,
            "cards": 0,
            "possession_ms": 0,
        }
        for t in TEAMS
    }
    window = [e for e in events if _in(e, start, end)]
    for e in window:
        s = stats.get(e.get("team") or "")
        if s is None:
            continue
        a = e.get("attrs", {})
        if e["type"] == "goal":
            s["goals"] += 1
        elif e["type"] == "shot":
            s["shots"] += 1
            s["xg"] += float(a.get("xg", 0.0))
            s["on_target"] += _outcome(e, window) in ("goal", "saved")
        elif e["type"] == "pass":
            s["passes"] += 1
            s["passes_completed"] += a.get("outcome") == "complete"
        elif e["type"] == "offside":
            s["offsides"] += 1
        elif e["type"] == "foul":
            s["fouls"] += 1
        elif e["type"] == "card":
            s["cards"] += 1
    on_ball = [e for e in window if e["type"] in ON_BALL and e.get("team") in TEAMS]
    for a, b in zip(on_ball, [*on_ball[1:], None], strict=True):
        gap = (b["t"] if b else end) - a["t"]
        stats[a["team"]]["possession_ms"] += min(max(gap, 0), POSSESSION_CAP_MS)
    held = sum(s["possession_ms"] for s in stats.values())
    for s in stats.values():
        s["xg"] = round(s["xg"], 3)
        s["pass_accuracy"] = round(s["passes_completed"] / s["passes"], 3) if s["passes"] else None
        s["possession"] = round(s["possession_ms"] / held, 3) if held else None
    return stats


def _shot_geometry(shot: Event, color: str) -> list[dict[str, Any]]:
    a = shot["attrs"]
    start, end = an._pt(a["start"]), an._pt(a["end"][:2])
    return [
        {"shape": "arrow", "geometry_m": {"points": [start, end]}, "style": {"color": color}},
        {
            "shape": "ring",
            "geometry_m": {"points": [start], "radius": 1.5, "player_id": shot["actors"][0]},
        },
    ]


def _at_geometry(e: Event, color: str, text: str) -> list[dict[str, Any]]:
    at = e.get("attrs", {}).get("at")
    if not at:
        return []
    pid = e["actors"][0] if e.get("actors") else None
    ring = {"points": [an._pt(at)], "radius": 1.5}
    if pid:
        ring["player_id"] = pid
    return [
        {"shape": "ring", "geometry_m": ring, "style": {"color": color}},
        {"shape": "label", "geometry_m": {"points": [an._pt(at)], "text": text}},
    ]


def candidates(events: Sequence[Event], start: int, end: int) -> list[dict[str, Any]]:
    """Every moment in [start, end] worth ranking, with its weight."""
    out: list[dict[str, Any]] = []
    window = [e for e in events if _in(e, start, end)]
    shots = [e for e in window if e["type"] == "shot"]
    goal_shots: set[str] = set()
    for e in window:
        team, a = e.get("team"), e.get("attrs", {})
        if e["type"] == "goal":
            before = _score_before(events, e["t"])
            after = a["score"]
            other = "away" if team == "home" else "home"
            swing = before[team] <= before[other]  # equaliser or the lead
            shot = next(
                (
                    s
                    for s in reversed(shots)
                    if s.get("team") == team and 0 <= e["t"] - s["t"] <= SHOT_TO_GOAL_MS
                ),
                None,
            )
            var = [
                v
                for v in window
                if v["type"] in ("var_check", "var_decision")
                and v.get("team") == team
                and 0 < v["t"] - e["t"] <= LINK_MS
            ]
            if shot:
                goal_shots.add(shot["id"])
            decision = next(
                (v["attrs"].get("decision") for v in var if v["type"] == "var_decision"), None
            )
            geometry = _shot_geometry(shot, team) if shot else []
            out.append(
                {
                    "kind": "goal",
                    "weight": 100 + (20 if swing else 0),
                    "t": e["t"],
                    "team": team,
                    "actors": e["actors"],
                    "events": [x["id"] for x in ([shot] if shot else []) + [e] + var],
                    "headline": f"Goal, {team}: {after['home']}-{after['away']}"
                    + (f" (VAR: {decision.replace('_', ' ')})" if decision else ""),
                    "score_after": after,
                    "xg": shot["attrs"].get("xg") if shot else None,
                    "var": {"check_t": var[0]["t"], "decision": decision} if var else None,
                    "end_t": max([e["t"]] + [v["t"] for v in var]),
                    "geometry": geometry,
                    "shot": shot,
                }
            )
        elif e["type"] == "card":
            red = a.get("colour") == "red"
            foul = next(
                (
                    f
                    for f in reversed(window)
                    if f["type"] == "foul" and 0 <= e["t"] - f["t"] <= 2000
                ),
                None,
            )
            out.append(
                {
                    "kind": "card",
                    "weight": 60 if red else 8,
                    "t": e["t"],
                    "team": team,
                    "actors": e["actors"],
                    "events": [x["id"] for x in ([foul] if foul else []) + [e]],
                    "headline": f"{a.get('colour', 'yellow').capitalize()} card, {team}",
                    "geometry": _at_geometry(foul, "danger", "foul") if foul else [],
                }
            )
        elif e["type"] == "offside":
            x = abs(float(a.get("at", [0, 0])[0]))
            if x >= 30:  # only offsides that stopped an attack near goal
                out.append(
                    {
                        "kind": "offside",
                        "weight": 6 + (x - 30) / 4,
                        "t": e["t"],
                        "team": team,
                        "actors": e["actors"],
                        "events": [e["id"]],
                        "headline": f"Offside, {team} attack stopped",
                        "geometry": _at_geometry(e, "danger", "offside"),
                    }
                )
    for s in shots:
        if s["id"] in goal_shots:
            continue
        a, team = s["attrs"], s.get("team")
        xg = float(a.get("xg", 0.0))
        outcome = _outcome(s, window)
        out.append(
            {
                "kind": "chance",
                "weight": 15 + 70 * xg + (5 if outcome == "saved" else 0),
                "t": s["t"],
                "team": team,
                "actors": s["actors"],
                "events": [s["id"]],
                "headline": f"Chance, {team}: xG {xg:.2f}, {outcome}".replace("_", " "),
                "xg": xg,
                "geometry": _shot_geometry(s, team),
                "shot": s,
            }
        )
    return out


def key_moments(events: Sequence[Event], start: int, end: int, n: int = 3) -> list[dict[str, Any]]:
    """The ``n`` heaviest moments in [start, end], in match order, each with its rank,
    evidence window and geometry (the shot arrow and the shooter, or a ring on the spot)."""
    pool = sorted(candidates(events, start, end), key=lambda m: (-m["weight"], m["t"]))[:n]
    for rank, m in enumerate(pool, 1):
        m["rank"] = rank
        m["weight"] = round(m["weight"], 2)
        m["evidence_window"] = an._window(
            max(0, m["t"] - PRE_MS), min(end, m.pop("end_t", m["t"]) + POST_MS)
        )
    return sorted(pool, key=lambda m: m["t"])


def summary(
    events: Sequence[Event], start: int, end: int, n: int = 3, metric: str = "summary"
) -> an.Result:
    """The moments that decided [start, end] and the team stats over it. The value is the
    score at ``end``; geometry is every moment's strokes, numbered by match order."""
    moments = key_moments(events, start, end, n)
    score = _score_before(events, end + 1)
    geometry: list[dict[str, Any]] = []
    for i, m in enumerate(moments, 1):
        geometry.extend(m["geometry"])
        anchor = m["geometry"][-1]["geometry_m"]["points"][0] if m["geometry"] else None
        if anchor:
            geometry.append({"shape": "label", "geometry_m": {"points": [anchor], "text": str(i)}})
    for m in moments:
        shot = m.pop("shot", None)
        m["shot_t"] = shot["t"] if shot else None
        m["shooter"] = shot["actors"][0] if shot else None
    return an.Result(
        metric=metric,
        value=f"{score['home']}-{score['away']}",
        unit="score",
        evidence_window=an._window(start, end),
        geometry=geometry,
        details={
            "score": score,
            "moments": moments,
            "stats": team_stats(events, start, end),
        },
    )
