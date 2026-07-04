"""Test configuration: make src/ and agent/ importable."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for sub in ("src", "agent"):
    p = str(REPO_ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
