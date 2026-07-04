"""Fixture-index helpers: buckets, evidence ids, resolvers, loaders."""
import fixtures_index as fx


def test_18_cases_and_buckets():
    assert len(fx.all_case_ids()) == 18
    assert fx.case_bucket("D-0001") == "approve"
    assert fx.case_bucket("D-0008") == "deny"
    assert fx.case_bucket("D-0010") == "partial"
    assert fx.case_bucket("D-0014") == "escalate"
    assert fx.case_bucket("D-0016") == "ambiguous"
    assert fx.case_bucket("D-0017") == "memory"


def test_valid_evidence_ids_cover_namespaces():
    v = fx.valid_evidence_ids()
    assert "PROMO-2026-Q1-008" in v
    assert "SH-2025-Q4-011" in v
    assert "contract:valumax:section-5.2" in v
    assert "contract:harvest-co:section-3.4" in v
    assert "PROMO-9999" not in v


def test_every_reference_evidence_id_resolves():
    valid = fx.valid_evidence_ids()
    for case_id in fx.all_case_ids():
        ref = fx.load_reference_solution(case_id)
        for e in ref["evidence_ids"]:
            assert e in valid, f"{case_id} cites {e!r} which is not in the fixtures"


def test_labels_and_refs_align_on_action():
    for case_id in fx.all_case_ids():
        lbl = fx.load_label(case_id)
        ref = fx.load_reference_solution(case_id)
        assert ref["action"] == lbl["expected_action"], case_id


def test_resolve_evidence_renders_and_flags_missing():
    assert "per_unit_scanned" in fx.resolve_evidence("PROMO-2026-Q1-001")
    assert "SLOT-VM-2025-09" in fx.resolve_evidence("SH-2025-Q4-011")
    assert "MDF" in fx.resolve_evidence("contract:valumax:section-5.2")
    assert "not found" in fx.resolve_evidence("PROMO-9999")
