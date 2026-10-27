"""The live crew that answers "Ask the pundit": one question about one moment, as AskEvents.

Flow (each step is streamed as it happens):
1. Safety: Prompt Shields and a harm check on the question; a refusal ends the run.
2. Director (code) reads the moment and routes the question: explain, or also "what should
   they have done?".
3. Analyst (Foundry agent) chooses which MCP tools to call; every call is a ``tool`` event.
4. Pundit (Foundry agent) answers in a few sentences; the Verifier (code) checks every number
   against the tools and sends it back with the tool's value, up to ``MAX_REWRITES`` times.
5. Tactician (Foundry agent) proposes offsets for named players; the Critic (code) re-runs the
   frame through ``what_if`` and accepts only if the metrics improve. Accepted moves are drawn
   as ghost players, with before/after values as claims.
6. The overlay: claims and strokes from tool outputs, word cues from Speech, a gate that
   re-runs every claimed tool call. Then ``done`` with the trace id.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import math
import queue
import re
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Any

from chalktalk_contracts import validate
from chalktalk_core.geometry import attack_sign

from ..lang import get_lang, voice_for
from ..script import render
from ..speech import SpeechClient
from . import verify
from .agents import AskRunner, data_block, default_plan
from .safety import SafetyClient
from .toolbox import Call, ToolBox, ToolCapReached, summarise

log = logging.getLogger(__name__)

MAX_REWRITES = 2
ANALYST_CALLS = 5
LOOK_BACK_MS, LOOK_BACK_STEP_MS = 4000, 200  # how far back a loose ball's last touch is sought
MAX_CALLS = 9  # Analyst calls plus up to two what_if runs and slack
DEADLINE_S = 25.0
LEAD_MS = 150
SHAPES = {
    "arrow",
    "run",
    "pass_lane",
    "line",
    "offside_line",
    "zone",
    "ring",
    "spotlight",
    "ghost_path",
    "label",
}
WHAT_IF_INTENT = re.compile(
    # Spanish: every form of "deber" (debieron, debió, debería) and "poder" (pudieron, podría).
    r"\b(should|could|would|instead|what if|better|have done|deb(?:er|ie|i[oó])\w*|"
    r"podr[ií]a\w*|pudi\w*|mejor|qu[eé] pasar[ií]a|en vez)\b",
    re.IGNORECASE,
)
MATCH_ID = re.compile(r"sim-\d+")
LABELS = {
    "en": {
        "pitch_control": "pitch control",
        "line_gap_m": "the gap between the lines",
        "pressure": "pressure on the ball",
        "obso": "the scoring threat",
    },
    "es": {
        "pitch_control": "el control del espacio",
        "line_gap_m": "el hueco entre líneas",
        "pressure": "la presión sobre el balón",
        "obso": "la amenaza de gol",
    },
}
CF_INTRO = {
    "en": "Better: [[{cue}]] {who} {verb} over, and {metric} goes from {before} to {after}.",
    "es": "Mejor: si [[{cue}]] {who} {verb}, {metric} pasa de {before} a {after}.",
}
# The viewer's own idea is answered kept or not: the Critic's verdict is the point.
CF_MINE = {
    "en": {
        True: "Your idea works: [[{cue}]] {who} {verb} over, and {metric} goes from {before} "
        "to {after}.",
        False: "Your idea does not help: when [[{cue}]] {who} {verb} over, {metric} goes from "
        "{before} to {after}.",
    },
    "es": {
        True: "Tu idea funciona: si [[{cue}]] {who} {verb}, {metric} pasa de {before} a {after}.",
        False: "Tu idea no mejora la jugada: si [[{cue}]] {who} {verb}, {metric} pasa de "
        "{before} a {after}.",
    },
}
MAX_MINE = 3  # what_if moves at most 3 players
# With the viewer's idea, the Analyst and Pundit explain the moment; only the Critic, after its
# re-run, may say whether the idea helps.
MINE_QUESTION = {"en": "What happened in this moment?", "es": "¿Qué pasó en esta jugada?"}
MINE_SHIFT_M = 10.0  # and each by at most 10 m
PLAYER_ID = re.compile(r"^[HA]\d{1,2}$")
WHO = {"en": ("{team} number {n}", " and "), "es": ("el número {n} {team}", " y ")}
VERB = {"en": ("moves", "move"), "es": ("se mueve", "se mueven")}
TEAM = {"en": {"home": "home", "away": "away"}, "es": {"home": "local", "away": "visitante"}}
# The control room's step lines, in the viewer's language.
STEPS = {
    "en": {
        "cached": "Answered this before; replaying it.",
        "safe": "Question checked: safe to answer.",
        "moment": "Moment at {clock}: {team} on the ball.",
        "explain": "Explain it.",
        "explain_cf": "Explain it, then test a better option.",
        "explain_mine": "Explain it, then test the viewer's idea.",
        "mine": "The viewer's idea: {moves}.",
        "mine_move": "{who} {dist:.0f} m",
        "choose": "Choosing which tools to run.",
        "analyst_down": "Agent unavailable ({err}); using the default tools.",
        "write": "Writing the answer.",
        "rewrite": "Rewriting with the tool's numbers.",
        "pundit_down": "Agent unavailable ({err}).",
        "fallback": "Using a checked answer written from the tool results.",
        "no_what_if": "The what-if tool is not deployed yet; skipping the better option.",
        "propose": "Proposing a better position.",
        "propose_again": "Trying another change.",
        "rerun": "Re-running the frame with the change.",
        "out_of_calls": "Out of tool calls; no better option tested.",
        "unusable": "unusable proposal",
        "gate_passed": "Gate passed: {n} claims re-run.",
        "gate_failed": "Gate failed: {n} claims re-run.",
        "timeout": "The answer took too long; try again.",
        "problem": "The crew hit a problem: {err}.",
    },
    "es": {
        "cached": "Ya respondida; se repite la respuesta.",
        "safe": "Pregunta revisada: se puede responder.",
        "moment": "Jugada en el {clock}: el balón es del equipo {team}.",
        "explain": "Explicarla.",
        "explain_cf": "Explicarla y probar una opción mejor.",
        "explain_mine": "Explicarla y probar la idea del espectador.",
        "mine": "La idea del espectador: {moves}.",
        "mine_move": "{who} {dist:.0f} m",
        "choose": "Eligiendo qué herramientas ejecutar.",
        "analyst_down": "Agente no disponible ({err}); se usan las herramientas por defecto.",
        "write": "Escribiendo la respuesta.",
        "rewrite": "Reescribiendo con los números de la herramienta.",
        "pundit_down": "Agente no disponible ({err}).",
        "fallback": "Respuesta verificada, escrita con los resultados de las herramientas.",
        "no_what_if": "La herramienta what-if no está desplegada; no se prueba otra opción.",
        "propose": "Proponiendo una posición mejor.",
        "propose_again": "Probando otro cambio.",
        "rerun": "Volviendo a jugar la imagen con el cambio.",
        "out_of_calls": "Sin llamadas a herramientas; no se probó otra opción.",
        "unusable": "propuesta inservible",
        "gate_passed": "Control superado: {n} datos comprobados de nuevo.",
        "gate_failed": "Control no superado: {n} datos comprobados de nuevo.",
        "timeout": "La respuesta tardó demasiado; inténtalo de nuevo.",
        "problem": "El equipo tuvo un problema: {err}.",
    },
}
# Refusals by the check that refused, for the viewer (the English text is the safety module's).
REFUSALS_ES = {
    "length": "Haz una pregunta corta sobre esta jugada.",
    "prompt_shield": "Solo puedo hablar del fútbol que hay en pantalla.",
    "harm": "No puedo responder a eso. Pregúntame por la jugada.",
}


def step_text(lang: str, key: str, **kw: Any) -> str:
    return STEPS["es" if lang.startswith("es") else "en"][key].format(**kw)


CF_UNITS = {"pitch_control": "share", "line_gap_m": "m", "pressure": "prob", "obso": "xG"}
# What each tool's number is, in the viewer's language. The Pundit names a number only with its
# own label, so a pitch-control share is never called "pressure" and Spanish stays Spanish.
METRIC_LABELS = {
    "en": {
        "pitch_control": "the {team} team's share of pitch control",
        "control_at": "the {team} team's chance to win a ball played there",
        "pressure_on_ball": "the pressure on the player with the ball",
        "pressing_intensity": "the {team} team's pressing intensity",
        "line_gap": "the gap between the {team} team's lines",
        "team_shape": "the area the {team} team covers",
        "distance_between": "the distance between {a} and {b}",
        "shot_xg": "the chance of a goal from a shot here (xG)",
        "xt_added": "the threat added (xT)",
        "offside_line": "the {team} team's offside line",
        "var_offside": "the VAR check on {player}",
        "pass_options": "the safe passing options",
        "ball_speed": "the ball's speed",
        "player_run": "{player}'s top speed",
        "formation": "the {team} team's formation",
        "line_breaking_passes": "the {team} team's passes that broke a line",
        "obso": "the scoring threat (xG)",
    },
    "es": {
        "pitch_control": "el control del espacio del equipo {team}",
        "control_at": "la probabilidad de que el equipo {team} gane un balón jugado ahí",
        "pressure_on_ball": "la presión sobre el jugador con el balón",
        "pressing_intensity": "la intensidad de la presión del equipo {team}",
        "line_gap": "el hueco entre las líneas del equipo {team}",
        "team_shape": "el área que cubre el equipo {team}",
        "distance_between": "la distancia entre {a} y {b}",
        "shot_xg": "la probabilidad de gol de un disparo desde aquí (xG)",
        "xt_added": "la amenaza añadida (xT)",
        "offside_line": "la línea del fuera de juego del equipo {team}",
        "var_offside": "la revisión del VAR sobre {player}",
        "pass_options": "las opciones de pase seguras",
        "ball_speed": "la velocidad del balón",
        "player_run": "la velocidad máxima de {player}",
        "formation": "el sistema del equipo {team}",
        "line_breaking_passes": "los pases del equipo {team} que rompieron una línea",
        "obso": "la amenaza de gol (xG)",
    },
}
NOT_MEASURED = {
    "en": {"pressure_on_ball": "pressure on the ball: nobody had the ball at that moment"},
    "es": {"pressure_on_ball": "presión sobre el balón: nadie tenía el balón en ese momento"},
}
# Tools that set the scene but give no number to quote.
UNQUOTED = ("frame", "events", "match_info", "what_if")


def metric_label(c: Call, lang: str) -> str:
    """The tool's number named in the viewer's language, with the team or players it is about."""
    metric = str(c.out.get("metric") or c.name)
    lng = "es" if lang.startswith("es") else "en"
    template = METRIC_LABELS[lng].get(metric)
    if template is None:
        return metric.replace("_", " ")
    args = c.args
    team = args.get("team") or args.get("defending_team")
    names = {
        "team": TEAM[lng].get(str(team), ""),
        "a": args.get("a", ""),
        "b": args.get("b", ""),
        "player": args.get("player_id", ""),
    }
    return " ".join(template.format(**names).split()).replace(" 's", "'s")


def _say(c: Call, lang: str) -> str:
    """The result's spoken form. The offside line's value is a signed pitch coordinate, so it
    is said as a distance from halfway ("6.3 m from halfway"), never as "-6.3 m"."""
    value, unit = c.out.get("value"), c.out.get("unit")
    if c.name == "offside_line" and isinstance(value, int | float):
        dist = verify.say(abs(value), unit, lang)
        return (
            f"a {dist} de la línea de medio campo"
            if lang.startswith("es")
            else f"{dist} from halfway"
        )
    if c.name == "var_offside" and isinstance(value, int | float):
        dist = verify.say(abs(value), unit, lang)
        if lang.startswith("es"):
            return f"fuera de juego por {dist}" if value > 0 else f"en posición legal por {dist}"
        return f"offside by {dist}" if value > 0 else f"onside by {dist}"
    return verify.say(value, unit, lang)


@dataclass(frozen=True)
class AskRequest:
    show_id: str
    match_tc: int
    question: str
    lens: str = "casual"
    side: str = "neutral"
    lang: str = "en-GB"
    # The viewer's own idea: (player_id, x, y) targets in pitch metres, "You be the tactician".
    moves: tuple[tuple[str, float, float], ...] = ()

    @classmethod
    def from_json(cls, body: dict[str, Any]) -> AskRequest:
        lens, side = body.get("lens") or "casual", body.get("side") or "neutral"
        if lens not in ("casual", "analyst", "newcomer") or side not in ("home", "away", "neutral"):
            raise ValueError("lens or side is not one of the allowed values")
        lang = body.get("lang") or "en-GB"
        get_lang(lang)  # UnsupportedLanguage is a ValueError
        return cls(
            show_id=str(body["show_id"]),
            match_tc=int(body["match_tc"]),
            question=str(body.get("question") or ""),
            lens=lens,
            side=side,
            lang=lang,
            moves=_moves(body.get("moves")),
        )

    @property
    def match_id(self) -> str:
        m = MATCH_ID.search(self.show_id)
        if not m:
            raise ValueError(f"no match in show id {self.show_id!r}")
        return m.group(0)

    def cache_key(self) -> tuple[Any, ...]:
        q = re.sub(r"[^\w\s]", "", self.question.lower())
        return (
            self.show_id,
            self.match_tc,
            " ".join(q.split()),
            self.lens,
            self.side,
            self.lang,
            self.moves,
        )


def _moves(raw: Any) -> tuple[tuple[str, float, float], ...]:
    """The viewer's dragged players, checked: 1..3 players of one team, finite coordinates."""
    if not raw:
        return ()
    if not isinstance(raw, list) or len(raw) > MAX_MINE:
        raise ValueError(f"moves: give 1..{MAX_MINE} players")
    out = []
    for m in raw:
        pid = str(m.get("player_id") or "") if isinstance(m, dict) else ""
        if not PLAYER_ID.match(pid):
            raise ValueError("moves: bad player_id")
        x, y = float(m["x"]), float(m["y"])
        if not (math.isfinite(x) and math.isfinite(y) and abs(x) <= 60 and abs(y) <= 40):
            raise ValueError("moves: x or y off the pitch")
        out.append((pid, round(x, 2), round(y, 2)))
    if len({p[0] for p in out}) != len(out) or len({p[0][0] for p in out}) != 1:
        raise ValueError("moves: each player once, all from one team")
    return tuple(out)


class Cancelled(RuntimeError):
    pass


class Emitter:
    """Numbers events, stamps them with ms since the request began and hands them on."""

    def __init__(self, sink: Callable[[dict[str, Any]], None], start: float | None = None):
        self.sink = sink
        self.start = time.monotonic() if start is None else start
        self.seq = 0
        self.cancelled = False

    def __call__(self, type_: str, **fields: Any) -> dict[str, Any]:
        if self.cancelled:
            raise Cancelled()
        ev = {"type": type_, "seq": self.seq, "t_ms": int((time.monotonic() - self.start) * 1000)}
        ev.update({k: v for k, v in fields.items() if v is not None})
        self.seq += 1
        self.sink(ev)
        return ev

    def step(self, agent: str, text: str) -> None:
        self("step", agent=agent, text=text[:400])


@dataclass
class Answer:
    text: str  # with [[call_id]] cue marks
    rounds: int
    fallback: bool = False


@dataclass
class Counterfactual:
    call: Call
    proposal: str
    team: str
    accepted: bool = True
    mine: bool = False  # the viewer's idea, spoken kept or not


@dataclass
class Stats:
    """Counters the evidence note reports (rejection rate, Critic acceptance, latency)."""

    asks: int = 0
    cached: int = 0
    refused: int = 0
    drafts: int = 0
    rejected_drafts: int = 0
    fallbacks: int = 0
    proposals: int = 0
    accepted: int = 0
    latencies_ms: list[int] = field(default_factory=list)


def call_strokes(call: Call) -> list[dict[str, Any]]:
    """A tool call's own geometry as stroke shapes, styles and metres (no timing yet)."""
    team = (call.out.get("details") or {}).get("team")
    out = []
    for g in call.out.get("geometry") or []:
        if g.get("shape") not in SHAPES or not g.get("geometry_m", {}).get("points"):
            continue
        style = {k: v for k, v in (g.get("style") or {}).items() if k in ("color", "width", "dash")}
        style.setdefault("color", team if team in ("home", "away") else "chalk")
        geom = {
            k: v
            for k, v in g["geometry_m"].items()
            if k in ("points", "radius", "player_id", "text")
        }
        out.append({"shape": g["shape"], "geometry_m": geom, "style": style})
    return out


def trace_span(name: str) -> contextlib.AbstractContextManager[str]:
    """An OpenTelemetry span (exported to Foundry when tracing is configured); yields its
    trace id, or a random id when OpenTelemetry is not installed."""

    @contextlib.contextmanager
    def span() -> Iterator[str]:
        try:
            from opentelemetry import trace
        except ImportError:
            yield uuid.uuid4().hex
            return
        with trace.get_tracer("chalktalk.ask").start_as_current_span(name) as s:
            ctx = s.get_span_context()
            yield format(ctx.trace_id, "032x") if ctx.trace_id else uuid.uuid4().hex

    return span()


class AskCrew:
    def __init__(
        self,
        tools: Any,
        runner: AskRunner,
        speech: SpeechClient,
        safety: SafetyClient,
        *,
        deadline_s: float = DEADLINE_S,
        cache_size: int = 256,
        audio_store: Callable[[str, bytes], str] | None = None,
    ) -> None:
        self.tools = tools
        self.runner = runner
        self.speech = speech
        self.safety = safety
        self.deadline_s = deadline_s
        self.audio_store = audio_store
        self.cache: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
        self.cache_size = cache_size
        self.stats = Stats()
        self._lock = threading.Lock()

    # --- streaming ---------------------------------------------------------------------------

    def warm(self, match_id: str) -> None:
        """Load (or generate) the match outside the deadline: a 45-minute-half sim takes ~27 s
        to build the first time, which is the store's cost, not the crew's."""
        store = getattr(self.tools, "store", None)
        if store is not None:
            store.get(match_id)

    def stream(self, req: AskRequest) -> Iterator[dict[str, Any]]:
        """AskEvents as they happen; past the deadline an ``error`` event ends the stream."""
        with contextlib.suppress(ValueError, KeyError):
            self.warm(req.match_id)
        start = time.monotonic()
        q: queue.Queue[dict[str, Any] | None] = queue.Queue()
        emit = Emitter(q.put, start)

        def work() -> None:
            try:
                self.answer(req, emit)
            except Cancelled:
                pass
            except Exception as err:  # noqa: BLE001 - reported to the viewer as an error event
                log.exception("ask %s failed", req.show_id)
                with contextlib.suppress(Cancelled):
                    emit("error", text=step_text(req.lang, "problem", err=type(err).__name__)[:400])
            finally:
                q.put(None)

        threading.Thread(target=work, daemon=True, name="ask").start()
        while True:
            left = self.deadline_s - (time.monotonic() - start)
            try:
                ev = q.get(timeout=max(0.0, left))
            except queue.Empty:
                emit.cancelled = True
                yield {
                    "type": "error",
                    "seq": emit.seq,
                    "t_ms": int((time.monotonic() - start) * 1000),
                    "text": step_text(req.lang, "timeout"),
                }
                return
            if ev is None:
                return
            yield ev

    def ask(self, req: AskRequest) -> list[dict[str, Any]]:
        return list(self.stream(req))

    # --- the run ---------------------------------------------------------------------------

    def answer(self, req: AskRequest, emit: Emitter) -> None:
        with self._lock:
            self.stats.asks += 1
            hit = self.cache.get(req.cache_key())
            if hit is not None:
                self.cache.move_to_end(req.cache_key())
        if hit is not None:
            self.stats.cached += 1
            emit.step("director", step_text(req.lang, "cached"))
            emit("overlay", overlay=hit["overlay"], audio_url=hit.get("audio_url"))
            emit("done", cached=True, trace_id=hit["trace_id"])
            return
        with trace_span("chalktalk.ask") as trace_id:
            verdict = self.safety.check(req.question)
            if not verdict.ok:
                self.stats.refused += 1
                reason = verdict.reason
                if req.lang.startswith("es"):
                    reason = REFUSALS_ES.get(verdict.check, reason)
                emit("refusal", agent="safety", text=reason[:400])
                emit("done", cached=False, trace_id=trace_id)
                return
            emit.step("safety", step_text(req.lang, "safe"))
            match_id = req.match_id
            box = ToolBox(self.tools, match_id, max_calls=ANALYST_CALLS)
            moment: dict[str, int] = {}

            def on_call(c: Call) -> None:
                tool = {"name": c.name, "args": c.args, "summary": summarise(c.out), "ms": c.ms}
                # Drawn at once while the crew thinks, so the viewer sees chalk in seconds; the
                # spoken overlay replaces it. Only once the moment is known.
                sketch = call_strokes(c) if "t" in moment and c.name != "what_if" else []
                if sketch:
                    tool["sketch"] = {"match_tc": moment["t"], "strokes": sketch}
                emit("tool", tool=tool)

            box.on_call = on_call
            ctx = self._moment(box, req)
            moment["t"] = ctx["t"]
            wants_cf = bool(req.moves) or bool(WHAT_IF_INTENT.search(req.question))
            lng = "es" if req.lang.startswith("es") else "en"
            plan = "explain_mine" if req.moves else "explain_cf" if wants_cf else "explain"
            emit.step(
                "director",
                step_text(req.lang, "moment", clock=ctx["clock"], team=TEAM[lng][ctx["attacking"]])
                + " "
                + step_text(req.lang, plan),
            )
            told = replace(req, question=MINE_QUESTION[lng]) if req.moves else req
            self._analyse(told, box, ctx, emit)
            # The Tactician's first proposal needs only the analysis, so it is drafted while the
            # Pundit writes (one Foundry round trip saved on "what should they have done").
            first = None
            if wants_cf and not req.moves and "what_if" in box.available:
                pool = ThreadPoolExecutor(1, thread_name_prefix="ask-tactician")
                first = pool.submit(self._propose, req, ctx, "")
                pool.shutdown(wait=False)
            ans = self._write(told, box, ctx, emit)
            box.max_calls = MAX_CALLS
            if req.moves:
                cf = self._mine(req, box, ctx, emit)
            else:
                cf = self._counterfactual(req, box, ctx, emit, first) if wants_cf else None
            overlay, audio_url = self._overlay(req, box, ans, cf, ctx)
            emit.step(
                "verifier",
                step_text(
                    req.lang,
                    "gate_passed" if overlay["gate"]["passed"] else "gate_failed",
                    n=len(overlay["claims"]),
                ),
            )
            emit("overlay", overlay=overlay, audio_url=audio_url)
            emit("done", cached=False, trace_id=trace_id)
            self.stats.latencies_ms.append(int((time.monotonic() - emit.start) * 1000))
        if overlay["gate"]["passed"]:
            with self._lock:
                self.cache[req.cache_key()] = {
                    "overlay": overlay,
                    "audio_url": audio_url,
                    "trace_id": trace_id,
                }
                while len(self.cache) > self.cache_size:
                    self.cache.popitem(last=False)

    def _moment(self, box: ToolBox, req: AskRequest) -> dict[str, Any]:
        """Who has the ball and who is near it, read silently (not a claim, not drawn)."""
        fr = self.tools.frame(box.match_id, req.match_tc)["details"]["frame"]
        ball = fr["ball"]
        owner = ball.get("owner") or ""
        # A loose ball (a shot or pass in flight) belongs to whoever last touched it: at a goal the
        # ball sits by the beaten keeper, so "nearest player" would name the wrong team.
        touch = owner or self._last_touch(box.match_id, int(fr["t"]))
        attacking = "home" if touch.startswith("H") else "away" if touch.startswith("A") else None
        if attacking is None:  # nobody touched it lately: the team nearer to it
            near = min(
                fr["players"], key=lambda p: (p["x"] - ball["x"]) ** 2 + (p["y"] - ball["y"]) ** 2
            )
            attacking = near["team"]
        players = sorted(
            fr["players"], key=lambda p: (p["x"] - ball["x"]) ** 2 + (p["y"] - ball["y"]) ** 2
        )
        t = int(fr["t"])
        return {
            "t": t,
            "clock": f"{t // 60000:02d}:{t // 1000 % 60:02d}",
            "attacking": attacking,
            "defending": "away" if attacking == "home" else "home",
            "ball_owner": owner or None,
            "last_touch": touch or None,
            "players": [
                {
                    "id": p["id"],
                    "team": p["team"],
                    "dist_to_ball_m": round(
                        ((p["x"] - ball["x"]) ** 2 + (p["y"] - ball["y"]) ** 2) ** 0.5, 1
                    ),
                }
                for p in players[:10]
            ],
        }

    def _last_touch(self, match_id: str, t: int) -> str:
        for back in range(LOOK_BACK_STEP_MS, LOOK_BACK_MS + 1, LOOK_BACK_STEP_MS):
            if t - back < 0:
                break
            fr = self.tools.frame(match_id, t - back)["details"]["frame"]
            if fr["ball"].get("owner"):
                return str(fr["ball"]["owner"])
        return ""

    def _analyse(self, req: AskRequest, box: ToolBox, ctx: dict[str, Any], emit: Emitter) -> None:
        emit.step("analyst", step_text(req.lang, "choose"))
        data = {"question": req.question, "lens": req.lens, "side": req.side, **ctx}
        prompt = f"Question: {req.question}\nPaused at t={ctx['t']} ms.\n{data_block(data)}"
        try:
            self.runner.run("ask-analyst", prompt, box)
        except Cancelled:
            raise
        except Exception as err:  # noqa: BLE001 - the plan below still answers
            emit.step("analyst", step_text(req.lang, "analyst_down", err=type(err).__name__))
        # The question's obvious tools, then the general ones if none of those could measure
        # (shot_xg fails when nobody has the ball).
        for question in (req.question, ""):
            if any(_quotable(c) for c in box.calls):
                break
            for name, args in default_plan(question, ctx):
                with contextlib.suppress(ToolCapReached, KeyError, ValueError, TypeError):
                    box.call(name, args)
        if not box.calls:
            raise RuntimeError("no tool could measure this moment")

    def _results(self, box: ToolBox, lang: str) -> list[dict[str, Any]]:
        out = []
        for c in box.calls:
            if not _quotable(c):
                continue
            out.append(
                {
                    "call_id": c.id,
                    "tool": c.name,
                    "label": metric_label(c, lang),
                    "args": c.args,
                    "say": _say(c, lang),
                }
            )
        return out

    @staticmethod
    def _scene(box: ToolBox, lang: str) -> dict[str, list[Any]]:
        """What the Pundit may say without numbers: the events found, and what could not be
        measured and why, so an answer never claims there is "no data"."""
        events: list[dict[str, Any]] = []
        missing: list[str] = []
        lng = "es" if lang.startswith("es") else "en"
        for c in box.calls:
            if c.name == "events":
                for e in (c.out.get("details") or {}).get("events", [])[-6:]:
                    team = TEAM[lng].get(str(e.get("team")), e.get("team"))
                    events.append({"type": e.get("type"), "team": team})
            elif not _measured(c):
                note = NOT_MEASURED[lng].get(str(c.out.get("metric")))
                if note and note not in missing:
                    missing.append(note)
        return {"events": events[-6:], "not_measured": missing}

    def _write(self, req: AskRequest, box: ToolBox, ctx: dict[str, Any], emit: Emitter) -> Answer:
        lang = req.lang
        calls = [c for c in box.calls if c.name not in ("frame", "events", "match_info")]
        results = self._results(box, lang)
        scene = self._scene(box, lang)
        feedback = ""
        for rnd in range(1, MAX_REWRITES + 2):
            emit.step(
                "pundit",
                step_text(lang, "write" if rnd == 1 else "rewrite"),
            )
            data: dict[str, Any] = {
                "question": req.question,
                "lang": lang,
                "lens": req.lens,
                "side": req.side,
                "attacking": ctx["attacking"],
                "ball_owner": ctx.get("ball_owner"),
                "results": results,
            }
            if scene["events"]:
                data["events"] = scene["events"]
            if scene["not_measured"]:
                data["not_measured"] = scene["not_measured"]
            if feedback:
                data["feedback"] = feedback
            prompt = (
                f"Question: {req.question}\nLanguage: {lang}. Viewer's side: {req.side}.\n"
                + (f"FEEDBACK: {feedback}\n" if feedback else "")
                + data_block(data)
            )
            try:
                text = self.runner.run("ask-pundit", prompt)
            except Cancelled:
                raise
            except Exception as err:  # noqa: BLE001
                emit.step("pundit", step_text(lang, "pundit_down", err=type(err).__name__))
                break
            text = verify.normalize(" ".join(text.replace("*", "").split())[:600])
            result = verify.check(text, calls, lang)
            self.stats.drafts += 1
            findings = result.findings or [
                verify.Finding(
                    verify.CUE.sub("", text)[:200],
                    True,
                    "no numbers to check",
                    shown=verify.NO_NUMBERS[lang.split("-")[0]]
                    if lang.split("-")[0] in verify.NO_NUMBERS
                    else "",
                )
            ]
            for f in findings:
                emit(
                    "verdict",
                    agent="verifier",
                    verdict={
                        "claim": f.claim or "-",
                        "ok": f.ok,
                        "round": rnd,
                        **({"reason": f.shown or f.reason} if f.reason else {}),
                    },
                )
            if result.ok:
                return Answer(text, rnd)
            self.stats.rejected_drafts += 1
            feedback = result.feedback()
        self.stats.fallbacks += 1
        emit.step("verifier", step_text(lang, "fallback"))
        return Answer(self._fallback_text(results), MAX_REWRITES + 1, fallback=True)

    @staticmethod
    def _fallback_text(results: list[dict[str, Any]]) -> str:
        parts = [f"[[{r['call_id']}]] {r['label'].capitalize()}: {r['say']}." for r in results[:3]]
        return " ".join(parts)

    # --- what should they have done? ---------------------------------------------------------

    def _propose(self, req: AskRequest, ctx: dict[str, Any], feedback: str) -> str:
        data = {"question": req.question, "side": req.side, **ctx}
        if feedback:
            data["feedback"] = feedback
        prompt = (
            f"Question: {req.question}\n"
            f"Language: {req.lang}. Write the 'proposal' field in this language; keep player ids "
            "as they are.\n"
            f"Change the defending team ({ctx['defending']}) unless the question is about the "
            "attack.\n" + (f"FEEDBACK: {feedback}\n" if feedback else "") + data_block(data)
        )
        return self.runner.run("ask-tactician", prompt)

    def _counterfactual(
        self,
        req: AskRequest,
        box: ToolBox,
        ctx: dict[str, Any],
        emit: Emitter,
        first: Future[str] | None = None,
    ) -> Counterfactual | None:
        if "what_if" not in box.available:
            emit.step("critic", step_text(req.lang, "no_what_if"))
            return None
        feedback = ""
        for attempt in (1, 2):
            emit.step(
                "tactician",
                step_text(req.lang, "propose" if attempt == 1 else "propose_again"),
            )
            try:
                drafted = first.result() if attempt == 1 and first else None
                plan = _json(drafted or self._propose(req, ctx, feedback))
                team, moves = plan["team"], plan["moves"]
                proposal = str(plan.get("proposal") or "a change of position")[:200]
                emit.step("critic", step_text(req.lang, "rerun"))
                call = box.call("what_if", {"t": ctx["t"], "team": team, "moves": moves})
            except Cancelled:
                raise
            except ToolCapReached:
                emit.step("critic", step_text(req.lang, "out_of_calls"))
                return None
            except Exception as err:  # noqa: BLE001 - a bad proposal is rejected, not fatal
                self.stats.proposals += 1
                feedback = f"that proposal could not be tested: {err}"[:200]
                emit(
                    "counterfactual",
                    agent="critic",
                    counterfactual={
                        "proposal": step_text(req.lang, "unusable"),
                        "accepted": False,
                        "metrics": [],
                    },
                )
                continue
            details = call.out["details"]
            accepted = bool(details["improved"]) and not details["worse"]
            self.stats.proposals += 1
            self.stats.accepted += int(accepted)
            metrics = [
                {"name": name, "before": m["before"], "after": m["after"], "tool_call": call.id}
                for name, m in details["metrics"].items()
            ]
            emit(
                "counterfactual",
                agent="critic",
                counterfactual={
                    "proposal": proposal,
                    "accepted": accepted,
                    "metrics": metrics,
                    "net": len(details["improved"]) - len(details["worse"]),
                },
            )
            if accepted:
                return Counterfactual(call, proposal, team)
            worse = (
                ", ".join(
                    f"{n} {details['metrics'][n]['before']} -> {details['metrics'][n]['after']}"
                    for n in details["worse"]
                )
                or "nothing improved"
            )
            feedback = f"rejected: {worse}"[:200]
        return None

    def _mine(
        self, req: AskRequest, box: ToolBox, ctx: dict[str, Any], emit: Emitter
    ) -> Counterfactual | None:
        """'You be the tactician': the viewer dragged players; the Critic judges their idea with
        the same re-run and the same rule as the Tactician's. No model proposes anything."""
        if "what_if" not in box.available:
            emit.step("critic", step_text(req.lang, "no_what_if"))
            return None
        lng = "es" if req.lang.startswith("es") else "en"
        team = "home" if req.moves[0][0].startswith("H") else "away"
        try:
            moves, said = self._offsets(box.match_id, ctx["t"], team, req.moves)
        except ValueError:
            emit.step("critic", step_text(req.lang, "unusable"))
            return None
        fmt, joiner = WHO[lng]
        proposal = step_text(
            req.lang,
            "mine",
            moves=joiner.join(
                step_text(
                    req.lang,
                    "mine_move",
                    who=fmt.format(team=TEAM[lng][team], n=int(pid[1:])),
                    dist=dist,
                )
                for pid, dist in said
            ),
        )[:200]
        emit.step("tactician", proposal)
        emit.step("critic", step_text(req.lang, "rerun"))
        try:
            call = box.call("what_if", {"t": ctx["t"], "team": team, "moves": moves})
        except ToolCapReached:
            emit.step("critic", step_text(req.lang, "out_of_calls"))
            return None
        details = call.out["details"]
        accepted = bool(details["improved"]) and not details["worse"]
        self.stats.proposals += 1
        self.stats.accepted += int(accepted)
        metrics = [
            {"name": name, "before": m["before"], "after": m["after"], "tool_call": call.id}
            for name, m in details["metrics"].items()
        ]
        emit(
            "counterfactual",
            agent="critic",
            counterfactual={
                "proposal": proposal,
                "accepted": accepted,
                "metrics": metrics,
                "net": len(details["improved"]) - len(details["worse"]),
            },
        )
        if not details["metrics"]:
            return None
        return Counterfactual(call, proposal, team, accepted=accepted, mine=True)

    def _offsets(
        self, match_id: str, t: int, team: str, targets: tuple[tuple[str, float, float], ...]
    ) -> tuple[list[dict[str, Any]], list[tuple[str, float]]]:
        """Target spots -> what_if's own terms. 'Back' runs along the pitch towards the team's own
        goal and 'infield' across it towards the middle, so any drag splits exactly into the
        two (capped at 10 m, as the tool caps it)."""
        fr = self.tools.frame(match_id, t)["details"]["frame"]
        at = {p["id"]: p for p in fr["players"]}
        sign = attack_sign(team, int(fr["period"]))
        moves, said = [], []
        for pid, x, y in targets:
            p = at.get(pid)
            if p is None:
                raise ValueError(f"{pid} is not on the pitch at this moment")
            dx, dy = x - p["x"], y - p["y"]
            dist = math.hypot(dx, dy)
            if dist > MINE_SHIFT_M:
                dx, dy = dx * MINE_SHIFT_M / dist, dy * MINE_SHIFT_M / dist
                dist = MINE_SHIFT_M
            side = math.copysign(1.0, p["y"]) if abs(p["y"]) > 0.5 else 0.0
            moves.append(
                {
                    "player_id": pid,
                    "back_m": round(-sign * dx, 2),
                    "infield_m": round(-side * dy, 2),
                    "to_ball_m": 0.0,
                }
            )
            said.append((pid, dist))
        return moves, said

    # --- the overlay -------------------------------------------------------------------------

    def _overlay(
        self,
        req: AskRequest,
        box: ToolBox,
        ans: Answer,
        cf: Counterfactual | None,
        ctx: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        lang, short = req.lang, req.lang.split("-")[0]
        calls = [c for c in box.calls if c.name != "what_if"]
        text = ans.text
        check = verify.check(text, calls, lang)
        claims: list[dict[str, Any]] = []
        values: dict[str, str] = {}
        cue_of: dict[str, str] = {}
        claims_of: dict[str, list[str]] = {}

        def cue_for(call_id: str) -> str:
            return cue_of.setdefault(call_id, f"k{len(cue_of) + 1}")

        def add_claim(call: Call, value: Any, unit: str | None, slot_text: str) -> str:
            n = len(claims) + 1
            slot = f"v{n}"
            claims.append(
                {
                    "id": f"c{n}",
                    "text_slot": slot,
                    "value": value,
                    "unit": unit,
                    "tool_call": call.out["tool_call"],
                    "evidence_window": call.out["evidence_window"],
                    "tolerance": None,
                    "verified": None,
                }
            )
            claims_of.setdefault(call.id, []).append(f"c{n}")
            values[slot] = slot_text
            return slot

        # Numbers become slots (right to left so spans stay valid), each bound to its call.
        cued = {m.group(1) for m in verify.CUE.finditer(text)}
        for f in sorted(
            (f for f in check.findings if f.ok and f.call_id), key=lambda f: -f.span[0]
        ):
            call = box.by_id(f.call_id)
            assert call is not None
            slot = add_claim(call, call.out["value"], call.out.get("unit"), f.number)
            mark = "" if call.id in cued else f"[[{call.id}]] "
            cued.add(call.id)
            text = text[: f.span[0]] + mark + "{" + slot + "}" + text[f.span[1] :]
        claims.reverse()  # back to reading order (ids stay as numbered)

        if cf is not None:
            text += " " + self._cf_sentence(cf, short, add_claim)

        # Cue marks: tool call ids -> k1, k2 ...; marks for calls without geometry are dropped.
        def recue(m: re.Match[str]) -> str:
            call = box.by_id(m.group(1))
            if call is None or not call.out.get("geometry"):
                return ""
            return f"[[{cue_for(call.id)}]]"

        template = verify.CUE.sub(recue, text)
        voice = voice_for(lang)
        rendered = render(template, values, lang=lang, voice=voice)
        speech = self.speech.synthesize(rendered.ssml)
        audio_url = speech.audio_url
        if audio_url is None and speech.audio and self.audio_store:
            audio_url = self.audio_store(
                hashlib.sha256(speech.audio).hexdigest()[:16], speech.audio
            )
        offsets = {c: speech.bookmarks.get(c, 0) for c in rendered.cue_order}
        strokes = []
        for call_id, cue in cue_of.items():
            call = box.by_id(call_id)
            assert call is not None
            for g in call_strokes(call):
                strokes.append(
                    {
                        "id": f"s{len(strokes) + 1}",
                        **g,
                        "cue_id": cue,
                        "lead_ms": min(LEAD_MS, offsets.get(cue, 0)),
                        "duration_ms": 600,
                        "claim_ids": claims_of.get(call_id, []),
                    }
                )
        script: dict[str, Any] = {
            "ssml": rendered.ssml,
            "text": rendered.text,
            "cues": [{"cue_id": c, "offset_ms": offsets[c]} for c in rendered.cue_order],
            "words": [
                {"text": w.text, "offset_ms": w.offset_ms, "duration_ms": w.duration_ms}
                for w in speech.words
            ],
        }
        if audio_url:
            script["audio_url"] = audio_url
        verified = self._gate(box, claims)
        digest = hashlib.sha256(json.dumps(req.cache_key()).encode()).hexdigest()[:12]
        overlay = {
            "id": f"ask-{digest}",
            "stream_tc": None,
            "match_tc": ctx["t"],
            "surface": "player",
            "claims": claims,
            "strokes": strokes,
            "script": script,
            "camera": {"preset": "tactical"},
            "lens": req.lens,
            "side": req.side,
            "lang": lang,
            "approval": {"state": "auto", "by": "verifier", "at": None},
            "gate": {
                "passed": verified == len(claims),
                "scores": {
                    "claims_verified": verified / len(claims) if claims else 1.0,
                    "rewrite_rounds": float(ans.rounds - 1),
                    "template_fallback": float(ans.fallback),
                    "tool_calls": float(len(box.calls)),
                    "counterfactual": float(cf is not None),
                },
            },
        }
        validate("overlay", overlay)
        return overlay, audio_url

    def _cf_sentence(self, cf: Counterfactual, lang: str, add_claim: Callable[..., str]) -> str:
        lang = lang if lang in CF_INTRO else "en"
        details = cf.call.out["details"]
        # Kept: the biggest gain. Not kept: the biggest loss, else the biggest change.
        pool = details["improved"] if cf.accepted else details["worse"] or list(details["metrics"])
        name = max(
            pool,
            key=lambda n: abs(details["metrics"][n]["after"] - details["metrics"][n]["before"]),
        )
        m = details["metrics"][name]
        unit = CF_UNITS[name]
        fmt, joiner = WHO[lang]
        team = TEAM[lang][cf.team]
        who = joiner.join(
            fmt.format(team=team, n=int(mv["player_id"][1:])) for mv in details["moves"]
        )
        before = add_claim(cf.call, m["before"], unit, verify.say(m["before"], unit, lang))
        after = add_claim(cf.call, m["after"], unit, verify.say(m["after"], unit, lang))
        template = CF_MINE[lang][cf.accepted] if cf.mine else CF_INTRO[lang]
        return template.format(
            who=who,
            verb=VERB[lang][len(details["moves"]) > 1],
            cue=cf.call.id,
            metric=LABELS[lang][name],
            before="{" + before + "}",
            after="{" + after + "}",
        )

    def _gate(self, box: ToolBox, claims: list[dict[str, Any]]) -> int:
        """Re-run each claimed tool call; a claim is verified when the output hash matches."""
        fresh: dict[str, bool] = {}
        for claim in claims:
            tc = claim["tool_call"]
            if tc["id"] not in fresh:
                try:
                    fresh[tc["id"]] = box.rerun(tc)["tool_call"]["output_hash"] == tc["output_hash"]
                except Exception:  # noqa: BLE001
                    fresh[tc["id"]] = False
            claim["verified"] = fresh[tc["id"]]
        return sum(1 for c in claims if c["verified"])


def _measured(call: Call) -> bool:
    """A value the Pundit may quote: pressure with no ball carrier is a default 0, not a reading."""
    out = call.out
    if not isinstance(out.get("value"), int | float | str):
        return False
    details = out.get("details") or {}
    return not ("carrier" in details and details["carrier"] is None)


def _quotable(call: Call) -> bool:
    return call.name not in UNQUOTED and _measured(call)


def _json(text: str) -> dict[str, Any]:
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])
