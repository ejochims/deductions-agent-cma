"""Regression tests from the second soundness pass.

Each test pins a bug found by adversarial review: stale drafts surviving a
retry, plausible-empty tool results for a typo'd retailer, the settlement gate
accepting an approve/partial without an amount, and the sweep's missing cost
preflight.
"""

import json

import pytest
from tools_server import ToolError, ToolServer

import run_agent
import sweep
from fixtures_index import FIXTURES_DIR


@pytest.fixture
def ts(tmp_path):
    return ToolServer(FIXTURES_DIR, tmp_path)


# --- stale draft across retries -------------------------------------------
def test_clear_prior_draft_removes_stale_settlement(tmp_path, monkeypatch):
    monkeypatch.setattr(run_agent, "RUNS_DIR", tmp_path)
    stale = tmp_path / "t0" / "D-0001" / "settlement.json"
    stale.parent.mkdir(parents=True)
    stale.write_text(json.dumps({"action": "approve", "amount": 1.0}))

    run_agent.clear_prior_draft("t0", "D-0001")
    assert not stale.exists()
    # And it's safe when nothing exists:
    run_agent.clear_prior_draft("t0", "D-0001")


# --- unknown retailer must error, not return plausible-empty ---------------
def test_search_promotions_unknown_retailer_raises(ts):
    with pytest.raises(ToolError, match="Unknown retailer"):
        ts.dispatch("search_promotions", {"retailer": "wallmart"}, "t")


def test_history_unknown_retailer_raises(ts):
    with pytest.raises(ToolError, match="Unknown retailer"):
        ts.dispatch("check_settlement_history", {"retailer": "wallmart"}, "t")


def test_known_retailer_spellings_still_resolve(ts):
    for spelling in ("valumax", "ValuMax", "Harvest & Co", "harvest-co", "NorthCart"):
        r = ts.dispatch("search_promotions", {"retailer": spelling}, "t")
        assert r["retailer"] in ("valumax", "harvest-co", "northcart")


# --- the settlement gate enforces amounts both ways ------------------------
def test_approve_without_amount_rejected(ts):
    for bad in (None, 0, -5, True, "6800"):
        with pytest.raises(ToolError, match="positive numeric amount"):
            ts.dispatch("draft_settlement", {
                "case_id": "D-0001", "action": "approve", "amount": bad,
                "justification": "x", "evidence_ids": []}, "t")


def test_partial_with_valid_amount_accepted(ts):
    res = ts.dispatch("draft_settlement", {
        "case_id": "D-0009", "action": "partial", "amount": 5519.80,
        "justification": "x", "evidence_ids": []}, "t")
    assert res["settlement"]["amount"] == 5519.80


def test_deny_escalate_still_coerce_to_null(ts):
    for action in ("deny", "escalate"):
        res = ts.dispatch("draft_settlement", {
            "case_id": "D-0008", "action": action, "amount": 12000.0,
            "justification": "x", "evidence_ids": []}, "t")
        assert res["settlement"]["amount"] is None


# --- sweep prints a preflight estimate --------------------------------------
def test_sweep_estimate_totals():
    est = sweep.sweep_estimate(sweep.GRID, n_cases=18, n_trials=3, use_judge=False)
    assert set(est["per_config"]) == {c["label"] for c in sweep.GRID}
    assert est["total"] == round(sum(est["per_config"].values()), 2)
    assert est["total"] > 0
