.PHONY: install lint verify-quickstart clean ui demo deck \
        gates phase-a phase-b phase-c phase-d phase-e phase-f \
        test calibrate judge-calibrate run-one estimate trial eval digest sweep

install:
	pip install -e ".[dev,ui]"

lint:
	ruff check src tests agent ui

# Verify the README quickstart from a clean checkout (fresh venv). No key needed.
verify-quickstart:
	bash scripts/verify_quickstart.sh

# =====================================================================
# Cheap-first run sequence. Run top to bottom; stop and read between phases.
# Phases a+b are free; c onward need a live ANTHROPIC key and cost money.
# =====================================================================

# (a) unit tests + tools-consistency check — zero API cost
phase-a test:
	pytest

# (b) calibration gates A + B — zero API cost
phase-b calibrate:
	python src/calibration.py

# a + b together — the free gate before anything paid
gates: phase-a phase-b

# (c) judge calibration — trust the judge before it grades (prints cost estimate)
phase-c judge-calibrate:
	python src/judge.py --calibrate

# (d) ONE case end to end, then STOP and read runs/t0/D-0001/record.json
phase-d run-one:
	python src/run_agent.py --case D-0001 --trial t0

# preflight: print the cost estimate for a full run without spending anything
estimate:
	python src/eval_runner.py --trials 3 --judge --estimate-only

# (e) one full trial x all cases, judge OFF (prints estimate, actuals, digest)
phase-e trial:
	python src/eval_runner.py --trials 1

# (f) 3 trials x all cases, judge ON (prints estimate, actuals, digest)
phase-f eval:
	python src/eval_runner.py --trials 3 --judge

# failure digest from the last run (reports; never fixes)
digest:
	python src/digest.py

# local review UI (case queue, investigation replay, dashboard, live run)
ui:
	streamlit run ui/app.py

# team demo — same app, framed as the presenter entry point. Works fully offline
# out of the box (curated transcripts + committed results.json); the Live-run tab
# lights up automatically when ANTHROPIC_API_KEY is set. See WALKTHROUGH.md sec 17.
demo: ui

# the slide deck (docs/presentation.html) at :8777 — docs/index.html redirects to it
deck:
	python -m http.server 8777 -d docs

# model sweep (cost-per-success)
sweep:
	python src/sweep.py --trials 3

clean:
	rm -f runs/.managed_ids.json runs/results.json runs/digest.md
	find runs -mindepth 1 -maxdepth 1 -type d ! -name curated -exec rm -rf {} +
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
