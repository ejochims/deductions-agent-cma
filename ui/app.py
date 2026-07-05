"""Deductions Desk — local review UI.

A thin window onto the artifacts the harness produces: the case queue as an
analyst would see it, replayed investigations (transcript -> draft -> grader
scorecard), the eval dashboard, and an optional live-run panel. The UI shows
drafts and evidence only — there is no "execute settlement" anywhere, mirroring
the system's draft-never-execute design.

Run:  make ui        (streamlit run ui/app.py)
"""

from __future__ import annotations

import os

import data
import streamlit as st
import theme

st.set_page_config(page_title="Deductions Desk", page_icon="🧾", layout="wide")
st.markdown(theme.CSS, unsafe_allow_html=True)

cases = data.load_cases()
total_at_issue = sum(c["amount"] for c in cases)
over_threshold = sum(1 for c in cases if c["amount"] > 10_000)

st.title("Deductions Desk")
st.markdown(
    f"<div style='margin:-6px 0 4px 0;color:{theme.INK_2};'>"
    "Trade-promotion deduction settlement with bounded autonomy — the agent "
    "<b>drafts</b>, never executes; anything above &#36;10,000 routes to a human."
    "</div>",
    unsafe_allow_html=True,
)
st.markdown(
    theme.chip(f"{len(cases)} OPEN DEDUCTIONS", theme.INK_2, "#f0efec") + " " +
    theme.chip(f"{theme.money(total_at_issue, 0)} AT ISSUE", theme.ACCENT_DEEP, "#e7f0fb") + " " +
    theme.chip(f"{over_threshold} ABOVE &#36;10K THRESHOLD", "#3a2d85", "#edeafa") + " " +
    theme.chip("DRAFT-ONLY · HUMAN EXECUTES", "#006300", "#eaf6ea"),
    unsafe_allow_html=True,
)
st.write("")

RATE_COLUMNS = {
    "mean pass rate": st.column_config.NumberColumn("Mean pass rate", format="percent"),
    "pass^k": st.column_config.NumberColumn("pass^k", format="percent"),
    "bucket": st.column_config.TextColumn("Bucket"),
    "cases": st.column_config.NumberColumn("Cases"),
}

tab_queue, tab_investigation, tab_dashboard, tab_live = st.tabs(
    ["Case queue", "Investigation viewer", "Results dashboard", "Live run"]
)


# ------------------------------------------------------------------ case queue
with tab_queue:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Open deductions", len(cases))
    m2.metric("Dollars at issue", f"${total_at_issue:,.0f}")
    m3.metric("Largest claim", f"${max(c['amount'] for c in cases):,.0f}")
    m4.metric("Retailers", len({c["retailer_id"] for c in cases}))
    st.write("")

    st.dataframe(
        data.queue_rows(cases),
        use_container_width=True,
        hide_index=True,
        column_config={
            "case": st.column_config.TextColumn("Case"),
            "retailer": st.column_config.TextColumn("Retailer"),
            "amount": st.column_config.NumberColumn("Deducted", format="dollar"),
            "type": st.column_config.TextColumn("Type"),
            "date": st.column_config.TextColumn("Date"),
            "bucket": st.column_config.TextColumn("Bucket"),
        },
    )

    case_ids = [c["case_id"] for c in cases]
    picked = st.selectbox("Inspect a case", case_ids, key="queue_case")
    case = next(c for c in cases if c["case_id"] == picked)

    with st.container(border=True):
        head_l, head_r = st.columns([3, 1])
        head_l.markdown(f"#### {case['case_id']} · {case['retailer_id']}")
        head_r.markdown(
            f"<div style='text-align:right;font-size:1.35rem;font-weight:700;"
            f"color:{theme.INK};'>{theme.money(case['amount'])}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            theme.chip(case["deduction_type"].replace("_", " ").upper(),
                       theme.INK_2, "#f0efec") + " " +
            theme.chip(case.get("deduction_date", ""), theme.INK_2, "#f0efec") + " " +
            theme.chip(str(case.get("claimed_reference", "—")),
                       theme.ACCENT_DEEP, "#e7f0fb"),
            unsafe_allow_html=True,
        )
        left, right = st.columns([1, 1])
        with left:
            st.write("**Remittance text** *(as the retailer wrote it)*")
            st.code(case.get("remittance_text", ""), language=None)
            attachments = case.get("attachments", [])
            if attachments:
                st.write("**Attachments**")
                for a in attachments:
                    st.markdown(f"- *{a.get('type')}* — {a.get('description')}")
        with right:
            st.write("**Claim detail**")
            st.json(case.get("claim_detail", {}))


# --------------------------------------------------------- investigation viewer
with tab_investigation:
    runs = data.list_runs()
    if not runs:
        st.info(
            "No runs on disk yet. Run a case first (`make phase-d`), or generate "
            "the offline null baseline from the Results dashboard tab — live "
            "transcripts appear here automatically once runs exist."
        )
    else:
        c1, c2 = st.columns(2)
        trial = c1.selectbox("Trial", sorted(runs.keys()))
        case_id = c2.selectbox("Case", runs[trial])
        settlement, record = data.load_artifacts(trial, case_id)

        if record:
            st.write("**Investigation steps**")
            for i, step in enumerate(data.transcript_steps(record), 1):
                if step["kind"] == "agent_text":
                    st.markdown(f"**{i}.** 💬 {step['body']}")
                else:
                    flag = "  ⚠️ error" if step.get("is_error") else ""
                    with st.expander(f"{i} · 🔧 {step['title']}{flag}"):
                        st.write("Input:")
                        st.json(step["body"])
                        if "result" in step:
                            st.write("Result:")
                            st.json(step["result"])
            usage = record.get("usage") or {}
            if usage:
                st.caption(
                    f"tokens: {usage.get('input_tokens', 0):,} in / "
                    f"{usage.get('output_tokens', 0):,} out · "
                    f"wall clock: {record.get('timings', {}).get('wall_clock_s', '?')}s"
                )
        else:
            st.caption("(No transcript for this run — e.g. the null baseline "
                       "writes drafts only.)")

        if settlement:
            with st.container(border=True):
                amount = settlement.get("amount")
                amount_txt = (f"&nbsp;·&nbsp;<b>{theme.money(amount)}</b>"
                              if isinstance(amount, (int, float)) else "")
                st.markdown(
                    f"<div style='font-size:1.02rem;margin-bottom:6px;'>"
                    f"Drafted settlement {theme.action_chip(settlement.get('action', ''))}"
                    f"{amount_txt}"
                    f"<span style='color:{theme.MUTED};font-size:0.8rem;'>"
                    f"&nbsp;&nbsp;draft only — nothing executes</span></div>",
                    unsafe_allow_html=True,
                )
                st.markdown(theme.esc_md(settlement.get("justification", "")))
                evidence = settlement.get("evidence_ids", [])
                st.markdown(
                    "**Cited evidence:**&nbsp; " + (" ".join(
                        theme.chip(e, theme.ACCENT_DEEP, "#e7f0fb")
                        for e in evidence) or "—"),
                    unsafe_allow_html=True,
                )
                st.write("")
                passed, checks = data.scorecard(settlement, case_id)
                verdict = theme.chip("PASS", "#006300", "#eaf6ea") if passed \
                    else theme.chip("FAIL", "#a02020", "#fbeaea")
                st.markdown("**Grader scorecard** " + verdict, unsafe_allow_html=True)
                st.markdown(
                    " ".join(theme.check_chip(c["name"], c["passed"], c["applicable"])
                             for c in checks),
                    unsafe_allow_html=True,
                )
                fails = [c for c in checks if c["applicable"] and not c["passed"]]
                for c in fails:
                    st.caption(f"✕ {c['name']}: {c.get('detail', '')}")


# -------------------------------------------------------------------- dashboard
with tab_dashboard:
    results = data.load_results()
    if results:
        st.caption(
            f"Last full eval — trials={len(results.get('trials', []))} · "
            f"judge={'on' if results.get('used_judge') else 'off'} · "
            f"memory={'on' if results.get('used_memory', True) else 'off'}"
        )
        rows = data.bucket_table(results["summary"])
        overall = next(r for r in rows if r["bucket"] == "OVERALL")
        k1, k2, k3 = st.columns(3)
        k1.metric("Overall pass^k", f"{(overall['pass^k'] or 0):.0%}")
        k2.metric("Mean pass rate", f"{(overall['mean pass rate'] or 0):.0%}")
        k3.metric("Cases", overall["cases"])
        st.altair_chart(theme.bucket_bar(rows), use_container_width=True)
        st.dataframe(rows, use_container_width=True, hide_index=True,
                     column_config=RATE_COLUMNS)
    else:
        st.info("No `runs/results.json` yet — run the eval (`make phase-e` / "
                "`make phase-f`) to populate this.")

    st.divider()
    st.write("**Offline demo: the null baseline** — grade an agent that blindly "
             "approves every claim. It must fail every non-approve bucket; that's "
             "the harness's known-bad calibration, visualized. Free, no API key.")
    if st.button("Generate + grade the null baseline"):
        st.session_state["null_trial"] = data.generate_null_baseline()
    null_trial = st.session_state.get("null_trial")
    if null_trial:
        agg = data.grade_trial(null_trial)
        if agg:
            rows = data.bucket_table(agg)
            st.altair_chart(theme.bucket_bar(rows), use_container_width=True)
            st.dataframe(rows, use_container_width=True, hide_index=True,
                         column_config=RATE_COLUMNS)
            st.caption("Reading: the approve bucket scores where blind approval "
                       "happens to be right; every judgement bucket fails. A real "
                       "agent must beat this floor everywhere.")


# --------------------------------------------------------------------- live run
with tab_live:
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    st.write("Drives one Managed Agents session end to end: the agent "
             "investigates via its six tools (fulfilled locally from fixtures) "
             "and drafts a settlement. **Costs ~\\$0.15 and takes 1–3 minutes.**")
    if not has_key:
        st.warning("`ANTHROPIC_API_KEY` is not set — set it and restart the UI "
                   "to enable live runs. Everything else in this app works "
                   "without it.")
    case_id = st.selectbox("Case", data.all_case_ids(), key="live_case")
    trial = st.text_input("Trial label", value="ui")
    if st.button("Investigate live", disabled=not has_key, type="primary"):
        from run_agent import run_one_case
        with st.status(f"Session running for {case_id}… (watch the trace URL "
                       f"in the terminal)", expanded=False) as status:
            recorder = run_one_case(case_id, trial)
            if recorder.status == "ok":
                status.update(label="Session complete", state="complete")
            else:
                status.update(label=f"infra_error: {recorder.error}", state="error")
        if recorder.status == "ok":
            st.success(f"Done — open the **Investigation viewer** tab and select "
                       f"trial `{trial}`, case `{case_id}` to replay it.")
            settlement, _ = data.load_artifacts(trial, case_id)
            if settlement:
                st.json(settlement)
        else:
            st.error("The run was recorded as an infra_error (not an agent "
                     "failure). See the terminal output; it is safe to retry.")
    st.caption("There is deliberately no way to execute a settlement from this "
               "UI — drafts only, same as the system.")
