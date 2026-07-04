"""Calibration gates — run these before trusting any eval result (§6).

Known-good must score ~100%, known-bad ~chance, or the harness is broken.

Gate A (reference solutions): every hand-written reference settlement must pass
        the programmatic graders. 16/16 required. If one fails, fix the case or
        the grader BEFORE running any model.

Gate B (null agent): the always-approve baseline must FAIL the deny, partial,
        escalate, and ambiguous buckets and pass the clean-approve bucket.

Both gates depend on Evan's graders.py being implemented; they raise
NotImplementedError until then. Gate A is Claude-Code plumbing around Evan's
checks; running it is how Evan knows the checks are right.

Usage:  python src/calibration.py
"""

from __future__ import annotations

import sys

from fixtures_index import (
    all_case_ids,
    case_bucket,
    load_label,
    load_reference_solution,
    valid_evidence_ids,
)
from null_agent import null_settlement


def _grade(settlement: dict, case_id: str) -> tuple[bool, list]:
    from graders import run_all_checks, passed_all
    results = run_all_checks(settlement, load_label(case_id), valid_evidence_ids())
    return passed_all(results), results


def gate_a_reference_solutions() -> tuple[bool, list[str]]:
    """Every reference solution passes the graders. Returns (ok, failures)."""
    failures = []
    for case_id in all_case_ids():
        ref = load_reference_solution(case_id)
        passed, results = _grade(ref, case_id)
        if not passed:
            bad = [r.name for r in results if r.applicable and not r.passed]
            failures.append(f"{case_id}: failed {bad}")
    return (not failures), failures


def gate_b_null_agent() -> tuple[bool, list[str]]:
    """Null agent must fail deny/partial/escalate/ambiguous, pass approve.

    Returns (ok, anomalies) where an anomaly is a case that graded the wrong way
    for the null (always-approve) baseline.
    """
    anomalies = []
    for case_id in all_case_ids():
        bucket = case_bucket(case_id)
        passed, _ = _grade(null_settlement(case_id), case_id)
        # The null approves everything: it should only pass the approve bucket.
        should_pass = bucket == "approve"
        if passed != should_pass:
            anomalies.append(
                f"{case_id} ({bucket}): null agent passed={passed}, "
                f"expected {should_pass}")
    return (not anomalies), anomalies


def main() -> None:
    print("Gate A — reference solutions through graders (expect 16/16):")
    a_ok, a_fail = gate_a_reference_solutions()
    if a_ok:
        print("  PASS: all reference solutions pass the graders.")
    else:
        for f in a_fail:
            print(f"  FAIL: {f}")

    print("Gate B — null agent fails the right buckets:")
    b_ok, b_anom = gate_b_null_agent()
    if b_ok:
        print("  PASS: null agent passes only the approve bucket.")
    else:
        for a in b_anom:
            print(f"  ANOMALY: {a}")

    sys.exit(0 if (a_ok and b_ok) else 1)


if __name__ == "__main__":
    main()
