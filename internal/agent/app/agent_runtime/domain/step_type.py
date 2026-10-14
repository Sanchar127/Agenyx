from __future__ import annotations

from enum import StrEnum


class StepType(StrEnum):
    PLAN = "plan"
    INFERENCE = "inference"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    OBSERVATION = "observation"
    FINAL = "final"
