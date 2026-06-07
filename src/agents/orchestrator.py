import time

from src.agents.document_agent import DocumentAgent
from src.agents.prompts import ORCHESTRATOR_PROMPT, RESPONSE_COMPOSER_PROMPT
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
            used_agents = ["Orchestrator Agent"]

            if plan.needs_documents:
                evidence_chunks = self.document_agent.retrieve_evidence(session_id, run_id, user_request)
                evidence_texts = [chunk.content for chunk in evidence_chunks]
                used_agents.append(self.document_agent.name)

            document_summary = self.document_agent.summarize_evidence(evidence_chunks)

            web_summary = ""
            if plan.needs_web_search:
                web_summary = self.web_agent.search(session_id, run_id, user_request)
                used_agents.append(self.web_agent.name)

            artifact_ids = []
            if plan.needs_visualization:
                used_agents.append(self.visualization_agent.name)
                if "mermaid" in plan.visualization_types:
                    self.visualization_agent.create_mermaid(session_id, run_id, user_request, evidence_texts)
                    artifact_ids.append("mermaid")
                if "vega_lite" in plan.visualization_types:
                    self.visualization_agent.create_vega_lite(session_id, run_id, user_request, evidence_texts)
                    artifact_ids.append("vega_lite")

            answer = self.compose_answer(user_request, document_summary, web_summary, artifact_ids)
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.db.complete_run(run_id, answer, duration_ms)
            return AgentResponse(answer=answer, used_agents=used_agents, artifacts=artifact_ids)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.db.complete_run(run_id, f"Run failed: {exc}", duration_ms, status="failed")
            raise

    def plan(self, user_request: str) -> RoutePlan:
        lower = user_request.lower()
        needs_web = any(
            word in lower
            for word in ["latest", "current", "recent", "web", "internet", "market", "news", "competitor"]
        )
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

        return RoutePlan(
            needs_documents=True,
            needs_web_search=needs_web,
            needs_visualization=needs_visual,
            visualization_types=visualization_types,
        )

    def compose_answer(
        self,
        user_request: str,
        document_summary: str,
        web_summary: str,
        artifact_ids: list[str],
    ) -> str:
        parts = [
            "I routed this through the orchestrator and kept the prompt context compact.",
            "",
            "**Document evidence**",
            document_summary,
        ]
        if web_summary:
            parts.extend(["", "**Web research**", web_summary])
        if artifact_ids:
            labels = ", ".join(artifact_ids)
            parts.extend(["", "**Artifacts**", f"Created: {labels}. Open the Artifacts tab to render or inspect them."])
        parts.extend(
            [
                "",
                "**Context policy**",
                "The orchestrator used retrieved chunks and summary memory, not the full uploaded document text.",
            ]
        )
        return "\n".join(parts)

    def compact_memory(self, session_id: str, force: bool = False) -> str:
        unsummarized = self.db.list_messages(session_id, include_summarized=False)
        if len(unsummarized) <= self.config.memory_turn_threshold and not force:
            return ""

        keep = self.config.raw_message_window
        to_summarize = unsummarized[:-keep] if len(unsummarized) > keep else unsummarized
        if not to_summarize:
            return ""

        previous = self.db.latest_summary(session_id)
        lines = [previous] if previous else []
        lines.append("Compressed conversation memory:")
        for message in to_summarize:
            content = message["content"].replace("\n", " ")
            lines.append(f"- {message['role']}: {content[:350]}")

        summary = "\n".join(lines)[-6000:]
        self.db.add_summary(session_id, summary, [message["id"] for message in to_summarize])
        return "Compacted older conversation turns into session memory."
