"""The calibration gates are the harness's own correctness proof."""
import calibration


def test_gate_a_all_reference_solutions_pass():
    ok, failures = calibration.gate_a_reference_solutions()
    assert ok, f"reference solutions failing graders: {failures}"


def test_gate_b_null_fails_every_non_approve_case():
    ok, anomalies, _info = calibration.gate_b_null_agent()
    assert ok, f"null agent wrongly passed non-approve cases: {anomalies}"
