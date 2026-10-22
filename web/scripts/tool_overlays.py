"""Overlays built straight from B's analytics tools, for the web fixtures.

Every coordinate is the tool's own geometry and every spoken number is a claim bound to the
tool call that produced it (same output hash), so these need no LLM and pass the gate by
construction. The script is a fixed template rendered by the crew's own renderer and timed by
its fake speech client, as the crew does for its template fallback.
"""

from __future__ import annotations

from typing import Any

from chalktalk_crew.script import check_template, format_value, render
from chalktalk_crew.speech import FakeSpeechClient
from chalktalk_mcp.store import Store
from chalktalk_mcp.tools import Tools

VOICE = {"en-GB": "en-GB-RyanNeural"}
GATE = {
    "passed": True,
    "scores": {"geometry_from_tools": 1.0, "hash_match_rate": 1.0, "template_fallback": 1.0},
}

ToolOut = dict[str, Any]


def tools(half_minutes: float, digest: str) -> Tools:
    """B's tools over the same seeded match the crew cache was made from."""
    t = Tools(Store(half_minutes=half_minutes, prefer_packages=False))
    got = t.store.get("sim-7").match.digest()[:8]
    if got != digest:
        raise SystemExit(f"tool store match {got} != crew cache {digest}")
    return t


def claim(cid: str, slot: str, out: ToolOut, value: Any, unit: str | None, tol: float) -> dict:
    return {
        "id": cid,
        "text_slot": slot,
        "value": value,
        "unit": unit,
        "tool_call": out["tool_call"],
        "evidence_window": out["evidence_window"],
        "tolerance": tol,
        "verified": True,
    }


def overlay(
    oid: str,
    match_tc: int,
    template: str,
    values: dict[str, str],
    strokes: list[tuple[dict[str, Any], str, list[str]]],
    claims: list[dict[str, Any]],
    *,
    lens: str = "analyst",
    side: str = "neutral",
    lang: str = "en-GB",
    camera: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A contract overlay. ``strokes`` are (tool geometry item, cue id, claim ids)."""
    cues = {cue for _, cue, _ in strokes}
    check_template(template, set(values), cues)
    r = render(template, values, lang=lang, voice=VOICE[lang])
    speech = FakeSpeechClient().synthesize(r.ssml)
    out = {
        "id": oid,
        "stream_tc": None,
        "match_tc": match_tc,
        "surface": "show",
        "claims": claims,
        "strokes": [
            {
                "id": f"s{i}",
                "shape": g["shape"],
                "geometry_m": g["geometry_m"],
                **({"style": g["style"]} if "style" in g else {}),
                "cue_id": cue,
                "lead_ms": 150,
                "duration_ms": 1400 if g["shape"] in ("ghost_path", "run") else 600,
                "claim_ids": ids,
            }
            for i, (g, cue, ids) in enumerate(strokes, 1)
        ],
        "script": {
            "text": r.text,
            "ssml": r.ssml,
            "cues": [{"cue_id": c, "offset_ms": speech.bookmarks[c]} for c in r.cue_order],
            "words": [
                {"text": w.text, "offset_ms": w.offset_ms, "duration_ms": w.duration_ms}
                for w in speech.words
            ],
        },
        "lens": lens,
        "side": side,
        "lang": lang,
        "approval": {"state": "auto", "by": None, "at": None},
        "gate": GATE,
    }
    if camera:
        out["camera"] = camera
    return out


# ------------------------------------------------------------------------------------- ghost
GHOST_WINDOW_MS = 6000
GHOST_MIN_GAP_M = 3.0
GHOST_TEMPLATE = (
    "Where should number {shirt} have been? The [[g1]]ghost holds their slot in the team shape, "
    "{gap_m} metres from where they really were. Their [[g2]]real run pulled them out of it; "
    "with the ghost there, pitch control swings by {pc_pts} {points} {way}."
)


def _roster(t: Tools) -> dict[str, dict[str, Any]]:
    """Player id -> roster entry (number, name, role) from match_info."""
    teams = t.match_info("sim-7")["teams"]
    return {p["id"]: p for side in ("home", "away") for p in teams[side]["players"]}


def ghost_overlay(t: Tools, moment_t: int, side: str = "neutral") -> dict[str, Any]:
    """The off-ball player whose drift from their slot cost (or won) the most pitch control
    as the moment built, and their ghost."""
    end = t.store.get("sim-7").clamp(moment_t)
    start = end - GHOST_WINDOW_MS
    fr = t.store.get("sim-7").frame(end)
    roster = _roster(t)
    owner = fr["ball"].get("owner")
    on_ball = next((p["team"] for p in fr["players"] if p["id"] == owner), None)
    defending = [
        p["id"]
        for p in fr["players"]
        if p["id"] in roster and p["team"] != on_ball and roster[p["id"]]["role"] != "GK"
    ]
    runs = [t.ghost("sim-7", pid, start, end) for pid in defending]
    # The ghost that tells the story: out of position by a few metres, and it mattered.
    far = [r for r in runs if r["value"] >= GHOST_MIN_GAP_M] or runs
    best = max(far, key=lambda r: abs(r["details"]["deltas"]["pitch_control"] or 0.0))
    pid = best["details"]["player"]
    delta = best["details"]["deltas"]["pitch_control"] or 0.0
    pc_pts = round(abs(delta) * 100)
    geo = {g["shape"]: g for g in best["geometry"]}
    claims = [
        claim("c1", "gap_m", best, best["value"], "m", 0.5),
        claim("c2", "pc_pts", best, pc_pts, "points", 1.0),
    ]
    values = {
        "shirt": str(roster[pid]["number"]),
        "gap_m": format_value(best["value"], "m"),
        "points": "point" if pc_pts == 1 else "points",
        "way": "their way" if delta >= 0 else "the other way, so the run was the right call",
        "pc_pts": format_value(pc_pts, "points"),
    }
    end_ghost = best["details"]["ghost_end"]
    return overlay(
        f"ov-ghost-m{moment_t}-{pid}-{side}",
        end,
        GHOST_TEMPLATE,
        values,
        [
            (geo["ghost_path"], "g1", ["c1"]),
            (geo["ring"], "g1", ["c1"]),
            (geo["run"], "g2", ["c2"]),
        ],
        claims,
        side=side,
        camera={"preset": "tactical", "target": end_ghost},
    )


# ---------------------------------------------------------------------------------- evidence
EVIDENCE_PAD_MS = 2000
EVENT_KEEP = ("t", "type", "team", "actors")


def evidence_entry(t: Tools, overlay: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
    """What tapping claim ``c`` replays: B's ``evidence`` tool re-run of its call where that
    tool can re-run it, else the claim's own evidence window and the strokes bound to it.

    ``check`` says which: ``match`` (same output hash, or the value within the claim's
    tolerance), ``differs`` (the re-run disagrees; shown, never hidden) or ``window`` (no re-run).
    """
    tc = c["tool_call"]
    own = [
        {k: s[k] for k in ("shape", "geometry_m", "style") if k in s}
        for s in overlay["strokes"]
        if c["id"] in s.get("claim_ids", [])
    ]
    base = {"tool": tc["name"], "args": tc["args"], "claim_value": c["value"], "unit": c["unit"]}
    try:
        args = {"match_id": "sim-7", **tc["args"]}
        e = t.evidence(tc["name"], args, tc["output_hash"], pad_ms=EVIDENCE_PAD_MS)
    except (ValueError, TypeError, KeyError):
        w = c["evidence_window"]
        src = t.store.get("sim-7")
        a, b = (
            max(0, w["start_t"] - EVIDENCE_PAD_MS),
            min(src.duration_ms, w["end_t"] + EVIDENCE_PAD_MS),
        )
        hits = [x for x in src.events() if a <= x["t"] <= b]
        return {
            **base,
            "check": "window",
            "rerun_value": None,
            "hash_match": None,
            "replay": {"start_t": a, "end_t": b},
            "geometry": own,
            "events": [{k: x[k] for k in EVENT_KEEP if k in x} for x in hits],
        }
    d = e["details"]
    v, tol = e["value"], c.get("tolerance") or 0
    close = isinstance(v, int | float) and isinstance(c["value"], int | float)
    ok = d["hash_match"] or (close and abs(v - c["value"]) <= tol + 1e-9) or v == c["value"]
    return {
        **base,
        "check": "match" if ok else "differs",
        "rerun_value": v,
        "hash_match": d["hash_match"],
        "replay": d["replay"],
        "geometry": e["geometry"],
        "events": [{k: x[k] for k in EVENT_KEEP if k in x} for x in d["events"]],
    }


def evidence_map(t: Tools, overlays: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every claim's evidence, keyed by its tool call's output hash (one entry per call)."""
    out: dict[str, dict[str, Any]] = {}
    for o in overlays:
        for c in o["claims"]:
            h = c["tool_call"]["output_hash"]
            if h not in out:
                out[h] = evidence_entry(t, o, c)
    return out


# --------------------------------------------------------------------------------------- VAR
VAR_TEMPLATE = (
    "VAR is checking the goal for [[v1]]offside. The line is the second-last defender at the "
    "moment of the shot, and [[v2]]number {shirt} is {margin_m} metres {way}. "
    "[[v3]]Check complete: {decision}."
)
VAR_DECISIONS = {"goal_stands": "the goal stands", "goal_disallowed": "no goal"}


def var_overlay(t: Tools, goal: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The VAR check on ``goal``: B's ``var_offside`` at the play that made it, and the check's
    own timing (``var_check`` and ``var_decision`` events) for the provisional graphics.

    Returns the overlay and its VAR meta: everything before the ``v3`` cue is provisional."""
    src = t.store.get("sim-7")
    evs = src.events()
    check = next(e for e in evs if e["type"] == "var_check" and e["t"] >= goal["t"])
    decided = next(e for e in evs if e["type"] == "var_decision" and e["t"] >= check["t"])
    scorer = goal["actors"][0]
    shot = max(
        (e for e in evs if e["type"] == "shot" and e["t"] <= goal["t"] and scorer in e["actors"]),
        key=lambda e: e["t"],
    )
    r = t.var_offside("sim-7", shot["t"], scorer)
    d = r["details"]
    margin = round(abs(r["value"]), 2)
    geo = {g["shape"]: g for g in r["geometry"]}
    strokes = [
        (geo["offside_line"], "v1", ["c1"]),
        (geo["line"], "v2", ["c1"]),
        (geo["ring"], "v2", ["c1"]),
    ]
    if "pass_lane" in geo:
        strokes.append((geo["pass_lane"], "v2", ["c1"]))
    strokes.append((geo["label"], "v3", ["c1"]))
    decision = VAR_DECISIONS.get(decided["attrs"]["decision"], decided["attrs"]["decision"])
    values = {
        "shirt": str(_roster(t)[scorer]["number"]),
        "margin_m": format_value(margin, "m"),
        "way": "beyond it" if d["decision"] == "offside" else "behind it",
        "decision": decision,
    }
    ov = overlay(
        f"ov-var-m{goal['t']}-{scorer}",
        shot["t"],
        VAR_TEMPLATE,
        values,
        strokes,
        [claim("c1", "margin_m", r, margin, "m", 0.05)],
        camera={"preset": "tactical", "target": geo["ring"]["geometry_m"]["points"][0]},
    )
    meta = {
        "check_t": check["t"],
        "decision_t": decided["t"],
        "reason": check["attrs"].get("reason"),
        "decision": decided["attrs"]["decision"],
        "offside": d["decision"],
        "decision_cue": "v3",
    }
    return ov, meta


# ---------------------------------------------------------------------------------- summaries
MOMENT_PRE_MS = 6000
MOMENT_POST_MS = 2000


def moment_entry(t: Tools, m: dict[str, Any]) -> dict[str, Any]:
    """What tapping a summary moment replays: the play into it (inside its evidence window) with
    its own geometry, checked by re-running its ``shot_xg`` call through B's ``evidence`` tool
    when it has one."""
    src = t.store.get("sim-7")
    ew = m["evidence_window"]
    w = {
        "start_t": max(ew["start_t"], m["t"] - MOMENT_PRE_MS),
        "end_t": min(ew["end_t"], m["t"] + MOMENT_POST_MS),
    }
    hits = [x for x in src.events() if w["start_t"] <= x["t"] <= w["end_t"]]
    xg = next((c for c in m["evidence"] if c["name"] == "shot_xg"), None)
    entry = {
        "tool": "events",
        "args": {"start_t": w["start_t"], "end_t": w["end_t"]},
        "claim_value": m["headline"],
        "unit": None,
        "check": "window",
        "rerun_value": None,
        "hash_match": None,
        "replay": dict(w),
        "geometry": m["geometry"],
        "events": [{k: x[k] for k in EVENT_KEEP if k in x} for x in hits],
    }
    if xg is not None:
        e = t.evidence("shot_xg", xg["args"], xg["output_hash"], pad_ms=EVIDENCE_PAD_MS)
        ok = e["details"]["hash_match"] or abs(e["value"] - (m["xg"] or 0)) <= 0.005
        entry |= {
            "tool": "shot_xg",
            "args": xg["args"],
            "claim_value": m["xg"],
            "unit": "xG",
            "check": "match" if ok else "differs",
            "rerun_value": e["value"],
            "hash_match": e["details"]["hash_match"],
        }
    return entry


def summary(t: Tools, kind: str, at_t: int | None = None) -> dict[str, Any]:
    """B's ``half_time`` or ``catch_up`` output, with each moment's replay entry."""
    r = t.half_time("sim-7") if kind == "half_time" else t.catch_up("sim-7", at_t)
    moments = sorted(r["details"]["moments"], key=lambda m: m["rank"])
    for m in moments:
        m["replay"] = moment_entry(t, m)
    return {
        "kind": kind,
        "at_t": r["evidence_window"]["end_t"],
        "value": r["value"],
        "score": r["details"]["score"],
        "stats": r["details"]["stats"],
        "geometry": r["geometry"],
        "moments": moments,
        "tool_call": r["tool_call"],
    }
