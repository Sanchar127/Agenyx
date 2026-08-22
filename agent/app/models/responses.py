from typing import Any

from pydantic import BaseModel, Field


class ToolCallResult(BaseModel):
    name: str
    arguments: dict[str, Any]
    result: str


class AgentResponse(BaseModel):
    execution_id: str
    status: str
    answer: str
    steps: int
    tool_calls: list[ToolCallResult] = Field(
        default_factory=list
    )
