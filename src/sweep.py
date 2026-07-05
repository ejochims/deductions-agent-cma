"""Model sweep with cost-per-success.

Runs the same protocol across a grid of models via per-session
agent_with_overrides — one persisted agent, cheap per-session model swaps. For each
model it records the pass^k, mean pass rate, and cost, and derives cost-per-success
so the model recommendation is empirical, not asserted.

Scope note: Managed Agents lets a session override only model / system / tools /
mcp_servers / skills — NOT thinking. So this sweep varies the MODEL and runs every
model with the shipped thinking config (extended thinking on, the MA default; see
agent/agent.yaml). Comparing thinking on vs off would require separate versioned
agents (or the future local Messages-API runner, where thinking is a request
parameter) and is intentionally out of scope here.

The pure pieces (pricing -> cost, cost-per-success) are unit-tested offline;
running the grid and plotting needs the API + matplotlib.

Usage:  python src/sweep.py --trials 3            # full grid
        python src/sweep.py --trials 1 --quick    # cheap smoke of the grid
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from costs import usage_cost
from eval_runner import run_matrix
from fixtures_index import REPO_ROOT, all_case_ids

RUNS_DIR = REPO_ROOT / "runs"
SWEEP_DIR = RUNS_DIR / "sweep"

# The sweep grid — the candidate model tiers (Haiku / Sonnet; Fable is pricey,
# opt in explicitly). Every entry runs with the shipped thinking config.
GRID: list[dict] = [
    {"label": "haiku", "model": "claude-haiku-4-5"},
    {"label": "sonnet-4-6", "model": "claude-sonnet-4-6"},
    {"label": "sonnet-5", "model": "claude-sonnet-5"},
    # {"label": "fable", "model": "claude-fable-5"},  # most capable, most expensive
]


def summarize_config(model: str, payload: dict) -> dict:
    """Pass metrics + total cost + cost-per-success for one configuration."""
    results = payload["results"]
    total_cost = 0.0
    successes = 0
    ok_trials = 0
    for r in results:
        rec_usage = r.get("usage") or _usage_from_record(r)
        total_cost += usage_cost(model, rec_usage)
        if r["status"] == "ok":
            ok_trials += 1
            if r["passed"]:
                successes += 1
    overall = payload["summary"]["overall"]
    return {
        "model": model,
        "pass_k": overall["pass_k"],
        "mean_pass_rate": overall["mean_pass_rate"],
        "ok_trials": ok_trials,
        "successes": successes,
        "total_cost_usd": round(total_cost, 4),
        "cost_per_success_usd": (round(total_cost / successes, 4) if successes else None),
    }


def _usage_from_record(r: dict) -> dict:
    """The TrialResult carried by results.json doesn't embed token usage (that lives
    in each run's record.json). Read it back if present; else empty."""
    path = RUNS_DIR / r["trial"] / r["case_id"] / "record.json"
    if path.exists():
        return json.loads(path.read_text()).get("usage", {})
    return {}


# --------------------------------------------------------------------- plots
def plot_sweep(rows: list[dict], out_dir: Path) -> list[Path]:
    """Pass-rate and cost-per-success bar charts. Guarded import so the module is
    usable without matplotlib installed."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    labels = [r["label"] for r in rows]

    def _bar(values: list[float], ylabel: str, title: str, fname: str,
             ylim: tuple[float, float] | None = None) -> Path:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(labels, values)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        if ylim:
            ax.set_ylim(*ylim)
        fig.autofmt_xdate()
        fig.tight_layout()
        path = out_dir / fname
        fig.savefig(path)
        return path

    return [
        _bar([r["mean_pass_rate"] or 0 for r in rows],
             "mean pass rate", "Pass rate by configuration", "pass_rate.png", (0, 1)),
        _bar([r["cost_per_success_usd"] or 0 for r in rows],
             "cost per success ($)", "Cost per successful settlement by configuration",
             "cost_per_success.png"),
    ]


# ---------------------------------------------------------------------- main
def run_sweep(trials: int, case_ids: list[str], *, use_judge: bool) -> list[dict]:
    client = None  # constructed lazily inside run_one_case
    trial_labels = [f"t{i}" for i in range(trials)]
    rows = []
    for cfg in GRID:
        override = {"model": cfg["model"]}  # MA overrides model only (see module docstring)
        out_path = SWEEP_DIR / f"results_{cfg['label']}.json"
        SWEEP_DIR.mkdir(parents=True, exist_ok=True)
        # Namespace the trial labels per config so runs/ files don't collide.
        cfg_trials = [f"{cfg['label']}-{t}" for t in trial_labels]
        payload = run_matrix(cfg_trials, case_ids, client, use_judge=use_judge,
                             agent_override=override, results_path=out_path)
        row = {"label": cfg["label"], **summarize_config(cfg["model"], payload)}
        rows.append(row)
        print(f"{cfg['label']:16s} pass^k={row['pass_k']} "
              f"cost/success=${row['cost_per_success_usd']}")

    (SWEEP_DIR / "sweep_summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    try:
        written = plot_sweep(rows, SWEEP_DIR)
        print("plots:", ", ".join(str(p) for p in written))
    except ImportError:
        print("(matplotlib not installed — skipping plots; summary json written)")

    best = max((r for r in rows if r["cost_per_success_usd"]),
               key=lambda r: (r["pass_k"] or 0, -(r["cost_per_success_usd"] or 1e9)),
               default=None)
    if best:
        print(f"\nRecommendation: {best['label']} "
              f"(pass^k={best['pass_k']}, ${best['cost_per_success_usd']}/success)")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Model sweep (cost-per-success).")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--quick", action="store_true",
                        help="Run 4 representative cases instead of all 18.")
    args = parser.parse_args()
    cases = (["D-0001", "D-0008", "D-0014", "D-0017"] if args.quick else all_case_ids())
    run_sweep(args.trials, cases, use_judge=args.judge)


if __name__ == "__main__":
    main()
