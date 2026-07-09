"""Drift guard: the deck's hardcoded figures must match the committed eval data.

docs/presentation.html is a static artifact — nothing regenerates it when the
eval re-runs. These tests parse the numbers out of the HTML and compare them to
the curated results (and the curated D-0009 settlement), so a re-run that
changes the data fails the free test phase instead of silently staling the deck.
"""
import json
import re

from fixtures_index import REPO_ROOT

DECK = (REPO_ROOT / "docs" / "presentation.html").read_text()
POSTFIX = json.loads(
    (REPO_ROOT / "runs" / "curated" / "postfix_results.json").read_text()
)
BASELINE = json.loads(
    (REPO_ROOT / "runs" / "curated" / "baseline_results.json").read_text()
)


def pct(x: float) -> int:
    return round(x * 100)


BAR_ROW = re.compile(
    r'<div class="bar-lab">(?P<bucket>\w+)<span class="bar-n">n=(?P<n>\d+)</span></div>\s*'
    r'<div class="bar-track" title="(?P=bucket) · (?P=n) cases · mean (?P<mean_t>\d+)%">'
    r'<div class="bar-fill" data-pct="(?P<pass_k>\d+)">.*?'
    r'<span class="bar-mean" data-mean="(?P<mean>\d+)" style="left:(?P<mean_left>\d+)%"',
    re.S,
)


def test_results_chart_matches_postfix_by_bucket():
    rows = {m["bucket"]: m for m in BAR_ROW.finditer(DECK)}
    by_bucket = POSTFIX["summary"]["by_bucket"]
    assert set(rows) == set(by_bucket), "deck buckets != results buckets"
    for bucket, stats in by_bucket.items():
        m = rows[bucket]
        assert int(m["n"]) == stats["n_cases"], f"{bucket}: n"
        assert int(m["pass_k"]) == pct(stats["pass_k"]), f"{bucket}: pass^3 bar"
        for field in ("mean_t", "mean", "mean_left"):
            assert int(m[field]) == pct(stats["mean_pass_rate"]), f"{bucket}: {field}"


def test_title_kpis_and_overall_strip_match_postfix():
    overall = POSTFIX["summary"]["overall"]
    kpi = lambda label: re.search(  # noqa: E731
        label + r'</div>\s*<div class="k-val num">(\d+)', DECK
    )
    assert int(kpi(r"Overall pass\^3")[1]) == pct(overall["pass_k"])
    assert int(kpi(r"Mean pass rate")[1]) == pct(overall["mean_pass_rate"])

    strip = re.findall(r'<span class="ov-n num">(\d+)%?</span><span class="ov-l">', DECK)
    assert [int(s) for s in strip] == [
        pct(overall["pass_k"]),
        pct(overall["mean_pass_rate"]),
        overall["n_cases"],
    ]


def test_memory_slide_before_after_matches_both_runs():
    pairs = {
        m[1]: (int(m[2]), int(m[3]))
        for m in re.finditer(
            r'aria-label="([\w ]+?)(?: bucket)? pass\^3: before (\d+)%, after (\d+)%"',
            DECK,
        )
    }
    base, post = BASELINE["summary"], POSTFIX["summary"]
    assert pairs["Memory"] == (
        pct(base["by_bucket"]["memory"]["pass_k"]),
        pct(post["by_bucket"]["memory"]["pass_k"]),
    )
    assert pairs["Ambiguous"] == (
        pct(base["by_bucket"]["ambiguous"]["pass_k"]),
        pct(post["by_bucket"]["ambiguous"]["pass_k"]),
    )
    assert pairs["Overall"] == (
        pct(base["overall"]["pass_k"]),
        pct(post["overall"]["pass_k"]),
    )


def test_trace_slide_matches_curated_d0009_settlement():
    settlement = json.loads(
        (REPO_ROOT / "runs" / "curated" / "t0" / "D-0009" / "settlement.json").read_text()
    )
    gate = DECK[DECK.index('class="step gate"'):]
    gate = gate[: gate.index("</li>")]
    assert settlement["action"] == "partial"
    assert f'class="chip {settlement["action"]}"' in gate
    assert f"${settlement['amount']:,.2f}" in gate
    for evidence_id in settlement["evidence_ids"]:
        assert evidence_id in gate, f"missing evidence chip {evidence_id}"
