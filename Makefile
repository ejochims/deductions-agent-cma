.PHONY: install test lint calibrate eval sweep run clean

install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check src tests agent

# Offline gate: the harness proves itself before any model runs.
calibrate:
	python src/calibration.py

# --- the following need a live ANTHROPIC key ---
run:
	python src/run_agent.py --case D-0001 --trial t0

eval:
	python src/eval_runner.py --trials 3 --judge

sweep:
	python src/sweep.py --trials 3

clean:
	rm -rf runs/*/ runs/.managed_ids.json runs/results.json runs/sweep
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
