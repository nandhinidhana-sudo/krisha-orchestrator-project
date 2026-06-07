# Orchestrator Agent System

Streamlit application for an orchestrator agent connected to three specialist agents:

- Document agent: upload, extract, chunk, retrieve, and summarize document evidence.
- Web search agent: use OpenAI web search when available, with a local fallback for development.
- Visualization agent: produce Mermaid diagrams and Vega-Lite business chart specs.

The app stores session state, messages, document metadata, chunks, artifacts, tool calls, and run logs in SQLite. Large documents are never pushed wholesale into the orchestrator context; only relevant chunks are retrieved per request.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## OpenAI API Key

Create a local `.env` file in the project root:

```text
OPENAI_API_KEY=sk-your-real-key-here
```

Do not commit `.env`; it is ignored by `.gitignore`. The app loads this value at startup through `python-dotenv`.

You can also set the variable only for the current PowerShell session:

```powershell
$env:OPENAI_API_KEY="sk-your-real-key-here"
streamlit run app.py
```

Set `OPENAI_API_KEY` to enable live OpenAI Agents SDK web search behavior. Without it, the app uses deterministic local fallbacks so the workflow can still be exercised.

## Test

```bash
pytest
```

## Architecture

```text
Streamlit UI
  -> App services
  -> SQLite + local file storage
  -> Orchestrator
      -> Document agent/tools
      -> Web search agent/tools
      -> Visualization agent/tools
```

## Storage

Runtime data is stored under `app_data/`:

- `app_data/app.db`: SQLite database.
- `app_data/uploads/`: original uploaded files.
- `app_data/extracted/`: extracted text files.

## Context Strategy

Each run uses:

- current user request
- latest compact conversation summary
- last few raw messages
- retrieved document chunks
- relevant generated artifacts

After every 10 user/assistant turns, older messages are summarized and the raw prompt context stays small.

## Agent Prompts

The prompt/instruction contracts live in `src/agents/prompts.py`:

- `ORCHESTRATOR_PROMPT`
- `DOCUMENT_AGENT_PROMPT`
- `WEB_SEARCH_AGENT_PROMPT`
- `VISUALIZATION_AGENT_PROMPT`
- `RESPONSE_COMPOSER_PROMPT`

The orchestrator routes requests according to these rules:

- Document QA or uploaded-file analysis uses the Document Agent.
- Latest/current/market/competitor/news requests use the Web Search Agent.
- Workflow, process, architecture, or system diagrams create Mermaid artifacts.
- KPI, metric, revenue, sales, cost, trend, dashboard, or numeric business charts create Vega-Lite artifacts.

Mermaid and Vega-Lite artifacts are rendered in the Artifacts tab.
