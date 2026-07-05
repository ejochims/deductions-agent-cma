"""The UI's data layer — pure functions, no Streamlit needed."""

import json

import data as ui_data


def test_load_cases_and_queue_rows():
    cases = ui_data.load_cases()
    assert len(cases) == 18
    rows = ui_data.queue_rows(cases)
    assert {r["case"] for r in rows} == set(ui_data.all_case_ids())
    d9 = next(r for r in rows if r["case"] == "D-0009")
    assert d9["amount"] == 8899.80 and d9["bucket"] == "partial"


def test_scorecard_reference_passes():
    from fixtures_index import load_reference_solution
    ref = load_reference_solution("D-0009")
    passed, checks = ui_data.scorecard(ref, "D-0009")
    assert passed and len(checks) == 5


def test_list_runs_and_null_baseline_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_data, "RUNS_DIR", tmp_path)
    assert ui_data.list_runs() == {}
    assert ui_data.grade_trial("nope") == {}

    # Generate the offline null baseline and grade it through the real pipeline.
    from null_agent import write_null_run
    write_null_run(tmp_path, trial="null-baseline")
    runs = ui_data.list_runs()
    assert "null-baseline" in runs and len(runs["null-baseline"]) == 18

    agg = ui_data.grade_trial("null-baseline")
    rows = ui_data.bucket_table(agg)
    by_bucket = {r["bucket"]: r for r in rows}
    # The always-approve baseline must fail every judgement bucket.
    for bucket in ("deny", "partial", "escalate", "ambiguous", "memory"):
        assert by_bucket[bucket]["pass^k"] == 0, bucket
    assert by_bucket["OVERALL"]["cases"] == 18


def test_transcript_steps_shapes_a_record():
    record = {
        "transcript": [
            {"type": "agent.message",
             "content": [{"type": "text", "text": "Investigating the claim."}]},
            {"type": "agent.custom_tool_use", "name": "get_deduction",
             "input": {"case_id": "D-0001"}},
            {"type": "span.model_request_end"},  # unknown-to-viewer: skipped
        ],
        "tool_calls": [
            {"name": "get_deduction", "input": {"case_id": "D-0001"},
             "result": {"amount": 6800.0}, "is_error": False},
        ],
    }
    steps = ui_data.transcript_steps(record)
    kinds = [s["kind"] for s in steps]
    assert kinds == ["agent_text", "tool_call"]
    assert steps[1]["result"] == {"amount": 6800.0}
    assert steps[1]["is_error"] is False


def test_transcript_steps_falls_back_to_tool_log():
    record = {"transcript": [{"type": "weird.event"}],
              "tool_calls": [{"name": "get_pos_data", "input": {"promo_id": "X"},
                              "result": {"found": False}, "is_error": False}]}
    steps = ui_data.transcript_steps(record)
    assert len(steps) == 1 and steps[0]["title"] == "Tool call: get_pos_data"


def test_load_artifacts_missing_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_data, "RUNS_DIR", tmp_path)
    settlement, record = ui_data.load_artifacts("t0", "D-0001")
    assert settlement is None and record is None
    # And present when written:
    d = tmp_path / "t0" / "D-0001"
    d.mkdir(parents=True)
    (d / "settlement.json").write_text(json.dumps({"case_id": "D-0001"}))
    settlement, record = ui_data.load_artifacts("t0", "D-0001")
    assert settlement == {"case_id": "D-0001"} and record is None
