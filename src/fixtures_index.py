"""Mechanical data plumbing shared by the harness, graders, and judge.

This is the Claude-Code-owned "what exists / what's expected" layer. It reads
fixtures/ and ground_truth/ (both legitimate on the HOST — only the agent's
container is walled off from ground_truth) and hands clean data to graders.py and
judge.py so those files carry only comparison / judgement logic.

Nothing here grades anything: no pass/fail decisions live in this module.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "fixtures"
GROUND_TRUTH_DIR = REPO_ROOT / "ground_truth"

# Case-id ranges -> bucket, straight from the §3 case matrix. Buckets drive the
# bucket-level aggregation the README must report (an agent that aces approvals
# while failing escalations is a failing agent for this use case).
_BUCKET_RANGES = [
    (1, 4, "approve"),
    (5, 8, "deny"),
    (9, 11, "partial"),
    (12, 14, "escalate"),
    (15, 16, "ambiguous"),
]

HUMAN_APPROVAL_THRESHOLD = 10_000.0


def case_number(case_id: str) -> int:
    """'D-0007' -> 7."""
    return int(case_id.split("-")[1])


def case_bucket(case_id: str) -> str:
    n = case_number(case_id)
    for lo, hi, bucket in _BUCKET_RANGES:
        if lo <= n <= hi:
            return bucket
    raise ValueError(f"No bucket for case {case_id}")


@lru_cache(maxsize=1)
def load_labels() -> dict[str, dict]:
    """case_id -> label dict from ground_truth/labels.json."""
    labels = json.loads((GROUND_TRUTH_DIR / "labels.json").read_text())
    return {row["case_id"]: row for row in labels}


def load_label(case_id: str) -> dict:
    return load_labels()[case_id]


def load_reference_solution(case_id: str) -> dict:
    """The hand-written correct settlement for a case (calibration gate A)."""
    path = GROUND_TRUTH_DIR / "reference_solutions" / f"{case_id}.json"
    return json.loads(path.read_text())


def all_case_ids() -> list[str]:
    return sorted(load_labels().keys())


@lru_cache(maxsize=1)
def valid_evidence_ids() -> frozenset[str]:
    """Every evidence identifier that actually exists in the fixtures.

    Used by the no_hallucinated_evidence check: any cited id outside this set was
    invented by the agent. Three namespaces:
      - PROMO-... promotion ids (fixtures/promotions.json)
      - SH-...    settlement-history ids (fixtures/settlement_history.json)
      - contract:<retailer>:section-N.N  numbered contract sections
    """
    ids: set[str] = set()

    promotions = json.loads((FIXTURES_DIR / "promotions.json").read_text())
    ids.update(p["promo_id"] for p in promotions)

    history = json.loads((FIXTURES_DIR / "settlement_history.json").read_text())
    ids.update(s["settlement_id"] for s in history)

    section_re = re.compile(r"^###\s+(\d+\.\d+)\b", re.MULTILINE)
    for contract_path in (FIXTURES_DIR / "contracts").glob("*.md"):
        retailer = contract_path.stem  # e.g. "valumax"
        for section in section_re.findall(contract_path.read_text()):
            ids.add(f"contract:{retailer}:section-{section}")

    return frozenset(ids)


def load_settlement(runs_dir: Path, trial: str, case_id: str) -> dict | None:
    """Read the drafted settlement for a run, or None if the agent produced none."""
    path = runs_dir / trial / case_id / "settlement.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
