"""Token/cost estimates (before a run) and actuals (after a run).

One source of truth for pricing. Estimates are intentionally rough and labelled as
such — they exist so no expensive run starts without a printed dollar figure. After
the first real run, actuals from the recorded token usage replace the guesses.
"""

from __future__ import annotations

import json
from pathlib import Path

from judge import DIMENSIONS, JUDGE_MODEL

# Blended $/1M tokens (input, output). Refresh from the current price list.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-fable-5": (10.00, 50.00),
}

# --- pre-run estimate assumptions (rough; replaced by actuals after a run) -----
# Per case the agent makes several tool-call turns, each re-sending the growing
# context, so input tokens dominate. These are deliberately conservative.
EST_AGENT_INPUT_TOKENS_PER_CASE = 25_000
EST_AGENT_OUTPUT_TOKENS_PER_CASE = 3_000
# The judge makes one isolated call per dimension over the cited-evidence context.
EST_JUDGE_INPUT_TOKENS_PER_DIM = 2_500
EST_JUDGE_OUTPUT_TOKENS_PER_DIM = 150


def usage_cost(model: str, usage: dict) -> float:
    """Dollar cost of one usage block. Cache reads/writes fold into input at the
    headline rate (a simplification; refine if cache volume is large)."""
    in_rate, out_rate = PRICING[model]
    in_tok = (usage.get("input_tokens", 0)
              + usage.get("cache_read_input_tokens", 0)
              + usage.get("cache_creation_input_tokens", 0))
    out_tok = usage.get("output_tokens", 0)
    return in_tok / 1e6 * in_rate + out_tok / 1e6 * out_rate


def estimate_eval(n_cases: int, n_trials: int, agent_model: str,
                  use_judge: bool) -> dict:
    """Estimated cost of an N-trial x M-case eval (agent + optional judge)."""
    runs = n_cases * n_trials
    agent_in = runs * EST_AGENT_INPUT_TOKENS_PER_CASE
    agent_out = runs * EST_AGENT_OUTPUT_TOKENS_PER_CASE
    agent_cost = usage_cost(agent_model,
                            {"input_tokens": agent_in, "output_tokens": agent_out})
    judge_cost = 0.0
    if use_judge:
        dim_calls = runs * len(DIMENSIONS)
        j_in = dim_calls * EST_JUDGE_INPUT_TOKENS_PER_DIM
        j_out = dim_calls * EST_JUDGE_OUTPUT_TOKENS_PER_DIM
        judge_cost = usage_cost(JUDGE_MODEL,
                                {"input_tokens": j_in, "output_tokens": j_out})
    return {
        "runs": runs, "agent_model": agent_model, "use_judge": use_judge,
        "agent_cost": round(agent_cost, 2),
        "judge_cost": round(judge_cost, 2),
        "total_cost": round(agent_cost + judge_cost, 2),
    }


def estimate_judge_calibration(n_negatives: int = 3) -> dict:
    """Estimated cost of running the known-negative judge calibration."""
    dim_calls = n_negatives * len(DIMENSIONS)
    cost = usage_cost(JUDGE_MODEL, {
        "input_tokens": dim_calls * EST_JUDGE_INPUT_TOKENS_PER_DIM,
        "output_tokens": dim_calls * EST_JUDGE_OUTPUT_TOKENS_PER_DIM})
    return {"calls": dim_calls, "judge_model": JUDGE_MODEL, "total_cost": round(cost, 2)}


def actuals_from_runs(runs_dir: Path, trials: list[str], cases: list[str],
                      agent_model: str) -> dict:
    """Sum recorded agent-side token usage across a run and price it.

    Reads runs/<trial>/<case>/record.json (written by run_agent). Judge tokens are
    not captured in the record, so judge cost stays estimate-only for now.
    """
    in_tok = out_tok = 0
    n = 0
    for trial in trials:
        for case in cases:
            rec = runs_dir / trial / case / "record.json"
            if not rec.exists():
                continue
            usage = json.loads(rec.read_text()).get("usage", {})
            in_tok += (usage.get("input_tokens", 0)
                       + usage.get("cache_read_input_tokens", 0)
                       + usage.get("cache_creation_input_tokens", 0))
            out_tok += usage.get("output_tokens", 0)
            n += 1
    cost = usage_cost(agent_model, {"input_tokens": in_tok, "output_tokens": out_tok})
    return {"records": n, "input_tokens": in_tok, "output_tokens": out_tok,
            "agent_cost": round(cost, 4)}


def format_estimate(est: dict) -> str:
    lines = [
        f"COST ESTIMATE (rough, pre-run) — {est['runs']} agent runs on {est['agent_model']}",
        f"  agent:  ~${est['agent_cost']:.2f}",
    ]
    if est["use_judge"]:
        lines.append(f"  judge:  ~${est['judge_cost']:.2f}  (on {JUDGE_MODEL})")
    lines.append(f"  TOTAL:  ~${est['total_cost']:.2f}")
    lines.append("  (assumptions in costs.py; actuals printed after the run)")
    return "\n".join(lines)


def format_actuals(act: dict, agent_model: str) -> str:
    return (f"COST ACTUALS — {act['records']} records on {agent_model}: "
            f"{act['input_tokens']:,} in + {act['output_tokens']:,} out "
            f"= ${act['agent_cost']:.4f} (agent side; judge tokens not captured)")
