"""The prompt's citation format must match what the graders accept.

The failure mode this guards: agent.yaml tells the agent one citation format,
fixtures_index enumerates valid evidence ids in another, and a correctly
reasoned settlement fails no_hallucinated_evidence purely on formatting. Every
format template and every concrete example in the prompt is checked against the
actual valid-id set, so the namespace cannot silently drift.
"""

import re

import yaml

from fixtures_index import FIXTURES_DIR, REPO_ROOT, valid_evidence_ids

AGENT_YAML = (REPO_ROOT / "agent" / "agent.yaml").read_text()
VALID = valid_evidence_ids()

CANONICAL_TEMPLATE = "contract:{retailer_id}:section-N.N"


def test_prompt_uses_only_the_canonical_contract_template():
    # The canonical placeholder form appears, and no drifted variants do.
    assert CANONICAL_TEMPLATE in AGENT_YAML
    assert "<retailer>" not in AGENT_YAML          # angle brackets vanish in renderers
    assert "contract::section" not in AGENT_YAML   # the missing-retailer variant


def test_every_concrete_citation_example_in_prompt_resolves():
    examples = set(re.findall(r"contract:[a-z][a-z-]*:section-\d+\.\d+", AGENT_YAML))
    assert examples, "prompt should carry at least one concrete contract example"
    for ex in examples:
        assert ex in VALID, f"prompt example {ex!r} does not resolve in fixtures"


def test_promo_and_history_examples_in_prompt_resolve():
    for ex in set(re.findall(r"PROMO-\d{4}-Q\d-\d{3}", AGENT_YAML)):
        assert ex in VALID, f"prompt promo example {ex!r} not in fixtures"
    for ex in set(re.findall(r"SH-\d{4}-Q\d-\d{3}", AGENT_YAML)):
        assert ex in VALID, f"prompt history example {ex!r} not in fixtures"


def test_template_grammar_matches_generator():
    # Rendering the template for every retailer/section yields exactly the ids
    # the generator produces — the two sides share one grammar.
    section_re = re.compile(r"^###\s+(\d+\.\d+)\b", re.MULTILINE)
    rendered = set()
    for contract in (FIXTURES_DIR / "contracts").glob("*.md"):
        for section in section_re.findall(contract.read_text()):
            rendered.add(CANONICAL_TEMPLATE
                         .replace("{retailer_id}", contract.stem)
                         .replace("N.N", section))
    contract_ids = {v for v in VALID if v.startswith("contract:")}
    assert rendered == contract_ids


def test_precedent_citations_resolve():
    # Precedent notes steer the agent's citations too — their ids must be real.
    import json
    precedents = json.loads((FIXTURES_DIR / "precedents.json").read_text())
    for note in precedents:
        for ex in set(re.findall(r"SH-\d{4}-Q\d-\d{3}", note["content"])):
            assert ex in VALID, f"precedent cites {ex!r} not in fixtures"


def test_agent_yaml_parses_with_expected_tool_count():
    cfg = yaml.safe_load(AGENT_YAML)
    assert len([t for t in cfg["tools"] if t["type"] == "custom"]) == 7
