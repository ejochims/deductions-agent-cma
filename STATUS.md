# Status

**Coming back to this project?** Start at `WALKTHROUGH.md` §14 (the 30-minute
re-orientation), then §15 for the code tour, §16 for the tests, §17 to demo it.

## Implemented and offline-verified (no API key required)
- **Fixtures + ground truth** — 18 cases across 6 buckets; 12 promotions, 3
  contracts, POS (incl. one missing on purpose), settlement history (incl. the
  duplicate twin and the 60% precedent). `fixtures/` + `ground_truth/`.
- **Agent config** — `agent/agent.yaml` (system prompt, model, 7 custom tools),
  `agent/environment.yaml` (locked-down sandbox), `agent/tools_server.py`
  (host-side fixture fulfilment + `get_precedents` + `draft_settlement` gate).
- **Harness** — `src/graders.py` (5 checks), `src/judge.py` (3 isolated dimensions),
  `src/eval_runner.py` (3×N, pass^k, infra separation, per-bucket rollups),
  `src/calibration.py` (gates A + B), `src/null_agent.py`, `src/fixtures_index.py`,
  `src/sweep.py`.
- **Tests** — `tests/` (pytest); CI runs them + calibration on every push.
- **Local UI** — `ui/` (Streamlit, `make ui`): case queue, investigation
  replay + grader scorecard, results dashboard with offline null-baseline demo,
  optional live-run panel (key-gated). Styled via a validated palette
  (`.streamlit/config.toml` + `ui/theme.py`).
- **Calibration** — Gate A: all 18 reference solutions pass the graders. Gate B: the
  null agent fails every non-approve case. `python src/calibration.py`.

## Latest live eval (2026-07-07, fingerprint `bc748e7bf9fa2807`)
3 trials × 18 cases, judge on. **Overall `pass^3 = 0.78`** (a case counts only if
all three trials pass; mean pass rate 0.83), up from `0.667` before the memory
fix. The fix moved precedent recall from the unreadable native store to the
host-fulfilled `get_precedents` tool. The memory bucket went `0.00 → 1.00` and
ambiguous `0.00 → 0.50`, and a `--no-memory` re-run collapses both back to
`0.00`, confirming the recall depends on the tool. Safety held: the $10k
threshold was never breached and no evidence was hallucinated. Results are
frozen at `runs/curated/postfix_results.json`, with the before/after in
`ITERATIONS.md` #1. Known failures D-0011, D-0013, D-0016 (and a D-0006 deny
flake) are left unfixed to avoid overfitting the measured cases.

## Needs a live Anthropic key to run
(Step-by-step runbook with costs and expected output: `WALKTHROUGH.md` §11.)
- One case end to end: `python src/run_agent.py --case D-0001 --trial t0`
- Judge calibration: `python src/judge.py --calibrate`
- Full eval: `python src/eval_runner.py --trials 3 --judge`
- Memory delta: add `--no-memory` to compare
- Model sweep: `python src/sweep.py --trials 3`
- Then paste the pass^3-by-bucket numbers and the two sweep PNGs into `README.md`
  §7 and §9.

## Possible next steps
- Prompt iteration loop: edit the `system:` block in `agent.yaml`, re-run the eval,
  record before/after deltas.
- Expand the judge calibration set beyond the 3 seeded negatives.
- Cache-aware cost accounting in the sweep once transcripts show real cache volume.
