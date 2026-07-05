"""LLM judge for justification quality.

The judge grades ONLY what code cannot: the quality of the justification, given the
cited evidence. Three dimensions, each scored by its OWN isolated API call (not one
blended score) so a weak dimension can't be masked by a strong one:
  1. consistent     — the justification is logically consistent with the evidence
                      it cites.
  2. dispute_proof  — the justification would satisfy a retailer dispute
                      (professional, specific, complete).
  3. no_unsupported — the justification makes no claims its evidence doesn't
                      support.

Each returns pass | fail | unknown with a one-line reason. The judge sees the
drafted settlement and the fixture text behind each cited evidence id — NOT the
ground-truth label; it grades quality, not correctness.

Judge model is a DIFFERENT tier than the agent under test (agent default: Sonnet;
judge: Opus) to reduce self-preference. Before trusting it, run judge calibration
(`python src/judge.py --calibrate`): it must fail an empty, a confident-but-wrong,
and an evidence-free justification.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from fixtures_index import resolve_evidence

DIMENSIONS = ("consistent", "dispute_proof", "no_unsupported")

# Judge on a different tier than the agent under test (agent default: Sonnet).
JUDGE_MODEL = "claude-opus-4-8"

# One concrete rubric per dimension. Each is graded in isolation.
RUBRICS: dict[str, str] = {
    "consistent": (
        "Dimension: LOGICAL CONSISTENCY WITH EVIDENCE.\n"
        "Pass only if every factual and numeric claim in the justification is "
        "logically consistent with the cited evidence — the action follows from "
        "the evidence, and any arithmetic (units x rate, cap, tolerance) matches "
        "the evidence shown. Fail if the justification contradicts its own "
        "evidence, or the stated numbers do not reconcile. Use 'unknown' only if "
        "the evidence provided is insufficient to judge consistency at all."
    ),
    "dispute_proof": (
        "Dimension: WOULD SATISFY A RETAILER DISPUTE.\n"
        "Imagine the retailer's deductions analyst reads this justification to "
        "contest the settlement. Pass only if it is professional, specific, and "
        "complete: it names the governing promotion/deal or contract term, states "
        "the reconciliation or reason plainly, and would leave a reasonable "
        "counterparty with no obvious opening. Fail if it is vague, unprofessional, "
        "conclusory ('approved as claimed'), or omits the key fact the dispute "
        "would turn on."
    ),
    "no_unsupported": (
        "Dimension: NO UNSUPPORTED CLAIMS.\n"
        "Pass only if the justification asserts nothing that the cited evidence "
        "does not support — no invented figures, no appeals to documents not in "
        "evidence, no claims of proof that isn't shown. Fail if any assertion goes "
        "beyond what the evidence establishes. Be strict: a plausible-sounding but "
        "uncited claim is a fail."
    ),
}

_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail", "unknown"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}

_JUDGE_SYSTEM = (
    "You are a strict, fair grader auditing a trade-promotion deduction "
    "settlement drafted by an analyst agent. You grade exactly ONE quality "
    "dimension at a time, described below. You are given the drafted settlement "
    "and the source evidence the analyst cited (and nothing else — do not assume "
    "facts not shown). Return only your verdict for THIS dimension as JSON with "
    "keys 'verdict' (pass | fail | unknown) and 'reason' (one line)."
)


@dataclass
class Verdict:
    dimension: str
    verdict: str          # "pass" | "fail" | "unknown"
    reason: str


def _evidence_context(settlement: dict) -> str:
    """Assemble the fixture text behind every cited evidence id."""
    cited = settlement.get("evidence_ids") or []
    if not cited:
        return "(the analyst cited no evidence)"
    return "\n\n".join(resolve_evidence(e) for e in cited)


def _dimension_prompt(settlement: dict, dimension: str) -> str:
    return (
        f"{RUBRICS[dimension]}\n\n"
        "=== DRAFTED SETTLEMENT ===\n"
        f"action: {settlement.get('action')}\n"
        f"amount: {settlement.get('amount')}\n"
        f"justification: {settlement.get('justification')}\n"
        f"cited evidence ids: {settlement.get('evidence_ids')}\n\n"
        "=== SOURCE EVIDENCE (all the analyst may rely on) ===\n"
        f"{_evidence_context(settlement)}\n\n"
        f"Grade the '{dimension}' dimension now."
    )


def judge_dimension(client, settlement: dict, dimension: str) -> Verdict:
    """One isolated API call scoring a single dimension.

    The call is independent per dimension: no shared conversation, so a strong
    dimension cannot leak into a weak one's score.
    """
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=512,
        system=_JUDGE_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": _VERDICT_SCHEMA}},
        messages=[{"role": "user", "content": _dimension_prompt(settlement, dimension)}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)
        return Verdict(dimension, parsed["verdict"], parsed["reason"])
    except (json.JSONDecodeError, KeyError) as exc:
        # A judge that returns unparseable output is an infra problem, not a
        # 'fail' — surface it as unknown so the harness doesn't score it as a
        # quality failure.
        return Verdict(dimension, "unknown", f"unparseable judge reply: {exc}")


def judge_settlement(client, settlement: dict) -> list[Verdict]:
    """Score all three dimensions with independent calls. Called by the harness."""
    return [judge_dimension(client, settlement, dim) for dim in DIMENSIONS]


def all_pass(verdicts: list[Verdict]) -> bool:
    return all(v.verdict == "pass" for v in verdicts)


# --------------------------------------------------------------- calibration
def known_negatives() -> list[tuple[str, dict]]:
    """Three settlements a trustworthy judge MUST fail (judge calibration)."""
    return [
        ("empty_justification", {
            "case_id": "CAL-1", "action": "approve", "amount": 6800.0,
            "justification": "", "evidence_ids": ["PROMO-2026-Q1-001"]}),
        ("confident_wrong", {
            "case_id": "CAL-2", "action": "approve", "amount": 6800.0,
            "justification": ("Fully verified: POS confirms all 20,000 claimed "
                              "units at $0.50, well within the promotion's cap, so "
                              "the claim is unquestionably valid and paid in full."),
            "evidence_ids": ["PROMO-2026-Q1-001"]}),  # promo caps at 10k units
        ("evidence_free", {
            "case_id": "CAL-3", "action": "approve", "amount": 6800.0,
            "justification": "Looks fine to me; approving as claimed.",
            "evidence_ids": []}),
    ]


def run_calibration(client) -> None:
    for label, settlement in known_negatives():
        verdicts = judge_settlement(client, settlement)
        failed = [v.dimension for v in verdicts if v.verdict == "fail"]
        ok = "PASS" if failed else "PROBLEM"
        print(f"[{ok}] {label}: judge failed dimensions {failed}")
        for v in verdicts:
            print(f"    {v.dimension:14s} {v.verdict:8s} {v.reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Judge calibration (needs API).")
    parser.add_argument("--calibrate", action="store_true",
                        help="Run the 3 known-negative settlements through the judge.")
    args = parser.parse_args()
    if not args.calibrate:
        parser.error("nothing to do; pass --calibrate")
    from costs import estimate_judge_calibration
    est = estimate_judge_calibration(len(known_negatives()))
    print(f"COST ESTIMATE (rough) — {est['calls']} judge calls on "
          f"{est['judge_model']}: ~${est['total_cost']:.2f}\n")
    import anthropic  # local: only needed when actually calling the API
    run_calibration(anthropic.Anthropic())


if __name__ == "__main__":
    main()
