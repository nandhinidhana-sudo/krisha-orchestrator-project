from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    answer: str
    used_agents: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class RoutePlan(BaseModel):
    needs_documents: bool
    needs_web_search: bool
    needs_visualization: bool
    visualization_types: list[Literal["mermaid", "vega_lite"]] = Field(default_factory=list)


class ToolResult(BaseModel):
    summary: str
    data: Any = None


class ChartRequest(BaseModel):
    prompt: str
    evidence: list[str] = Field(default_factory=list)
    chart_type: Literal["mermaid", "vega_lite"]
