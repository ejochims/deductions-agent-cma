"""Orchestrate the eval: N trials x all cases -> results.json.

Drives run_agent per (case, trial), grades each drafted settlement with
graders.py, optionally judges it with judge.py, and aggregates into mean pass
rate +/- spread and pass^k, reported overall AND per bucket.

Doctrine baked in:
  - infra_error is kept SEPARATE from pass/fail: excluded from the pass rate,
    counted on its own, and retried once.
  - pass^k per case = 1 iff all k ok-trials passed; overall/bucket pass^k is the
    mean of that over cases.
  - aggregation matches the question: bucket-level results, not just overall.

The aggregation math (aggregate / pass_k) is pure and unit-tested independently of
the agent and graders, so this file is trustworthy before the API/grader code
exists.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fixtures_index import (
    REPO_ROOT,
    all_case_ids,
    case_bucket,
    load_label,
    load_settlement,
    valid_evidence_ids,
)

RUNS_DIR = REPO_ROOT / "runs"
RESULTS_PATH = REPO_ROOT / "runs" / "results.json"


@dataclass
class TrialResult:
    case_id: str
    trial: str
    status: str            # "ok" | "infra_error"
    passed: bool | None    # None when infra_error or no draft
    check_results: list = field(default_factory=list)   # serialized CheckResults
    judge_verdicts: list = field(default_factory=list)   # serialized Verdicts
    note: str = ""


# ------------------------------------------------------------------- grading
def grade_settlement(settlement: dict | None, case_id: str) -> tuple[bool, list]:
    """Programmatic pass/fail for one drafted settlement.

    Returns (passed, serialized_check_results). A missing draft (None) is a fail,
    not an infra_error — the agent ran but produced no settlement.
    """
    from graders import passed_all, run_all_checks

    if settlement is None:
        return False, [{"name": "draft_present", "passed": False,
                        "applicable": True, "detail": "agent produced no settlement"}]
    label = load_label(case_id)
    results = run_all_checks(settlement, label, valid_evidence_ids())
    return passed_all(results), [asdict(r) for r in results]


_judge_client = None  # lazily constructed once; the judge is a plain Messages call


def judge_settlement_safe(client, settlement: dict | None) -> list:
    """Run the LLM judge over one settlement.

    `client` may be None (run_one_case builds its own client internally, so the
    harness often passes None through) — construct and cache one here rather
    than crashing on the first judged settlement.
    """
    if settlement is None:
        return []
    global _judge_client
    if client is None:
        if _judge_client is None:
            import anthropic
            _judge_client = anthropic.Anthropic()
        client = _judge_client
    from judge import judge_settlement
    return [asdict(v) for v in judge_settlement(client, settlement)]


# --------------------------------------------------------------- run one cell
def run_trial(case_id: str, trial: str, client, *, use_judge: bool,
              use_memory: bool = True, agent_override: dict | None = None,
              retry_once: bool = True) -> TrialResult:
    """Run one (case, trial): drive the agent, read the draft, grade (and judge).

    infra_error is retried once. run_agent.run_one_case is responsible for
    classifying its own failures as infra_error.
    """
    from run_agent import run_one_case  # imported lazily: touches the SDK code

    kw = dict(client=client, use_memory=use_memory, agent_override=agent_override)
    recorder = run_one_case(case_id, trial, **kw)
    if recorder.status == "infra_error" and retry_once:
        recorder = run_one_case(case_id, trial, **kw)

    if recorder.status == "infra_error":
        return TrialResult(case_id, trial, status="infra_error", passed=None,
                          note=recorder.error or "")

    settlement = load_settlement(RUNS_DIR, trial, case_id)
    passed, checks = grade_settlement(settlement, case_id)
    verdicts = judge_settlement_safe(client, settlement) if use_judge else []
    return TrialResult(case_id, trial, status="ok", passed=passed,
                      check_results=checks, judge_verdicts=verdicts)


# ---------------------------------------------------------------- aggregation
def pass_k(trial_flags: list[bool | None]) -> int | None:
    """pass^k for one case: 1 if every ok trial passed, else 0; None if no ok trials.

    infra_error trials (None) are dropped from the denominator entirely, so a case
    whose every trial errored out is reported as None (uncertain), not as a fail.
    """
    ok = [p for p in trial_flags if p is not None]
    if not ok:
        return None
    return 1 if all(ok) else 0


def aggregate(results: list[TrialResult]) -> dict:
    """Overall and per-bucket pass rate (+/- spread) and pass^k.

    Pure over TrialResult data — no I/O, no agent, no graders.
    """
    by_case: dict[str, list[bool | None]] = {}
    for r in results:
        by_case.setdefault(r.case_id, []).append(r.passed)

    # Per-case pass rate (over ok trials) and pass^k.
    per_case = {}
    for case_id, flags in by_case.items():
        ok = [p for p in flags if p is not None]
        infra = sum(1 for p in flags if p is None)
        per_case[case_id] = {
            "bucket": case_bucket(case_id),
            "trials": len(flags),
            "infra_errors": infra,
            "pass_rate": (sum(ok) / len(ok)) if ok else None,
            "pass_k": pass_k(flags),
        }

    def summarize(case_ids: list[str]) -> dict:
        rates = [per_case[c]["pass_rate"] for c in case_ids
                 if per_case[c]["pass_rate"] is not None]
        ks = [per_case[c]["pass_k"] for c in case_ids
              if per_case[c]["pass_k"] is not None]
        return {
            "n_cases": len(case_ids),
            "mean_pass_rate": (statistics.mean(rates) if rates else None),
            "pass_rate_stdev": (statistics.pstdev(rates) if len(rates) > 1 else 0.0),
            "pass_k": (statistics.mean(ks) if ks else None),
            "cases_all_infra": sum(
                1 for c in case_ids if per_case[c]["pass_rate"] is None),
        }

    buckets: dict[str, list[str]] = {}
    for case_id in per_case:
        buckets.setdefault(case_bucket(case_id), []).append(case_id)

    return {
        "overall": summarize(list(per_case.keys())),
        "by_bucket": {b: summarize(cs) for b, cs in sorted(buckets.items())},
        "per_case": per_case,
        "total_infra_errors": sum(pc["infra_errors"] for pc in per_case.values()),
    }


# ---------------------------------------------------------------------- main
def run_matrix(trials: list[str], case_ids: list[str], client, *,
               use_judge: bool, use_memory: bool = True,
               agent_override: dict | None = None,
               results_path: Path = RESULTS_PATH) -> dict:
    results: list[TrialResult] = []
    for trial in trials:
        for case_id in case_ids:
            results.append(run_trial(case_id, trial, client, use_judge=use_judge,
                                     use_memory=use_memory,
                                     agent_override=agent_override))
    summary = aggregate(results)
    payload = {
        "trials": trials,
        "cases": case_ids,
        "used_judge": use_judge,
        "used_memory": use_memory,
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    results_path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def _agent_model() -> str:
    from run_agent import load_agent_config
    return load_agent_config()["model"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the N-trial x cases eval matrix.")
    parser.add_argument("--trials", type=int, default=3, help="Trials per case.")
    parser.add_argument("--cases", nargs="*", default=None,
                        help="Case ids to run (default: all cases).")
    parser.add_argument("--judge", action="store_true", help="Enable the LLM judge.")
    parser.add_argument("--no-memory", action="store_true",
                        help="Disable the precedent tool (for the with/without delta).")
    parser.add_argument("--estimate-only", action="store_true",
                        help="Print the cost estimate and exit without running.")
    args = parser.parse_args()

    trials = [f"t{i}" for i in range(args.trials)]
    case_ids = args.cases or all_case_ids()
    model = _agent_model()

    # Cost visibility: always print an estimate before spending anything.
    from costs import actuals_from_runs, estimate_eval, format_actuals, format_estimate
    est = estimate_eval(len(case_ids), len(trials), model, args.judge)
    print(format_estimate(est))
    if args.estimate_only:
        return

    client = None  # run_one_case constructs anthropic.Anthropic() when None
    payload = run_matrix(trials, case_ids, client, use_judge=args.judge,
                         use_memory=not args.no_memory)

    overall = payload["summary"]["overall"]
    print(f"\noverall pass^{len(trials)} = {overall['pass_k']} "
          f"mean pass rate = {overall['mean_pass_rate']}")
    for bucket, s in payload["summary"]["by_bucket"].items():
        print(f"  {bucket:10s} pass^k={s['pass_k']} mean={s['mean_pass_rate']} "
              f"(n={s['n_cases']})")

    print()
    print(format_actuals(actuals_from_runs(RUNS_DIR, trials, case_ids, model), model))

    # Failure digest (reports, never fixes).
    print()
    from digest import write_and_print
    write_and_print(RESULTS_PATH)


if __name__ == "__main__":
    main()
