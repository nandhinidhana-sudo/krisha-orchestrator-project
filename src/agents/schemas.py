from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["document_qa", "web_search", "visualization"]


class AgentResponse(BaseModel):
    answer: str
    used_agents: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class RoutePlan(BaseModel):
    needs_documents: bool
    needs_web_search: bool
    needs_visualization: bool
    visualization_types: list[Literal["mermaid", "vega_lite"]] = Field(default_factory=list)
    required_agents: list[AgentName] = Field(default_factory=list)
    execution_groups: list[list[AgentName]] = Field(default_factory=list)
    rationale: str = ""


class ToolResult(BaseModel):
    summary: str
    data: Any = None


class ChartRequest(BaseModel):
    prompt: str
    evidence: list[str] = Field(default_factory=list)
    chart_type: Literal["mermaid", "vega_lite"]
