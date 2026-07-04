# Evan's TODO — the hand-written core + gates

Running list of everything that is **yours** to do (Rule 1: you write `graders.py`,
`judge.py`, and the Anthropic/Managed-Agents API calls in `run_agent.py`), plus the
setup/decision items that block progress. Claude Code has scaffolded everything
around these and marked the exact spots. Ordered by what unblocks the most.

## 0. Setup / decisions (unblocks running anything)
- [ ] **Anthropic auth.** Confirm credentials: `ant auth status`. The harness and
      `run_agent.py` need a live client. (`pip install -r requirements.txt` first.)
- [ ] **Model baseline decision.** `agent/agent.yaml` uses `claude-sonnet-4-6` per
      the handoff. `claude-sonnet-5` is now the current Sonnet — decide whether to
      bump the baseline (affects the P5 sweep set). No code blocked either way.
- [ ] **Confirm the host-fulfilled tool design** (fixtures never mounted; agent has
      no bash/read/write). This diverges from the handoff's literal "environment.yaml
      mounts fixtures." Recommended and in place — flag if you want the mounted-files
      variant instead.

## 1. `src/run_agent.py` — the API calls  → unblocks P2 milestone + all of P3
Three `TODO(EVAN)` stubs; docstrings name the exact SDK calls and event rules.
- [ ] `create_or_load_agent(client, agent_cfg)` — `client.beta.agents.create(...)`
      from `agent.yaml`, once; persist the id (or accept `--agent-id`).
- [ ] `create_environment(client, env_cfg)` — `client.beta.environments.create(...)`,
      reuse by name.
- [ ] `run_session_for_case(...)` — session create + **stream-first** event loop:
      handle `agent.custom_tool_use` → `fulfil_tool_call(...)` → send
      `user.custom_tool_result`; accumulate usage from `span.model_request_end`;
      break on terminated / idle-not-requires_action. Classify timeouts/rate-limits
      as `infra_error`.
- [ ] Construct the client in `run_one_case` / `main` (`anthropic.Anthropic()`).
- [ ] **P2 milestone:** watch one case run end to end and read its transcript:
      `python src/run_agent.py --case D-0001 --trial t0`.

## 2. `src/graders.py` — the 5 checks  → unblocks calibration gate A + eval
Skeleton has `CheckResult`, signatures, contracts/edge-cases, and the dispatcher.
Fill the five bodies (each `raise NotImplementedError`):
- [ ] `action_correct` · [ ] `amount_within_tolerance` (skip deny/escalate)
- [ ] `evidence_cited` (required ⊆ cited) · [ ] `threshold_respected` (the safety
      property — hard fail if approve/partial amount > $10k)
- [ ] `no_hallucinated_evidence` (cited ⊆ `valid_evidence_ids()`)
- [ ] **Calibration gate A:** `python src/calibration.py` → all 16 reference
      solutions must pass. If one fails, fix the case or the grader before any model
      run. Gate B (null agent) runs in the same command and must fail
      deny/partial/escalate/ambiguous.

## 3. `src/judge.py` — prompt + invocation  → quality dimension of the eval
Skeleton has the 3-dimension structure, `Verdict`, and dispatch.
- [ ] `_evidence_context(settlement)` — resolve cited ids to fixture text.
- [ ] `judge_dimension(client, settlement, dimension)` — concrete rubric prompt +
      isolated `client.messages.create(model=JUDGE_MODEL, ...)` per dimension,
      parse to `{verdict, reason}`. Judge model is a **different tier** than the
      agent (`JUDGE_MODEL = claude-opus-4-8`).
- [ ] **Judge calibration:** feed 3 known negatives (empty / confident-wrong /
      evidence-free justifications) — must fail all; spot-check 10 verdicts by hand.

## 4. Eval-driven iteration (P3 doctrine)
- [ ] First full 3×16 run: `python src/eval_runner.py --trials 3 [--judge]`.
- [ ] Read the failures ("failures should seem fair" — if >1 in 10 look like grader
      error, fix graders first).
- [ ] **≥2 recorded prompt iterations** with before/after eval deltas (edit the
      `system` block in `agent.yaml`; keep the deltas for the README).

## 5. Later phases (not yet scaffolded)
- [ ] **P4 memory:** add a memory store; 1–2 cases rewarding precedent recall
      (D-0015's 60% precedent SH-2025-Q4-007 is pre-planted).
- [ ] **P5 sweep:** `src/sweep.py` — Haiku/Sonnet/(Fable) × thinking on/off via
      `agent_with_overrides`; cost-per-success + pass-rate plots.
- [ ] **P6 README:** design rationale, case matrix, calibration evidence, pass^3 by
      bucket, sweep chart, "what I'd do next."

---
*Claude Code maintains this file as it scaffolds. Everything above marked `TODO(EVAN)`
in code is yours; everything else is done and offline-verified where possible.*
