#!/usr/bin/env bash
# Verify the README quickstart from a clean checkout: fresh venv, install, then the
# two offline gates (tests + calibration). No API key required.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> fresh clone into $WORK"
git clone --quiet "$REPO_ROOT" "$WORK/repo"
cd "$WORK/repo"

echo "==> create venv + install (pinned deps)"
python -m venv "$WORK/venv"
# shellcheck disable=SC1091
source "$WORK/venv/bin/activate"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e ".[dev,ui]"

echo "==> offline gate: tests"
python -m pytest -q

echo "==> offline gate: calibration"
python src/calibration.py

echo "==> quickstart OK"
