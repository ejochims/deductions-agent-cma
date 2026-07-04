"""Sweep cost math (pure) and grid well-formedness."""
import sweep


def test_usage_cost():
    u = {"input_tokens": 1_000_000, "output_tokens": 200_000}
    assert abs(sweep.usage_cost("claude-haiku-4-5", u) - 2.00) < 1e-9    # 1*1 + .2*5
    assert abs(sweep.usage_cost("claude-sonnet-4-6", u) - 6.00) < 1e-9   # 1*3 + .2*15


def test_usage_cost_folds_cache_into_input():
    u = {"input_tokens": 0, "cache_read_input_tokens": 500_000,
         "cache_creation_input_tokens": 500_000, "output_tokens": 0}
    assert abs(sweep.usage_cost("claude-haiku-4-5", u) - 1.00) < 1e-9    # 1M in @ $1


def test_summarize_config():
    u = {"input_tokens": 1_000_000, "output_tokens": 200_000}
    payload = {
        "summary": {"overall": {"pass_k": 0.5, "mean_pass_rate": 0.5}},
        "results": [
            {"case_id": "D-0001", "trial": "x-t0", "status": "ok", "passed": True, "usage": u},
            {"case_id": "D-0002", "trial": "x-t0", "status": "ok", "passed": False, "usage": u},
        ],
    }
    row = sweep.summarize_config("claude-haiku-4-5", payload)
    assert row["ok_trials"] == 2 and row["successes"] == 1
    assert abs(row["total_cost_usd"] - 4.00) < 1e-9
    assert abs(row["cost_per_success_usd"] - 4.00) < 1e-9


def test_grid_models_all_priced():
    for cfg in sweep.GRID:
        assert cfg["model"] in sweep.PRICING
