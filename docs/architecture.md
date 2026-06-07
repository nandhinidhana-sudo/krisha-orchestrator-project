# Agent Orchestrator Architecture

## Product Shape

The application is a Streamlit product shell backed by an OpenAI Agents SDK-style orchestration layer.

```text
Streamlit
  -> Session and upload UI
  -> Orchestrator
      -> Document Agent
      -> Web Search Agent
      -> Visualization Agent
  -> SQLite monitoring and artifact views
```

## Agents

### Orchestrator Agent

Responsibilities:

- Classify each user request.
- Decide whether document retrieval, web search, visualization, or all three are required.
- Keep context small.
- Compose the final response.
- Trigger conversation compaction.
- Follow `ORCHESTRATOR_PROMPT` in `src/agents/prompts.py`.

### Document Agent

Responsibilities:

- Retrieve relevant chunks from uploaded documents.
- Summarize retrieved evidence.
- Avoid sending complete documents into the orchestrator prompt.
- Follow `DOCUMENT_AGENT_PROMPT` in `src/agents/prompts.py`.

Tools:

- `search_uploaded_documents`
- `summarize_document_evidence`

### Web Search Agent

Responsibilities:

- Use OpenAI Agents SDK `WebSearchTool` when `OPENAI_API_KEY` is configured.
- Return a development fallback when live web search is unavailable.
- Log all search calls.
- Follow `WEB_SEARCH_AGENT_PROMPT` in `src/agents/prompts.py`.

Tools:

- `web_search`

### Visualization Agent

Responsibilities:

- Generate Mermaid diagrams.
- Generate Vega-Lite chart specs.
- Store artifacts for rendering and later inspection.
- Follow `VISUALIZATION_AGENT_PROMPT` in `src/agents/prompts.py`.

Tools:

- `generate_mermaid`
- `generate_vega_lite`

Visualization routing:

- Mermaid: workflows, process diagrams, architecture, systems, decision trees, journeys, and sequence-style views.
- Vega-Lite: KPIs, numeric business charts, revenue, sales, cost, trend, comparison, dashboard, and metric views.

## Storage

SQLite stores:

- `sessions`
- `messages`
- `conversation_summaries`
- `documents`
- `document_chunks`
- `agent_runs`
- `agent_steps`
- `tool_calls`
- `artifacts`
- `citations`
- `user_preferences`
- `errors`

Files are stored under `app_data/uploads`, and extracted text is stored under `app_data/extracted`.

## Context Management

The orchestrator receives:

- the current user request
- recent raw messages
- latest compact conversation summary
- relevant document chunks
- generated artifacts when relevant

It does not receive:

- entire uploaded documents
- full historical conversation logs
- unrelated artifacts

Every 10 unsummarized turns, older messages are compressed into `conversation_summaries`; the most recent raw messages remain available for conversational continuity.

## Production Upgrade Path

Recommended next upgrades:

- Replace TF-IDF retrieval with OpenAI embeddings plus pgvector or Chroma.
- Add authenticated users and per-user document isolation.
- Add chart validators for Mermaid and Vega-Lite.
- Add real citations for web search and document chunks.
- Add cost/token accounting from model usage metadata.
- Add FastAPI endpoints if another frontend or external integration needs API access.
