"""Run the Deductions Desk agent on one case.

Creates (once) the agent from agent/agent.yaml and the environment from
agent/environment.yaml, starts one session per case, streams events, fulfils each
custom-tool call host-side via ToolServer.dispatch, and saves a full transcript +
the drafted settlement + token usage + timing to runs/<trial>/<case_id>/.

The eval harness (src/eval_runner.py) imports and calls run_one_case across
3 trials x N cases. To watch a single case end to end:

    python src/run_agent.py --case D-0001 --trial t0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

# Make agent/ importable so we can reuse the host-side tool fulfilment.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent"))
from tools_server import ToolError, ToolServer  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "fixtures"
RUNS_DIR = REPO_ROOT / "runs"
AGENT_YAML = REPO_ROOT / "agent" / "agent.yaml"
ENV_YAML = REPO_ROOT / "agent" / "environment.yaml"


# ---------------------------------------------------------------- config load
def load_agent_config() -> dict:
    """Parse agent/agent.yaml (system prompt, model, custom-tool schemas).

    This dict is the single source of truth passed to agents.create so the SDK
    and the `ant` CLI provision the same agent.
    """
    return yaml.safe_load(AGENT_YAML.read_text())


def load_environment_config() -> dict:
    return yaml.safe_load(ENV_YAML.read_text())


def assert_tools_consistent(agent_cfg: dict) -> None:
    """Guard against drift: every custom tool declared in agent.yaml must have a
    handler in ToolServer.dispatch, and vice versa."""
    declared = {
        t["name"] for t in agent_cfg.get("tools", []) if t.get("type") == "custom"
    }
    fulfilled = {
        "get_deduction", "search_promotions", "get_contract_terms",
        "get_pos_data", "check_settlement_history", "draft_settlement",
    }
    missing = declared - fulfilled
    extra = fulfilled - declared
    if missing or extra:
        raise SystemExit(
            f"agent.yaml / tools_server.py mismatch: "
            f"declared-but-unfulfilled={sorted(missing)}, "
            f"fulfilled-but-undeclared={sorted(extra)}"
        )


# --------------------------------------------------------------- transcript io
class TrialRecorder:
    """Accumulates everything worth keeping for one (case, trial) run.

    Kept separate from pass/fail: `status` is 'ok' or 'infra_error'. The harness
    excludes infra_error runs from the pass rate and retries them.
    """

    def __init__(self, case_id: str, trial: str) -> None:
        self.case_id = case_id
        self.trial = trial
        self.events: list[dict] = []          # every message / tool call / result
        self.tool_calls: list[dict] = []      # grader-relevant tool I/O
        self.usage: dict = {}                 # token usage from the API usage block
        self.timings: dict = {}               # wall-clock and per-call timing
        self.status: str = "ok"
        self.error: str | None = None
        self.started_at = datetime.now(UTC).isoformat()

    def record_event(self, event: dict) -> None:
        self.events.append(event)

    def record_tool_call(self, name: str, tool_input: dict, result: object,
                         is_error: bool) -> None:
        self.tool_calls.append({
            "name": name, "input": tool_input,
            "result": result, "is_error": is_error,
        })

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "trial": self.trial,
            "status": self.status,
            "error": self.error,
            "started_at": self.started_at,
            "usage": self.usage,
            "timings": self.timings,
            "tool_calls": self.tool_calls,
            "transcript": self.events,
        }

    def save(self) -> Path:
        out_dir = RUNS_DIR / self.trial / self.case_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "record.json"
        # default=str so raw datetimes from SDK event model_dump() (and any other
        # non-JSON-native value) serialize instead of crashing the record write.
        out_path.write_text(json.dumps(self.to_dict(), indent=2, default=str) + "\n")
        return out_path


# ------------------------------------------------------------- tool dispatch
def fulfil_tool_call(tools: ToolServer, name: str, tool_input: dict,
                     trial: str, recorder: TrialRecorder) -> tuple[str, bool]:
    """Run one custom-tool call host-side and return (result_text, is_error).

    result_text is JSON so the agent gets structured data back. A ToolError
    becomes an is_error result the agent can recover from, NOT a crash.
    """
    try:
        result = tools.dispatch(name, tool_input, trial)
        is_error = False
    except ToolError as exc:
        result = {"error": str(exc)}
        is_error = True
    recorder.record_tool_call(name, tool_input, result, is_error)
    return json.dumps(result), is_error


# ============================================================ API surface
# The Anthropic / Managed-Agents API surface. Agent and environment are created
# ONCE and their ids cached in runs/.managed_ids.json so they are reused across
# cases and trials (agents are versioned, reusable resources — never recreate per
# run). Session creation + the event loop happen per case.

_IDS_CACHE = RUNS_DIR / ".managed_ids.json"


def _load_ids() -> dict:
    if _IDS_CACHE.exists():
        return json.loads(_IDS_CACHE.read_text())
    return {}


def _save_ids(ids: dict) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _IDS_CACHE.write_text(json.dumps(ids, indent=2) + "\n")


def _as_dict(obj) -> dict:
    """Best-effort serialization of an SDK event/usage object for the transcript."""
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except TypeError:
                continue
    if isinstance(obj, dict):
        return obj
    return {"repr": repr(obj)}


def _agent_fingerprint(agent_cfg: dict) -> str:
    """Stable hash of the agent config, so a changed agent.yaml is detected."""
    canonical = json.dumps(agent_cfg, sort_keys=True).encode()
    return hashlib.sha256(canonical).hexdigest()[:16]


def create_or_load_agent(client, agent_cfg: dict) -> tuple[str, int]:
    """Create the agent once; publish a new version whenever agent.yaml changes.

    The cached id alone is not enough: if agent.yaml is edited (a prompt
    iteration) but the cached agent keeps serving the old system prompt, the
    eval silently measures the wrong agent. So the config fingerprint is cached
    alongside the id — on mismatch, agents.update publishes a new immutable
    version and sessions pin to it.
    """
    ids = _load_ids()
    fp = _agent_fingerprint(agent_cfg)
    if ids.get("agent_id") and ids.get("agent_fingerprint") == fp:
        return ids["agent_id"], ids["agent_version"]

    fields = {"model": agent_cfg["model"], "system": agent_cfg["system"],
              "tools": agent_cfg["tools"]}
    if ids.get("agent_id"):
        agent = client.beta.agents.update(
            ids["agent_id"], version=ids["agent_version"], **fields)
    else:
        agent = client.beta.agents.create(name=agent_cfg["name"], **fields)
    ids.update({"agent_id": agent.id, "agent_version": agent.version,
                "agent_fingerprint": fp})
    _save_ids(ids)
    return agent.id, agent.version


def create_environment(client, env_cfg: dict) -> str:
    """Create the sandbox environment once, or reuse the cached id."""
    ids = _load_ids()
    if ids.get("env_id"):
        return ids["env_id"]
    env = client.beta.environments.create(
        name=env_cfg["name"], config=env_cfg["config"]
    )
    ids["env_id"] = env.id
    _save_ids(ids)
    return env.id


def _agent_ref(agent_id: str, agent_version: int, override: dict | None) -> dict:
    """Session agent reference — pinned version, or agent_with_overrides for the sweep.

    `override` is e.g. {"model": "claude-haiku-4-5"}; it replaces those fields for
    this session only, without creating a new agent version. Managed Agents allows
    overriding model / system / tools / mcp_servers / skills only.
    """
    if not override:
        return {"type": "agent", "id": agent_id, "version": agent_version}
    return {"type": "agent_with_overrides", "id": agent_id,
            "version": agent_version, **override}


# Hard ceiling on one case's session. A session that exceeds it is raised as a
# TimeoutError and recorded as infra_error (excluded from pass rates, retried
# once) — a hung run must never look like a graded failure. The check fires as
# events arrive; a fully silent stream is bounded by the SDK/HTTP layer instead.
MAX_SESSION_SECONDS = 900


def run_session_for_case(client, agent_id: str, agent_version: int, env_id: str,
                         case_id: str, trial: str, tools: ToolServer,
                         recorder: TrialRecorder, resources: list | None = None,
                         agent_override: dict | None = None,
                         max_session_s: float = MAX_SESSION_SECONDS) -> None:
    """Drive one session to completion for one case (stream-first, Pattern 5 gate)."""
    session = client.beta.sessions.create(
        agent=_agent_ref(agent_id, agent_version, agent_override),
        environment_id=env_id,
        title=case_id,
        resources=resources or [],
    )
    print(f"  trace: https://platform.claude.com/workspaces/default/sessions/{session.id}")

    kickoff = (f"Investigate case {case_id} and draft a settlement. Call "
               f"get_deduction first, gather the evidence you need, then call "
               f"draft_settlement exactly once.")

    # Stream-first: open the stream, THEN send the kickoff, so no early events
    # are missed (the stream has no replay).
    deadline = time.monotonic() + max_session_s
    with client.beta.sessions.events.stream(session_id=session.id) as stream:
        client.beta.sessions.events.send(
            session_id=session.id,
            events=[{"type": "user.message",
                     "content": [{"type": "text", "text": kickoff}]}],
        )
        for event in stream:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"session for {case_id} exceeded {max_session_s:.0f}s")
            recorder.record_event(_as_dict(event))
            etype = getattr(event, "type", None)

            if etype == "agent.custom_tool_use":
                result_text, is_error = fulfil_tool_call(
                    tools, event.name, dict(event.input or {}), trial, recorder)
                client.beta.sessions.events.send(
                    session_id=session.id,
                    events=[{"type": "user.custom_tool_result",
                             "custom_tool_use_id": event.id,
                             "content": [{"type": "text", "text": result_text}],
                             "is_error": is_error}],
                )

            elif etype == "span.model_request_end":
                usage = _as_dict(getattr(event, "model_usage", {}) or {})
                for k, v in usage.items():
                    if isinstance(v, (int, float)):
                        recorder.usage[k] = recorder.usage.get(k, 0) + v

            elif etype == "session.status_terminated":
                break

            elif etype == "session.status_idle":
                stop_reason = getattr(event, "stop_reason", None)
                sr_type = getattr(stop_reason, "type", None)
                if sr_type != "requires_action":
                    break  # end_turn / retries_exhausted — terminal for this run


# --------------------------------------------------------------- orchestration
def clear_prior_draft(trial: str, case_id: str) -> None:
    """Remove a settlement.json left by an earlier attempt of this (trial, case)."""
    path = RUNS_DIR / trial / case_id / "settlement.json"
    path.unlink(missing_ok=True)


def run_one_case(case_id: str, trial: str, client=None, *,
                 use_memory: bool = True, agent_override: dict | None = None) -> TrialRecorder:
    """Run a single case end to end and persist its record.

    `client` is an Anthropic SDK client; when None one is constructed. `use_memory`
    attaches the precedent memory store to the session — set False to measure the
    with/without-memory delta. `agent_override` swaps model/thinking per
    session for the sweep, without creating a new agent version.
    """
    agent_cfg = load_agent_config()
    env_cfg = load_environment_config()
    assert_tools_consistent(agent_cfg)

    # Clear any draft left by a previous attempt of this same (trial, case).
    # Without this, a run that drafts and THEN hits an infra error leaves a
    # settlement.json behind — and if the retry finishes without drafting, the
    # harness would grade the stale draft as the retry's output.
    clear_prior_draft(trial, case_id)

    tools = ToolServer(FIXTURES_DIR, RUNS_DIR)
    recorder = TrialRecorder(case_id, trial)
    t0 = time.monotonic()
    try:
        if client is None:
            import anthropic  # local import: only needed when actually running
            client = anthropic.Anthropic()
        agent_id, agent_version = create_or_load_agent(client, agent_cfg)
        env_id = create_environment(client, env_cfg)
        resources = None
        if use_memory:
            from memory_store import create_or_load_memory_store, memory_resource
            resources = [memory_resource(create_or_load_memory_store(client))]
        run_session_for_case(client, agent_id, agent_version, env_id,
                             case_id, trial, tools, recorder, resources=resources,
                             agent_override=agent_override)
    except Exception as exc:  # noqa: BLE001 — infra failures are recorded, not raised
        recorder.status = "infra_error"
        recorder.error = f"{type(exc).__name__}: {exc}"
    finally:
        recorder.timings["wall_clock_s"] = round(time.monotonic() - t0, 3)
        recorder.save()
    return recorder


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Deductions Desk agent on one case.")
    parser.add_argument("--case", required=True, help="Case id, e.g. D-0001")
    parser.add_argument("--trial", default="t0", help="Trial label, e.g. t0")
    args = parser.parse_args()

    recorder = run_one_case(args.case, args.trial)
    print(f"[{recorder.status}] {args.case} / {args.trial} "
          f"-> {RUNS_DIR / args.trial / args.case}")


if __name__ == "__main__":
    main()
