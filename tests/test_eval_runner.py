"""Aggregation math: pass^k, infra separation, bucket rollups (pure)."""
import eval_runner as er
from eval_runner import TrialResult


def tr(case, trial, passed, status="ok"):
    return TrialResult(case, trial, status=status, passed=passed)


def test_pass_k_edge_cases():
    assert er.pass_k([True, True]) == 1
    assert er.pass_k([True, False]) == 0
    assert er.pass_k([True, None]) == 1        # infra dropped, remaining passed
    assert er.pass_k([None, None]) is None     # all infra -> uncertain


def test_aggregate_per_case_and_buckets():
    results = [
        tr("D-0001", "t0", True),  tr("D-0001", "t1", True),   # approve pass^2=1
        tr("D-0002", "t0", True),  tr("D-0002", "t1", False),  # approve pass^2=0, rate .5
        tr("D-0005", "t0", False), tr("D-0005", "t1", False),  # deny pass^2=0
        tr("D-0009", "t0", None, status="infra_error"),        # partial: one infra
        tr("D-0009", "t1", True),                              # ...remaining passes
    ]
    agg = er.aggregate(results)
    pc = agg["per_case"]
    assert pc["D-0001"]["pass_k"] == 1 and pc["D-0001"]["pass_rate"] == 1.0
    assert pc["D-0002"]["pass_k"] == 0 and pc["D-0002"]["pass_rate"] == 0.5
    assert pc["D-0005"]["pass_k"] == 0
    assert pc["D-0009"]["infra_errors"] == 1 and pc["D-0009"]["pass_k"] == 1
    assert agg["total_infra_errors"] == 1
    assert agg["by_bucket"]["approve"]["pass_k"] == 0.5
    assert agg["by_bucket"]["deny"]["pass_k"] == 0.0
    assert agg["by_bucket"]["partial"]["pass_k"] == 1.0


def test_grade_settlement_missing_draft_is_fail():
    passed, checks = er.grade_settlement(None, "D-0001")
    assert not passed and checks[0]["name"] == "draft_present"


def test_grade_settlement_reference_passes():
    import fixtures_index as fx
    ref = fx.load_reference_solution("D-0009")
    passed, _ = er.grade_settlement(ref, "D-0009")
    assert passed


def test_grade_settlement_broken_fails_right_checks():
    bad = {"case_id": "D-0014", "action": "approve", "amount": 42000.0,
           "justification": "x", "evidence_ids": ["PROMO-FAKE-999"]}
    passed, checks = er.grade_settlement(bad, "D-0014")
    failed = {c["name"] for c in checks if c["applicable"] and not c["passed"]}
    assert not passed
    assert {"action_correct", "threshold_respected", "no_hallucinated_evidence"} <= failed
