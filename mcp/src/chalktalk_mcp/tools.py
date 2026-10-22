"""The Analyst's tools, as plain functions over a :class:`Store`.

Every tool returns a dict with the metric, value, unit, ``evidence_window``, drawable
``geometry`` (stroke shapes in pitch metres), ``details`` and a ``tool_call``
``{id, name, args, output_hash}`` ready to copy into a ``claim``. ``output_hash`` is the
sha256 of the canonical JSON of everything except the ``tool_call`` itself, so the Verifier
can re-run the same name and args (``verify``) and compare hashes or values.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from chalktalk_core import analytics as an
from chalktalk_core import ghost as gh
from chalktalk_core import summary
from chalktalk_core.geometry import attack_sign
from chalktalk_core.provenance import canonical_json, normalise, output_hash

from .store import Store

MAX_EVENTS = 200
MAX_PAD_MS = 10_000
MAX_REPLAY_MS = 60_000
NOT_EVIDENCE = ("list_matches", "verify", "evidence")
VAR_LOOKBACK_MS = 15_000
MAX_MOMENTS = 10
EVENT_FIELDS = ("id", "t", "type", "actors", "team", "attrs")

ToolFn = Callable[..., dict[str, Any]]


def _call_id(name: str, args: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json({"name": name, "args": args}).encode()).hexdigest()
    return f"tc_{name}_{digest[:12]}"


def _seal(name: str, args: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    args = normalise(args)
    body = normalise(body)
    body["tool_call"] = {
        "id": _call_id(name, args),
        "name": name,
        "args": args,
        "output_hash": output_hash(body),
    }
    return body


def _result(name: str, args: dict[str, Any], match_id: str, r: an.Result) -> dict[str, Any]:
    return _seal(name, args, {"match_id": match_id, **r.to_dict()})


class Tools:
    """Bound to one store; each public method is one MCP tool."""

    def __init__(self, store: Store):
        self.store = store

    # ----------------------------------------------------------------- match data
    def list_matches(self) -> dict[str, Any]:
        """Matches the tools can read (packages on disk and matches already generated)."""
        return {"matches": self.store.list()}

    def match_info(self, match_id: str) -> dict[str, Any]:
        """Teams, players (id, number, name, role), duration, score and chunk index."""
        src = self.store.get(match_id)
        info = {k: v for k, v in src.info.items() if k not in ("calibration", "chunks")}
        return _seal("match_info", {"match_id": match_id}, info)

    def frame(self, match_id: str, t: int) -> dict[str, Any]:
        """Positions of the ball and all players at match time t (ms)."""
        src = self.store.get(match_id)
        fr = src.frame(t)
        body = {
            "match_id": match_id,
            "metric": "frame",
            "value": fr["t"],
            "unit": "ms",
            "evidence_window": {"start_t": fr["t"], "end_t": fr["t"]},
            "geometry": [],
            "details": {"frame": fr},
        }
        return _seal("frame", {"match_id": match_id, "t": t}, body)

    def events(
        self,
        match_id: str,
        start_t: int = 0,
        end_t: int | None = None,
        types: list[str] | None = None,
        team: str | None = None,
    ) -> dict[str, Any]:
        """Events in [start_t, end_t], optionally filtered by type and team (max 200)."""
        src = self.store.get(match_id)
        end = src.duration_ms if end_t is None else int(end_t)
        want = set(types or ())
        hits = [
            {k: e[k] for k in EVENT_FIELDS if k in e}
            for e in src.events()
            if start_t <= e["t"] <= end
            and (not want or e["type"] in want)
            and (team is None or e.get("team") == team)
        ]
        counts: dict[str, int] = {}
        for e in hits:
            counts[e["type"]] = counts.get(e["type"], 0) + 1
        body = {
            "match_id": match_id,
            "metric": "events",
            "value": len(hits),
            "unit": "count",
            "evidence_window": {"start_t": int(start_t), "end_t": end},
            "geometry": [],
            "details": {
                "counts": counts,
                "events": hits[:MAX_EVENTS],
                "truncated": len(hits) > MAX_EVENTS,
            },
        }
        args = {
            "match_id": match_id,
            "start_t": start_t,
            "end_t": end_t,
            "types": types,
            "team": team,
        }
        return _seal("events", args, body)

    # ----------------------------------------------------------------- summaries
    def half_time(self, match_id: str, n: int = 3) -> dict[str, Any]:
        """Half-time summary: the n moments that decided the first half (goals, red cards,
        big chances, offsides near goal) in match order, the score and per-team stats."""
        src = self.store.get(match_id)
        end = next(
            (
                e["t"]
                for e in src.events()
                if e["type"] == "period_end" and e.get("attrs", {}).get("period") == 1
            ),
            src.duration_ms // 2,
        )
        args = {"match_id": match_id, "n": n}
        return self._summary("half_time", args, match_id, 0, end, n)

    def catch_up(self, match_id: str, t: int, since_t: int = 0, n: int = 3) -> dict[str, Any]:
        """Catch-up for a viewer joining at t: the n moments that decided since_t..t, the
        score at t and per-team stats over the window."""
        src = self.store.get(match_id)
        end = src.clamp(t)
        start = min(src.clamp(since_t), end)
        args = {"match_id": match_id, "t": t, "since_t": since_t, "n": n}
        return self._summary("catch_up", args, match_id, start, end, n)

    def _summary(
        self, name: str, args: dict[str, Any], match_id: str, start: int, end: int, n: int
    ) -> dict[str, Any]:
        if not 1 <= n <= MAX_MOMENTS:
            raise ValueError(f"n must be 1..{MAX_MOMENTS}")
        r = summary.summary(self.store.get(match_id).events(), start, end, n, metric=name)
        # Evidence links: every moment carries the tool calls that back it (its events, and
        # the shot's xG where there was one), each re-runnable by the Verifier.
        for m in r.details["moments"]:
            w = m["evidence_window"]
            links = [self.events(match_id, start_t=w["start_t"], end_t=w["end_t"])["tool_call"]]
            if m.get("shot_t") is not None:
                links.append(self.shot_xg(match_id, m["shot_t"], m["shooter"])["tool_call"])
            m["evidence"] = links
        return _result(name, args, match_id, r)

    # ----------------------------------------------------------------- one frame
    def team_shape(self, match_id: str, t: int, team: str) -> dict[str, Any]:
        """Compactness (outfield hull area, m2), width, length, line heights and gaps."""
        fr = self.store.get(match_id).frame(t)
        args = {"match_id": match_id, "t": t, "team": team}
        return _result("team_shape", args, match_id, an.team_shape(fr, team))

    def line_gap(
        self, match_id: str, t: int, team: str, between: str = "defence_midfield"
    ) -> dict[str, Any]:
        """Metres between two lines: 'defence_midfield' or 'midfield_attack'."""
        fr = self.store.get(match_id).frame(t)
        args = {"match_id": match_id, "t": t, "team": team, "between": between}
        return _result("line_gap", args, match_id, an.line_gap(fr, team, between))

    def distance_between(self, match_id: str, t: int, a: str, b: str) -> dict[str, Any]:
        """Distance in metres between two players (ids like 'H04', 'A09')."""
        fr = self.store.get(match_id).frame(t)
        args = {"match_id": match_id, "t": t, "a": a, "b": b}
        return _result("distance_between", args, match_id, an.distance_between(fr, a, b))

    def pressure(self, match_id: str, t: int) -> dict[str, Any]:
        """Probability an opponent reaches the ball carrier within 1.5 s, with the pressers."""
        fr = self.store.get(match_id).frame(t)
        args = {"match_id": match_id, "t": t}
        return _result("pressure", args, match_id, an.pressure_on_ball(fr))

    def pitch_control(
        self,
        match_id: str,
        t: int,
        team: str,
        zone: list[float] | None = None,
        include_grid: bool = False,
    ) -> dict[str, Any]:
        """Share of a zone [x0, y0, x1, y1] (default the whole pitch) the team controls."""
        fr = self.store.get(match_id).frame(t)
        args = {
            "match_id": match_id,
            "t": t,
            "team": team,
            "zone": zone,
            "include_grid": include_grid,
        }
        r = an.pitch_control(fr, team, zone=zone, include_grid=include_grid)
        return _result("pitch_control", args, match_id, r)

    def control_at(self, match_id: str, t: int, team: str, x: float, y: float) -> dict[str, Any]:
        """Probability the team wins a ball played to (x, y) at time t."""
        fr = self.store.get(match_id).frame(t)
        args = {"match_id": match_id, "t": t, "team": team, "x": x, "y": y}
        return _result("control_at", args, match_id, an.control_at(fr, team, x, y))

    def shot_xg(self, match_id: str, t: int, player_id: str | None = None) -> dict[str, Any]:
        """xG of a shot from where the player (default the ball carrier) stands."""
        fr = self.store.get(match_id).frame(t)
        args = {"match_id": match_id, "t": t, "player_id": player_id}
        return _result("shot_xg", args, match_id, an.shot_xg(fr, player_id))

    def offside_line(self, match_id: str, t: int, defending_team: str) -> dict[str, Any]:
        """The defending team's offside line (x) and the attackers beyond it."""
        fr = self.store.get(match_id).frame(t)
        args = {"match_id": match_id, "t": t, "defending_team": defending_team}
        return _result("offside_line", args, match_id, an.offside_line(fr, defending_team))

    def var_offside(self, match_id: str, t: int, player_id: str | None = None) -> dict[str, Any]:
        """VAR offside check of the last pass at or before t (within 15 s; to player_id if
        given, by the scoring team when t falls on a goal or VAR check), judged on the frame
        at the moment of the pass: the line, the receiver's margin (m, > 0 offside) and the
        decision. With no such pass, the frame at t and player_id."""
        src = self.store.get(match_id)
        args = {"match_id": match_id, "t": t, "player_id": player_id}
        lo = t - VAR_LOOKBACK_MS
        team = next(
            (
                e.get("team")
                for e in reversed(src.events())
                if lo <= e["t"] <= t and e["type"] in ("goal", "var_check", "var_decision")
            ),
            None,
        )
        pas = next(
            (
                e
                for e in reversed(src.events())
                if e["type"] == "pass"
                and lo <= e["t"] <= t
                and e.get("attrs", {}).get("receiver")
                and (player_id is None or e["attrs"]["receiver"] == player_id)
                and (team is None or e.get("team") == team)
            ),
            None,
        )
        if pas is not None:
            fr = src.frame(pas["t"])
            receiver, passer = pas["attrs"]["receiver"], (pas.get("actors") or [None])[0]
        elif player_id is not None:
            fr, receiver, passer = src.frame(t), player_id, None
        else:
            raise ValueError(f"no pass in the {VAR_LOOKBACK_MS // 1000} s before t={t}")
        r = an.var_offside(fr, receiver, passer_id=passer)
        if pas is not None:
            r.evidence_window = {"start_t": int(fr["t"]), "end_t": max(int(fr["t"]), int(t))}
            r.details["pass_event"] = pas["id"]
            r.details["pass_outcome"] = pas["attrs"].get("outcome")
        return _result("var_offside", args, match_id, r)

    def pass_options(self, match_id: str, t: int) -> dict[str, Any]:
        """The carrier's pass options: lane risk, control at the receiver, xT gain, offside."""
        fr = self.store.get(match_id).frame(t)
        args = {"match_id": match_id, "t": t}
        return _result("pass_options", args, match_id, an.pass_options(fr))

    def formation(self, match_id: str, t: int, team: str, window_s: float = 30.0) -> dict[str, Any]:
        """The team's formation (e.g. 4-4-2) and each outfield player's role and slot, from
        its average shape over the window_s seconds up to t (0 for the frame at t alone)."""
        src = self.store.get(match_id)
        end = src.frame(t)["t"]
        start = max(0, end - int(window_s * 1000))
        frames = src.window(start, end, max_frames=60)
        args = {"match_id": match_id, "t": t, "team": team, "window_s": window_s}
        return _result("formation", args, match_id, an.formation(frames, team))

    def obso(self, match_id: str, t: int, team: str | None = None) -> dict[str, Any]:
        """Off-ball scoring opportunity: chance of scoring from the next action, with the
        three most dangerous cells. team defaults to the team on the ball."""
        fr = self.store.get(match_id).frame(t)
        args = {"match_id": match_id, "t": t, "team": team}
        return _result("obso", args, match_id, an.obso(fr, team))

    # ----------------------------------------------------------------- windows
    def xt_added(self, match_id: str, start_t: int, end_t: int) -> dict[str, Any]:
        """Expected threat the team on the ball at start_t added by moving it to end_t."""
        src = self.store.get(match_id)
        a, b = src.frame(start_t), src.frame(end_t)
        owner = a["ball"]["owner"]
        team = next((p["team"] for p in a["players"] if p["id"] == owner), None)
        if team not in ("home", "away"):
            raise ValueError(f"no team on the ball at t={a['t']}")
        r = an.xt_added(
            team,
            a["period"],
            (a["ball"]["x"], a["ball"]["y"]),
            (b["ball"]["x"], b["ball"]["y"]),
            a["t"],
        )
        r.evidence_window = {"start_t": a["t"], "end_t": b["t"]}
        r.details["sign"] = attack_sign(team, a["period"])
        args = {"match_id": match_id, "start_t": start_t, "end_t": end_t}
        return _result("xt_added", args, match_id, r)

    def line_breaking_passes(
        self, match_id: str, start_t: int, end_t: int, team: str
    ) -> dict[str, Any]:
        """Completed passes by the team that break opponent lines, with the lines broken and
        the opponents bypassed (max 200 passes)."""
        src = self.store.get(match_id)
        passes = [
            e
            for e in src.events()
            if e["type"] == "pass"
            and e.get("team") == team
            and start_t <= e["t"] <= end_t
            and e["attrs"].get("outcome") == "complete"
        ][:MAX_EVENTS]
        pairs = [(src.frame(e["t"]), e) for e in passes]
        args = {"match_id": match_id, "start_t": start_t, "end_t": end_t, "team": team}
        r = an.line_breaking_passes(pairs, team, (start_t, end_t))
        return _result("line_breaking_passes", args, match_id, r)

    def pressing_intensity(
        self, match_id: str, start_t: int, end_t: int, team: str
    ) -> dict[str, Any]:
        """Mean pressure the team puts on the opposing carrier over a window (max 180 s)."""
        frames = self.store.get(match_id).window(start_t, end_t, max_frames=150)
        args = {"match_id": match_id, "start_t": start_t, "end_t": end_t, "team": team}
        return _result("pressing_intensity", args, match_id, an.pressing_intensity(frames, team))

    def ball_speed(self, match_id: str, start_t: int, end_t: int) -> dict[str, Any]:
        """Top ball speed in a window, e.g. a shot (m/s and km/h)."""
        frames = self.store.get(match_id).window(start_t, end_t, max_frames=5000)
        args = {"match_id": match_id, "start_t": start_t, "end_t": end_t}
        return _result("ball_speed", args, match_id, an.ball_speed(frames))

    def player_run(self, match_id: str, start_t: int, end_t: int, player_id: str) -> dict[str, Any]:
        """A player's path, top speed and distance covered in a window."""
        frames = self.store.get(match_id).window(start_t, end_t, max_frames=5000)
        args = {"match_id": match_id, "start_t": start_t, "end_t": end_t, "player_id": player_id}
        return _result("player_run", args, match_id, an.player_run(frames, player_id))

    def ghost(
        self, match_id: str, player_id: str, start_t: int, end_t: int, baseline_s: float = 60.0
    ) -> dict[str, Any]:
        """Where the player should have been (window max 30 s): a ghost steers to the player's
        slot in the team shape (learned over the baseline_s seconds before start_t) under speed
        and acceleration limits. Returns the ghost path and the real run, the end gap in
        metres, and the change in pitch control, net OBSO and pressing had the player been
        the ghost."""
        if end_t - start_t > 30_000:
            raise ValueError("ghost window is at most 30 s")
        src = self.store.get(match_id)
        frames = src.window(start_t, end_t, max_frames=max(2, (end_t - start_t) // 100 + 1))
        b0 = max(0, start_t - int(baseline_s * 1000))
        baseline = src.window(b0, start_t, max_frames=60) if start_t - b0 >= 1000 else None
        args = {
            "match_id": match_id,
            "player_id": player_id,
            "start_t": start_t,
            "end_t": end_t,
            "baseline_s": baseline_s,
        }
        return _result("ghost", args, match_id, gh.ghost(frames, player_id, baseline))

    # ----------------------------------------------------------------- verifier
    def verify(
        self,
        name: str,
        args: dict[str, Any],
        output_hash: str | None = None,
        value: float | str | bool | None = None,
        tolerance: float | None = None,
    ) -> dict[str, Any]:
        """Re-run a tool call and check it: the hash matches, or the value is within tolerance."""
        if name not in TOOL_NAMES or name in ("verify", "evidence"):
            raise ValueError(f"unknown tool {name!r}")
        out = getattr(self, name)(**args)
        fresh = out["tool_call"]["output_hash"]
        hash_ok = output_hash is not None and fresh == output_hash
        value_ok = None
        diff = None
        if value is not None:
            got = out["value"]
            if isinstance(got, bool) or isinstance(value, bool) or isinstance(got, str):
                value_ok = got == value
            else:
                diff = round(abs(float(got) - float(value)), 6)
                value_ok = diff <= (tolerance or 0.0)
        verified = hash_ok if value_ok is None else value_ok
        return {
            "verified": bool(verified),
            "hash_match": hash_ok,
            "value_ok": value_ok,
            "value": out["value"],
            "diff": diff,
            "output_hash": fresh,
            "evidence_window": out["evidence_window"],
        }

    def evidence(
        self, name: str, args: dict[str, Any], output_hash: str | None = None, pad_ms: int = 2000
    ) -> dict[str, Any]:
        """Everything a tapped number needs to replay and draw its evidence: re-runs the tool
        call (checking output_hash when given), and returns its value, strokes and evidence
        window, a replay window padded by pad_ms each side, the events in it and the ball's
        path through it. The audit trail for one claim."""
        if name not in TOOL_NAMES or name in NOT_EVIDENCE:
            raise ValueError(f"no evidence for tool {name!r}")
        if not 0 <= pad_ms <= MAX_PAD_MS:
            raise ValueError(f"pad_ms must be 0..{MAX_PAD_MS}")
        out = getattr(self, name)(**args)
        match_id = out["match_id"]
        src = self.store.get(match_id)
        w = out["evidence_window"]
        a = max(0, w["start_t"] - pad_ms)
        b = min(src.duration_ms, w["end_t"] + pad_ms)
        if b - a > MAX_REPLAY_MS:  # long windows replay as their last stretch
            a = b - MAX_REPLAY_MS
        hits = [e for e in src.events() if a <= e["t"] <= b]
        trail = [an._pt((f["ball"]["x"], f["ball"]["y"])) for f in src.window(a, b, 40)]
        geometry = list(out.get("geometry", []))
        if len(trail) > 1:
            geometry.append({"shape": "run", "geometry_m": {"points": trail}, "style": {
                "color": "chalk", "dash": True}})  # fmt: skip
        body = {
            "match_id": match_id,
            "metric": "evidence",
            "value": out["value"],
            "unit": out.get("unit"),
            "evidence_window": w,
            "geometry": geometry,
            "details": {
                "claim_tool_call": out["tool_call"],
                "hash_match": None
                if output_hash is None
                else out["tool_call"]["output_hash"] == output_hash,
                "metric": out.get("metric"),
                "replay": {"start_t": a, "end_t": b},
                "events": [{k: e[k] for k in EVENT_FIELDS if k in e} for e in hits[:MAX_EVENTS]],
                "events_total": len(hits),
                "ball_path": trail,
                "details": out.get("details", {}),
            },
        }
        call = {"name": name, "args": args, "output_hash": output_hash, "pad_ms": pad_ms}
        return _seal("evidence", call, body)


TOOL_NAMES = (
    "list_matches",
    "evidence",
    "match_info",
    "frame",
    "events",
    "half_time",
    "catch_up",
    "team_shape",
    "line_gap",
    "distance_between",
    "pressure",
    "pitch_control",
    "control_at",
    "shot_xg",
    "offside_line",
    "var_offside",
    "pass_options",
    "formation",
    "obso",
    "xt_added",
    "line_breaking_passes",
    "pressing_intensity",
    "ball_speed",
    "player_run",
    "ghost",
    "verify",
)
