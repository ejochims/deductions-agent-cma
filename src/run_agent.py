"""[EVAN WRITES THE API CALLS] Run the Deductions Desk agent on one case.

Rule 1: the Anthropic / Managed-Agents API calls in this file are hand-written by
Evan. Claude Code scaffolded the orchestration plumbing around them — argument
parsing, config loading, the tool-dispatch bridge to agent/tools_server.py,
transcript/usage/timing capture, and the per-trial record — and left the three
SDK-touching functions as TODO(EVAN) stubs. The file will NOT run until those are
filled in; that is intentional.

What this does when complete: create (once) the agent from agent/agent.yaml and
the environment from agent/environment.yaml, start one session per case, stream
events, fulfil each custom-tool call host-side via ToolServer.dispatch, and save a
full transcript + the drafted settlement + token usage + timing to
runs/<trial>/<case_id>/.

The eval harness (src/eval_runner.py, Phase 3) will import and call run_one_case
across 3 trials x 16 cases. For Phase 2 the goal is to watch a SINGLE case run
end to end:  python src/run_agent.py --case D-0001 --trial t0
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Make agent/ importable so we can reuse the host-side tool fulfilment.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent"))
from tools_server import ToolServer, ToolError  # noqa: E402

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
    in Phase 3 excludes infra_error runs from the pass rate and retries them.
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
        self.started_at = datetime.now(timezone.utc).isoformat()

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
        out_path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
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
# ------------------------ TODO(EVAN): everything below calls the SDK ---------
# These three functions are the Anthropic / Managed-Agents API surface that Evan
# hand-writes (Rule 1). Signatures and docstrings describe exactly what each must
# do and which SDK calls / event patterns to use; the bodies are stubs.

def create_or_load_agent(client, agent_cfg: dict) -> tuple[str, int]:
    """Create the agent from agent_cfg (or reuse an existing one) and return
    (agent_id, version).

    TODO(EVAN): call client.beta.agents.create(name=..., model=..., system=...,
    tools=agent_cfg["tools"]) ONCE and persist the returned id (agents are
    versioned, reusable resources — do not recreate per run; hoist to setup or
    accept an --agent-id). Return (agent.id, agent.version).
    Ref: shared/managed-agents-core.md (Agents), python/managed-agents/README.md.
    """
    raise NotImplementedError("EVAN: implement agents.create / agent reuse")


def create_environment(client, env_cfg: dict) -> str:
    """Create the sandbox environment from env_cfg and return its id.

    TODO(EVAN): call client.beta.environments.create(name=env_cfg["name"],
    config=env_cfg["config"]) ONCE (reuse across cases) and return env.id.
    Environment names are unique — reuse an existing one if present.
    """
    raise NotImplementedError("EVAN: implement environments.create / reuse")


def run_session_for_case(client, agent_id: str, agent_version: int, env_id: str,
                         case_id: str, trial: str, tools: ToolServer,
                         recorder: TrialRecorder) -> None:
    """Drive one session to completion for one case.

    TODO(EVAN): implement the session lifecycle with the SDK:
      1. session = client.beta.sessions.create(agent={"type":"agent","id":agent_id,
         "version":agent_version}, environment_id=env_id, title=case_id)
         Print the Console trace URL:
         https://platform.claude.com/workspaces/default/sessions/{session.id}
      2. STREAM-FIRST: open client.beta.sessions.events.stream(session.id) BEFORE
         sending the kickoff, then send the user.message that names the case, e.g.
         "Investigate and draft a settlement for case {case_id}."
      3. For each streamed event:
           - record it with recorder.record_event(...)
           - on 'agent.custom_tool_use': call fulfil_tool_call(tools, event.name,
             event.input, trial, recorder), then send the result back with
             client.beta.sessions.events.send(session.id, events=[{
               "type":"user.custom_tool_result","custom_tool_use_id":event.id,
               "content":[{"type":"text","text":result_text}],"is_error":is_error}])
           - on 'span.model_request_end': accumulate event.model_usage into
             recorder.usage
      4. Break on 'session.status_terminated', or 'session.status_idle' whose
         stop_reason.type != 'requires_action' (see client-patterns.md Pattern 5).
    Capture timeouts / rate limits / tool-server crashes by setting
    recorder.status = "infra_error" and recorder.error; the harness handles retries.
    """
    raise NotImplementedError("EVAN: implement the session event loop")


# --------------------------------------------------------------- orchestration
def run_one_case(case_id: str, trial: str, client=None) -> TrialRecorder:
    """Run a single case end to end and persist its record.

    `client` is an Anthropic SDK client; when None, Evan's code should construct
    one (anthropic.Anthropic()). Everything except the three API functions above
    is wired up here.
    """
    agent_cfg = load_agent_config()
    env_cfg = load_environment_config()
    assert_tools_consistent(agent_cfg)

    tools = ToolServer(FIXTURES_DIR, RUNS_DIR)
    recorder = TrialRecorder(case_id, trial)
    t0 = time.monotonic()
    try:
        # TODO(EVAN): construct the client if not supplied, e.g.
        #   import anthropic; client = client or anthropic.Anthropic()
        agent_id, agent_version = create_or_load_agent(client, agent_cfg)
        env_id = create_environment(client, env_cfg)
        run_session_for_case(client, agent_id, agent_version, env_id,
                             case_id, trial, tools, recorder)
    except NotImplementedError:
        raise
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
