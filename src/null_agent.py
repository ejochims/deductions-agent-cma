"""Null agent: always approve the full claimed amount.

The known-bad calibration baseline. It runs no model — it just emits a
settlement per case. Because it approves everything, it MUST fail the deny,
partial, escalate, and ambiguous buckets; if the harness reports it doing well on
those, the harness (or the graders) is broken. It should look ~correct only on the
clean-approve bucket.

Writes settlement.json in the same shape run_agent produces, so the harness grades
it through exactly the same path.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fixtures_index import FIXTURES_DIR, all_case_ids


def null_settlement(case_id: str) -> dict:
    """Approve the full claimed amount, citing whatever promo the retailer named."""
    deduction = json.loads((FIXTURES_DIR / "deductions" / f"{case_id}.json").read_text())
    claimed_ref = deduction.get("claimed_reference", "")
    # Only cite it if it looks like a real promo id; otherwise cite nothing (the
    # null agent does no investigation).
    evidence = [claimed_ref] if claimed_ref.startswith("PROMO-") else []
    return {
        "case_id": case_id,
        "action": "approve",
        "amount": deduction["amount"],
        "justification": "Approved as claimed.",
        "evidence_ids": evidence,
        "drafted_at": datetime.now(UTC).isoformat(),
    }


def write_null_run(runs_dir: Path, trial: str = "null") -> list[str]:
    """Emit a null settlement for every case under runs/<trial>/<case>/."""
    written = []
    for case_id in all_case_ids():
        out_dir = runs_dir / trial / case_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "settlement.json").write_text(
            json.dumps(null_settlement(case_id), indent=2) + "\n"
        )
        written.append(case_id)
    return written
