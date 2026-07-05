"""Host-side fulfilment of the Deductions Desk custom tools.

The agent (running on Anthropic's orchestration layer) calls the six tools
declared in agent/agent.yaml. It never executes them itself: the session emits
`agent.custom_tool_use`, and the orchestrator (src/run_agent.py) calls
`ToolServer.dispatch(...)` here to produce the result, then returns it to the
session as a `user.custom_tool_result` event.

Everything is read straight from `fixtures/`. This module is deliberately dumb:
no grading, no ground-truth access, no API calls. It reads `fixtures/` and writes
draft settlements to `runs/`. `ground_truth/` is never referenced — that is the
anti-leakage boundary, enforced here by simply never importing or opening it.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ToolError(Exception):
    """Raised for a bad tool call (unknown case, unknown tool, bad action).

    The orchestrator turns this into a tool_result with is_error=True so the
    agent can recover, rather than crashing the run.
    """


VALID_ACTIONS = ("approve", "deny", "partial", "escalate")


def _normalize(retailer: str) -> str:
    """Fold a retailer id or display name to a canonical id fragment.

    Accepts "valumax", "ValuMax", "Harvest & Co", "harvest-co", etc. so the
    tools are forgiving about whichever form the agent passes.
    """
    return "".join(ch for ch in retailer.lower() if ch.isalnum())


class ToolServer:
    def __init__(self, fixtures_dir: str | Path, runs_dir: str | Path) -> None:
        self.fixtures = Path(fixtures_dir)
        self.runs = Path(runs_dir)
        # Load the small, static fixtures once.
        self.company: dict = self._load_json("company.json")
        self.retailers: list = self._load_json("retailers.json")
        self.promotions: list = self._load_json("promotions.json")
        self.history: list = self._load_json("settlement_history.json")
        # Map any accepted retailer spelling -> canonical retailer_id.
        self._retailer_ids: dict[str, str] = {}
        for r in self.retailers:
            rid = r["retailer_id"]
            self._retailer_ids[_normalize(rid)] = rid
            self._retailer_ids[_normalize(r["name"])] = rid

    # ------------------------------------------------------------------ io
    def _load_json(self, name: str) -> Any:
        return json.loads((self.fixtures / name).read_text())

    def _resolve_retailer(self, retailer: str) -> str | None:
        return self._retailer_ids.get(_normalize(retailer))

    # --------------------------------------------------------------- tools
    def get_deduction(self, case_id: str) -> dict:
        path = self.fixtures / "deductions" / f"{case_id}.json"
        if not path.exists():
            raise ToolError(f"No deduction case '{case_id}'.")
        return json.loads(path.read_text())

    def search_promotions(
        self,
        retailer: str,
        date_range: list[str] | None = None,
        sku: str | None = None,
    ) -> dict:
        rid = self._resolve_retailer(retailer)
        if rid is None:
            # A typo'd retailer must be an ERROR, not a plausible-empty result —
            # "0 promotions found" would read as "unauthorized deduction" and
            # steer the agent toward a wrong deny.
            raise ToolError(f"Unknown retailer '{retailer}'.")
        results = [p for p in self.promotions if p["retailer_id"] == rid]
        if sku:
            results = [p for p in results if sku in p.get("skus", [])]
        if date_range and len(date_range) == 2 and all(date_range):
            start, end = date_range[0], date_range[1]
            # Keep promos whose [start_date, end_date] overlaps [start, end].
            results = [
                p for p in results
                if p["start_date"] <= end and p["end_date"] >= start
            ]
        return {
            "retailer": rid,
            "count": len(results),
            "promotions": results,
        }

    def get_contract_terms(self, retailer: str) -> dict:
        rid = self._resolve_retailer(retailer)
        if rid is None:
            raise ToolError(f"Unknown retailer '{retailer}'.")
        path = self.fixtures / "contracts" / f"{rid}.md"
        if not path.exists():
            raise ToolError(f"No contract on file for '{rid}'.")
        return {"retailer": rid, "contract_markdown": path.read_text()}

    def get_pos_data(self, promo_id: str) -> dict:
        path = self.fixtures / "pos" / f"{promo_id}.csv"
        if not path.exists():
            # Deliberately not an error: "missing POS" is a real, gradeable
            # signal that should push the agent toward escalate, not a crash.
            return {
                "promo_id": promo_id,
                "found": False,
                "message": "No POS data is available for this promotion.",
                "rows": [],
            }
        with path.open() as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            row["units_scanned"] = int(row["units_scanned"])
            row["avg_unit_price"] = float(row["avg_unit_price"])
        total = sum(r["units_scanned"] for r in rows)
        return {
            "promo_id": promo_id,
            "found": True,
            "total_units_scanned": total,
            "rows": rows,
        }

    def check_settlement_history(
        self, retailer: str, invoice_ref: str | None = None
    ) -> dict:
        rid = self._resolve_retailer(retailer)
        if rid is None:
            # Same rule as search_promotions: an empty history for a typo'd
            # retailer would masquerade as "no duplicate exists".
            raise ToolError(f"Unknown retailer '{retailer}'.")
        results = [s for s in self.history if s["retailer_id"] == rid]
        if invoice_ref:
            needle = invoice_ref.lower()
            results = [
                s for s in results
                if needle in s.get("deduction_ref", "").lower()
                or needle in s.get("reference", "").lower()
            ]
        return {
            "retailer": rid,
            "count": len(results),
            "settlements": results,
        }

    def draft_settlement(
        self,
        case_id: str,
        action: str,
        amount: float | None,
        justification: str,
        evidence_ids: list[str],
        trial: str,
    ) -> dict:
        """Write the drafted settlement to runs/<trial>/<case_id>/settlement.json.

        This is the approval gate. It records a draft for human review and
        executes nothing. Deny/escalate carry a null amount by policy.
        """
        if action not in VALID_ACTIONS:
            raise ToolError(
                f"action must be one of {VALID_ACTIONS}, got '{action}'."
            )
        if action in ("deny", "escalate"):
            amount = None
        elif not isinstance(amount, (int, float)) or isinstance(amount, bool) \
                or amount <= 0:
            # Symmetric with the null coercion above: the gate enforces policy in
            # code, so an approve/partial without a positive dollar amount is
            # rejected back to the agent rather than recorded as a broken draft.
            raise ToolError(
                f"{action} requires a positive numeric amount, got {amount!r}."
            )
        settlement = {
            "case_id": case_id,
            "action": action,
            "amount": amount,
            "justification": justification,
            "evidence_ids": list(evidence_ids or []),
            "drafted_at": datetime.now(UTC).isoformat(),
        }
        out_dir = self.runs / trial / case_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "settlement.json"
        out_path.write_text(json.dumps(settlement, indent=2) + "\n")
        return {"status": "drafted", "path": str(out_path), "settlement": settlement}

    # ------------------------------------------------------------ dispatch
    def dispatch(self, name: str, tool_input: dict, trial: str) -> dict:
        """Route a custom-tool call to its handler.

        `trial` is injected by the orchestrator (it is a property of the eval
        run, not something the agent supplies) and is only used by
        draft_settlement to decide where to write.
        """
        tool_input = dict(tool_input or {})
        if name == "get_deduction":
            return self.get_deduction(tool_input["case_id"])
        if name == "search_promotions":
            return self.search_promotions(
                tool_input["retailer"],
                tool_input.get("date_range"),
                tool_input.get("sku"),
            )
        if name == "get_contract_terms":
            return self.get_contract_terms(tool_input["retailer"])
        if name == "get_pos_data":
            return self.get_pos_data(tool_input["promo_id"])
        if name == "check_settlement_history":
            return self.check_settlement_history(
                tool_input["retailer"], tool_input.get("invoice_ref")
            )
        if name == "draft_settlement":
            return self.draft_settlement(
                tool_input["case_id"],
                tool_input["action"],
                tool_input.get("amount"),
                tool_input["justification"],
                tool_input.get("evidence_ids", []),
                trial,
            )
        raise ToolError(f"Unknown tool '{name}'.")
