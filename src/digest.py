"""Failure digest for an eval run — reports, never fixes.

Reads runs/results.json and produces a per-failure line: case, bucket, which
programmatic check or judge dimension failed, a one-line summary, and the path to
the transcript to read. Also lists infra errors separately. Writes runs/digest.md
and prints to stdout.

This tool deliberately does NOT touch the agent prompt or the graders. Prompt and
grader changes are decided by a human reading the transcripts and logged in
ITERATIONS.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fixtures_index import REPO_ROOT

RUNS_DIR = REPO_ROOT / "runs"
RESULTS_PATH = RUNS_DIR / "results.json"


def _failed_checks(result: dict) -> list[str]:
    out = []
    for c in result.get("check_results", []):
        if c.get("applicable", True) and not c.get("passed", True):
            detail = c.get("detail", "")
            out.append(f"{c['name']}: {detail}" if detail else c["name"])
    for v in result.get("judge_verdicts", []):
        if v.get("verdict") == "fail":
            out.append(f"judge/{v['dimension']}: {v.get('reason', '')}")
    return out


def build_digest(results_path: Path = RESULTS_PATH) -> str:
    if not results_path.exists():
        return f"No results at {results_path}. Run an eval first."
    payload = json.loads(results_path.read_text())
    results = payload["results"]

    failures = [r for r in results if r["status"] == "ok" and r["passed"] is False]
    infra = [r for r in results if r["status"] == "infra_error"]

    lines = [
        "# Failure digest",
        "",
        f"trials={payload['trials']}  judge={'on' if payload.get('used_judge') else 'off'}  "
        f"memory={'on' if payload.get('used_memory', True) else 'off'}",
        f"failures={len(failures)}  infra_errors={len(infra)}  total_runs={len(results)}",
        "",
    ]

    if failures:
        lines.append("## Graded failures (read the transcript; do not auto-fix)")
        for r in sorted(failures, key=lambda r: (r["case_id"], r["trial"])):
            from fixtures_index import case_bucket
            bucket = case_bucket(r["case_id"])
            reasons = _failed_checks(r) or ["(no per-check detail captured)"]
            transcript = RUNS_DIR / r["trial"] / r["case_id"] / "record.json"
            lines.append(f"- **{r['case_id']}** [{bucket}] trial={r['trial']}")
            for reason in reasons:
                lines.append(f"    - {reason}")
            lines.append(f"    - transcript: {transcript}")
        lines.append("")

    if infra:
        lines.append("## Infra errors (excluded from pass rate, retried once)")
        for r in sorted(infra, key=lambda r: (r["case_id"], r["trial"])):
            lines.append(f"- {r['case_id']} trial={r['trial']}: {r.get('note', '')}")
        lines.append("")

    if not failures and not infra:
        lines.append("No graded failures and no infra errors. ✅")
        lines.append("")

    return "\n".join(lines)


def write_and_print(results_path: Path = RESULTS_PATH) -> Path:
    text = build_digest(results_path)
    out = RUNS_DIR / "digest.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n")
    print(text)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Failure digest from runs/results.json.")
    parser.add_argument("--results", type=Path, default=RESULTS_PATH)
    args = parser.parse_args()
    write_and_print(args.results)


if __name__ == "__main__":
    main()
