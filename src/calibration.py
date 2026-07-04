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


def gate_b_null_agent() -> tuple[bool, list[str], str]:
    """The always-approve baseline must FAIL every non-approve case.

    That is the safety-relevant property (a settle-everything agent must fail the
    deny/partial/escalate/ambiguous buckets), and it is guaranteed by
    action_correct alone since the null always drafts 'approve'. Passing the
    approve bucket is NOT required: a null that does no investigation legitimately
    cannot cite the promo on a messy-paperwork approve (D-0003), so it fails there
    — that is correct null behaviour, not a broken harness. Approve-bucket passes
    are reported for information only.

    Returns (ok, anomalies, info) — an anomaly is a non-approve case the null
    wrongly PASSED.
    """
    anomalies = []
    approve_pass = approve_total = 0
    for case_id in all_case_ids():
        bucket = case_bucket(case_id)
        passed, _ = _grade(null_settlement(case_id), case_id)
        if bucket == "approve":
            approve_total += 1
            approve_pass += int(passed)
        elif passed:
            # A non-approve case the null passed would mean the harness is broken.
            anomalies.append(f"{case_id} ({bucket}): null agent wrongly PASSED")
    info = f"null passed {approve_pass}/{approve_total} approve-bucket cases (informational)"
    return (not anomalies), anomalies, info


def main() -> None:
    n = len(all_case_ids())
    print(f"Gate A — reference solutions through graders (expect {n}/{n}):")
    a_ok, a_fail = gate_a_reference_solutions()
    if a_ok:
        print("  PASS: all reference solutions pass the graders.")
    else:
        for f in a_fail:
            print(f"  FAIL: {f}")

    print("Gate B — null agent fails every non-approve case:")
    b_ok, b_anom, b_info = gate_b_null_agent()
    if b_ok:
        print("  PASS: null agent fails all deny/partial/escalate/ambiguous cases.")
    else:
        for a in b_anom:
            print(f"  ANOMALY: {a}")
    print(f"  info: {b_info}")

    sys.exit(0 if (a_ok and b_ok) else 1)


if __name__ == "__main__":
    main()
