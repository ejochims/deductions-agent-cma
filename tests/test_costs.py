"""Cost estimate + actuals math (pure)."""
import json

import costs


def test_usage_cost_matches_pricing():
    u = {"input_tokens": 1_000_000, "output_tokens": 200_000}
    assert abs(costs.usage_cost("claude-sonnet-4-6", u) - 6.00) < 1e-9  # 1*3 + .2*15


def test_estimate_eval_judge_adds_cost():
    no_judge = costs.estimate_eval(18, 3, "claude-sonnet-4-6", use_judge=False)
    with_judge = costs.estimate_eval(18, 3, "claude-sonnet-4-6", use_judge=True)
    assert no_judge["judge_cost"] == 0.0
    assert with_judge["judge_cost"] > 0.0
    assert with_judge["total_cost"] > no_judge["total_cost"]
    assert no_judge["runs"] == 54


def test_estimate_judge_calibration():
    est = costs.estimate_judge_calibration(3)
    assert est["calls"] == 9 and est["total_cost"] > 0


def test_actuals_reads_records(tmp_path):
    # two fake records with usage
    for case in ["D-0001", "D-0002"]:
        d = tmp_path / "t0" / case
        d.mkdir(parents=True)
        (d / "record.json").write_text(json.dumps(
            {"usage": {"input_tokens": 1_000_000, "output_tokens": 100_000}}))
    act = costs.actuals_from_runs(tmp_path, ["t0"], ["D-0001", "D-0002"], "claude-haiku-4-5")
    assert act["records"] == 2
    assert act["input_tokens"] == 2_000_000 and act["output_tokens"] == 200_000
    # 2M in @ $1 + 0.2M out @ $5 = 2.00 + 1.00 = 3.00
    assert abs(act["agent_cost"] - 3.00) < 1e-9


def test_actuals_empty(tmp_path):
    act = costs.actuals_from_runs(tmp_path, ["t0"], ["D-0001"], "claude-sonnet-4-6")
    assert act["records"] == 0 and act["agent_cost"] == 0.0
