# Failure digest

trials=['t0', 't1', 't2']  judge=off  memory=on
failures=6  infra_errors=0  total_runs=15

## Graded failures (read the transcript; do not auto-fix)
- **D-0013** [escalate] trial=t0
    - action_correct: drafted='deny' expected='escalate'
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t0/D-0013/record.json
- **D-0013** [escalate] trial=t1
    - action_correct: drafted='deny' expected='escalate'
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t1/D-0013/record.json
- **D-0013** [escalate] trial=t2
    - action_correct: drafted='deny' expected='escalate'
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t2/D-0013/record.json
- **D-0017** [memory] trial=t0
    - evidence_cited: missing ['SH-2025-Q4-007']
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t0/D-0017/record.json
- **D-0017** [memory] trial=t1
    - evidence_cited: missing ['SH-2025-Q4-007']
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t1/D-0017/record.json
- **D-0017** [memory] trial=t2
    - amount_within_tolerance: drafted=2850 expected=4500.0 |delta|=1650.00 allowed=225.00
    - evidence_cited: missing ['SH-2025-Q4-007']
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t2/D-0017/record.json

