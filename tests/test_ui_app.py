"""Render the whole Streamlit app headlessly and assert it throws nothing.

AppTest executes ui/app.py end to end (all four tabs run on a script pass), so
this catches template/data errors without a browser. The live-run button is not
clicked, so no API call is made.
"""

import pytest

st = pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from fixtures_index import REPO_ROOT  # noqa: E402

APP = str(REPO_ROOT / "ui" / "app.py")


def test_app_renders_without_exceptions():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception, [str(e) for e in at.exception]
    assert at.title[0].value == "Deductions Desk"


def test_null_baseline_button_renders_dashboard(tmp_path, monkeypatch):
    # Point the shared data layer at a scratch runs/ dir, then click the button.
    import data as ui_data
    monkeypatch.setattr(ui_data, "RUNS_DIR", tmp_path)

    at = AppTest.from_file(APP, default_timeout=30).run()
    button = next(b for b in at.button if "null baseline" in b.label)
    at = button.click().run()
    assert not at.exception, [str(e) for e in at.exception]
    # The graded baseline table rendered (null fails the judgement buckets).
    assert (tmp_path / "null-baseline" / "D-0001" / "settlement.json").exists()
