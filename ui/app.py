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

st.set_page_config(page_title="Deductions Desk", page_icon="🧾", layout="wide")

st.title("Deductions Desk")
st.caption(
    "Trade-promotion deduction settlement with bounded autonomy — the agent "
    "**drafts** (never executes) and anything above $10,000 routes to a human."
)

tab_queue, tab_investigation, tab_dashboard, tab_live = st.tabs(
    ["📥 Case queue", "🔍 Investigation viewer", "📊 Results dashboard", "▶️ Live run"]
)

ACTION_BADGE = {"approve": "🟢 approve", "deny": "🔴 deny",
                "partial": "🟡 partial", "escalate": "⬆️ escalate"}


# ------------------------------------------------------------------ case queue
with tab_queue:
    st.subheader("Open deductions")
    st.caption("The worklist as a deductions analyst would see it — click into a "
               "case to see the claim exactly as the agent receives it.")
    cases = data.load_cases()
    st.dataframe(data.queue_rows(cases), use_container_width=True, hide_index=True)

    case_ids = [c["case_id"] for c in cases]
    picked = st.selectbox("Inspect a case", case_ids, key="queue_case")
    case = next(c for c in cases if c["case_id"] == picked)

    left, right = st.columns([1, 1])
    with left:
        st.metric("Deducted", f"${case['amount']:,.2f}")
        st.write(f"**Retailer:** {case['retailer_id']}  \n"
                 f"**Type:** {case['deduction_type']}  \n"
                 f"**Reference:** {case.get('claimed_reference', '—')}  \n"
                 f"**Date:** {case.get('deduction_date', '—')}")
        st.write("**Remittance text (as the retailer wrote it):**")
        st.code(case.get("remittance_text", ""), language=None)
    with right:
        st.write("**Claim detail:**")
        st.json(case.get("claim_detail", {}))
        attachments = case.get("attachments", [])
        if attachments:
            st.write("**Attachments:**")
            for a in attachments:
                st.write(f"- *{a.get('type')}*: {a.get('description')}")


# --------------------------------------------------------- investigation viewer
with tab_investigation:
    st.subheader("Replay an investigation")
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
                    st.markdown(f"**{i}. 💬 Agent:** {step['body']}")
                else:
                    flag = " ⚠️ error" if step.get("is_error") else ""
                    with st.expander(f"{i}. 🔧 {step['title']}{flag}"):
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
            st.divider()
            st.write("**Drafted settlement** *(draft only — nothing executes)*")
            badge = ACTION_BADGE.get(settlement.get("action", ""), settlement.get("action"))
            amount = settlement.get("amount")
            st.markdown(
                f"### {badge}"
                + (f" — ${amount:,.2f}" if isinstance(amount, (int, float)) else "")
            )
            st.write(settlement.get("justification", ""))
            st.write("**Cited evidence:** " + (", ".join(
                f"`{e}`" for e in settlement.get("evidence_ids", [])) or "—"))

            st.write("**Grader scorecard**")
            passed, checks = data.scorecard(settlement, case_id)
            for c in checks:
                if not c["applicable"]:
                    icon, note = "⚪", " (not applicable — skipped)"
                else:
                    icon, note = ("✅", "") if c["passed"] else ("❌", "")
                st.write(f"{icon} `{c['name']}`{note} — {c.get('detail', '')}")
            st.markdown(f"**Overall: {'✅ PASS' if passed else '❌ FAIL'}**")


# -------------------------------------------------------------------- dashboard
with tab_dashboard:
    st.subheader("Eval results")
    results = data.load_results()
    if results:
        st.caption(
            f"Last full eval — trials={len(results.get('trials', []))}, "
            f"judge={'on' if results.get('used_judge') else 'off'}, "
            f"memory={'on' if results.get('used_memory', True) else 'off'}"
        )
        rows = data.bucket_table(results["summary"])
        st.dataframe(rows, use_container_width=True, hide_index=True)
        chart_rows = {r["bucket"]: r["pass^k"] or 0 for r in rows if r["bucket"] != "OVERALL"}
        st.bar_chart(chart_rows, x_label="bucket", y_label="pass^k")
    else:
        st.info("No `runs/results.json` yet — run the eval (`make phase-e` / "
                "`make phase-f`) to populate this.")

    st.divider()
    st.write("**Offline demo: the null baseline** — grade an agent that blindly "
             "approves every claim. It must fail every non-approve bucket; that's "
             "the harness's known-bad calibration, visualized. Free, no API key.")
    if st.button("Generate + grade the null baseline"):
        trial = data.generate_null_baseline()
        st.session_state["null_trial"] = trial
    null_trial = st.session_state.get("null_trial")
    if null_trial:
        agg = data.grade_trial(null_trial)
        if agg:
            rows = data.bucket_table(agg)
            st.dataframe(rows, use_container_width=True, hide_index=True)
            chart_rows = {r["bucket"]: (r["pass^k"] if r["pass^k"] is not None else 0)
                          for r in rows if r["bucket"] != "OVERALL"}
            st.bar_chart(chart_rows, x_label="bucket", y_label="pass^k")
            st.caption("Reading: the approve bucket scores where blind approval "
                       "happens to be right; every judgement bucket fails. A real "
                       "agent must beat this floor everywhere.")


# --------------------------------------------------------------------- live run
with tab_live:
    st.subheader("Run the agent on a case (live)")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    st.write("Drives one Managed Agents session end to end: the agent "
             "investigates via its six tools (fulfilled locally from fixtures) "
             "and drafts a settlement. **Costs ~$0.15 and takes 1–3 minutes.**")
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
