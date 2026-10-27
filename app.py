#!/usr/bin/env python3
from __future__ import annotations
import os
import streamlit as st
from demo_common import load_environment, get_model_name, create_openai_client
from triage_workflow import TriageResult, create_triage_issue
from persistent_memory import load_memory, format_memory_for_prompt, update_convention

DEFAULT_ISSUE = """Payment button returns HTTP 500 for all Visa cards since 14:30.
Please triage this issue and identify the responsible team."""

st.set_page_config(
    page_title="Issue Triage",
    page_icon="IT",
    layout="wide",
    initial_sidebar_state="expanded",
)

def render_result(result: TriageResult) -> None:
    triage = result.triage
    st.subheader("Triage Result")
    status_column, severity_column = st.columns(2)
    status_column.metric("Status", triage.status)
    severity_column.metric("Severity", triage.severity or "N/A")

    component_column, urgent_column = st.columns(2)
    component_column.metric("Component", triage.component or "N/A")
    urgent_column.metric("Urgent", "Yes" if triage.needs_urgent_response else "No")

    st.write("**Reason**")
    st.info(triage.reason)
    if result.tool_traces:
        owner = result.tool_traces[0].result.get("owner")
        if owner:
            st.write("**Responsible Team**")
            st.info(owner)

    if result.tool_traces:
        with st.expander("Trace function calling", expanded=True):
            for index, trace in enumerate(
                result.tool_traces,
                start=1,
            ):
                st.markdown(f"**{index}. Model requests tool** `{trace.name}`")
                st.json({
                    "id": trace.call_id,
                    "arguments": trace.arguments,
                })
                st.markdown("**Application validates and executes**")
                st.json(trace.result)

def main() -> None:
    load_environment()
    with st.sidebar:
        st.header("Runtime")
        st.write("OpenAI-compatible API")

        st.code(
            os.getenv("OPENAI_BASE_URL")
            or "URL not configured",
            language=None,
        )

        st.write("Model")
        st.code(
            os.getenv("OPENAI_MODEL")
            or "Model not configured",
            language=None,
        )

        st.divider()
        st.subheader("Persistent Memory")
        current_memory = load_memory()
        if current_memory.get("conventions"):
            for key, value in sorted(current_memory["conventions"].items()):
                st.caption(key)
                st.write(value)
        else:
            st.caption("No conventions saved yet.")

        with st.form("update-project-memory"):
            memory_key = st.text_input(
                "Convention key",
                placeholder="severity_policy",
                help="A short name for a project rule you want future sessions to remember.",
            )
            memory_value = st.text_area(
                "Convention value",
                placeholder="Use P1 when a payment outage affects all users.",
                height=100,
            )
            save_memory_clicked = st.form_submit_button("Save / Update Convention")
        if save_memory_clicked:
            try:
                update_convention(memory_key, memory_value)
                st.success("Convention saved to disk. It will be loaded on future runs.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    st.title("Issue Triage")
    st.write(
            "LLM-powered software issue triage "
            "with application-controlled function calling."
        )

    with st.form("issue-triage-form"):
        issue = st.text_area(
            "Describe issue",
            value=DEFAULT_ISSUE,
            height=220,
            help=(
                "Describe the symptom, impact scope, " ""
                "and start time if available."
            ),
        )

        submitted = st.form_submit_button(
            "Triage Issue",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    if not issue.strip():
        st.error(
            "Enter an issue description before running triage."
        )
        return

    try:
        with st.spinner(
            "Calling the model and processing the tool request…"
        ):
            memory = load_memory()
            memory_context = format_memory_for_prompt(memory)
            result = create_triage_issue(
                create_openai_client(),
                get_model_name(),
                issue.strip(),
                memory_context=memory_context
            )
    except Exception as error:
        st.error(
            f"Triage failed: {error}"
        )
        st.info(
            "Check OPENAI_BASE_URL, OPENAI_MODEL, and model access permissions in .env."
        )
        return
    st.success("Triage completed successfully.")
    render_result(result)

if __name__ == "__main__":
    main()