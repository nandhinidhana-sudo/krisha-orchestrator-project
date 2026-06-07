import os
import asyncio

from src.agents.prompts import WEB_SEARCH_AGENT_PROMPT
from src.storage.database import Database


class WebSearchAgent:
    name = "Web Search Agent"
    instructions = WEB_SEARCH_AGENT_PROMPT

    def __init__(self, db: Database):
        self.db = db

    def search(self, session_id: str, run_id: str, query: str) -> str:
        if os.getenv("OPENAI_API_KEY"):
            summary = self._search_with_openai_agents(query)
        else:
            summary = (
                "Web search fallback: no OPENAI_API_KEY was detected, so this run did not call the live web. "
                "Use this placeholder result for development and tests."
            )

        self.db.add_tool_call(
            run_id,
            session_id,
            "web_search",
            {"query": query},
            summary,
        )
        self.db.add_step(run_id, session_id, self.name, "Prepared web research findings.")
        return summary

    def _search_with_openai_agents(self, query: str) -> str:
        try:
            from agents import Agent, Runner, WebSearchTool

            agent = Agent(
                name="Web Search Agent",
                instructions=self.instructions,
                tools=[WebSearchTool()],
            )

            async def run_search() -> str:
                result = await Runner.run(agent, query)
                return str(result.final_output)

            return asyncio.run(run_search())
        except Exception as exc:
            return (
                "Live web search was requested, but the OpenAI Agents SDK call could not complete. "
                f"Fallback reason: {exc}"
            )
