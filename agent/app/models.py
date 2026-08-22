from typing import Any

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=10_000)


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    status: str
    answer: str
    steps: int
    tool_calls: list[ToolCall] = Field(default_factory=list)
