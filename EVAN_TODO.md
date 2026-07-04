# Evan's TODO — review + live-API verification

Status update: the handoff (Rule 1) reserved `graders.py`, `judge.py`, and the API
calls in `run_agent.py` for Evan. **Evan asked Claude Code to draft all three**, so
they are now written. Everything offline-verifiable has been verified; what remains
is (a) your review/ownership of those drafts and (b) the steps that need a live API
key. Treat the drafted core as a strong first draft to read and be ready to defend
— that was the point of Rule 1.

## Verified already (no action needed to trust these)
- ✅ **Calibration gate A**: all 16 reference solutions pass the graders.
- ✅ **Calibration gate B**: the null agent fails every non-approve case (passes
      3/4 approves; D-0003's messy-invoice approve is the expected miss).
- ✅ Full grading path exercised end to end (reference-passes, broken-fails-the-
      right-checks, missing-draft-fails).
- ✅ Tool layer (all 6 tools) dispatches correctly against fixtures.
- ✅ `run_agent.py` / `judge.py` import clean; judge evidence-resolver + prompt
      assembly verified offline.
  Re-run any time: `python src/calibration.py`

## 0. Setup / decisions (needed before the live-API steps)
- [ ] **Anthropic auth**: `pip install -r requirements.txt` then `ant auth status`.
- [ ] **Model baseline**: `agent.yaml` uses `claude-sonnet-4-6` (handoff default).
      `claude-sonnet-5` is now current Sonnet — bump or keep? Affects the P5 sweep.
- [ ] **Confirm host-fulfilled tool design** (fixtures never mounted). In place and
      recommended; flag if you want the mounted-files variant instead.

## 1. Review the drafted core (your fingers-on-keys call)
- [ ] Read `src/graders.py` — the 5 checks. All pass calibration; the one judgement
      call to sign off on is `amount_within_tolerance` applicability (keyed to the
      label's expected payout, so a wrong-action draft double-fails; documented).
- [ ] Read `src/judge.py` — 3 rubrics, isolated per-dimension calls, opus judge vs
      sonnet agent. Own the rubric wording.
- [ ] Read `run_agent.py` API section — agent/env cached in `runs/.managed_ids.json`
      (created once), stream-first loop, custom-tool round-trip.

## 2. Live-API verification (needs credentials)
- [ ] **P2 milestone**: `python src/run_agent.py --case D-0001 --trial t0` → watch
      one case run end to end; read `runs/t0/D-0001/record.json`.
- [ ] **Judge calibration**: `python src/judge.py --calibrate` → must fail all 3
      known negatives (empty / confident-wrong / evidence-free). Spot-check 10 real
      verdicts by hand once the eval runs.
- [ ] **First full run**: `python src/eval_runner.py --trials 3 --judge`.
- [ ] Read the failures ("failures should seem fair"); if >1 in 10 look like grader
      error, fix graders first.

## 3. Eval-driven iteration (P3 doctrine)
- [ ] **≥2 recorded prompt iterations** with before/after eval deltas — edit the
      `system:` block in `agent.yaml`, keep the deltas for the README.

## 4. Later phases
- ✅ **P4 memory** — SCAFFOLDED. `src/memory_store.py` (create/seed/attach, cached),
      `agent/memory_seed.json` (the 60% demo-billback precedent + scan conventions),
      a "## Precedents (memory)" paragraph in `agent.yaml`, and 2 new cases
      (D-0017/18, "memory" bucket) that reward recalling the seeded 60% rule. Now 18
      cases; calibration still 18/18. Attach is on by default; `--no-memory` on
      `eval_runner` measures the with/without delta.
    - [ ] Live-API: run with and without memory and record the recall delta.
- ✅ **P5 sweep** — SCAFFOLDED. `src/sweep.py`: Haiku/Sonnet × thinking on/off via
      per-session `agent_with_overrides`, cost-per-success from token usage, pass-rate
      + cost plots. Pure cost math unit-tested; Fable row is commented (opt in).
    - [ ] Live-API: `python src/sweep.py --trials 3` → plots + one-line recommendation.
      Uncomment the Fable row if budget allows.
- ✅ **P6 README** — DRAFTED (`README.md`). Design rationale, host-fulfilled-tools
      decision, fixture universe, 18-case matrix, agent spec, harness, **real
      calibration evidence**, memory, reproduce steps, "what I'd do next." The
      pass^3-by-bucket and sweep tables are left as templates with the exact
      commands — they populate from the first live run (do NOT hand-fill).
    - [ ] After the first eval + sweep: paste the real pass^3-by-bucket numbers and
      the two sweep PNGs into §7 and §9.

---
*Maintained by Claude Code. Drafted-core items were done at Evan's explicit request,
overriding the handoff's Rule 1; they are written to be reviewed and owned.*
