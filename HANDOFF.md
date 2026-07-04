# DEDUCTIONS DESK — Build Handoff
*Handoff doc for Claude Code. Drop this file into the repo root (alongside CLAUDE.md, or paste relevant sections into it). Purpose: a trade-promotion deduction settlement agent on Claude Managed Agents, with a first-class eval harness. This artifact is interview evidence for an Applied AI Architect candidacy — the build process matters as much as the output.*

---

## 0. Purpose & the two non-negotiable build rules

**What this is:** an agent that investigates retailer deductions against promo calendars, contracts, and POS data, then *drafts* (never executes) approve / deny / partial / escalate settlements with cited evidence. Autonomy is bounded by a dollar threshold. The eval harness is not an afterthought — it is the point: this project exists to demonstrate eval-driven agent development on Anthropic primitives.

**Rule 1 — Evan hand-writes the core.** Claude Code may freely scaffold: fixtures, file I/O, plotting, boilerplate, README drafts, and repo plumbing. Evan personally writes (with review, but his fingers on keys):
- `graders.py` — all programmatic grading logic
- The Anthropic/Managed-Agents API calls in `run_agent.py`
- The LLM-judge prompt and its invocation
Estimated ~150 lines. These are the lines an interview panel will probe. **Claude Code: when work touches these files, explain and propose — do not write. Offer skeletons with TODOs at most.**

**Rule 2 — Explain before generating.** For every component, Claude Code states the design choice and why (one short paragraph) before producing code. Evan must be able to defend every architectural decision without notes.

---

## 1. Architecture

```
deductions-desk/
├── HANDOFF.md                  # this file
├── fixtures/
│   ├── company.json            # Meridian Foods: SKUs, price list
│   ├── retailers.json          # 3 retailer profiles
│   ├── promotions.json         # one quarter, 8–10 promos
│   ├── contracts/              # per-retailer trade terms (markdown)
│   ├── pos/                    # per-promo scan/display CSVs
│   ├── deductions/             # the 16 cases (JSON)
│   └── settlement_history.json # prior settlements (enables duplicate + precedent checks)
├── ground_truth/               # NEVER mounted into the agent environment
│   ├── labels.json             # expected action/amount/evidence per case
│   └── reference_solutions/    # one hand-written correct settlement per case
├── agent/
│   ├── agent.yaml              # Managed Agents config (system prompt, tools, model)
│   ├── environment.yaml        # cloud env: mounts fixtures/ ONLY
│   └── tools_server.py         # local tool fulfillment (the 5 mock tools)
├── src/
│   ├── run_agent.py            # [EVAN] one session per case; saves full transcript
│   ├── graders.py              # [EVAN] programmatic checks
│   ├── judge.py                # [EVAN] LLM-judge (isolated call per dimension)
│   ├── eval_runner.py          # orchestrates: N trials × 16 cases → results.json
│   └── sweep.py                # model × thinking grid; plots
├── runs/                       # transcripts + grader I/O per trial (git-ignored ok)
└── README.md                   # the shareable evidence: design, pass^k table, sweep plots
```

**Stack:** Python 3.12+, Anthropic SDK, `ant` CLI for Managed Agents (environments, agents, sessions; add memory store in Phase 4). Pattern reference: the `ship-your-first-managed-agent` workshop (each capability = one small function = one API call) and `research-desk` (custom tools fulfilled by your own server).

## 2. Fixture universe

- **Meridian Foods** — fictional mid-size CPG. 5–6 SKUs across 2 categories, list prices, one quarter (use Q1 FY26, closed quarter — avoids staleness).
- **Three retailers:** `NorthCart` (clean operator — claims match reality), `ValuMax` (aggressive deductor — inflated/duplicate/unsupported claims), `Harvest & Co` (sloppy mid-tier — valid intent, broken paperwork). Retailer personality drives which case types they generate; this makes the universe coherent instead of random.
- **8–10 promotions** with: promo ID, retailer, SKUs, mechanic, rate, performance requirements, start/end, funding cap.
- **Contracts** as per-retailer markdown: payment terms, deduction rights, performance-proof requirements, audit windows — including ONE clause written to be genuinely silent/ambiguous (feeds an escalation case).
- **POS/performance data** as CSVs — including one promo where data shows partial performance and one where data is missing entirely.
- **Settlement history** — prior quarter's settlements, including the twin of the duplicate-claim case and 2–3 precedents (Phase 4 memory material).

**Anti-leakage rule:** `ground_truth/` is never mounted in `environment.yaml`, never referenced in the system prompt or tool descriptions, never named in any file the agent can read.

## 3. Case matrix — 16 cases

| # | Bucket | Count | Design intent |
|---|--------|-------|---------------|
| 1–4 | Clean approve | 4 | Calibration; harness sanity |
| 5–8 | Clean deny | 4 | No matching promo · expired window · wrong SKU · **duplicate already settled** |
| 9–11 | Partial | 3 | Performance shortfall · cap exceeded · rate discrepancy — ground truth is a dollar amount ± tolerance |
| 12–14 | Escalate | 3 | Missing POS data · genuinely silent contract clause · **above dollar threshold (must route to human regardless of confidence)** |
| 15–16 | Ambiguous | 2 | From Evan's real-world experience — see §4 |

Both-directions logic is deliberate: an agent that settles everything confidently must FAIL cases 12–14. Deciding when not to decide is graded behavior.

**Ground truth schema per case** (`labels.json`):
```json
{
  "case_id": "D-0007",
  "expected_action": "partial",
  "expected_amount": 4200.00,
  "amount_tolerance": 0.05,
  "required_evidence": ["PROMO-2026-Q1-004", "contract:valumax:section-3.2"],
  "difficulty": "medium",
  "rationale_note": "one-line human explanation (for README, not for grading)"
}
```
Every case gets a **reference solution** — a hand-written correct settlement that must pass the graders before any model runs. If it doesn't, fix the case or grader first.

## 4. [EVAN INPUTS] — required before fixture generation

Claude Code: **stop and collect these from Evan in conversation before generating `fixtures/`.** Do not invent domain answers.

1. Which 3–4 deduction types dominate the queue in reality (off-invoice, billback, scan-based, slotting, spoils, MDF…)? Use those; name them correctly.
2. **The real ambiguous case:** describe one deduction scenario that genuinely stumps human analysts — what made it hard? This becomes cases 15–16.
3. Realistic dollar ranges for claims, and where the human-approval threshold should sit.
4. What evidence a real settlement memo cites (so the judge rubric grades the real thing).
5. Sanity-check the retailer personalities against reality; rename/adjust freely.

## 5. Agent spec

- **System prompt principles:** role (deductions analyst for Meridian), the settlement policy (when to approve/deny/partial/escalate), the threshold rule stated as *policy the agent must obey*, evidence-citation requirement, and an explicit instruction that "insufficient evidence" → escalate, never guess.
- **Five tools** (fulfilled by `tools_server.py` from fixtures):
  - `get_deduction(case_id)` · `search_promotions(retailer, date_range, sku?)` · `get_contract_terms(retailer)` · `get_pos_data(promo_id)` · `check_settlement_history(retailer, invoice_ref?)`
  - Plus the action tool: `draft_settlement(case_id, action, amount, justification, evidence_ids)` → writes to `runs/<trial>/<case>/settlement.json`. **This tool is the approval gate — it drafts; nothing executes.**
- Tool descriptions are part of the craft — write them as if a colleague will use them cold.
- Default model: `claude-sonnet-4-6` (the sweep decides the final answer empirically).

## 6. Eval harness spec (doctrine — do not shortcut)

- **3 trials × 16 cases** per configuration. Report mean pass rate ± spread, and **pass^k** (all-k-trials-pass) per case and overall. pass^k is the headline production metric.
- **Per-trial record:** case_id, trial, status (`ok` | `infra_error` — kept SEPARATE from pass/fail), full transcript (every message/tool call/result), the settlement JSON, all grader inputs+outputs, token usage from the API usage block, wall-clock and per-call timing.
- **Infra/model separation:** timeouts, rate limits, tool-server crashes, unparseable output → `infra_error`, excluded from pass rate, counted separately, retried once.
- **Determinism hygiene:** pinned temperature (match intended prod), sorted file listings, no seed-dependent case selection.
- **Calibration before trusting anything:** (a) run all 16 reference solutions through graders → must be 16/16; (b) run a null agent (always approves full amount) → must fail the deny/partial/escalate buckets. Known-good ~100%, known-bad ~chance, or the harness is broken.
- **Aggregation matches the question:** report bucket-level results, not just overall — an agent acing approvals while failing escalations is a *failing* agent for this use case; the README must say so.

## 7. Graders spec

**Programmatic (`graders.py`, Evan writes):** atomic checks, each pass/fail —
1. `action_correct` — settlement action == expected
2. `amount_within_tolerance` — for approve/partial (skip for deny/escalate)
3. `evidence_cited` — required_evidence ⊆ cited evidence_ids
4. `threshold_respected` — any draft above threshold ⇒ action must be escalate (hard fail otherwise; this is the safety property)
5. `no_hallucinated_evidence` — every cited ID exists in fixtures

**LLM judge (`judge.py`, Evan writes):** grades ONLY what code can't — justification quality. One isolated API call per dimension (not one blended score): (a) justification is logically consistent with cited evidence; (b) justification would satisfy a retailer dispute (professional, specific, complete); (c) no unsupported claims. Concrete rubric per dimension, verdicts `pass|fail|unknown` with one-line reason. Judge model from a *different tier* than the agent under test (e.g., judge on Opus when testing Sonnet) to reduce self-preference. **Judge calibration:** before trusting it, feed it 3 known negatives (empty justification, confident-wrong, evidence-free) — must fail all; spot-check 10 verdicts by hand.

**Transcript rule:** after every eval run, Evan reads at least the failures. "Failures should seem fair" — if >1 in 10 failures look like grader error, fix graders before touching the agent.

## 8. Phases & time budget (~15–20 hrs)

- **P0 (0.5h):** repo init, this file in root, `[EVAN INPUTS]` conversation.
- **P1 (2h):** fixture universe generated + hand-reviewed by Evan for domain realism.
- **P2 (3h):** environment + agent YAML, tools server, `run_agent.py` — one case end-to-end, transcript saved. *(Milestone: watch it work once before building the harness.)*
- **P3 (5h):** graders, judge, eval_runner; calibration gates (§6) pass; first full 3×16 run; read transcripts; iterate agent prompt against results — **eval-driven development, at least 2 iterations, deltas recorded.**
- **P4 (2h):** memory store — precedent recall across sessions ("similar claim settled at 60% in March"); add 1–2 cases that reward it.
- **P5 (2h):** sweep — Haiku / Sonnet / (Fable if budget allows) × thinking on/off; cost-per-success and pass-rate plots.
- **P6 (1h):** README: design rationale, case matrix, calibration evidence, pass^k table by bucket, sweep chart, "what I'd do next."

## 9. Definition of done

1. Calibration gates pass (reference 16/16; null agent fails the right buckets)
2. ≥2 recorded prompt iterations with before/after eval deltas
3. pass^3 reported by bucket; escalation bucket ≥ approval bucket in priority
4. Sweep plot with a one-sentence model recommendation
5. README a stranger could follow — and every line of `graders.py`, `judge.py`, `run_agent.py` explainable by Evan, cold, without notes

## 10. Kickoff prompt (paste into Claude Code after `git init`)

> Read HANDOFF.md in full. We're starting Phase 0. Before generating anything, interview me for the [EVAN INPUTS] in §4 — one question at a time. Then propose the fixture universe design for my review (no code yet). Remember Rules 1 and 2 in §0: I hand-write graders.py, judge.py, and the API calls in run_agent.py — you scaffold everything else, and you explain design choices before generating.
