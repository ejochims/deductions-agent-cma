"""Data layer for the local UI — pure functions over fixtures/ and runs/.

No Streamlit imports here: everything is unit-testable and reusable. The UI is a
window onto artifacts the harness already produces (deduction fixtures, run
transcripts, drafted settlements, grader results); this module does the reading
and shaping, app.py does the rendering.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for sub in ("src", "agent"):
    p = str(REPO_ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from eval_runner import TrialResult, aggregate, grade_settlement  # noqa: E402
from fixtures_index import FIXTURES_DIR, all_case_ids, case_bucket  # noqa: E402

RUNS_DIR = REPO_ROOT / "runs"


# ------------------------------------------------------------------ fixtures
def load_cases() -> list[dict]:
    """All deduction cases as the agent sees them, plus their bucket."""
    cases = []
    for case_id in all_case_ids():
        d = json.loads((FIXTURES_DIR / "deductions" / f"{case_id}.json").read_text())
        d["bucket"] = case_bucket(case_id)
        cases.append(d)
    return cases


def queue_rows(cases: list[dict]) -> list[dict]:
    """The analyst-worklist view: one compact row per open deduction."""
    return [
        {
            "case": c["case_id"],
            "retailer": c["retailer_id"],
            "amount": c["amount"],
            "type": c["deduction_type"],
            "date": c.get("deduction_date", ""),
            "bucket": c["bucket"],
        }
        for c in cases
    ]


# ---------------------------------------------------------------------- runs
def list_runs() -> dict[str, list[str]]:
    """trial -> case ids that have a drafted settlement on disk.

    Discovers trials at any depth under runs/ so nested curated runs surface
    too: a live run at runs/ui/D-0009/ keys as "ui", while the committed
    showcase transcripts at runs/curated/t0/D-0009/ key as "curated/t0". The
    trial label is the settlement's grandparent relative to runs/, which stays
    compatible with load_artifacts() (RUNS_DIR / trial / case_id).
    """
    out: dict[str, list[str]] = {}
    if not RUNS_DIR.exists():
        return out
    for sp in RUNS_DIR.rglob("settlement.json"):
        trial = sp.parent.parent.relative_to(RUNS_DIR).as_posix()
        out.setdefault(trial, []).append(sp.parent.name)
    return {trial: sorted(set(cases)) for trial, cases in sorted(out.items())}


def load_artifacts(trial: str, case_id: str) -> tuple[dict | None, dict | None]:
    """(settlement, record) for one run; either may be missing."""
    base = RUNS_DIR / trial / case_id
    settlement = record = None
    if (base / "settlement.json").exists():
        settlement = json.loads((base / "settlement.json").read_text())
    if (base / "record.json").exists():
        record = json.loads((base / "record.json").read_text())
    return settlement, record


def transcript_steps(record: dict) -> list[dict]:
    """Shape a run record into displayable investigation steps.

    Prefers the recorder's tool_calls (name/input/result/is_error) interleaved
    with agent text from the event transcript. Best-effort: unknown event shapes
    are skipped rather than crashing the viewer.
    """
    steps: list[dict] = []
    for ev in record.get("transcript", []):
        etype = ev.get("type", "")
        if etype == "agent.message":
            text = " ".join(
                blk.get("text", "") for blk in ev.get("content", [])
                if isinstance(blk, dict) and blk.get("type") == "text"
            ).strip()
            if text:
                steps.append({"kind": "agent_text", "title": "Agent", "body": text})
        elif etype == "agent.custom_tool_use":
            steps.append({
                "kind": "tool_call",
                "title": f"Tool call: {ev.get('name', '?')}",
                "body": ev.get("input", {}),
            })
    # Attach results by matching order of tool_calls to tool-call steps.
    results = iter(record.get("tool_calls", []))
    for step in steps:
        if step["kind"] == "tool_call":
            tc = next(results, None)
            if tc is not None:
                step["result"] = tc.get("result")
                step["is_error"] = tc.get("is_error", False)
    if not steps and record.get("tool_calls"):
        # No parseable transcript events — fall back to the tool-call log alone.
        steps = [
            {"kind": "tool_call", "title": f"Tool call: {tc.get('name', '?')}",
             "body": tc.get("input", {}), "result": tc.get("result"),
             "is_error": tc.get("is_error", False)}
            for tc in record["tool_calls"]
        ]
    return steps


# ------------------------------------------------------------------- grading
def scorecard(settlement: dict | None, case_id: str) -> tuple[bool, list[dict]]:
    """Grade one settlement through the real graders (offline, free)."""
    return grade_settlement(settlement, case_id)


def grade_trial(trial: str) -> dict:
    """Grade every drafted settlement in one runs/<trial>/ and aggregate.

    Pure offline pipeline: read drafts -> graders -> pass^k/bucket rollup. Used
    by the dashboard both for real runs and for the null baseline.
    """
    results = []
    for case_id in all_case_ids():
        settlement, _ = load_artifacts(trial, case_id)
        if settlement is None:
            continue
        passed, checks = grade_settlement(settlement, case_id)
        results.append(TrialResult(case_id, trial, status="ok", passed=passed,
                                   check_results=checks))
    if not results:
        return {}
    return aggregate(results)


def generate_null_baseline(trial: str = "null-baseline") -> str:
    """Write the always-approve baseline drafts so the dashboard has offline data."""
    from null_agent import write_null_run
    write_null_run(RUNS_DIR, trial=trial)
    return trial


def load_results() -> dict | None:
    """The last full eval's results.json, if one exists."""
    path = RUNS_DIR / "results.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def bucket_table(summary: dict) -> list[dict]:
    """summary['by_bucket'] -> rows for a table/chart."""
    rows = []
    for bucket, s in summary.get("by_bucket", {}).items():
        rows.append({
            "bucket": bucket,
            "cases": s["n_cases"],
            "mean pass rate": s["mean_pass_rate"],
            "pass^k": s["pass_k"],
        })
    overall = summary.get("overall")
    if overall:
        rows.append({"bucket": "OVERALL", "cases": overall["n_cases"],
                     "mean pass rate": overall["mean_pass_rate"],
                     "pass^k": overall["pass_k"]})
    return rows
