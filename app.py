import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.agents.orchestrator import Orchestrator
from src.agents.prompts import (
    DOCUMENT_AGENT_PROMPT,
    ORCHESTRATOR_PROMPT,
    RESPONSE_COMPOSER_PROMPT,
    VISUALIZATION_AGENT_PROMPT,
    WEB_SEARCH_AGENT_PROMPT,
)
from src.config import AppConfig
from src.documents.pipeline import DocumentPipeline
from src.storage.database import Database


st.set_page_config(page_title="Agent Orchestrator", layout="wide")


@st.cache_resource
def bootstrap() -> tuple[AppConfig, Database, DocumentPipeline, Orchestrator]:
    config = AppConfig()
    config.ensure_directories()
    db = Database(config.database_path)
    db.initialize()
    docs = DocumentPipeline(config, db)
    orchestrator = Orchestrator(config, db, docs)
    return config, db, docs, orchestrator


config, db, docs, orchestrator = bootstrap()


def render_mermaid(source: str) -> None:
    components.html(
        f"""
        <div class="mermaid">{source}</div>
        <script type="module">
          import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
          mermaid.initialize({{ startOnLoad: true, securityLevel: 'loose' }});
        </script>
        """,
        height=420,
        scrolling=True,
    )

if "session_id" not in st.session_state:
    st.session_state.session_id = db.create_session("New analysis session")
if "processed_uploads" not in st.session_state:
    st.session_state.processed_uploads = set()

st.title("Agent Orchestrator")

with st.sidebar:
    st.header("Session")
    sessions = db.list_sessions()
    session_options = {f"{s['title']} ({s['id'][:8]})": s["id"] for s in sessions}
    selected_label = st.selectbox(
        "Active session",
        options=list(session_options.keys()),
        index=list(session_options.values()).index(st.session_state.session_id)
        if st.session_state.session_id in session_options.values()
        else 0,
    )
    st.session_state.session_id = session_options[selected_label]

    if st.button("New session", use_container_width=True):
        st.session_state.session_id = db.create_session("New analysis session")
        st.rerun()

    st.header("Documents")
    uploaded_files = st.file_uploader(
        "Upload PDF, DOCX, TXT, CSV, or XLSX",
        type=["pdf", "docx", "txt", "csv", "xlsx"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        for uploaded_file in uploaded_files:
            upload_key = f"{st.session_state.session_id}:{uploaded_file.name}:{uploaded_file.getbuffer().nbytes}"
            if upload_key in st.session_state.processed_uploads:
                continue
            result = docs.ingest_uploaded_file(st.session_state.session_id, uploaded_file)
            st.session_state.processed_uploads.add(upload_key)
            st.success(f"Indexed {result.filename}: {result.chunk_count} chunks")

    st.header("Controls")
    st.caption("Conversation is compressed every 10 turns, while the latest messages stay raw.")
    if st.button("Compact memory now", use_container_width=True):
        summary = orchestrator.compact_memory(st.session_state.session_id, force=True)
        st.info(summary or "No memory compaction needed yet.")


tab_chat, tab_artifacts, tab_monitoring = st.tabs(["Chat", "Artifacts", "Monitoring"])

with tab_chat:
    messages = db.list_messages(st.session_state.session_id)
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Ask the orchestrator to analyze documents, search the web, or create visuals")
    if prompt:
        db.add_message(st.session_state.session_id, "user", prompt)
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Orchestrator is planning and calling specialist agents..."):
                response = orchestrator.run(st.session_state.session_id, prompt)
            st.markdown(response.answer)

        db.add_message(st.session_state.session_id, "assistant", response.answer)
        st.rerun()

with tab_artifacts:
    artifacts = db.list_artifacts(st.session_state.session_id)
    if not artifacts:
        st.info("Generated Mermaid and Vega-Lite artifacts will appear here.")
    for artifact in artifacts:
        st.subheader(f"{artifact['kind']} - {artifact['created_at']}")
        if artifact["kind"] == "vega_lite":
            st.vega_lite_chart(artifact["content"], use_container_width=True)
            st.json(artifact["content"])
        elif artifact["kind"] == "mermaid":
            render_mermaid(artifact["content"])
            st.code(artifact["content"], language="mermaid")
        else:
            st.write(artifact["content"])

with tab_monitoring:
    st.subheader("Agent Prompts")
    prompt_tabs = st.tabs(["Orchestrator", "Document QA", "Web Search", "Visualization", "Response"])
    with prompt_tabs[0]:
        st.code(ORCHESTRATOR_PROMPT.strip())
    with prompt_tabs[1]:
        st.code(DOCUMENT_AGENT_PROMPT.strip())
    with prompt_tabs[2]:
        st.code(WEB_SEARCH_AGENT_PROMPT.strip())
    with prompt_tabs[3]:
        st.code(VISUALIZATION_AGENT_PROMPT.strip())
    with prompt_tabs[4]:
        st.code(RESPONSE_COMPOSER_PROMPT.strip())

    st.subheader("Agent Runs")
    runs = pd.DataFrame(db.list_agent_runs(st.session_state.session_id))
    st.dataframe(runs, use_container_width=True, hide_index=True)

    st.subheader("Tool Calls")
    tool_calls = pd.DataFrame(db.list_tool_calls(st.session_state.session_id))
    st.dataframe(tool_calls, use_container_width=True, hide_index=True)

    st.subheader("Documents")
    documents = pd.DataFrame(db.list_documents(st.session_state.session_id))
    st.dataframe(documents, use_container_width=True, hide_index=True)

    st.subheader("Token Estimates")
    token_rows = db.token_summary(st.session_state.session_id)
    if token_rows:
        chart = (
            alt.Chart(pd.DataFrame(token_rows))
            .mark_bar()
            .encode(x="source:N", y="tokens:Q", color="source:N")
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Token estimates appear after messages and document chunks are stored.")
