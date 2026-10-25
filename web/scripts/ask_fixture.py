"""Writes the rehearsal feeds for "Ask the pundit": public/fixtures/ask/*.ndjson.

Each feed is what POST /api/ask streams (contracts/schemas/ask-event.schema.json), so the studio UI
can be built and tested without the live crew. The answer overlays are the show's own chapters
(their tool-measured strokes, claims and recorded voice); only the control-room lines around them
are written here. Run from web/: python3 -I scripts/ask_fixture.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOW = ROOT / "public/fixtures/show-sim-7.json"
OUT = ROOT / "public/fixtures/ask"
AUDIO_BASE = "/fixtures/show-sim-7/"

# Control-room lines per language: (type, agent, text or payload). t_ms is spaced out below.
LINES = {
    "counterfactual": {
        "en-GB": {
            "steps": [
                ("director", "Question on the goal at 02:55: what should they have done?"),
                ("analyst", "Measuring where No. 11 was against their slot in the shape"),
                ("tactician", "Proposing a change: No. 11 holds the slot"),
                ("critic", "Re-running pitch control with the ghost in place"),
                ("pundit", "Drafting the answer"),
                ("verifier", "Checking every number against the tools"),
                ("pundit", "Rewriting the rejected line"),
            ],
            "proposal": "No. 11 holds the slot in the team shape",
            "draft": "No. 11 should have held their slot, 8 metres back",
            "draft_reason": "Ghost tool says 6.3 m, and pitch control is 3 points worse with the ghost there",
            "final": "The run was the right call: holding the slot gives up 3 points of pitch control",
            "ghost_summary": "No. 11 was 6.3 m from their slot",
            "pc_summary": "With the ghost there, control swings 3 points the other way",
        },
        "es-ES": {
            "steps": [
                ("director", "Pregunta sobre el gol del 02:55: ¿qué debieron hacer?"),
                ("analyst", "Midiendo dónde estaba el 11 respecto a su sitio en el dibujo"),
                ("tactician", "Propuesta: el 11 mantiene su sitio"),
                ("critic", "Recalculando el control del campo con el fantasma"),
                ("pundit", "Redactando la respuesta"),
                ("verifier", "Comprobando cada cifra con las herramientas"),
                ("pundit", "Reescribiendo la frase rechazada"),
            ],
            "proposal": "El 11 mantiene su sitio en el dibujo del equipo",
            "draft": "El 11 debió quedarse en su sitio, 8 metros atrás",
            "draft_reason": "La herramienta fantasma dice 6,3 m, y el control del campo baja 3 puntos con el fantasma",
            "final": "La carrera fue la decisión correcta: quedarse en el sitio cuesta 3 puntos de control",
            "ghost_summary": "El 11 estaba a 6,3 m de su sitio",
            "pc_summary": "Con el fantasma ahí, el control cambia 3 puntos al rival",
        },
    },
}


def chapter(show_fx: dict, prefix: str, lang: str) -> dict:
    for show in show_fx["shows"]:
        if show["lens"] == "analyst" and show["side"] == "away" and show["lang"] == lang:
            for seg in show["segments"]:
                ov = seg.get("overlay") or {}
                if ov.get("id", "").startswith(prefix):
                    return ov
    raise SystemExit(f"no {prefix} chapter for {lang}")


def counterfactual_feed(show_fx: dict, lang: str) -> list[dict]:
    t = LINES["counterfactual"][lang]
    ov = json.loads(json.dumps(chapter(show_fx, "ov-ghost", lang)))
    ghost_call = ov["claims"][0]["tool_call"]
    gap = next(c["value"] for c in ov["claims"] if c["text_slot"] == "gap_m")
    pc = next(c["value"] for c in ov["claims"] if c["text_slot"] == "pc_pts")
    ov["id"] = f"ask-cf-{ov['id']}"
    ov["surface"] = "player"
    ov["approval"] = {"state": "auto", "by": None, "at": None}
    ov["script"]["audio_url"] = AUDIO_BASE + ov["script"]["audio_url"]
    steps = t["steps"]
    events: list[tuple[str, dict]] = [
        ("step", {"agent": steps[0][0], "text": steps[0][1]}),
        ("step", {"agent": steps[1][0], "text": steps[1][1]}),
        ("tool", {"agent": "analyst", "tool": {"name": "ghost", "args": ghost_call["args"], "summary": t["ghost_summary"], "ms": 412}}),
        ("step", {"agent": steps[2][0], "text": steps[2][1]}),
        ("step", {"agent": steps[3][0], "text": steps[3][1]}),
        ("tool", {"agent": "critic", "tool": {"name": "pitch_control", "args": {"match_id": "sim-7", "t": ov["match_tc"], "ghost": "H11"}, "summary": t["pc_summary"], "ms": 655}}),
        (
            "counterfactual",
            {
                "agent": "critic",
                "counterfactual": {
                    "proposal": t["proposal"],
                    "accepted": False,
                    "metrics": [
                        {"name": "gap_m", "before": gap, "after": 0, "tool_call": ghost_call["id"]},
                        {"name": "pc_pts", "before": 0, "after": -pc, "tool_call": ghost_call["id"]},
                    ],
                },
            },
        ),
        ("step", {"agent": steps[4][0], "text": steps[4][1]}),
        ("step", {"agent": steps[5][0], "text": steps[5][1]}),
        ("verdict", {"agent": "verifier", "verdict": {"claim": t["draft"], "ok": False, "reason": t["draft_reason"], "round": 1}}),
        ("step", {"agent": steps[6][0], "text": steps[6][1]}),
        ("verdict", {"agent": "verifier", "verdict": {"claim": t["final"], "ok": True, "round": 2}}),
        ("overlay", {"agent": "pundit", "overlay": ov}),
        ("done", {"cached": True, "trace_id": "rehearsal"}),
    ]
    # Paced like a live run: about two seconds of thinking before the answer airs.
    gaps = [0, 180, 420, 160, 260, 380, 120, 220, 200, 300, 260, 240, 260, 40]
    out, t_ms = [], 0
    for seq, ((kind, body), dt) in enumerate(zip(events, gaps, strict=True)):
        t_ms += dt
        out.append({"type": kind, "seq": seq, "t_ms": t_ms, **body})
    return out


def main() -> None:
    show_fx = json.loads(SHOW.read_text())
    OUT.mkdir(exist_ok=True)
    index = []
    for lang in ("en-GB", "es-ES"):
        feed = counterfactual_feed(show_fx, lang)
        name = f"sim-7-counterfactual-{lang}.ndjson"
        (OUT / name).write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in feed))
        index.append({"key": "counterfactual", "match_id": "sim-7", "match_tc": feed[-2]["overlay"]["match_tc"], "lang": lang, "file": name})
    (OUT / "index.json").write_text(json.dumps({"feeds": index}, indent=2) + "\n")
    print(f"wrote {len(index)} feeds to {OUT}")


if __name__ == "__main__":
    main()
