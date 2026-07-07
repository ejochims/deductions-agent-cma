# ADR 0001 — Precedent recall via a host-fulfilled tool, not native memory

- **Status:** Accepted
- **Date:** 2026-07-07
- **Area:** agent architecture / security boundary
- **Implemented in:** PR #16 (`claude/memory-precedents-tool`)
- **Related:** README §8, WALKTHROUGH §8 (how it works) and §13 (design decisions)

## Context

Deductions Desk needs **precedent recall**: some cases can only be settled
correctly by applying an established, cross-claim convention rather than
re-deriving a decision from the case's own data. The load-bearing example is the
demo-billback convention — *a demo/sampling billback missing the signed Exhibit B
forms, but corroborated by store photos and POS scan lift, settles at 60% of the
claimed amount* (precedent `SH-2025-Q4-007`). Cases D-0017/D-0018 are built to
reward exactly that recall.

The first implementation used the Managed Agents **native memory store**: a
persistent store was created, seeded from `agent/memory_seed.json`, attached to
every session `read_write`, and the system prompt told the agent it was *"mounted
at `/mnt/memory/`."*

**It never worked.** The `memory` bucket scored **0% pass^3**. The run records
show why: the agent tried to read the store with `read_file` / `list_files` (and,
when appending, `write_file`) and every call returned **`"Unknown tool"`**:

```
read_file  /mnt/memory/meridian-deductions-precedents/          -> "Unknown tool 'read_file'"
list_files /mnt/memory/meridian-deductions-precedents/          -> "Unknown tool 'list_files'"
read_file  /mnt/memory/meridian-deductions-precedents/precedents.md -> "Unknown tool 'read_file'"
```

The store was attached, but **nothing exposed it to the model**, so the agent
drafted D-0017/D-0018 blind. The run's `status` stayed `ok`, so it degraded
silently rather than surfacing as an error.

### How we found it: the evals surfaced it, not the code

We did not catch this by reading the code — the **eval harness** did. The feature
looked complete from the outside: the store was created, seeded, and attached,
and the system prompt referenced it, so nothing about the wiring looked wrong.
What flagged it was the **`memory` bucket scoring 0% pass^3** in the eval, sitting
next to healthy scores in every other bucket. That per-bucket signal is what
triggered the investigation, which then traced the run records to the
`"Unknown tool"` errors above.

This is itself an argument for the harness. A capability that degrades *silently*
— the session `status` stayed `ok`, no exception, a plausible-looking draft — is
exactly the failure a happy-path demo sails straight past and a per-bucket,
ground-truth eval catches. The memory bug is a concrete instance of the repo's
core thesis: **you cannot trust a capability you cannot measure**, and the reason
we could even have this architecture conversation is that the eval made an
invisible failure visible.

### The constraint that makes this non-trivial

This is not a bug we can fix by "granting a permission." It is a direct
consequence of the system's **load-bearing security decision**: *the tool
boundary is the security boundary* (WALKTHROUGH §5, §13). The sandbox
(`agent/environment.yaml`) mounts nothing, permits no egress, and gives the agent
**no `bash` / `read` / `write` / file tools**. That is what makes the answer key
(`ground_truth/`) unreachable by construction and what neutralizes prompt
injection from the untrusted retailer remittance text.

A native memory store is reached through a filesystem-style / memory tool. To use
it, we would have to put a model-facing, read/write, stateful interface **inside
the very sandbox we deliberately kept toolless**. The property that makes the
architecture safe is the same property that made the mounted store unreadable.

## Decision

Serve precedent recall the **same way as every other capability in this system —
a host-fulfilled custom tool**, `get_precedents`, rather than a native memory
store.

- `get_precedents` is declared in `agent/agent.yaml` (bringing the agent to 7
  custom tools) and fulfilled host-side in `agent/tools_server.py`, reading
  `fixtures/precedents.json`. The agent emits `custom_tool_use`, idles, and the
  orchestrator returns the precedents — identical to the other read tools.
- The system prompt's "## Precedents" section now says *"call `get_precedents`…
  cite the settlement-history id it records,"* replacing the `/mnt/memory/`
  filesystem framing.
- A `precedents_enabled` flag on `ToolServer` (driven by `--no-memory`) makes the
  tool return an empty set when disabled, preserving the with/without-memory
  delta measurement without a native store.
- The native memory wiring is **retired**: `src/memory_store.py` and
  `agent/memory_seed.json` are removed; the session mounts no resources.

## Trade-off: what we give up by NOT using native memory

This is a real trade-off, made deliberately.

**What native memory would have given us, and we are choosing to forgo:**

1. **Genuine write-then-recall across sessions.** With native memory the agent
   could *author* a new precedent when it settles a novel pattern and have a
   later case recall it — institutional knowledge accumulating autonomously over
   time. Our tool is **read-only over a curated set**: precedents are authored by
   humans, not the agent.
2. **The "agentic learning" narrative.** "The system learns and gets more
   consistent on its own" is a compelling story we are not telling. Ours is
   "the system applies a curated, version-controlled rulebook consistently."
3. **A showcase of the platform's native memory feature.** We are not
   demonstrating Managed Agents memory; we are demonstrating the tool boundary.

**Why we accept that, for this system specifically:**

1. **The security boundary stays intact.** No model-writable persistent surface
   means **no memory-poisoning attack**: prompt-injected remittance text cannot
   write a bad precedent ("demo billbacks settle at 100%") that persists and
   biases *future* cases. With host-fulfilled precedents, the host owns the data
   and the agent can only *ask*.
2. **One consistent architecture.** Every capability — including memory — is a
   narrow, host-mediated tool. Nothing is mounted; the answer key remains
   unreachable by construction. The whole system reasons about one boundary.
3. **Auditable and offline-testable.** Precedents are a fixture graded by the
   same offline pipeline as everything else. If we ever add precedent *writes*,
   they can be validated or human-gated in host code rather than committed
   unilaterally by the model.
4. **The eval does not yet exercise native memory's unique power.** D-0017/D-0018
   both only need to **read** the same seeded convention; neither tests
   write-then-recall. Adopting native memory today would add a capability (and an
   attack surface) the harness does not measure.

For a proof of concept whose entire differentiator is *bounded autonomy you can
trust with money*, the host-fulfilled tool is the more coherent choice — not a
workaround.

## Alternatives considered

- **A — Native memory tool (view/read/write).** Rejected: re-introduces
  model-writable persistent state and a memory-poisoning surface, dents the
  toolless-sandbox thesis, and the eval doesn't test its upside.
- **B — Hybrid: native store for recall, host- or human-gated writes.** Deferred.
  This is the right answer *if institutional learning becomes a product goal* —
  it keeps "policy lives in host code" while using the real memory feature for
  storage. More work, and it re-opens the sandbox-lockdown question. Revisit when
  requirements change (see below).
- **C — Remove the memory feature entirely.** Rejected: abandons a real
  capability the case set is designed to test.

## Consequences

- The agent now has a working, offline-testable path to precedents; the memory
  bucket is expected to lift materially (empirical `pass^3` to be confirmed by a
  paid re-run of D-0017/D-0018 — retrieval is unblocked and Gate A already proves
  the target is graders-passable).
- The system keeps a single, uniform security story: the tool boundary is the
  only surface the agent can act through.
- Precedent management becomes a **content** task (edit `fixtures/precedents.json`)
  rather than an agent-behavior concern.

## When to revisit

Move to **Alternative B (hybrid)** if the product needs the agent to *accumulate
novel precedents over time* rather than apply a curated set. If we do, we must
also:

1. Extend the eval with a **write→recall** case pair (settle a novel pattern in
   case N; a later case passes only if that self-authored precedent is recalled).
2. Add a **memory-governance / poisoning** test (an adversarial remittance that
   tries to write a bad precedent must be rejected or quarantined).

Until the eval can measure both the upside and the new risk, host-fulfilled
`get_precedents` remains the correct design.
