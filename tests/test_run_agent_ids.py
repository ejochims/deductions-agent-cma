"""Agent create/update/cache lifecycle — no API, driven by a stub client.

The trap this guards: a prompt iteration edits agent.yaml, but a stale cached
agent id keeps serving the OLD system prompt, so the eval silently measures the
wrong agent. create_or_load_agent must create once, reuse on identical config,
and publish a new version when the config changes.
"""

from types import SimpleNamespace

import run_agent


class StubAgents:
    def __init__(self):
        self.create_calls = 0
        self.update_calls = 0
        self.version = 0

    def create(self, **kw):
        self.create_calls += 1
        self.version = 1
        return SimpleNamespace(id="agent_test", version=1)

    def update(self, agent_id, *, version, **kw):
        assert agent_id == "agent_test"
        assert version == self.version  # optimistic lock uses the cached version
        self.update_calls += 1
        self.version += 1
        return SimpleNamespace(id="agent_test", version=self.version)


def _client(stub):
    return SimpleNamespace(beta=SimpleNamespace(agents=stub))


def _cfg(system="v1 prompt"):
    return {"name": "Test Agent", "model": "claude-sonnet-4-6",
            "system": system, "tools": [{"type": "custom", "name": "t",
                                         "description": "d", "input_schema": {}}]}


def test_create_then_cache_then_update_on_change(tmp_path, monkeypatch):
    monkeypatch.setattr(run_agent, "_IDS_CACHE", tmp_path / "ids.json")
    stub = StubAgents()

    # First call: creates.
    aid, ver = run_agent.create_or_load_agent(_client(stub), _cfg())
    assert (aid, ver) == ("agent_test", 1)
    assert stub.create_calls == 1 and stub.update_calls == 0

    # Same config: cached — no API call at all.
    aid, ver = run_agent.create_or_load_agent(_client(stub), _cfg())
    assert (aid, ver) == ("agent_test", 1)
    assert stub.create_calls == 1 and stub.update_calls == 0

    # Changed system prompt (a prompt iteration): publishes a new version.
    aid, ver = run_agent.create_or_load_agent(_client(stub), _cfg(system="v2 prompt"))
    assert (aid, ver) == ("agent_test", 2)
    assert stub.create_calls == 1 and stub.update_calls == 1

    # And the new version is cached in turn.
    aid, ver = run_agent.create_or_load_agent(_client(stub), _cfg(system="v2 prompt"))
    assert (aid, ver) == ("agent_test", 2)
    assert stub.update_calls == 1


def test_fingerprint_stability_and_sensitivity():
    a = run_agent._agent_fingerprint(_cfg())
    assert a == run_agent._agent_fingerprint(_cfg())          # deterministic
    assert a != run_agent._agent_fingerprint(_cfg("v2"))       # prompt-sensitive


def test_judge_safe_skips_missing_settlement_without_client():
    from eval_runner import judge_settlement_safe
    # No settlement -> no judge call and no client construction.
    assert judge_settlement_safe(None, None) == []
