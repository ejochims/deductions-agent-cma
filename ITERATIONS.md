# Iterations

Log of eval-driven changes to the agent prompt or graders. Every change is decided
by a human reading transcripts (via the failure digest, `runs/digest.md`) — the
harness reports failures, it does not fix them. Each entry records the before/after
pass rate by bucket so the delta is auditable.

## How to log an iteration
1. Run the eval; read `runs/digest.md` and the linked transcripts.
2. Decide the change (prompt or grader). Record it below.
3. Re-run the eval; paste the before/after pass^k (or mean pass rate) by bucket.

## Template

```
### N. <short title>  (<date>, git <sha>)
Change: <what changed and why, from which transcripts>
Config: model=<>, trials=<>, judge=<on/off>

| bucket    | before pass^k | after pass^k |
|-----------|---------------|--------------|
| approve   |               |              |
| deny      |               |              |
| partial   |               |              |
| escalate  |               |              |
| ambiguous |               |              |
| memory    |               |              |
| overall   |               |              |

Notes: <what the delta tells us; any regressions>
```

---

_No iterations recorded yet — awaiting the first live eval run._
