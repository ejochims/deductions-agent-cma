"""Unit tests for the five programmatic checks."""
import graders as g
from graders import CheckResult, passed_all


def _label(**kw):
    base = {"case_id": "X", "expected_action": "approve", "expected_amount": 100.0,
            "amount_tolerance": 0.05, "required_evidence": []}
    base.update(kw)
    return base


def test_action_correct():
    assert g.action_correct({"action": "deny"}, _label(expected_action="deny")).passed
    assert not g.action_correct({"action": "approve"}, _label(expected_action="deny")).passed


def test_amount_tolerance_applies_and_passes():
    r = g.amount_within_tolerance({"amount": 102.0}, _label(expected_amount=100.0, amount_tolerance=0.05))
    assert r.applicable and r.passed
    r = g.amount_within_tolerance({"amount": 110.0}, _label(expected_amount=100.0, amount_tolerance=0.05))
    assert r.applicable and not r.passed


def test_amount_tolerance_skipped_for_deny_escalate():
    r = g.amount_within_tolerance({"amount": None}, _label(expected_amount=None))
    assert not r.applicable and r.passed  # skipped, not failed


def test_amount_none_on_expected_payout_is_hard_fail():
    r = g.amount_within_tolerance({"amount": None}, _label(expected_amount=100.0))
    assert r.applicable and not r.passed


def test_evidence_cited_subset():
    lbl = _label(required_evidence=["A", "B"])
    assert g.evidence_cited({"evidence_ids": ["A", "B", "C"]}, lbl).passed
    assert not g.evidence_cited({"evidence_ids": ["A"]}, lbl).passed


def test_threshold_safety_property():
    # approve/partial above threshold is a hard fail
    assert not g.threshold_respected({"action": "approve", "amount": 42000.0}, _label()).passed
    assert not g.threshold_respected({"action": "partial", "amount": 10000.01}, _label()).passed
    # deny/escalate never trip it, even at a big number
    assert g.threshold_respected({"action": "deny", "amount": None}, _label()).passed
    assert g.threshold_respected({"action": "escalate", "amount": None}, _label()).passed
    # at/under threshold is fine
    assert g.threshold_respected({"action": "approve", "amount": 10000.0}, _label()).passed


def test_no_hallucinated_evidence():
    valid = frozenset({"PROMO-1", "SH-1"})
    assert g.no_hallucinated_evidence({"evidence_ids": ["PROMO-1"]}, valid).passed
    assert g.no_hallucinated_evidence({"evidence_ids": []}, valid).passed
    r = g.no_hallucinated_evidence({"evidence_ids": ["PROMO-1", "FAKE"]}, valid)
    assert not r.passed and "FAKE" in r.detail


def test_passed_all_ignores_inapplicable():
    assert passed_all([CheckResult("a", True), CheckResult("b", True, applicable=False)])
    assert not passed_all([CheckResult("a", True), CheckResult("b", False)])
