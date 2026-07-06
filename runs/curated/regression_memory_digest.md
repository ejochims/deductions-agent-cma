# Failure digest

trials=['t0', 't1', 't2']  judge=off  memory=on
failures=6  infra_errors=0  total_runs=6

## Graded failures (read the transcript; do not auto-fix)
- **D-0017** [memory] trial=t0
    - amount_within_tolerance: drafted=4750 expected=4500.0 |delta|=250.00 allowed=225.00
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t0/D-0017/record.json
- **D-0017** [memory] trial=t1
    - action_correct: drafted='deny' expected='partial'
    - amount_within_tolerance: expected ~4500.0 but no amount drafted
    - evidence_cited: missing ['SH-2025-Q4-007']
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t1/D-0017/record.json
- **D-0017** [memory] trial=t2
    - action_correct: drafted='escalate' expected='partial'
    - amount_within_tolerance: expected ~4500.0 but no amount drafted
    - evidence_cited: missing ['SH-2025-Q4-007']
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t2/D-0017/record.json
- **D-0018** [memory] trial=t0
    - action_correct: drafted='deny' expected='partial'
    - amount_within_tolerance: expected ~6300.0 but no amount drafted
    - evidence_cited: missing ['SH-2025-Q4-007']
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t0/D-0018/record.json
- **D-0018** [memory] trial=t1
    - action_correct: drafted='escalate' expected='partial'
    - amount_within_tolerance: expected ~6300.0 but no amount drafted
    - evidence_cited: missing ['SH-2025-Q4-007']
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t1/D-0018/record.json
- **D-0018** [memory] trial=t2
    - action_correct: drafted='deny' expected='partial'
    - amount_within_tolerance: expected ~6300.0 but no amount drafted
    - evidence_cited: missing ['SH-2025-Q4-007']
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t2/D-0018/record.json

