"""[EVAN WRITES THE PROMPT + INVOCATION] LLM judge for justification quality.

Rule 1: the judge prompt and its API invocation are hand-written by Evan. Claude
Code provided the skeleton — the three-dimension structure, the Verdict container,
the per-dimension dispatch, and the calibration harness — and left the prompt text
and the Anthropic call as TODO(EVAN).

The judge grades ONLY what code cannot: the quality of the justification, given
the cited evidence. Three dimensions, each scored by its OWN isolated API call
(not one blended score) so a weak dimension can't be masked by a strong one:
  1. consistent   — the justification is logically consistent with the evidence
                    it cites.
  2. dispute_proof — the justification would satisfy a retailer dispute
                    (professional, specific, complete).
  3. no_unsupported — the justification makes no claims its evidence doesn't
                    support.

Each returns pass | fail | unknown with a one-line reason.

Judge model must be from a DIFFERENT tier than the agent under test (e.g. judge on
Opus while testing Sonnet) to reduce self-preference. Before trusting the judge,
run judge calibration (calibration.py / the 3 known negatives) — it must fail an
empty justification, a confident-but-wrong one, and an evidence-free one.
"""

from __future__ import annotations

from dataclasses import dataclass

DIMENSIONS = ("consistent", "dispute_proof", "no_unsupported")

# Judge on a different tier than the agent under test (agent default: Sonnet).
JUDGE_MODEL = "claude-opus-4-8"


@dataclass
class Verdict:
    dimension: str
    verdict: str          # "pass" | "fail" | "unknown"
    reason: str


def _evidence_context(settlement: dict) -> str:
    """Build the evidence the judge is allowed to reason over.

    The judge sees the settlement's action, amount, justification, and the
    fixture content behind each cited evidence id — NOT the ground-truth label
    (the judge grades quality, not correctness). Resolving evidence ids to their
    fixture text is mechanical; Evan can flesh this out with fixtures_index /
    tools_server reads as the prompt requires.
    """
    # TODO(EVAN): assemble the cited promo terms / contract sections / history
    # entries into the context string the prompt will reference.
    raise NotImplementedError("EVAN: assemble evidence context for the judge")


def judge_dimension(client, settlement: dict, dimension: str) -> Verdict:
    """One isolated API call scoring a single dimension.

    TODO(EVAN): write the concrete rubric prompt for `dimension`, call
    client.messages.create(model=JUDGE_MODEL, ...) with a structured/JSON output
    constraining the reply to {verdict: pass|fail|unknown, reason: <one line>},
    parse it, and return a Verdict. Keep each dimension's call independent — do
    not share context between dimensions.
    """
    raise NotImplementedError(f"EVAN: implement judge prompt/call for '{dimension}'")


def judge_settlement(client, settlement: dict) -> list[Verdict]:
    """Score all three dimensions with independent calls. Called by the harness."""
    return [judge_dimension(client, settlement, dim) for dim in DIMENSIONS]


def all_pass(verdicts: list[Verdict]) -> bool:
    return all(v.verdict == "pass" for v in verdicts)
