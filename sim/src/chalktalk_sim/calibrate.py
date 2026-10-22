"""Build the realism reference profile from DFL tracking data (IDSSE, Bassek et al. 2025).

Reads the three DFL XML files of a match (match information, raw events and observed
positions), streams the positions file (several hundred MB) with ``iterparse`` and turns
it into the arrays :func:`realism.samples_from_arrays` takes, so real and simulated
matches are measured by the same code. Only the quantile summaries leave this module:
no real tracking data is shipped or shown.

    python -I -m chalktalk_sim.calibrate MATCH_DIR [MATCH_DIR ...] --out profile.json

Each ``MATCH_DIR`` holds ``matchinformation*.xml``, ``events*.xml`` and ``positions*.xml``
(any names, found by their root element). The data is untrusted: run with ``python -I``
and keep it outside the repository.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .realism import samples_from_arrays, summarise

DT = 0.04  # DFL positions are 25 Hz
KMH = 1 / 3.6
SECTIONS = {"firstHalf": 1, "secondHalf": 2}
OWNER_RADIUS_M = 2.0
KEEPER = "TW"


@dataclass
class Person:
    pid: str
    team: str  # home / away / ref
    keeper: bool = False


@dataclass
class Section:
    """One half: positions (T, N, 2), speeds (T, N) and the ball, NaN where absent."""

    period: int
    xy: np.ndarray
    speed: np.ndarray
    ball_xy: np.ndarray
    ball_speed: np.ndarray
    alive: np.ndarray
    possession: np.ndarray  # 0 none, 1 home, 2 away


@dataclass
class TrackedMatch:
    people: list[Person]
    sections: list[Section] = field(default_factory=list)
    pass_lengths: np.ndarray = field(default_factory=lambda: np.zeros(0))


def _iter_end(path: Path, tag: str) -> Iterator[ET.Element]:
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == tag:
            yield el


def _root_tag(path: Path) -> str:
    """Name of the first element below ``PutDataRequest`` (reads only the head)."""
    for i, (_, el) in enumerate(ET.iterparse(path, events=("start",))):
        if i == 1:
            return el.tag
    return ""


def find_files(match_dir: Path) -> dict[str, Path]:
    kinds = {"MatchInformation": "info", "Event": "events", "Positions": "positions"}
    out = {}
    for p in sorted(match_dir.iterdir()):
        if p.is_file():
            kind = kinds.get(_root_tag(p))
            if kind:
                out[kind] = p
    missing = {"info", "events", "positions"} - set(out)
    if missing:
        raise FileNotFoundError(f"{match_dir}: no {', '.join(sorted(missing))} file")
    return out


def read_info(path: Path) -> tuple[dict[str, str], dict[str, Person]]:
    """Team id -> home/away and person id -> Person for players and referees."""
    teams: dict[str, str] = {}
    people: dict[str, Person] = {}
    for el in _iter_end(path, "Team"):
        side = "home" if el.get("Role") == "home" else "away"
        teams[el.get("TeamId", "")] = side
        for pl in el.iter("Player"):
            pid = pl.get("PersonId", "")
            people[pid] = Person(pid, side, pl.get("PlayingPosition") == KEEPER)
    return teams, people


def read_pass_lengths(path: Path) -> np.ndarray:
    """Lengths (m) of completed passes: from the pass to the recipient's next action."""
    rows: list[tuple[float, float, set[str], str | None]] = []
    for ev in _iter_end(path, "Event"):
        try:
            x, y = float(ev.get("X-Position", "")), float(ev.get("Y-Position", ""))
        except ValueError:
            ev.clear()
            continue
        actors = {v for el in ev.iter() for k, v in el.attrib.items() if k == "Player"}
        recipient = None
        for play in ev.iter("Play"):
            if (
                play.find("Pass") is not None
                and play.get("Evaluation") == "successfullyCompleted"
                and play.get("Recipient")
            ):
                recipient = play.get("Recipient")
        rows.append((x, y, actors, recipient))
        ev.clear()
    lengths = []
    for i, (x, y, _, recv) in enumerate(rows):
        if recv is None:
            continue
        for x2, y2, actors, _ in rows[i + 1 : i + 6]:
            if recv in actors:
                lengths.append(math.hypot(x2 - x, y2 - y))
                break
    return np.array(lengths, dtype=float)


def read_positions(path: Path, teams: dict[str, str], people: dict[str, Person]) -> TrackedMatch:
    """Stream the positions file into per-half arrays (float32, about 25 MB a half)."""
    tracks: dict[tuple[int, str], tuple[np.ndarray, np.ndarray]] = {}
    ball: dict[int, np.ndarray] = {}
    order: list[str] = []
    context = ET.iterparse(path, events=("start", "end"))
    _, root = next(context)
    cur: dict[str, Any] = {}
    buf: list[tuple[float, ...]] = []
    for event, el in context:
        if event == "start":
            if el.tag == "FrameSet":
                cur = dict(el.attrib)
                buf = []
            continue
        if el.tag == "Frame":
            a = el.attrib
            if cur.get("TeamId") == "BALL":
                buf.append(
                    (
                        float(a["N"]),
                        float(a["X"]),
                        float(a["Y"]),
                        float(a.get("S", "nan")),
                        float(a.get("BallStatus", "1")),
                        float(a.get("BallPossession", "0")),
                    )
                )
            else:
                buf.append((float(a["N"]), float(a["X"]), float(a["Y"]), float(a["S"])))
            el.clear()
        elif el.tag == "FrameSet":
            period = SECTIONS.get(cur.get("GameSection", ""))
            arr = np.array(buf, dtype=np.float64)
            if period is not None and len(arr):
                if cur.get("TeamId") == "BALL":
                    ball[period] = arr
                else:
                    pid = cur.get("PersonId", "")
                    if pid not in people:
                        team = teams.get(cur.get("TeamId", ""), "ref")
                        people[pid] = Person(pid, team)
                    if pid not in order:
                        order.append(pid)
                    ns = arr[:, 0].astype(np.int64)
                    tracks[(period, pid)] = (ns, arr[:, 1:].astype(np.float32))
            buf = []
            el.clear()
            root.clear()
    match = TrackedMatch(people=[people[p] for p in order])
    col = {p: i for i, p in enumerate(order)}
    for period in sorted(ball):
        b = ball[period]
        n0 = int(b[:, 0].min())
        t = int(b[:, 0].max()) - n0 + 1
        xy = np.full((t, len(order), 2), np.nan, dtype=np.float32)
        speed = np.full((t, len(order)), np.nan, dtype=np.float32)
        for (p, pid), (ns, vals) in tracks.items():
            if p != period:
                continue
            ok = (ns >= n0) & (ns < n0 + t)
            rows = ns[ok] - n0
            xy[rows, col[pid]] = vals[ok, :2]
            speed[rows, col[pid]] = vals[ok, 2] * KMH
        rows = b[:, 0].astype(np.int64) - n0
        ball_xy = np.full((t, 2), np.nan)
        ball_speed = np.full(t, np.nan)
        alive = np.zeros(t, dtype=bool)
        poss = np.zeros(t, dtype=np.int8)
        ball_xy[rows] = b[:, 1:3]
        ball_speed[rows] = b[:, 3] * KMH
        alive[rows] = b[:, 4] == 1
        poss[rows] = b[:, 5].astype(np.int8)
        match.sections.append(Section(period, xy, speed, ball_xy, ball_speed, alive, poss))
    return match


def owners(sec: Section, team: np.ndarray) -> np.ndarray:
    """Player index on the ball: nearest player of the team in possession, within 2 m."""
    out = np.full(len(sec.xy), -1, dtype=np.int64)
    for side, code in (("home", 1), ("away", 2)):
        cols = np.flatnonzero(team == side)
        rows = np.flatnonzero(sec.alive & (sec.possession == code))
        if not len(cols) or not len(rows):
            continue
        d = np.hypot(
            sec.xy[rows][:, cols, 0] - sec.ball_xy[rows, None, 0],
            sec.xy[rows][:, cols, 1] - sec.ball_xy[rows, None, 1],
        )
        d = np.where(np.isfinite(d), d, np.inf)
        k = np.argmin(d, axis=1)
        near = d[np.arange(len(rows)), k] <= OWNER_RADIUS_M
        out[rows[near]] = cols[k[near]]
    return out


def load_match(match_dir: Path) -> TrackedMatch:
    files = find_files(match_dir)
    teams, people = read_info(files["info"])
    match = read_positions(files["positions"], teams, people)
    match.pass_lengths = read_pass_lengths(files["events"])
    return match


def match_samples(match: TrackedMatch, step: int = 5) -> dict[str, np.ndarray]:
    team = np.array([p.team for p in match.people])
    outfield = np.array([p.team != "ref" and not p.keeper for p in match.people])
    parts = []
    for sec in match.sections:
        parts.append(
            samples_from_arrays(
                xy=sec.xy,
                speed=sec.speed,
                team=team,
                outfield=outfield,
                owner=owners(sec, team),
                period=np.full(len(sec.xy), sec.period),
                ball_speed=sec.ball_speed[sec.alive],
                pass_lengths=np.zeros(0),
                dt=DT,
                step=step,
            )
        )
    out = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    out["pass_length_m"] = match.pass_lengths
    return out


def kinematics(match: TrackedMatch) -> dict[str, list[float]]:
    """Per-player top speed and peak acceleration and deceleration (p99.9 of 25 Hz data)."""
    out: dict[str, list[float]] = {"vmax": [], "vmax_keeper": [], "accel": [], "decel": []}
    for j, person in enumerate(match.people):
        if person.team == "ref":
            continue
        v = np.concatenate([s.speed[:, j] for s in match.sections])
        a = np.concatenate([np.diff(s.speed[:, j]) / DT for s in match.sections])
        v, a = v[np.isfinite(v)], a[np.isfinite(a)]
        if v.size < 25 * 60 * 20:  # at least 20 minutes on the pitch
            continue
        out["vmax_keeper" if person.keeper else "vmax"].append(float(np.quantile(v, 0.999)))
        if not person.keeper:
            out["accel"].append(float(np.quantile(a, 0.999)))
            out["decel"].append(float(-np.quantile(a, 0.001)))
    return out


def fit(kin: dict[str, list[float]]) -> dict[str, float | None]:
    """Suggested :class:`Calibration` fields from pooled per-player kinematics."""

    def agg(key: str, fn: Any) -> float | None:
        vals = kin.get(key) or []
        return round(float(fn(vals)), 2) if vals else None

    return {
        "vmax_mean": agg("vmax", np.mean),
        "vmax_sd": agg("vmax", np.std),
        "vmax_keeper": agg("vmax_keeper", np.mean),
        "accel_max": agg("accel", np.median),
        "decel_max": agg("decel", np.median),
    }


def build(match_dirs: list[Path]) -> dict[str, Any]:
    pooled: dict[str, list[np.ndarray]] = {}
    kin: dict[str, list[float]] = {}
    for d in match_dirs:
        m = load_match(d)
        for k, v in match_samples(m).items():
            pooled.setdefault(k, []).append(v)
        for k, v in kinematics(m).items():
            kin.setdefault(k, []).extend(v)
        del m
    return {
        "source": "IDSSE (Bassek et al. 2025, CC BY 4.0, data by DFL)",
        "matches": len(match_dirs),
        "fit": fit(kin),
        "profile": summarise({k: np.concatenate(v) for k, v in pooled.items()}),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="chalktalk_sim.calibrate", description=__doc__)
    ap.add_argument("match_dirs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    ref = build(args.match_dirs)
    args.out.write_text(json.dumps(ref, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"fit": ref["fit"], "n": {k: v["n"] for k, v in ref["profile"].items()}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
