"""Custom Foundry evaluators (S4) and the manual Foundry evaluation run (M10).

Three code evaluators, each a plain callable in the shape ``azure.ai.evaluation.evaluate``
expects (keyword columns in, a dict of scores out):

- ``ClaimGroundednessEvaluator``: every number spoken is a claim's value, and every claim is
  bound to a tool call whose recorded output it reports;
- ``NumericToleranceEvaluator``: every claim value is within its tolerance of the tool output;
- ``CueTimingEvaluator``: every stroke has a cue, starts no earlier than the audio, and its cue
  sits on the start of a spoken word (stroke-to-word timing).

A dataset row holds one overlay and the outputs of a fresh re-run of its tool calls, so the
evaluators need no tool access and score the same locally, in CI and in Foundry.

CI scores the dataset locally with ``evaluate_local`` (no Azure). The Foundry run is manual:

    set -a; . ~/.config/chalktalk/azure.env; set +a
    PYTHONPATH=evals/src uv run --with azure-ai-evaluation \\
        python -m chalktalk_evals.foundry --out .chalktalk-evals [--log-to-foundry] [--judge]

``--log-to-foundry`` uploads the results to the project's Evaluations page (no tokens).
``--judge`` adds Foundry's built-in LLM ``GroundednessEvaluator`` on ``gpt-4.1-mini``, about
1.5k tokens per item: under $0.01 for the 10 items. The run prints the estimated cost.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .harness import Thresholds, load_moments
from .metrics import claim_grounding, cue_timing, numeric_tolerance

ITEMS = 10
LENSES = ("casual", "analyst", "newcomer")
SIDES = ("home", "away", "neutral")
# gpt-4.1-mini list prices, USD per 1M tokens; the judge's prompt is ~1.4k tokens per item.
JUDGE_TOKENS_IN, JUDGE_TOKENS_OUT = 1400, 120
PRICE_IN_PER_M, PRICE_OUT_PER_M = 0.40, 1.60


def _key(name: str, args: dict[str, Any]) -> str:
    return json.dumps([name, args], sort_keys=True)


class RecordedTools:
    """Answers tool calls from the outputs recorded in a dataset row."""

    def __init__(self, outputs: dict[str, Any]) -> None:
        self.outputs = outputs

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return self.outputs[_key(name, args)]


def build_items(
    crew: Any,
    tools: Any,
    n: int = ITEMS,
    moments: list[dict[str, Any]] | None = None,
    lang: str = "en-GB",
) -> list[dict[str, Any]]:
    """``n`` dataset rows, spread over the test moments, lenses and sides (deterministic)."""
    moments = moments if moments is not None else load_moments()
    combos = [(m, lens, SIDES[i % len(SIDES)]) for i, lens in enumerate(LENSES) for m in moments]
    rows: list[dict[str, Any]] = []
    for moment, lens, side in combos[:n]:
        overlay = crew.run(moment["events"], lenses=(lens,), sides=(side,), lang=lang)[0]
        outputs = {
            _key(c["tool_call"]["name"], c["tool_call"]["args"]): tools.call(
                c["tool_call"]["name"], c["tool_call"]["args"]
            )
            for c in overlay["claims"]
        }
        rows.append(
            {
                "id": overlay["id"],
                "moment": moment["id"],
                "overlay": overlay,
                "tool_outputs": outputs,
                # Columns for the built-in LLM groundedness judge (--judge):
                "query": f"Explain moment {moment['id']} for a {lens} viewer ({side} fans).",
                "response": overlay["script"]["text"],
                "context": json.dumps(
                    [{k: o.get(k) for k in ("value", "unit")} for o in outputs.values()]
                ),
            }
        )
    return rows


def _result(ok: bool) -> str:
    return "pass" if ok else "fail"


class ClaimGroundednessEvaluator:
    """Spoken numbers come from claims; claims come from tool calls that return them."""

    id = "chalktalk_claim_groundedness"

    def __call__(self, *, overlay: dict[str, Any], tool_outputs: dict[str, Any]) -> dict:
        scores = claim_grounding(overlay)
        backed = 0
        for claim in overlay["claims"]:
            call = claim.get("tool_call") or {}
            out = tool_outputs.get(_key(call.get("name", ""), call.get("args", {})))
            backed += out is not None and out.get("unit") == claim.get("unit")
        n = len(overlay["claims"])
        claims_backed = 1.0 if n == 0 else backed / n
        score = min(scores["grounding_rate"], scores["claims_with_tool_call"], claims_backed)
        return {
            "claim_groundedness": score,
            "claim_groundedness_result": _result(n > 0 and score == 1.0),
            "unsupported_numbers": scores["numbers"] - scores["grounded_numbers"],
            "claims_backed_by_tool": claims_backed,
        }


class NumericToleranceEvaluator:
    """Each claim value is within its tolerance of the recorded tool output."""

    id = "chalktalk_numeric_tolerance"

    def __call__(self, *, overlay: dict[str, Any], tool_outputs: dict[str, Any]) -> dict:
        try:
            scores = numeric_tolerance(overlay, RecordedTools(tool_outputs))
        except KeyError:  # a claim whose tool call was never made backs nothing
            return {
                "numeric_tolerance": 0.0,
                "numeric_tolerance_result": "fail",
                "max_abs_error": float("inf"),
            }
        rate = scores["within_tolerance_rate"]
        return {
            "numeric_tolerance": rate,
            "numeric_tolerance_result": _result(rate == 1.0),
            "max_abs_error": scores["max_abs_error"],
        }


class CueTimingEvaluator:
    """Strokes start on the word that names them: cue bound, not before audio, on a word start."""

    id = "chalktalk_cue_timing"

    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self.t = thresholds or Thresholds()

    def __call__(self, *, overlay: dict[str, Any], tool_outputs: dict[str, Any] | None = None):
        s = cue_timing(overlay)
        ok = (
            s["cue_bound_rate"] >= self.t.cue_bound_rate
            and s["negative_starts"] <= self.t.negative_starts
            and s["cue_word_align_p95_ms"] <= self.t.cue_word_align_p95_ms
        )
        return {
            "cue_timing": 1.0 if ok else 0.0,
            "cue_timing_result": _result(ok),
            "cue_bound_rate": s["cue_bound_rate"],
            "cue_word_align_p95_ms": s["cue_word_align_p95_ms"],
            "negative_starts": s["negative_starts"],
        }


def evaluators() -> dict[str, Any]:
    return {
        "claim_groundedness": ClaimGroundednessEvaluator(),
        "numeric_tolerance": NumericToleranceEvaluator(),
        "cue_timing": CueTimingEvaluator(),
    }


def evaluate_local(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The same evaluators without Azure; the shape mirrors ``evaluate``'s rows and metrics."""
    out_rows = []
    for row in rows:
        scores = {
            name: ev(overlay=row["overlay"], tool_outputs=row["tool_outputs"])
            for name, ev in evaluators().items()
        }
        failed = [name for name, s in scores.items() if s[f"{name}_result"] != "pass"]
        out_rows.append({"id": row["id"], "scores": scores, "failed": failed})
    n = len(out_rows)
    metrics = {
        f"{name}.pass_rate": sum(name not in r["failed"] for r in out_rows) / n if n else 0.0
        for name in evaluators()
    }
    return {"passed": n > 0 and not any(r["failed"] for r in out_rows), "metrics": metrics,
            "rows": out_rows}  # fmt: skip


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    return path


def judge_cost_usd(items: int) -> float:
    return items * (JUDGE_TOKENS_IN * PRICE_IN_PER_M + JUDGE_TOKENS_OUT * PRICE_OUT_PER_M) / 1e6


def run_foundry(
    data: Path, out: Path, *, log_to_foundry: bool, judge: bool
) -> dict[str, Any]:  # pragma: no cover - manual, needs azure-ai-evaluation and Azure
    from azure.ai.evaluation import evaluate

    evs: dict[str, Any] = evaluators()
    config: dict[str, Any] = {
        name: {"column_mapping": {"overlay": "${data.overlay}",
                                  "tool_outputs": "${data.tool_outputs}"}}
        for name in evs
    }  # fmt: skip
    if judge:
        from azure.ai.evaluation import AzureOpenAIModelConfiguration, GroundednessEvaluator
        from chalktalk_crew import CrewConfig

        crew_cfg = CrewConfig.from_env()
        if not (crew_cfg.foundry_endpoint and crew_cfg.foundry_api_key):
            raise RuntimeError("--judge needs AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY")
        model = AzureOpenAIModelConfiguration(
            azure_endpoint=crew_cfg.foundry_endpoint,
            api_key=crew_cfg.foundry_api_key,
            azure_deployment=crew_cfg.foundry_deployment or "gpt-4.1-mini",
            api_version=crew_cfg.foundry_api_version,
        )
        evs["llm_groundedness"] = GroundednessEvaluator(model_config=model)
        config["llm_groundedness"] = {
            "column_mapping": {
                "query": "${data.query}",
                "response": "${data.response}",
                "context": "${data.context}",
            }
        }
    project = os.environ.get("AZURE_AI_PROJECT_ENDPOINT") if log_to_foundry else None
    if log_to_foundry and not project:
        raise RuntimeError("--log-to-foundry needs AZURE_AI_PROJECT_ENDPOINT")
    result = evaluate(
        data=str(data),
        evaluators=evs,
        evaluator_config=config,
        evaluation_name="chalktalk-s4-evaluators",
        output_path=str(out / "foundry-result.json"),
        **({"azure_ai_project": project} if project else {}),
    )
    return {"metrics": result.get("metrics"), "studio_url": result.get("studio_url")}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - manual run
    parser = argparse.ArgumentParser(prog="chalktalk_evals.foundry")
    parser.add_argument("--out", type=Path, default=Path(".chalktalk-evals"))
    parser.add_argument("--items", type=int, default=ITEMS)
    parser.add_argument("--lang", default="en-GB")
    parser.add_argument("--local", action="store_true", help="score without azure-ai-evaluation")
    parser.add_argument("--log-to-foundry", action="store_true")
    parser.add_argument("--judge", action="store_true", help="add the LLM groundedness judge")
    args = parser.parse_args(argv)

    from chalktalk_crew import FakeAnalyticsTools, crew_from_env

    tools = FakeAnalyticsTools()
    rows = build_items(crew_from_env(tools), tools, args.items, lang=args.lang)
    data = write_jsonl(rows, args.out / "dataset.jsonl")
    local = evaluate_local(rows)
    report: dict[str, Any] = {"items": len(rows), "local": local["metrics"]}
    if not args.local:
        report["foundry"] = run_foundry(
            data, args.out, log_to_foundry=args.log_to_foundry, judge=args.judge
        )
        report["est_judge_cost_usd"] = round(judge_cost_usd(len(rows)), 4) if args.judge else 0.0
    print(json.dumps(report, indent=2))
    for row in local["rows"]:
        if row["failed"]:
            print(f"FAIL {row['id']}: {', '.join(row['failed'])}", file=sys.stderr)
    return 0 if local["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
