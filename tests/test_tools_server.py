"""Tool-server fulfilment against the real fixtures."""
import json

import pytest
from tools_server import ToolError, ToolServer

from fixtures_index import FIXTURES_DIR


@pytest.fixture
def ts(tmp_path):
    return ToolServer(FIXTURES_DIR, tmp_path)


def test_get_deduction(ts):
    d = ts.dispatch("get_deduction", {"case_id": "D-0009"}, "t")
    assert d["case_id"] == "D-0009" and d["amount"] == 8899.80


def test_search_promotions_filters(ts):
    r = ts.dispatch("search_promotions", {"retailer": "Harvest & Co", "sku": "MF-BV-101"}, "t")
    assert "PROMO-2026-Q1-008" in [p["promo_id"] for p in r["promotions"]]


def test_search_promotions_excludes_out_of_window(ts):
    # promo 004 ends 2025-10-27; an 10/28-11/17 window must not match it
    r = ts.dispatch("search_promotions",
                    {"retailer": "valumax", "date_range": ["2025-10-28", "2025-11-17"], "sku": "MF-SN-003"}, "t")
    assert all(p["promo_id"] != "PROMO-2026-Q1-004" for p in r["promotions"])


def test_get_pos_present_and_missing(ts):
    present = ts.dispatch("get_pos_data", {"promo_id": "PROMO-2026-Q1-008"}, "t")
    assert present["found"] and present["total_units_scanned"] == 8492
    missing = ts.dispatch("get_pos_data", {"promo_id": "PROMO-2026-Q1-009"}, "t")
    assert missing["found"] is False


def test_check_settlement_history_duplicate(ts):
    h = ts.dispatch("check_settlement_history", {"retailer": "valumax", "invoice_ref": "VM-88214"}, "t")
    assert "SH-2025-Q4-011" in [s["settlement_id"] for s in h["settlements"]]


def test_get_contract_terms(ts):
    c = ts.dispatch("get_contract_terms", {"retailer": "valumax"}, "t")
    assert "5.2" in c["contract_markdown"]


def test_draft_settlement_writes_file_and_nulls_amount(tmp_path):
    ts = ToolServer(FIXTURES_DIR, tmp_path)
    res = ts.dispatch("draft_settlement", {
        "case_id": "D-0008", "action": "deny", "amount": 12000.0,
        "justification": "dup", "evidence_ids": ["SH-2025-Q4-011"]}, "t")
    assert res["status"] == "drafted"
    written = json.loads((tmp_path / "t" / "D-0008" / "settlement.json").read_text())
    assert written["action"] == "deny" and written["amount"] is None


def test_get_precedents_returns_convention(ts):
    p = ts.dispatch("get_precedents", {}, "t")
    assert p["count"] >= 1
    blob = json.dumps(p["precedents"])
    # The demo-billback convention and the id to cite must be reachable.
    assert "60%" in blob and "SH-2025-Q4-007" in blob


def test_get_precedents_empty_when_disabled(tmp_path):
    ts = ToolServer(FIXTURES_DIR, tmp_path, precedents_enabled=False)
    p = ts.dispatch("get_precedents", {}, "t")
    assert p["count"] == 0 and p["precedents"] == []


def test_unknown_case_raises_toolerror(ts):
    with pytest.raises(ToolError):
        ts.dispatch("get_deduction", {"case_id": "D-9999"}, "t")


def test_unknown_tool_raises_toolerror(ts):
    with pytest.raises(ToolError):
        ts.dispatch("no_such_tool", {}, "t")
