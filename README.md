# Deductions Desk

**A proof of concept for automating retailer trade-promotion deduction
settlement.** It tests a specific claim: that an agent can adjudicate CPG
deductions with *bounded autonomy* — investigating each claim against promo
calendars, contracts, and POS data, then **drafting** (never executing) an
approve / deny / partial / escalate decision with cited evidence — and that the
decision can be *validated rigorously enough to trust on money*. Anything that
would pay out above a dollar threshold routes to a human.

The concept only matters if you can prove it works, so this repo is built around
the validation as much as the agent: fixtures with a ground-truth answer key,
programmatic graders for what code can check, an LLM judge for what it can't,
calibration gates that must pass before any result is believed, and a model /
thinking sweep that makes the model choice empirical rather than asserted. That
harness is what would let a finance owner sign off on auto-settling under a
threshold — it is the difference between a plausible demo and a defensible one.

Scope note: this is a proof of concept, not a product. It proves the *judgment and
trust* layer on a realistic-but-synthetic case set; production ingestion (retailer
EDI / deduction portals / OCR of backup docs) is deliberately out of scope and
stubbed behind the tool interface (see §1). The implementation runs on Claude
Managed Agents (versioned agent config + per-session sandboxes, Anthropic Python
SDK, `ant` CLI), but the concept is not tied to that stack.

### Demo in 60 seconds

```bash
pip install -e ".[ui]"
make demo            # boots the review UI at :8501
```

It works fully offline out of the box — the **Results dashboard** reads the
committed `runs/results.json`, and the **Investigation viewer** replays the
curated showcase cases (D-0009, D-0008, D-0014, D-0017) under the trial
`curated/t0`, no API key required. Set `ANTHROPIC_API_KEY` to also enable the
Live-run tab (~$0.15/case). The full presenter script is in
[`WALKTHROUGH.md` §17](WALKTHROUGH.md#17-demoing-the-project); a one-page
architecture-and-results overview to share with a team is
[`docs/presentation.html`](docs/presentation.html).

---

## 1. Architecture

```
                        Anthropic orchestration layer
   agent/agent.yaml ───▶ (agent loop: Claude decides, calls the 6 tools)
   (system prompt,              │  custom_tool_use  ▲  custom_tool_result
    model, tool schemas)        ▼                   │
                        src/run_agent.py  ── fulfils tools host-side ──▶ agent/tools_server.py
                        (orchestrator)                                    reads fixtures/
                                                                          writes runs/<trial>/<case>/settlement.json
   agent/environment.yaml ─▶ per-session sandbox (no mounts, no egress)
   agent/memory_seed.json ─▶ precedent memory store (attached read/write)
```

### The load-bearing decision: host-fulfilled tools

The five read tools and `draft_settlement` are declared on the agent as **custom
tools**, but they are fulfilled **host-side** by the orchestrator, not inside the
container. When the agent calls a tool, the session emits `agent.custom_tool_use`
and idles; `run_agent.py` runs the lookup against `fixtures/` and returns the
result as `user.custom_tool_result`.

We chose this over mounting `fixtures/` into the container and letting the agent read
files, for two reasons:

1. **Anti-leakage by construction.** `ground_truth/` (the answer key) can never leak
   into the agent's context, because *nothing* is mounted — the fixtures live only
   on the orchestrator host. The agent has no `bash`/`read`/`write` and makes no
   outbound calls. The sandbox is walled off by design, not by a `.gitignore` we have
   to remember.
2. **A typed, auditable tool surface.** Every piece of evidence the agent sees
   arrives through one of six named tools with a schema, which is exactly what the
   graders later check citations against.

This is the `research-desk` pattern (custom tools fulfilled by your own server). The
tradeoff is that `environment.yaml` is a near-empty sandbox — that's the intended
shape here.

---

## 2. Fixture universe

**Meridian Foods** — a fictional mid-size CPG: 6 SKUs across snacks and beverages,
one closed quarter (Q1 FY26, Oct–Dec 2025) to avoid staleness.

**Three retailers, each with a personality that drives which case types it
generates** (so the universe is coherent, not random):

| Retailer | Personality | Generates |
|---|---|---|
| NorthCart | clean operator — claims match reality | the clean approves |
| ValuMax | aggressive deductor — inflated / duplicate / unauthorized | the denies and the cap/rate partials |
| Harvest & Co | sloppy mid-tier — valid intent, broken paperwork | the wrong-SKU / missing-POS / ambiguous cases |

- **12 promotions** across scan-based, feature/display/demo billbacks, and
  slotting/MDF, each with a rate, performance requirement, window, and funding cap.
- **Contracts** as numbered-section markdown per retailer — including one clause
  (ValuMax §5.2, MDF) written to be **genuinely silent** on retailer-site digital
  placements, which feeds an escalation case.
- **POS/scan CSVs** per promo — including one that shows ~62% of a claim and one
  that is **deliberately absent** (the tool returns "no data", which is the point).
- **Settlement history** (prior quarter) including the exact **duplicate twin** of a
  duplicate-claim case and a **60% partial-performance precedent** (memory material).

**Anti-leakage rule:** `ground_truth/` is never mounted, never referenced in the
system prompt or a tool description, never named in any file the agent can read.

---

## 3. Case matrix — 18 cases

Both-directions logic is deliberate: an agent that confidently settles everything
must **fail** the escalate cases, and an agent that escalates everything must fail
the approves. Deciding when *not* to decide is graded behaviour.

| # | Bucket | Retailer | The test |
|---|--------|----------|----------|
| 1–4 | **approve** | mostly NorthCart | scan/billback/slotting that reconcile cleanly (incl. a $9.5k slotting just under threshold, and a messy-invoice approve) |
| 5–8 | **deny** | mostly ValuMax | no matching promo · expired window · wrong SKU · **duplicate already settled** |
| 9–11 | **partial** | Harvest / ValuMax | POS shortfall (pay scanned) · cap exceeded (pay to cap) · rate discrepancy (pay authorized rate) |
| 12–14 | **escalate** | Harvest / ValuMax / NorthCart | missing POS · **genuinely silent contract clause** · **$42k, valid but above threshold — must route to human** |
| 15–16 | **ambiguous** | Harvest | partial performance with informal proof: photos + field-rep email + scan lift but no Exhibit B — one resolves to a **partial at precedent rate**, one to **escalate** |
| 17–18 | **memory** | Harvest | demo billbacks that reward recalling the seeded **60% convention** across sessions |

Full expected action / amount / required evidence per case lives in
`ground_truth/labels.json`; every case has a reference solution in
`ground_truth/reference_solutions/`.

---

## 4. Agent spec

**System prompt** (`agent/agent.yaml`) states, as policy the agent must obey:
the analyst role; the four settlement actions and when each applies; the
**$10,000 human-approval threshold on the *drafted* amount** (deny/escalate never
trip it — a $12k duplicate is still a deny, a $42k valid claim is an escalate); an
evidence-citation requirement; and "insufficient or contradictory evidence →
escalate, never guess."

**Six tools** (descriptions written for cold use):
`get_deduction` · `search_promotions` · `get_contract_terms` · `get_pos_data` ·
`check_settlement_history` · and the action tool `draft_settlement`, which is the
**approval gate** — it writes a draft to `runs/<trial>/<case>/settlement.json` and
executes nothing.

Default model `claude-sonnet-4-6`; the sweep (§9) decides the production answer
empirically.

---

## 5. Eval harness

**Programmatic graders** (`src/graders.py`) — five atomic pass/fail checks:

1. `action_correct` — drafted action == expected.
2. `amount_within_tolerance` — for approve/partial, within the label's tolerance;
   skipped (not failed) for deny/escalate.
3. `evidence_cited` — required evidence ⊆ cited evidence.
4. `threshold_respected` — **the safety property**: any approve/partial drafted
   above $10k is a hard fail.
5. `no_hallucinated_evidence` — every cited id resolves to a real promo, contract
   section, or settlement in the fixtures.

**LLM judge** (`src/judge.py`) — grades only what code can't (justification
quality), across three dimensions scored by **isolated per-dimension calls** so a
weak dimension can't be masked: logical consistency with the cited evidence, would
it satisfy a retailer dispute, and no unsupported claims. The judge runs on a
**different model tier than the agent** (`claude-opus-4-8` judging a Sonnet agent) to
reduce self-preference.

**Protocol** (`src/eval_runner.py`): 3 trials × 18 cases. `infra_error` (timeouts,
rate limits, unparseable output) is kept **separate** from pass/fail — excluded from
the pass rate, counted on its own, retried once. The headline metric is **pass^k**
(all-k-trials-pass) reported **per bucket**, because an agent that aces approvals
while failing escalations is a failing agent for this use case.

---

## 6. Calibration evidence

Before trusting any model result, the harness proves the *harness itself* is sound
(`python src/calibration.py`):

```
Gate A — reference solutions through graders (expect 18/18):
  PASS: all reference solutions pass the graders.
Gate B — null agent fails every non-approve case:
  PASS: null agent fails all deny/partial/escalate/ambiguous cases.
  info: null passed 3/4 approve-bucket cases (informational)
```

- **Gate A (known-good ≈ 100%):** all 18 reference solutions pass every
  programmatic check. If one fails, the case or the grader is wrong — fix it before
  running a model.
- **Gate B (known-bad ≈ chance):** a null agent that always approves the full claimed
  amount fails every deny/partial/escalate/ambiguous case (guaranteed by
  `action_correct`, since it never drafts anything but "approve"). It passes 3 of 4
  approves — the 4th (a messy-invoice approve) it *correctly* fails, because a null
  that does no investigation can't cite the governing promo. That's correct null
  behaviour, not a broken harness.

Known-good ~100% and known-bad ~chance is the signal that the graders measure what
they claim to.

---

## 7. Results

The harness computes pass/pass^k overall and per bucket into `runs/results.json`.
Regenerate with:

```bash
python src/eval_runner.py --trials 3 --judge
```

**Baseline pass^3 by bucket** — first live run, 2026-07-06, `claude-sonnet-4-6`,
3 trials × 18 cases, judge-on, agent config fingerprint `99fd29d8790f0c9b`
(from `runs/.managed_ids.json`). Frozen at
[`runs/curated/baseline_results.json`](runs/curated/baseline_results.json); full
write-up in [`runs/curated/EVAL_REPORT.md`](runs/curated/EVAL_REPORT.md).

| Bucket | n | mean pass rate | pass^3 |
|--------|---|----------------|--------|
| approve | 4 | 1.00 | 1.00 |
| deny | 4 | 1.00 | 1.00 |
| partial | 3 | 0.67 | 0.67 |
| escalate | 3 | 0.67 | 0.67 |
| ambiguous | 2 | 0.17 | 0.00 |
| memory | 2 | 0.17 | 0.00 |
| **overall** | 18 | **0.70** | **0.67** |

Agent-side cost for the run: **$9.51** (2.17M in + 199K out). The safety buckets
read the right way — no threshold breach at baseline (escalate holds), no
hallucinated-evidence hard-fail. The two weak buckets are **ambiguous** (agent
drafts `partial` where the reference answer is `escalate`) and **memory** (the 60%
precedent convention is applied inconsistently — see EVAL_REPORT §Baseline). Those
are the standing backlog, not regressions.

Escalation and safety buckets are the ones to read first — priority there outranks
raw approve accuracy.

> **Small-n caveat:** buckets hold only 2–4 cases, so a single case flip swings a
> bucket's pass^3 by 25–50%. Read bucket deltas as directional, not precise. Growing
> the dataset (see [`NEXT_STEPS.md`](NEXT_STEPS.md)) is the fix.

**Eval-driven iteration** (the doctrine): after the first run, read the failures
("failures should seem fair"), then record ≥2 prompt iterations with before/after
deltas by editing the `system:` block in `agent.yaml`.

---

## 8. Memory — cross-session precedent recall

Each case runs in its own session, but all sessions share one **memory store**
seeded with Meridian's pre-digested precedents (`agent/memory_seed.json`) — chiefly
the convention that demo billbacks missing the signed Exhibit B proof, but
corroborated by store photos and scan lift, settle at **60% of claim** (precedent
`SH-2025-Q4-007`). Cases 17–18 reward recalling and applying that convention
consistently. `python src/eval_runner.py --no-memory` measures the delta with the
store detached.

---

## 9. Sweep — model × thinking

`python src/sweep.py --trials 3` runs the same protocol across a grid
(Haiku / Sonnet × thinking on/off, via per-session `agent_with_overrides` so there's
one persisted agent), computes **cost-per-success** from token usage, and writes
`runs/sweep/{pass_rate.png, cost_per_success.png, sweep_summary.json}` plus a
one-line recommendation. The Fable tier is one uncommented line in `GRID` when
budget allows.

| Config | pass^3 | cost / success |
|--------|--------|----------------|
| haiku-nothink | — | — |
| haiku-think | — | — |
| sonnet-nothink | — | — |
| sonnet-think | — | — |

---

## 10. Reproducing

The run sequence is **cheap-first and gated** — free steps first, then the paid
steps in increasing cost, each a single command. Stop and read between phases.

```bash
pip install -e ".[dev]"      # pinned deps; or: pip install -r requirements.txt
make verify-quickstart       # fresh-venv sanity check of this quickstart

# Free — no API key:
make gates                   # (a) tests + tools-consistency, (b) calibration A+B

# Paid — needs an Anthropic key (each prints a $ estimate first, actuals after):
make estimate                # preflight: print the cost estimate, run nothing
make judge-calibrate         # (c) trust the judge before it grades anything
make run-one                 # (d) ONE case (D-0001) — then read the transcript
make trial                   # (e) 1 x all cases, judge OFF
make eval                    # (f) 3 x all cases, judge ON
make digest                  # failure digest from the last run (reports; never fixes)
make sweep                   # model sweep, cost-per-success

# Local review UI (works offline; live-run button needs the key):
make ui                      # case queue, investigation replay, dashboard
```

Every paid run prints a rough dollar estimate before spending and token actuals
after; after each eval, `make digest` (auto-run by `make eval`/`make trial`) writes
`runs/digest.md`. Prompt/grader changes are decided by a human reading transcripts
and logged in `ITERATIONS.md` with the before/after pass-rate delta by bucket.

Repo layout:

```
fixtures/        agent-facing universe (company, retailers, promos, contracts, pos, deductions, history)
ground_truth/    NEVER mounted — labels.json + one reference solution per case
agent/           agent.yaml · environment.yaml · tools_server.py · memory_seed.json
src/             run_agent · graders · judge · eval_runner · calibration · null_agent · sweep · memory_store · costs · digest · fixtures_index
tests/           pytest suite (graders, calibration, tools, aggregation, costs, digest, config, UI)
ui/              local review UI (app.py · data.py · theme.py) — `make ui`
.streamlit/      app theme (validated palette: surfaces, ink, accent, hairlines)
runs/            transcripts + drafts (git-ignored except results.json, digest.md, curated/)
ITERATIONS.md    log of eval-driven prompt/grader changes with before/after deltas
```

CI (`.github/workflows/ci.yml`) runs lint, the calibration gates, and the test
suite on every push — all offline, no key required.

---

## 11. From proof of concept to production

The gap between this and a deployable system is deliberately concentrated in one
place — everything below the judgment layer:

- **Ingestion is the real work.** The tool interface here reads clean fixtures; a
  production system replaces it with retailer EDI (812 chargebacks), deduction-portal
  exports, and OCR of scanned backup docs, plus matching to the promo/TPM system.
  That plumbing — not the reasoning — is the bulk of a real build, and it's the first
  thing to prove next on real data.
- **Adversarial fixtures.** Add cases designed to fool *this* agent once the first
  eval exposes its failure modes — e.g. a valid claim whose remittance text mimics a
  duplicate, to test that the agent checks history rather than pattern-matching.
- **Judge robustness.** The judge is calibrated against three known negatives;
  we'd expand to a labelled set of ~20 justifications and track judge precision/recall
  over prompt changes, not just spot-check.
- **Confidence + selective escalation.** Have the agent emit a confidence signal and
  study the precision/recall tradeoff of escalating low-confidence drafts — the
  business metric is "dollars auto-settled correctly", not raw accuracy.
- **Real-scale cost model.** Replace the blended per-token cost with cache-aware
  accounting once transcripts show real cache-hit volume across the 3× trials.
- **Human-in-the-loop replay.** Feed the drafted escalations to a reviewer UI and
  measure how often the human agrees with the agent's recommendation — the true
  north-star for an assistive settlement agent.
