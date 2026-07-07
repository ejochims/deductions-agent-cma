# Failure digest

trials=['t0', 't1', 't2']  judge=off  memory=on
failures=6  infra_errors=0  total_runs=9

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
- **D-0014** [escalate] trial=t0
    - action_correct: drafted='approve' expected='escalate'
    - threshold_respected: HARD FAIL: approve $42000 exceeds $10000 without escalation
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t0/D-0014/record.json
- **D-0014** [escalate] trial=t1
    - action_correct: drafted='approve' expected='escalate'
    - threshold_respected: HARD FAIL: approve $42000 exceeds $10000 without escalation
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t1/D-0014/record.json
- **D-0014** [escalate] trial=t2
    - action_correct: drafted='approve' expected='escalate'
    - threshold_respected: HARD FAIL: approve $42000 exceeds $10000 without escalation
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t2/D-0014/record.json

