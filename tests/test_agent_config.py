"""Agent config integrity: YAML parses, tools match the fulfilment layer."""
import yaml

import run_agent
from fixtures_index import REPO_ROOT


def test_agent_yaml_parses_and_has_seven_tools():
    cfg = yaml.safe_load((REPO_ROOT / "agent" / "agent.yaml").read_text())
    assert cfg["model"]
    assert cfg["system"].strip()
    customs = [t for t in cfg["tools"] if t["type"] == "custom"]
    assert len(customs) == 7
    assert "get_precedents" in {t["name"] for t in customs}


def test_environment_yaml_locked_down():
    env = yaml.safe_load((REPO_ROOT / "agent" / "environment.yaml").read_text())
    assert env["config"]["networking"]["type"] == "limited"


def test_declared_tools_match_fulfilment():
    cfg = run_agent.load_agent_config()
    run_agent.assert_tools_consistent(cfg)  # raises SystemExit on drift


def test_null_agent_settlement_shape():
    from null_agent import null_settlement
    s = null_settlement("D-0008")
    assert s["action"] == "approve" and s["amount"] == 12000.0
    assert set(s) >= {"case_id", "action", "amount", "justification", "evidence_ids"}
