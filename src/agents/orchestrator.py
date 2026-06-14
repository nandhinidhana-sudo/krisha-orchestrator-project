import time
import json
import os
from concurrent.futures import ThreadPoolExecutor

from src.agents.document_agent import DocumentAgent
from src.agents.prompts import ORCHESTRATOR_PROMPT, PLANNER_PROMPT, RESPONSE_COMPOSER_PROMPT
from src.agents.schemas import AgentResponse, RoutePlan
from src.agents.visualization_agent import VisualizationAgent
from src.agents.web_agent import WebSearchAgent
from src.config import AppConfig
from src.documents.pipeline import DocumentPipeline
from src.storage.database import Database


class Orchestrator:
    instructions = ORCHESTRATOR_PROMPT
    response_instructions = RESPONSE_COMPOSER_PROMPT

    def __init__(self, config: AppConfig, db: Database, documents: DocumentPipeline):
        self.config = config
        self.db = db
        self.document_agent = DocumentAgent(db, documents)
        self.web_agent = WebSearchAgent(db)
        self.visualization_agent = VisualizationAgent(db)

    def run(self, session_id: str, user_request: str) -> AgentResponse:
        started = time.perf_counter()
        run_id = self.db.start_run(session_id, user_request)
        self.db.add_step(run_id, session_id, "Orchestrator Agent", "Started routing user request.")

        try:
            self.compact_memory(session_id)
            plan = self.plan(user_request)
            self.db.add_tool_call(
                run_id,
                session_id,
                "route_request",
                {"user_request": user_request, "instructions": self.instructions[:500]},
                plan.model_dump_json(),
            )

            evidence_chunks = []
            evidence_texts = []
            web_summary = ""
            artifact_ids = []
            used_agents = ["Orchestrator Agent"]

            for group in plan.execution_groups or [plan.required_agents]:
                results = self._run_agent_group(group, session_id, run_id, user_request)
                if "document_qa" in results:
                    evidence_chunks = results["document_qa"]
                    evidence_texts = [chunk.content for chunk in evidence_chunks]
                    used_agents.append(self.document_agent.name)
                if "web_search" in results:
                    web_summary = results["web_search"]
                    used_agents.append(self.web_agent.name)
                if "visualization" in group:
                    used_agents.append(self.visualization_agent.name)
                    if "mermaid" in plan.visualization_types:
                        self.visualization_agent.create_mermaid(session_id, run_id, user_request, evidence_texts)
                        artifact_ids.append("mermaid")
                    if "vega_lite" in plan.visualization_types:
                        self.visualization_agent.create_vega_lite(session_id, run_id, user_request, evidence_texts)
                        artifact_ids.append("vega_lite")

            document_summary = (
                self.document_agent.summarize_evidence(evidence_chunks)
                if plan.needs_documents
                else "Document QA was not required for this request."
            )

            answer = self.compose_answer(user_request, document_summary, web_summary, artifact_ids)
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.db.complete_run(run_id, answer, duration_ms)
            return AgentResponse(answer=answer, used_agents=used_agents, artifacts=artifact_ids)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.db.complete_run(run_id, f"Run failed: {exc}", duration_ms, status="failed")
            raise

    def plan(self, user_request: str) -> RoutePlan:
        if os.getenv("OPENAI_API_KEY"):
            llm_plan = self._plan_with_llm(user_request)
            if llm_plan:
                return llm_plan
        return self._fallback_plan(user_request)

    def _plan_with_llm(self, user_request: str) -> RoutePlan | None:
        try:
            from openai import OpenAI

            client = OpenAI()
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_ORCHESTRATOR_MODEL", "gpt-4.1-mini"),
                messages=[
                    {"role": "system", "content": PLANNER_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Plan the required specialist agents for this request.\n\n"
                            f"User request: {user_request}"
                        ),
                    },
                ],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            plan = RoutePlan.model_validate(data)
            return self._normalize_plan(plan)
        except Exception:
            return None

    def _fallback_plan(self, user_request: str) -> RoutePlan:
        lower = user_request.lower()
        document_terms = [
            "document",
            "uploaded",
            "upload",
            "file",
            "pdf",
            "docx",
            "report",
            "spreadsheet",
            "csv",
            "xlsx",
            "deck",
            "attachment",
            "from the doc",
            "from the file",
            "in the report",
        ]
        freshness_terms = [
            "latest",
            "current",
            "recent",
            "today",
            "now",
            "live",
            "real-time",
            "up to date",
            "this week",
            "this month",
            "2026",
        ]
        external_terms = [
            "web",
            "internet",
            "search",
            "google",
            "source",
            "sources",
            "market",
            "news",
            "competitor",
            "weather",
            "forecast",
            "stock",
            "price",
            "exchange rate",
        ]
        needs_documents = any(term in lower for term in document_terms)
        needs_web = any(term in lower for term in freshness_terms + external_terms)
        process_terms = [
            "diagram",
            "mermaid",
            "flow",
            "workflow",
            "process",
            "architecture",
            "system",
            "journey",
            "decision tree",
            "org chart",
            "sequence",
        ]
        kpi_terms = [
            "chart",
            "vega",
            "kpi",
            "metric",
            "revenue",
            "sales",
            "cost",
            "profit",
            "trend",
            "bar",
            "line",
            "graph",
            "dashboard",
            "funnel",
            "comparison",
        ]
        needs_visual = any(term in lower for term in process_terms + kpi_terms)
        visualization_types = []
        if needs_visual:
            if any(term in lower for term in process_terms):
                visualization_types.append("mermaid")
            if any(term in lower for term in kpi_terms):
                visualization_types.append("vega_lite")
            if not visualization_types:
                visualization_types = ["mermaid", "vega_lite"]

        required_agents = []
        if needs_documents:
            required_agents.append("document_qa")
        if needs_web:
            required_agents.append("web_search")
        if needs_visual:
            required_agents.append("visualization")

        execution_groups = []
        evidence_group = [agent for agent in required_agents if agent in {"document_qa", "web_search"}]
        if evidence_group:
            execution_groups.append(evidence_group)
        if "visualization" in required_agents:
            execution_groups.append(["visualization"])

        return RoutePlan(
            needs_documents=needs_documents,
            needs_web_search=needs_web,
            needs_visualization=needs_visual,
            visualization_types=visualization_types,
            required_agents=required_agents,
            execution_groups=execution_groups,
            rationale="Fallback heuristic plan used because LLM planning was unavailable.",
        )

    def _normalize_plan(self, plan: RoutePlan) -> RoutePlan:
        required_agents = list(dict.fromkeys(plan.required_agents))
        if plan.needs_documents and "document_qa" not in required_agents:
            required_agents.append("document_qa")
        if plan.needs_web_search and "web_search" not in required_agents:
            required_agents.append("web_search")
        if plan.needs_visualization and "visualization" not in required_agents:
            required_agents.append("visualization")

        if not plan.execution_groups:
            evidence_group = [agent for agent in required_agents if agent in {"document_qa", "web_search"}]
            execution_groups = []
            if evidence_group:
                execution_groups.append(evidence_group)
            if "visualization" in required_agents:
                execution_groups.append(["visualization"])
        else:
            execution_groups = [
                [agent for agent in group if agent in required_agents]
                for group in plan.execution_groups
            ]
