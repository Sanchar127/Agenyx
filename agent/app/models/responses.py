from typing import Any

from pydantic import BaseModel, Field


class ToolCallResult(BaseModel):
    """
    Represents the result of an individual tool call.

    call_id is optional for backward compatibility with older
    single-tool responses that did not expose a call identifier.
    """

    call_id: str | None = None

    name: str

    arguments: dict[str, Any]

    result: str


class AgentResponse(BaseModel):
    """
    Final response returned by the agent runtime.
    """

    execution_id: str

    status: str

    answer: str

    steps: int

    tool_calls: list[ToolCallResult] = Field(
        default_factory=list
    )
