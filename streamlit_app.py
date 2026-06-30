"""
streamlit_app.py
Streamlit front-end for the Praxis Advisory multi-agent engine. This is an
alternative to app.py (Flask) for deploying on Streamlit Community Cloud —
it reuses the exact same core/ orchestrator, skills, and guardrails, so the
agent behavior is identical regardless of which front-end you run.

Deploy: push this repo to GitHub, go to share.streamlit.io, point it at
this file. No server config needed.
"""
import streamlit as st
from core.orchestrator import Orchestrator
from core.skills_loader import list_skills, load_skill

st.set_page_config(
    page_title="Praxis Advisory — Claude Skills Multi-Agent Demo",
    page_icon="🧭",
    layout="wide",
)

EXAMPLES = {
    "Pricing & competition": (
        "Our mid-market SaaS company is losing customers to low-cost regional "
        "competitors. We are considering a 20% price cut but are worried about "
        "margin impact and whether it could trigger predatory-pricing scrutiny "
        "in two of our markets."
    ),
    "Layoffs & change management": (
        "We need to cut $4M in annual operating cost and are evaluating a 15% "
        "workforce reduction across two manufacturing sites. Leadership wants "
        "this done quietly without triggering union escalation or reputational "
        "damage."
    ),
    "Market entry": (
        "We are a US-based fintech evaluating entry into the UAE market within "
        "12 months. We don't yet know our competitive position there or what "
        "regulatory exposure we'd face."
    ),
}

STATUS_COLOR = {"PASS": "🟢", "WARN": "🟡", "BLOCKED": "🔴"}


def pretty(name: str) -> str:
    return name.replace("_", " ").title()


# ---------------- Sidebar: setup ----------------
with st.sidebar:
    st.markdown("## Praxis Advisory")
    st.caption("Multi-agent engagement engine · Powered by Claude Skills")

    api_key = st.text_input("Anthropic API key", type="password", help="Sent only with your request, never stored.")

    st.markdown("---")
    with st.expander("View agent skills"):
        for name in list_skills():
            with st.expander(pretty(name), expanded=False):
                st.code(load_skill(name), language="markdown")

# ---------------- Main: brief input ----------------
st.title("Start an engagement")

example_choice = st.radio(
    "Try an example brief, or write your own below:",
    ["Write my own"] + list(EXAMPLES.keys()),
    horizontal=True,
)

default_text = "" if example_choice == "Write my own" else EXAMPLES[example_choice]
brief = st.text_area("Client problem brief", value=default_text, height=140)

run_clicked = st.button("Run engagement ▸", type="primary")

# ---------------- Run pipeline ----------------
if run_clicked:
    if not api_key:
        st.error("Please enter your Anthropic API key in the sidebar.")
        st.stop()
    if not brief or len(brief.strip()) < 10:
        st.error("Please provide a more detailed client problem brief.")
        st.stop()

    with st.spinner("Routing brief to specialist agents... this can take 20-60 seconds."):
        try:
            orchestrator = Orchestrator(api_key)
            result = orchestrator.run(brief)
        except Exception as exc:
            st.error(f"Error: {exc}")
            st.stop()

    st.success("Engagement complete.")

    # ---- Pipeline overview ----
    st.header("Agent pipeline & decision trace")

    pipeline_steps = ["router"] + result["selected_skills"] + ["strategy_synthesis", "evaluation"]
    status_by_step = {
        t["step"]: t.get("guardrails", {}).get("status", "PASS")
        for t in result["trace"]
    }

    cols = st.columns(len(pipeline_steps))
    for col, step in zip(cols, pipeline_steps):
        status = status_by_step.get(f"agent:{step}", "PASS")
        with col:
            st.metric(pretty(step), STATUS_COLOR.get(status, "⚪") + " " + status)

    if result.get("router_decision", {}).get("reasoning"):
        st.caption(f"Router reasoning: {result['router_decision']['reasoning']}")

    # ---- Trace detail ----
    with st.expander("Full decision trace (prompts, raw outputs, guardrails, tokens)"):
        for i, t in enumerate(result["trace"], start=1):
            st.markdown(f"**{i}. {t['step']}** &nbsp;·&nbsp; {t.get('latency_seconds', '-')}s")
            st.text_area("Prompt sent", t.get("input_prompt", ""), height=100, key=f"prompt_{i}")
            st.text_area("Raw model output", t.get("output_raw", ""), height=100, key=f"output_{i}")
            if t.get("guardrails"):
                st.json(t["guardrails"])
            st.caption(f"Tokens — in: {t.get('input_tokens', '-')}, out: {t.get('output_tokens', '-')}")
            st.markdown("---")

    # ---- Final report ----
    st.header("Client-ready report")
    report = result.get("final_report") or {}
    evalr = result.get("evaluation") or {}

    if result.get("hard_stop_triggered") or report.get("decline_or_redirect"):
        st.error(
            f"**Engagement declined / redirected.**\n\n"
            f"{result.get('hard_stop_reason') or report.get('decline_reason') or 'A risk agent flagged a hard stop.'}"
        )

    st.subheader("Executive summary")
    st.write(report.get("executive_summary", "—"))

    st.subheader("Recommended actions")
    for action in report.get("recommended_actions", []):
        st.markdown(f"- {action.get('action', '')}  `{action.get('supported_by', '')}`")

    if report.get("assumptions_used"):
        st.subheader("Assumptions used")
        for a in report["assumptions_used"]:
            st.markdown(f"- {a}")

    # ---- Evaluation ----
    st.header("QA evaluation")
    if evalr.get("scores"):
        score_cols = st.columns(len(evalr["scores"]))
        for col, (k, v) in zip(score_cols, evalr["scores"].items()):
            with col:
                st.metric(pretty(k), f"{v}/5")

    verdict = evalr.get("verdict", "—")
    revised_tag = " (after 1 revision)" if result.get("revision_occurred") else ""
    if verdict == "PASS":
        st.success(f"Verdict: {verdict}{revised_tag}")
    elif verdict == "REVISE":
        st.warning(f"Verdict: {verdict}{revised_tag}")
    else:
        st.info(f"Verdict: {verdict}")

    if evalr.get("feedback"):
        st.subheader("Evaluator feedback")
        for f in evalr["feedback"]:
            st.markdown(f"- {f}")
else:
    st.info("Enter your API key in the sidebar, choose or write a brief, then click Run engagement.")
