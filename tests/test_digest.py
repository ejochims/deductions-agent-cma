"""Failure digest rendering (pure, from a synthetic results.json)."""
import json

import digest


def _results(tmp_path):
    payload = {
        "trials": ["t0"], "used_judge": True, "used_memory": True,
        "results": [
            {"case_id": "D-0001", "trial": "t0", "status": "ok", "passed": True,
             "check_results": [], "judge_verdicts": []},
            {"case_id": "D-0014", "trial": "t0", "status": "ok", "passed": False,
             "check_results": [
                 {"name": "action_correct", "passed": False, "applicable": True,
                  "detail": "drafted='approve' expected='escalate'"},
                 {"name": "threshold_respected", "passed": False, "applicable": True,
                  "detail": "HARD FAIL: approve $42000 exceeds $10000"}],
             "judge_verdicts": [
                 {"dimension": "no_unsupported", "verdict": "fail", "reason": "invented figure"}]},
            {"case_id": "D-0009", "trial": "t0", "status": "infra_error", "passed": None,
             "note": "APITimeoutError"},
        ],
    }
    p = tmp_path / "results.json"
    p.write_text(json.dumps(payload))
    return p


def test_digest_lists_failure_with_bucket_and_transcript(tmp_path):
    text = digest.build_digest(_results(tmp_path))
    assert "D-0014" in text and "[escalate]" in text
    assert "action_correct" in text and "threshold_respected" in text
    assert "judge/no_unsupported" in text
    assert "record.json" in text  # transcript path


def test_digest_lists_infra_errors_separately(tmp_path):
    text = digest.build_digest(_results(tmp_path))
    assert "Infra errors" in text and "D-0009" in text and "APITimeoutError" in text


def test_digest_passing_case_not_listed_as_failure(tmp_path):
    text = digest.build_digest(_results(tmp_path))
    # D-0001 passed; it should not appear under graded failures
    assert "**D-0001**" not in text


def test_digest_no_results(tmp_path):
    assert "Run an eval first" in digest.build_digest(tmp_path / "missing.json")
