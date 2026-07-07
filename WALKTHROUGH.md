# Walkthrough — how this system works, from first principles

This document explains everything happening in this repo, bottom-up: what an LLM
API call actually is, what "tool use" and "an agent" mean mechanically, how Claude
Managed Agents runs the loop, how one deduction case flows through the system end
to end, and how the eval harness proves the results are trustworthy. It assumes no
prior knowledge of the Anthropic API.

**How to use this document.** Learning how the system works for the first time:
read §1–§10 in order. Coming back after time away: start at **§14** (the
30-minute re-orientation). Running it: **§11** is the operator's runbook.
Reading or changing the code: **§15** is the module-by-module tour. Running or
writing tests: **§16**. Demoing the POC: **§17** is the demo script, showcase
cases, and offline fallback.

---

## 1. The problem in one paragraph

Retailers pay CPG manufacturers' invoices short, claiming promotional allowances —
"we ran your October scan promo, so we deducted $8,899.80." Someone has to check
each claim: does an authorized promotion exist, do the dates and SKUs match, does
scan data support the claimed volume, was this invoice already settled, what does
the contract require? That's the job this system does: it investigates each
deduction and **drafts** a settlement — approve, deny, partial, or escalate —
with cited evidence. It never moves money. Anything it would pay above $10,000 is
forced to a human.

---

## 2. First principles: what an LLM API call is

Everything downstream is built on one primitive. A call to the model is a single
stateless HTTPS request:

```
you send:    { model, system prompt, messages: [ ...conversation so far... ], tools }
model sends: one new assistant message
```

Six facts that shape everything else:

1. **The model is stateless.** It remembers nothing between calls. Every request
   re-sends the entire conversation. "Memory," "sessions," "agents" — all of that
   is bookkeeping *around* the model, not in it.
2. **The unit of cost is the token** (~¾ of a word). You pay per input token
   (everything you send) and per output token (everything it generates). Because
   the whole conversation is re-sent every call, input cost grows with every turn
   — which is why our cost estimator assumes input tokens dominate.
3. **The system prompt is the standing instruction set.** It rides at the front of
   every call and defines the role, the rules, and the policy. Ours carries the
   settlement policy: the four actions, the $10k threshold, the citation rule,
   "insufficient evidence → escalate, never guess."
4. **The model can "think" before it answers.** Extended thinking gives the
   model a private scratchpad: it generates reasoning tokens (billed like output)
   before and between its visible replies and tool calls. For multi-step work
   like reconciliation arithmetic this measurably improves reliability, which is
   why our agent runs with thinking on — the Managed Agents default, and the
   config the eval measures.
5. **Re-sending the conversation is cheaper than it looks.** Providers cache the
   prompt *prefix*: on each turn, the unchanged early part of the conversation is
   served as a cache read at roughly a tenth of the fresh-input price, and only
   the new tail costs full rate. Managed Agents applies this automatically; the
   recorded usage splits cache reads/writes out (our cost accounting folds them
   into input at the headline rate — deliberately conservative).
6. **The model only ever emits text/structured output.** It cannot read files,
   query databases, or move money. Which leads to tool use.

## 3. Tool use: the model asks, your code acts

"Tool use" is a protocol, not a capability. You describe tools to the model — a
name, a plain-English description, and a JSON schema of inputs:

```yaml
name: get_pos_data
description: Fetch weekly point-of-sale scan data for a promotion...
input_schema: { promo_id: string }
```

When the model decides it needs one, it doesn't *do* anything — it emits a
structured request in its reply:

```json
{ "type": "tool_use", "name": "get_pos_data", "input": { "promo_id": "PROMO-2026-Q1-008" } }
```

**Your code** executes it (here: read a CSV from `fixtures/pos/`) and appends the
result to the conversation as a new message. The model reads the result on the
next call and continues. Two consequences worth internalizing:

- The tool description is prompt engineering. The model chooses tools by reading
  the descriptions, so they're written for cold use ("Call it first", "a claim you
  cannot corroborate ... should be escalated").
- The tool boundary is the security boundary. The model can only see what tools
  return. Our agent has exactly six tools and nothing else — no filesystem, no
  shell — so the ground-truth answer key is unreachable *by construction*.

## 4. What an "agent" is

An agent is nothing more mysterious than a loop:

```
messages = [task]
loop:
    reply = model(system, messages, tools)
    if reply contains tool_use:  execute it, append result, continue
    else:                        done
```

System prompt + tools + loop-until-done. The model decides which tools to call,
in what order, and when it has enough evidence to act. Everything else in this
repo is either (a) infrastructure to run that loop, or (b) machinery to *measure*
whether the loop produces correct decisions.

## 5. Claude Managed Agents: who runs the loop

You can run the loop yourself with raw API calls. Managed Agents is Anthropic
running it server-side. Three resources:

| Resource | What it is | Ours |
|---|---|---|
| **Agent** | A persisted, versioned config: model, system prompt, tool declarations. Created once, referenced forever. Updating it creates a new immutable version. | `agent/agent.yaml` — one YAML that both the CLI and the SDK consume |
| **Environment** | A sandbox template for the per-session container. | `agent/environment.yaml` — nothing mounted, no network egress |
| **Session** | One live run of the agent. Sessions reference the agent by ID + version. | one session per (case, trial) |

Two mechanics of the agent resource matter here. First, **updates never mutate
in place** — every update publishes a new immutable version, and each session
pins the version it runs, so any past run is traceable to the exact prompt it
ran under. Second, our runner **fingerprints `agent.yaml`** (a hash of the
config, cached beside the agent id): edit the system prompt and the next run
automatically publishes a new version and pins to it. Without that, a stale
cached agent would keep serving the old prompt and the eval would silently
measure the wrong thing — the classic failure mode of prompt iteration.

You talk to a session through **events** over a server-sent-event stream:

- You send `user.message` ("Investigate case D-0009 and draft a settlement...").
- The stream delivers `agent.message` (text), `agent.thinking`, tool events, and
  status transitions (`session.status_running` / `idle` / `terminated`).
- Ordering rule: open the stream **before** sending the kickoff — the stream has
  no replay, so events emitted before you connect are lost.

### Custom tools: the host-fulfilled pattern

Our six tools are declared on the agent as **custom tools**, which means Anthropic
doesn't execute them — *our process does*. The mechanics:

1. The model calls `get_pos_data`. The session emits an
   `agent.custom_tool_use` event and goes **idle** — the loop pauses.
2. Our orchestrator (`src/run_agent.py`) catches the event, dispatches to
   `agent/tools_server.py`, which reads the fixture and returns JSON.
3. The orchestrator sends a `user.custom_tool_result` event carrying that JSON.
4. The session resumes; the model reads the result and continues.

So the division of labor is: **Anthropic runs the reasoning loop; we serve the
data.** The fixtures live only on our machine. The sandbox container is an empty
room the agent never even needs — it has no bash, no file access, and the
environment allows no network. In production, `tools_server.py` is the seam
where real systems (TPM/promo system, contract repository, POS feed, AR history)
plug in without touching anything else.

The orchestrator also records everything: every event into a transcript, token
usage from each `span.model_request_end` event, wall-clock timing, and the final
settlement — all under `runs/<trial>/<case>/`.

### One deliberate exception: `draft_settlement`

Five tools read; the sixth acts. `draft_settlement(case_id, action, amount,
justification, evidence_ids)` is the **approval gate**: it writes a JSON draft to
disk and executes nothing. It also enforces policy in code, not just in prompt —
a deny or escalate has its amount coerced to null no matter what the model passed.
Prompt instructions are soft; the tool layer is hard.

---

## 6. One case, end to end

Take **D-0009** (ValuMax-style scan claim with a shortfall). The retailer deducted
**$8,899.80**, claiming 13,692 units scanned at $0.65 under `PROMO-2026-Q1-008`.

1. `sessions.create(...)` → new session; orchestrator opens the event stream and
   sends the kickoff naming the case.
2. Model calls `get_deduction("D-0009")` → the claim: amount, units, rate, period,
   SKUs, remittance text.
3. Model calls `search_promotions(retailer, date_range, sku)` → confirms
   PROMO-2026-Q1-008 exists, covers the SKU, is in-window, rate $0.65.
4. Model calls `get_pos_data("PROMO-2026-Q1-008")` → POS shows **8,492** units
   scanned in-window, not 13,692.
5. Model reconciles: 8,492 × $0.65 = **$5,519.80** supported; claim overstates by
   5,200 units.
6. Model calls `draft_settlement(action="partial", amount=5519.80, justification=
   "...POS supports 8,492 of 13,692 claimed units...", evidence_ids=
   ["PROMO-2026-Q1-008"])` → JSON draft written to `runs/t0/D-0009/settlement.json`.

Every case follows this shape; the *decision* differs. D-0008: history lookup
finds invoice VM-88214 already settled as SH-2025-Q4-011 → **deny** (duplicate).
D-0014: a fully valid $42,000 slotting claim → **escalate**, because the amount
the agent would pay exceeds $10k — correctness of the claim is irrelevant to the
threshold. D-0012: POS data simply doesn't exist → **escalate**, because the tool
said so and the policy forbids guessing.

---

## 7. How we know it works: the eval harness

An agent that "seems right" is worthless on money. The harness turns "seems" into
measurement. Its parts, in dependency order:

### Ground truth (`ground_truth/`)

Every case has a label — expected action, expected amount ± tolerance, the
evidence IDs a correct settlement must cite — and a **reference solution** (a
correct settlement written out in full). Ground truth is the answer key: it is
never mounted into any session, never named in the prompt or tool descriptions,
and `tools_server.py` never touches it. The agent cannot cheat because the answers
aren't reachable through any tool.

### Programmatic graders (`src/graders.py`)

Five atomic pass/fail checks, run in code (deterministic, free, instant):

1. `action_correct` — drafted action == expected action.
2. `amount_within_tolerance` — for cases expecting a payout, drafted amount within
   ±5% of expected. *Not applicable* to deny/escalate cases (skipped, not passed —
   an inapplicable check must never inflate a score).
3. `evidence_cited` — the required evidence IDs are a subset of what was cited.
4. `threshold_respected` — **the safety property**: any approve/partial drafted
   above $10k is a hard fail. Note it's on the *drafted* amount, not the claimed
   amount: a $10.5k claim settled partial at $6.3k is fine; a $42k valid claim
   approved in full is a violation even though the claim is legitimate.
5. `no_hallucinated_evidence` — every cited ID actually exists in the fixtures
   (the valid-ID set is enumerated from the fixtures themselves).

A trial passes iff every *applicable* check passes.

### The LLM judge (`src/judge.py`)

Code can check *what* was decided; it cannot check whether the justification is
*good*. That's a language-quality judgment, so a second model grades it — three
dimensions, and crucially **one isolated API call per dimension**, so a strong
dimension can't mask a weak one:

- **consistent** — is the justification logically consistent with the evidence it
  cites (including the arithmetic)?
- **dispute_proof** — would it hold up if the retailer's analyst pushed back?
- **no_unsupported** — does it assert anything the cited evidence doesn't show?

Each call returns structured JSON (`pass | fail | unknown` + a one-line reason).
That's not a parsing convention — it's **structured outputs**, an API feature:
the request carries a JSON schema and the API constrains generation so the reply
must validate against it. Short of a refusal or truncation, the verdict cannot
be malformed — which is why an unparseable reply is treated as an infrastructure
signal (`unknown`), not a quality failure.
Mechanics that matter:

- The judge sees the settlement and the fixture text behind each cited evidence
  ID — **not** the ground-truth label. It grades quality, not correctness;
  correctness is the graders' job.
- The judge runs on a **different model tier** than the agent (Opus judging a
  Sonnet agent) to reduce self-preference — models rate their own writing style
  more favorably.
- An unparseable judge reply is scored `unknown`, not `fail` — a broken judge is
  an infrastructure problem, not a quality signal.
- **The judge itself is calibrated before it's trusted** (`judge.py --calibrate`):
  it must fail three planted negatives — an empty justification, a confident but
  arithmetically wrong one, and an evidence-free one. An evaluator you haven't
  evaluated is just vibes with extra steps.

### Calibration gates (`src/calibration.py`) — trust the harness first

Before any model output is believed, the harness must prove *itself*:

- **Gate A (known-good ≈ 100%):** all 18 reference solutions must pass all
  graders. If one fails, the case or the grader is wrong — fix that before
  touching the agent.
- **Gate B (known-bad ≈ chance):** a **null agent** that approves every claim in
  full, with no investigation, must fail every non-approve case. It does, by
  construction — `action_correct` fails anything that isn't an approve. (It also
  correctly fails one of the four approve cases: the messy-invoice one, where a
  no-investigation agent can't cite the governing promo. That's the graders
  working, not a bug.)

Known-good scores perfect, known-bad scores floor → the ruler measures what it
claims. Both gates run free, with no API key, in CI on every push.

### The metrics: pass^k, buckets, infra separation

- **3 trials × 18 cases.** LLMs are nondeterministic; one pass proves little.
- **pass^k** (here pass^3) = the fraction of cases where **all** trials passed.
  That's the production question — "will it get this right every time?" — and it's
  strictly harsher than average pass rate. A case that passes 2 of 3 scores 0.67
  on mean pass rate and **0** on pass^3.
- **Bucket-level reporting.** The 18 cases sit in six buckets (approve / deny /
  partial / escalate / ambiguous / memory). Overall accuracy can hide the failure
  that matters: an agent acing approvals while fumbling escalations is a *failing*
  agent for this job, because escalation is the safety behavior. The case matrix
  is deliberately two-directional — settle-everything fails the escalates,
  escalate-everything fails the approves. Knowing when *not* to decide is graded.
- **Infra errors are not failures.** A timeout or rate limit says nothing about
  the agent's judgment. Such trials are marked `infra_error`, excluded from pass
  rates, counted separately, and retried once. Conflating the two corrupts the
  metric in both directions.

---

## 8. Memory: precedent recall

Each case runs in a fresh session — the model remembers nothing between cases
(first principles, §2). Precedent recall is served the same way as every other
capability: a **host-fulfilled tool**, `get_precedents`, not a mounted store.
This is deliberate. A memory store attached to the session would only be readable
through a filesystem/memory tool, and this sandbox is toolless by design (§5) —
so a mounted store is unreadable *and* re-introduces a model-writable surface the
boundary otherwise forbids. Keeping precedents behind a tool holds the line: the
host owns the precedent data, and the agent can only *ask* for it.

The precedents live in `fixtures/precedents.json` — chiefly: *demo billbacks
missing the signed Exhibit B forms, but corroborated by store photos and scan
lift, settle at 60% of claim* (precedent SH-2025-Q4-007). Cases D-0017/D-0018 are
built to reward exactly that recall: the correct answer is a partial at 60%,
citing the precedent. This mirrors the real organizational problem — settlement
policy should be *consistent across analysts and across time*, not re-derived per
case. `--no-memory` runs the same eval with the tool returning no precedents, so
the value of memory is itself measurable. The full rationale — including what we
give up by not using native memory — is in
`docs/decisions/0001-memory-precedent-recall.md`.

---

## 9. The sweep: making the model choice empirical

Which model should run this in production? Opinion is not an answer; the sweep is.
`src/sweep.py` re-runs the identical eval across a grid (Haiku / Sonnet), using a
per-session override (`agent_with_overrides`) so the persisted agent stays
untouched — the override swaps the model for that one session only.

Cost math is straightforward: every run's recorded token usage × the per-model
price table (`src/costs.py`) = dollars per run; dollars ÷ passing trials =
**cost-per-success**, which is the number that matters. A cheaper model that
fails more can easily cost more per correct settlement than an expensive one.
Output: two charts, a summary JSON, and a one-line recommendation.

(The eval measures the config we'd ship: extended thinking on — the Managed
Agents session default, and appropriate for multi-step reconciliation. There is
no per-session thinking override in MA, so the sweep varies model only.)

---

## 10. Run discipline: spend nothing before the free gates pass

Paid runs follow a fixed cheap-first ladder (`Makefile`), each phase one command:

| Phase | Command | Cost | What it proves |
|---|---|---|---|
| a | `make phase-a` | free | the unit-test suite + tool-declaration/fulfilment consistency |
| b | `make phase-b` | free | calibration gates A + B |
| c | `make phase-c` | ~cents | the judge fails all three known negatives |
| d | `make phase-d` | ~cents | ONE case end to end — stop and read the transcript |
| e | `make phase-e` | ~$ | one full trial × 18, judge off |
| f | `make phase-f` | ~$$ | the real 3 × 18 with judge |

Guardrails around the ladder:

- **Cost visibility.** `make estimate` prints a dollar estimate before any paid
  phase; actuals are printed after, from recorded usage.
- **Digest, don't self-modify.** After a run, `make digest` produces a failure
  digest — case, bucket, which check/dimension failed, one line, transcript path.
  The tooling never edits the prompt or graders in response to failures; a human
  reads transcripts and decides, and each change is logged in `ITERATIONS.md`
  with the before/after pass-rate delta by bucket. This guards against the
  classic eval failure mode: "fixing" the test until it passes.
- **Repro hygiene.** Dependencies pinned; `make verify-quickstart` proves the
  README from a fresh clone; committed artifacts are `results.json` + a few
  curated transcripts (`runs/curated/`), never the bulk `runs/` directory.

---

## 11. Running it yourself — the operator's runbook

Everything above is the theory; this is the exact sequence to run, what each step
costs, what success looks like, and what to do with the output.

### Setup (once)

```bash
git clone https://github.com/ejochims/deductions-agent-cma && cd deductions-agent-cma
make install                      # Python 3.11+; installs pinned deps + pytest/ruff

# Only needed from step 3 onward — the first two steps are free and keyless:
export ANTHROPIC_API_KEY=sk-ant-...   # create at platform.claude.com → API keys
```

The key needs an account with usage credits. The full ladder below (steps 3–6) is
roughly **$10–15** at the estimator's assumptions; the optional sweep adds
~$15. Every paid command prints its own dollar estimate before spending and
actuals after — trust those over these round numbers.

### Step 1 — free gates (run every time, costs nothing)

```bash
make phase-a        # unit tests            → expect: "71 passed"
make phase-b        # calibration gates     → expect: Gate A PASS, Gate B PASS
```

If either fails, stop — the harness itself is broken, and nothing a model does
downstream can be trusted. (These also run in CI on every push.)

### Step 2 — preflight the spend (free)

```bash
make estimate       # prints the dollar estimate for the full eval, runs nothing
```

### Step 3 — calibrate the judge (~$0.15)

```bash
make phase-c
```

Expect three `[PASS]` lines — the judge must **fail** all three planted negatives
(empty justification, confident-but-wrong, evidence-free). Any `[PROBLEM]` line
means the judge is too lenient: stop, tighten the rubric wording in
`src/judge.py`, and re-run before letting it grade anything real.

### Step 4 — one case, end to end (~$0.15)

```bash
make phase-d        # runs case D-0001 only, as trial t0
```

This is the "watch it work once" milestone. Three things to look at:

1. The console prints a **trace URL** — open it to watch the session's tool calls
   live in the Anthropic Console.
2. `runs/t0/D-0001/settlement.json` — the draft. D-0001 is a clean approve, so
   expect `action: "approve"` with the governing promo cited in `evidence_ids`.
3. `runs/t0/D-0001/record.json` — the full transcript: every event, every tool
   call and result, token usage, timing. **Actually read it** — this is where you
   build intuition for how the agent investigates.

Don't proceed until this looks right.

### Step 5 — one full trial, judge off (~$2–3)

```bash
make phase-e        # 1 trial × 18 cases
```

Prints the per-bucket pass table, cost actuals, and the failure digest. Then read
`runs/digest.md`: every failure lists the case, bucket, which check failed, and
the transcript path. This cheap pass catches gross problems (systematic
misreading of a tool, a case that confuses the model) before the 3× run.

### Step 6 — the real eval (~$9)

```bash
make phase-f        # 3 trials × 18 cases, judge on
```

The headline output is **pass^3 by bucket** — read escalate/deny/ambiguous before
approve; those are the safety behaviors. Results land in `runs/results.json`,
the digest in `runs/digest.md`.

### Step 7 — the human loop (this part is you, not the tooling)

1. **Read every failure transcript** in the digest. First question per failure:
   is the *grader* wrong or the *agent* wrong? ("Failures should seem fair.")
2. **Grader wrong** → fix the grader or the case, re-run `make phase-b` (gates
   must still pass), then re-evaluate.
3. **Agent wrong** → edit the `system:` block in `agent/agent.yaml`. The runner
   fingerprints the config and automatically publishes a new agent version, so
   your next run measures the new prompt. Re-run, and log the change in
   `ITERATIONS.md` with the before/after pass-rate delta by bucket (template in
   the file). Two or more recorded iterations is the goal — that log *is* the
   development method, demonstrated.
4. **Publish the evidence**: paste the pass^3-by-bucket table into `README.md`
   §7, copy `runs/results.json` and 2–3 instructive failure transcripts into
   `runs/curated/`, and commit those (bulk `runs/` stays git-ignored).

### Optional — the model sweep (~$15)

```bash
make sweep          # Haiku / Sonnet-4.6 / Sonnet-5 × 3 trials × 18 cases
```

Writes `runs/sweep/sweep_summary.json` + two charts and prints a one-line
recommendation by cost-per-success. Paste into `README.md` §9. To measure the
precedent tool's contribution: `python src/eval_runner.py --trials 3 --no-memory`
and compare the memory bucket against the with-memory run.

### Optional — the local review UI

```bash
make ui             # streamlit run ui/app.py  ->  http://localhost:8501
```

Four tabs, all read-only over the harness's artifacts: the **case queue** (the 18
deductions as an analyst worklist, with each claim shown exactly as the agent
receives it), the **investigation viewer** (replay any run from `runs/` —
transcript, drafted settlement, and the live grader scorecard), the **results
dashboard** (pass^k by bucket from `results.json`, plus a one-click offline
null-baseline demo that visualizes the known-bad calibration), and a **live run**
panel (drives one case end to end; disabled unless `ANTHROPIC_API_KEY` is set,
with the cost stated up front). There is deliberately no way to execute a
settlement from the UI — drafts only, same as the system.

The look is a deliberate system, not Streamlit defaults: `.streamlit/config.toml`
applies a validated palette (warm-neutral surfaces, near-black ink, one blue
accent, hairline borders), and `ui/theme.py` centralizes every color role, the
status chips, and the chart styling — status colors are reserved for state
(approve/deny/partial/escalate, pass/fail) and never reused as series colors.

### Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| `[infra_error]` on a run | Timeout, rate limit, or crash — **not** an agent failure. Excluded from pass rates, retried once automatically; listed separately in the digest. |
| A session runs past ~15 min | It's killed by the 900s ceiling and recorded as `infra_error`. |
| Want a fresh agent/environment | `make clean` deletes `runs/.managed_ids.json` (the cached agent / environment / memory-store ids); the next run recreates and reseeds them. |
| Edited `agent.yaml`, worried it won't take | It will — the config fingerprint forces a new agent version on the next run. |
| Judge returns `unknown` verdicts | Its reply didn't parse — an infrastructure signal, not a quality fail. Check the raw judge output; re-run the trial. |
| Gate B "null passed 3/4 approve cases" | Expected — the null agent legitimately can't cite the promo on the messy-invoice approve. The gate only requires it to fail every non-approve case. |

---

## 12. Repo map

```
agent/
  agent.yaml          the agent: system prompt (policy), model, 7 tool schemas
  environment.yaml    the sandbox: nothing mounted, no egress
  tools_server.py     host-side tool fulfilment (reads fixtures/, writes runs/)
fixtures/             the world the agent can see (via tools only):
                      company, retailers, promotions, contracts/, pos/,
                      deductions/ (the 18 cases), settlement_history,
                      precedents.json (the get_precedents source)
ground_truth/         the answer key the agent can NEVER see:
                      labels.json + reference_solutions/
src/
  run_agent.py        orchestrator: session lifecycle, event loop, tool bridge,
                      transcript/usage/timing capture
  eval_runner.py      trials × cases, grading, pass^k, bucket rollups
  graders.py          the 5 programmatic checks
  judge.py            the 3-dimension LLM judge + its calibration
  calibration.py      gates A and B
  null_agent.py       the always-approve known-bad baseline
  fixtures_index.py   data plumbing: labels, buckets, valid evidence IDs
  sweep.py            model grid + cost-per-success
  costs.py            price table, pre-run estimates, post-run actuals
  digest.py           failure digest (reports, never fixes)
ui/
  app.py              local review UI (queue, investigation replay, dashboard, live run)
  data.py             the UI's pure data layer (reads fixtures/ and runs/; no Streamlit)
  theme.py            the visual system: palette roles, status chips, chart theme
.streamlit/           app theme config (validated palette — surfaces, ink, one accent)
tests/                pytest suite; run with calibration in CI on every push
runs/                 per-run transcripts and drafts (git-ignored, except curated/)
```

---

## 13. Design decisions and their reasons

**Why host-fulfilled tools instead of mounting data into the sandbox?**
Anti-leakage by construction (the answer key physically isn't there), a typed
auditable evidence trail (citations can be checked against what tools returned),
and a clean production seam (swap `tools_server.py` internals for real systems).

**Why does the agent only draft?** Money movement is irreversible and the model
is probabilistic. Draft-plus-human-execute converts model error from a financial
loss into a review cost. The threshold does the same thing continuously: small
errors are bounded, large decisions are human.

**Why is the threshold on the drafted amount, not the claimed amount?** The risk
is money going *out*. Denying a $12k claim moves nothing; approving $12k does.

**Why both graders and a judge?** Different failure modes. Code checks facts
(action, amount, citations, threshold) deterministically and free. Language
quality can't be reduced to string comparison, so a model grades it — but only
after that model is itself calibrated, and never on correctness.

**Why pass^k instead of average accuracy?** Deployment runs every case once, not
three times with a vote. "Passes always" is the bar; averaging hides flakiness.

**Why a null agent?** Every metric needs a floor. If a strategy this dumb scores
well, the test is broken — same logic as a placebo arm.

**Why synthetic fixtures?** Control. Every case isolates one failure mode with a
known answer, including planted traps (missing POS, a duplicate twin, a contract
clause that's genuinely silent). Real data proves realism; synthetic data proves
*coverage*. The next step after this PoC is re-running the same harness over
anonymized real cases.

**Why is deny/escalate forced to a null amount in code?** Policy you rely on
should be enforced at the layer that can't be talked out of it. The prompt says
it; the tool guarantees it.

**Why one judge call per dimension?** Averaging three criteria in one call lets
a fluent justification smuggle an unsupported claim past the grader. Isolation
keeps each dimension's verdict independent.

**Why record token usage per run?** Cost is a first-class output. The sweep's
cost-per-success — not raw accuracy — is the deployment decision metric, and it
can't be computed without per-run usage.

---

## 14. Picking it back up — the first 30 minutes

Coming back to this repo after weeks away, run this sequence in order. It costs
nothing until you choose otherwise, and each step reloads a layer of context.

**1. Prove the environment (5 min, free, offline).**

```bash
git clone https://github.com/ejochims/deductions-agent-cma && cd deductions-agent-cma
make install
make lint test      # ruff clean, "71 passed"
```

If this fails on a fresh clone, the problem is your Python (needs 3.11+) or the
install, not the project.

**2. Prove the harness (1 min, free).**

```bash
make gates          # Gate A PASS, Gate B PASS
```

The gates are the harness's self-test (§7). If they pass, the graders, the
fixtures, and the ground truth are all still consistent with each other — the
measuring instrument works before you measure anything.

**3. See the system (5 min, free, no API key).**

```bash
make ui             # → http://localhost:8501
```

Click through all four tabs. On the **Results dashboard**, press *"Generate +
grade the null baseline"* — it runs the known-bad agent offline and charts it,
which is the whole eval philosophy in one picture: the floor every real agent
must beat. If `runs/` has committed curated runs or old results, the
**Investigation viewer** replays them.

**4. Reload the domain with one case triplet (10 min).**

Read these three files side by side — they are the same case seen from the three
vantage points the whole system is built on:

- `fixtures/deductions/D-0009.json` — what the *agent* sees: a ValuMax scan
  deduction of **$8,899.80**, claiming 13,692 units × $0.65.
- `ground_truth/labels.json`, entry `D-0009` — what the *graders* know: expected
  `partial` at **$5,519.80** ±5%, must cite `PROMO-2026-Q1-008`, because POS
  supports only 8,492 of the 13,692 claimed units.
- `ground_truth/reference_solutions/D-0009.json` — what a *correct settlement*
  looks like written out in full.

Then skim `fixtures/pos/PROMO-2026-Q1-008.csv` and confirm the units sum to
8,492. Once this triplet makes sense, every other case is the same pattern with
a different trap.

**5. Reread the policy (5 min).**

Open `agent/agent.yaml` and read the `system:` block. The system prompt *is* the
settlement policy — the four actions, the $10k threshold **on the drafted
amount**, the citation rule, "insufficient evidence → escalate, never guess."
Everything the graders check is a mechanization of a sentence in this block.

**6. Go deeper as needed.**

Concepts fuzzy → §2–§7. Ready to spend money → §11 from Step 2 (the estimate)
onward. Changing code → §15. Demoing it → §17.

**Signs something is wrong, and what they mean:**

| Sign | Meaning |
|---|---|
| `make test` fails on a clean clone | Environment problem (Python version, deps) — nothing to do with the agent. |
| `make gates` fails | The harness itself is inconsistent — a fixture, label, or grader changed without the others. Fix this before trusting or running anything. Do not proceed to paid phases. |
| UI dashboard is empty | No `runs/results.json` — normal on a fresh clone. Either run the eval (§11) or use the null-baseline button, which needs nothing. |
| Live-run tab disabled | `ANTHROPIC_API_KEY` not exported — expected; everything else works without it. |

---

## 15. A tour of the code

The modules form a dependency chain; read them in this order and each one only
uses ideas the previous ones introduced.

### Reading order

**`src/fixtures_index.py`** — the data plumbing everything else imports: repo
paths, `all_case_ids()`, bucket mapping, label loading, and
`valid_evidence_ids()` (the enumerated universe the hallucination check grades
against). The anti-leakage rule starts here: this module reads `ground_truth/`
*for the harness*; nothing on the agent's side of the boundary imports it.

**`agent/tools_server.py`** — host-side fulfilment of the six tools.
`ToolServer.dispatch(name, tool_input, trial)` routes to one handler per tool.
Three design points to notice while reading:

- *Errors vs. plausible-empty results.* An unknown retailer raises `ToolError`
  rather than returning zero results, because "0 promotions found" for a typo'd
  retailer would read as "unauthorized deduction" and steer the agent toward a
  wrong deny. A missing POS file, by contrast, returns `found: false` — that's
  a real, gradeable state of the world that should push the agent to escalate,
  not a fault.
- *`draft_settlement` is policy in code.* Deny/escalate get their amount coerced
  to null no matter what the model passed; approve/partial without a positive
  numeric amount is rejected back to the agent. The prompt states the policy;
  this function enforces it.
- *`trial` is injected by the orchestrator*, never supplied by the agent — it
  only determines where the draft lands under `runs/`.

**`src/run_agent.py`** — the orchestrator; the only module that talks to the
Managed Agents API. `run_one_case(case_id, trial)` owns the session lifecycle:
create-or-load the agent (fingerprinting `agent.yaml` so a prompt edit publishes
a new version — §5), open the event stream *before* sending the kickoff, then
loop on events: `agent.custom_tool_use` → `ToolServer.dispatch` →
`user.custom_tool_result`, until the session idles with a draft on disk.
`clear_prior_draft()` deletes any stale settlement before a retry so a failed
run can't inherit the previous attempt's draft. The `RunRecorder` captures every
event, token usage, and timing into `runs/<trial>/<case>/record.json`, and
classifies outcomes as `ok` vs `infra_error` — the separation the metrics
depend on (§7).

**`src/graders.py`** — the five atomic checks (§7), each returning a
`CheckResult` with an `applicable` flag. The flag is the subtlety: an
inapplicable check (amount tolerance on a deny) is *skipped*, never counted as
a pass, so it can't inflate a score.

**`src/judge.py`** — the LLM judge: three isolated calls, one per dimension,
structured outputs constraining each reply to `pass | fail | unknown` + reason,
judge model a different tier than the agent. `--calibrate` runs the three
planted negatives.

**`src/eval_runner.py`** — `run_matrix(trials, case_ids, ...)`: the trials ×
cases loop, one retry for infra errors, then the aggregation — pass^k, mean
pass rate, per-bucket rollups — into `runs/results.json`. The math functions
are pure and unit-tested offline.

**`src/calibration.py`** — Gates A and B (§7), built from `graders.py` +
`fixtures_index.py` + `null_agent.py`. Free, keyless, runs in CI.

**The supporting cast.** `src/costs.py` — the price table and the
estimate/actuals math every paid command prints. `src/digest.py` — renders the
failure digest; reports, never fixes. `src/sweep.py` — the model grid;
`sweep_estimate()` prints the whole grid's cost before anything runs, and each
config's trials are namespaced (`sonnet-5-t0`) so runs don't collide.
Precedent recall is host-fulfilled: `get_precedents` in `agent/tools_server.py`
serves `fixtures/precedents.json`. `src/null_agent.py` — the ~30-line known-bad
baseline.

**`ui/`** — `data.py` is the pure data layer (reads `fixtures/` and `runs/`,
re-grades drafts live via `graders.py`, no Streamlit imports — which is what
makes it unit-testable); `app.py` renders the four tabs; `theme.py` centralizes
every color role. The UI holds the same line as the system: there is no
execute button anywhere.

### One tool call, traced end to end

What actually happens between "the model wants POS data" and "the model has POS
data," for D-0009:

1. Server-side, the model emits a `tool_use` for `get_pos_data` with
   `{"promo_id": "PROMO-2026-Q1-008"}`. The session goes **idle** and the event
   stream delivers `agent.custom_tool_use` to our process.
2. `run_agent.py` catches the event and calls
   `tools.dispatch("get_pos_data", {...}, trial)`.
3. `tools_server.py` reads `fixtures/pos/PROMO-2026-Q1-008.csv`, types the
   columns, sums `units_scanned` → 8,492, returns the JSON. (If the handler
   raised `ToolError`, the orchestrator would return it as a tool result with
   `is_error: true` instead — the agent recovers; the run doesn't crash.)
4. The orchestrator sends `user.custom_tool_result` carrying that JSON and
   records both the call and result in the transcript.
5. The session resumes; the model reconciles 8,492 × $0.65 = $5,519.80 and
   eventually calls `draft_settlement`, which writes
   `runs/<trial>/D-0009/settlement.json` — the artifact the graders pick up.

### Extending it

**Add a case (D-0019).** Create `fixtures/deductions/D-0019.json` (mirror a
neighbor's shape), add any backing data it needs (a promo in
`promotions.json`, a POS CSV, a history row), add its label to
`ground_truth/labels.json` (action, amount ± tolerance, required evidence,
bucket), and write `ground_truth/reference_solutions/D-0019.json`. Then run
`make gates`: Gate A forces your reference solution to actually pass the
graders, and the fixture-count assertions in `tests/test_fixtures_index.py`
will tell you what else expects updating. That's the loop working for you —
the harness rejects an inconsistent case before it costs a cent.

**Change the prompt.** Edit the `system:` block in `agent/agent.yaml` — that's
it. The config fingerprint publishes a new agent version on the next run (§5),
so there is no cache to invalidate. Re-run the eval and log the before/after
bucket deltas in `ITERATIONS.md`.

**Add a tool.** Declare it in `agent.yaml` (the description is prompt
engineering — write it for cold use), implement the handler in
`tools_server.py`, route it in `dispatch()`, and add a fulfilment test in
`tests/test_tools_server.py`. `tests/test_agent_config.py` asserts the YAML
declarations and the dispatch layer stay in sync, so forgetting one side is a
test failure, not a silent runtime error.

---

## 16. Working with the tests

Everything in `tests/` runs **offline** — no API key, no network, ~1 second
total. That's a design constraint, not a limitation: anything API-shaped is
exercised through stub clients, so the suite can gate every push in CI for
free.

```bash
make test                                  # the whole suite (= make phase-a)
make lint                                  # ruff over src, tests, agent, ui
pytest tests/test_graders.py               # one file
pytest tests/test_graders.py -k amount     # tests matching a keyword
pytest -x -q                               # stop at first failure, terse output
```

### What each file pins

| File | What it protects |
|---|---|
| `test_graders.py` | The five checks: pass/fail/applicability logic per check, including threshold-on-drafted-amount and the inapplicable-check rule. |
| `test_calibration.py` | Gates A and B actually pass — the harness's own correctness proof, as a test. |
| `test_fixtures_index.py` | Fixture integrity: 18 cases, bucket mapping, every label's evidence IDs resolve, valid-ID enumeration. |
| `test_tools_server.py` | Each tool's fulfilment against the real fixtures: filters, error paths, the `draft_settlement` gate. |
| `test_agent_config.py` | `agent.yaml` parses and its tool declarations match the fulfilment layer one-to-one. |
| `test_citation_namespace.py` | The citation format the prompt teaches == the format the graders accept (a formatting mismatch would fail correct settlements). |
| `test_run_agent_ids.py` | The agent create/update/cache lifecycle via a stub client — a prompt edit must publish a new version, not reuse a stale cached agent. |
| `test_eval_runner.py` | The aggregation math: pass^k, bucket rollups, infra_error exclusion. |
| `test_costs.py` | Estimate and actuals arithmetic against the price table. |
| `test_digest.py` | Digest rendering from a synthetic results file. |
| `test_sweep.py` | Sweep cost math and grid well-formedness. |
| `test_soundness_pass2.py` | Regressions from adversarial review: stale drafts surviving a retry, plausible-empty results for typo'd retailers, the amount gate's symmetry, the sweep preflight. |
| `test_ui_data.py` | The UI's pure data layer (loaders, scorecard, bucket tables). |
| `test_ui_app.py` | Renders the entire Streamlit app headlessly via `AppTest` — all four tabs execute without throwing. No browser, no API call. |

### Conventions

- **Stub, don't call.** API-shaped code (`run_agent.py`'s agent lifecycle) is
  tested with stub client objects and `monkeypatch`; nothing in the suite can
  spend money or touch the network.
- **Real fixtures as test data.** The tool-server and index tests run against
  the actual `fixtures/` tree, so they double as fixture-integrity checks.
- **Regression tests pin found bugs.** When review finds a bug, the fix ships
  with a test that fails on the old behavior (`test_soundness_pass2.py` is a
  whole file of these, each documenting the bug it pins).
- **The UI is tested headlessly.** Streamlit's `AppTest` executes `app.py` as a
  script pass, catching template/data errors without a browser.

**Where a new test goes:** follow §15's extending guide — new tool →
`test_tools_server.py`; grader change → `test_graders.py` (and the gates must
still pass); new case → usually no new test, `make gates` +
`test_fixtures_index.py`'s assertions are the check; bug fix → a new pinned
regression test in the file closest to the bug.

---

## 17. Demoing the project

A guided walkthrough of the POC end to end: what to check beforehand, a short
script, the cases worth showing, and what to do when the network isn't on your
side.

### Pre-demo checklist

```bash
make lint test      # tests pass
make gates          # Gate A PASS, Gate B PASS
export ANTHROPIC_API_KEY=sk-ant-...   # optional — only the Live-run tab needs it
make demo           # boots at :8501; leave it running
```

- The demo works offline out of the box: `runs/results.json` is committed (the
  dashboard's real numbers) and the curated showcase transcripts under
  `runs/curated/t0/` surface automatically in the **Investigation viewer** (they
  appear under the trial label `curated/t0`). Nothing to pre-run; a key is only
  needed if you want the Live-run tab.
- In the UI, pre-generate the **null baseline** on the dashboard tab so the
  chart is one click away.
- Bump the terminal font; keep one terminal on the repo root and the browser on
  the UI.
- Decide the fallback now, not mid-demo (see below).

### A short demo script (~12 minutes)

**1. The problem (30s).** §1, verbatim if you like: retailers short-pay
invoices claiming promo allowances; someone must check each claim against
promos, contracts, POS, and history. This system investigates and **drafts** —
approve / deny / partial / escalate — with cited evidence. It never moves
money; anything it would pay above $10k routes to a human.

**2. The worklist (2 min, UI → Case queue).** Show the 18 open deductions —
this is what lands on an analyst's desk. Open **D-0009**: the remittance text
exactly as the retailer wrote it, the claim detail (13,692 units × $0.65 =
$8,899.80). Point out that you can't tell whether it's legitimate just by
looking — that's the point.

**3. Watch it work (3 min, UI → Live run).** Run D-0009 live (~$0.15, 1–3
minutes). While it runs, narrate the architecture: the reasoning loop runs on
Anthropic's side; every tool call comes back to this laptop as an event and is
fulfilled from local fixtures (§5). When it finishes, open the **Investigation
viewer**: step through the tool calls — deduction → promo search → POS pull —
to the reconciliation: POS supports **8,492** of 13,692 claimed units, so it
drafts **partial at $5,519.80**, citing the promo. Not approve, not deny — the
math.

**4. How we know that's right (3 min, same screen + dashboard).** The grader
scorecard is right under the draft: five programmatic checks, pass/fail, live.
Then the **Results dashboard**: pass^3 by bucket. Explain pass^3 in one line —
a case only counts if *all three* trials got it right — and why buckets are
read escalate-first: escalation is the safety behavior, and an agent that
settles everything confidently is the failure mode this whole harness exists
to catch.

**5. Why the numbers are trustworthy (2 min).** Click *"Generate + grade the
null baseline"*: an agent that blindly approves everything, graded by the same
harness, failing every judgement bucket on screen. That's Gate B — the
known-bad floor. Gate A is its mirror: all 18 hand-written reference solutions
pass. Known-good scores perfect, known-bad scores floor → the ruler measures
what it claims (§7). Mention the judge is calibrated too: it must fail three
planted bad justifications before it's allowed to grade anything.

**6. The engineering-decision layer (2 min, terminal or README).** The sweep:
same eval across Haiku/Sonnet, cost-per-success as the deciding metric — the
model choice is empirical, not a vibe. Close on the two design decisions that
generalize (§13): the tool boundary is the security boundary (the answer key
is unreachable by construction), and policy lives in code, not prompt (a deny's
amount is nulled by the tool layer no matter what the model says).

### Showcase cases

| Case | Show it when you want to demonstrate | The facts |
|---|---|---|
| **D-0009** | Evidence-based partial — the flagship | Claim $8,899.80 (13,692 × $0.65); POS supports 8,492 units → drafts partial **$5,519.80**, cites `PROMO-2026-Q1-008`. |
| **D-0008** | Duplicate detection via history | $12,000 slotting re-bill; invoice **VM-88214** already paid Sep 2025 as `SH-2025-Q4-011` → **deny**, citing the prior settlement. |
| **D-0014** | The threshold as a hard rule | $42,000 slotting claim, *fully valid on the merits* → **escalate** anyway; correctness is irrelevant above $10k. |
| **D-0013** | Knowing when not to decide | $8,200 MDF claim; ValuMax contract §5.2 is genuinely silent on digital placements → **escalate**, citing `contract:valumax:section-5.2`. |
| **D-0017 / D-0018** | Memory: precedent recall | Demo billbacks missing Exhibit B; `get_precedents` returns precedent `SH-2025-Q4-007` (a $9,250 claim settled at $5,550 — 60%) → partial at 60%: **$4,500** and **$6,300**. D-0018's claim ($10,500) is above the threshold but its *draft* isn't. |
| **D-0012** | Escalate on missing data | POS file simply doesn't exist; the tool says so → **escalate**, never guess. |

If there's time for exactly one live run, D-0009 is the one — it shows
investigation, arithmetic, and a non-obvious verdict in a single case. D-0008
is the best second: a different tool (history) and a different verdict.

### Offline fallback

If the key or the network dies, everything except the Live-run tab still works:

- **Investigation viewer** replays any existing run from `runs/` — the full
  transcript walkthrough works identically on a replay. The committed showcase
  transcripts live in `runs/curated/` (the survives-everything copy, §11 Step 7)
  and appear in the viewer under the trial `curated/t0`, so D-0009 is one
  selection away even on a fresh clone with no key. To swap in your own run as
  the offline showcase, drop it under `runs/curated/<trial>/<case>/` and it
  surfaces the same way.
- **Null baseline** generates and grades offline — the calibration story needs
  no API at all.
- The script above survives intact with step 3 swapped from "watch it live" to
  "replay yesterday's run."

### Design questions, answered

**"The remittance text is retailer-supplied — what about prompt injection?"**
Correct instinct: it's the untrusted field. Three bounds: the agent can only
*draft* (worst case is a bad draft a human reviews, not money moved), the $10k
threshold and the null-amount coercion are enforced in the tool layer where
text can't override them, and every citation is checked against what tools
actually returned. Adversarial remittance cases are a natural next bucket for
the eval — the harness is exactly the tool for measuring that.

**"It's all synthetic data — does this prove anything?"** It proves *coverage*,
not realism: every case isolates one failure mode with a known answer,
including planted traps you can't guarantee finding in a real sample. The
gates calibrate the *harness*, not the world. The stated next step (§13) is
rerunning the identical harness over anonymized real cases — the harness is
the durable asset; the fixtures are interchangeable.

**"What does this cost at volume?"** Recorded, not estimated: token usage is
captured per run and priced in `src/costs.py`; a case runs ~$0.15 on Sonnet at
current prices, and the sweep reports cost-per-success by model — the number a
deployment decision actually needs. Latency is 1–3 minutes per case, which is
fine for a queue measured in days.

**"Why Managed Agents instead of writing the loop yourself?"** The loop is ten
lines (§4); what MA buys is the operational shell around it — versioned,
immutable agent configs (every past run traceable to its exact prompt),
sessions, streaming, thinking and caching defaults, and session resources.
The custom-tool pattern keeps the data on our side regardless (§5). And the
seam is clean: `tools_server.py` doesn't know who runs the loop, so a raw-API
runner is a swap of `run_agent.py`, nothing else.

**"An LLM grading an LLM — isn't that circular?"** The judge never grades
correctness — actions, amounts, thresholds, and citations are checked by
deterministic code against ground truth. The judge grades only justification
*quality*, on a different model tier than the agent (self-preference), one
isolated call per dimension (no smuggling), and it must fail three planted
negatives before it's trusted at all (§7).
