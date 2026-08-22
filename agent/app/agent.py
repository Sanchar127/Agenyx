import json
import os
from typing import Any

import httpx

from .models import AgentResponse, ToolCall
from .tools import Tool


SYSTEM_PROMPT = """
You are Agenyx, an AI agent runtime.

Your job is to solve the user's request by reasoning step by step.

You have access to tools.

When you need a tool, respond with ONLY valid JSON:

{
  "type": "tool_call",
  "name": "tool_name",
  "arguments": {
    "argument": "value"
  }
}

When you have the final answer, respond with ONLY valid JSON:

{
  "type": "final",
  "answer": "your answer"
}

Never invent tools.
Never execute code directly.
Use a registered tool when one is available.
""".strip()


class AgentError(Exception):
    """Base exception for agent execution errors."""


class AgentRuntime:
    def __init__(
        self,
        tools: dict[str, Tool],
        *,
        max_steps: int = 8,
    ) -> None:
        self.tools = tools
        self.max_steps = max_steps

        self.llm_url = os.getenv(
            "AGENYX_LLM_URL",
            "http://localhost:11434/v1/chat/completions",
        )
        self.model = os.getenv(
            "AGENYX_MODEL",
            "qwen2.5:7b",
        )

    async def run(self, intent: str) -> AgentResponse:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": intent,
            },
        ]

        tool_calls: list[ToolCall] = []

        for step in range(1, self.max_steps + 1):
            response = await self._query_llm(messages)

            action = self._parse_response(response)

            if action["type"] == "final":
                return AgentResponse(
                    status="success",
                    answer=action["answer"],
                    steps=step,
                    tool_calls=tool_calls,
                )

            if action["type"] != "tool_call":
                raise AgentError(
                    f"Unsupported agent action: {action['type']}"
                )

            tool_call = ToolCall(
                name=action["name"],
                arguments=action.get("arguments", {}),
            )

            tool_calls.append(tool_call)

            result = await self._execute_tool(tool_call)

            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(action),
                }
            )

            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool '{tool_call.name}' returned:\n"
                        f"{result}\n\n"
                        "Continue solving the original request."
                    ),
                }
            )

        raise AgentError(
            f"Agent exceeded maximum execution steps: {self.max_steps}"
        )

    async def _query_llm(
        self,
        messages: list[dict[str, Any]],
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.llm_url,
                    json=payload,
                )

            response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise AgentError("LLM request timed out") from exc

        except httpx.HTTPError as exc:
            raise AgentError(
                f"LLM request failed: {exc}"
            ) from exc

        data = response.json()

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AgentError(
                "LLM returned an invalid response"
            ) from exc

    @staticmethod
    def _parse_response(content: str) -> dict[str, Any]:
        content = content.strip()

        try:
            action = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AgentError(
                f"LLM returned invalid JSON: {content}"
            ) from exc

        if not isinstance(action, dict):
            raise AgentError("LLM response must be a JSON object")

        action_type = action.get("type")

        if action_type == "final":
            answer = action.get("answer")

            if not isinstance(answer, str):
                raise AgentError(
                    "Final action requires a string 'answer'"
                )

            return action

        if action_type == "tool_call":
            name = action.get("name")

            if not isinstance(name, str):
                raise AgentError(
                    "Tool call requires a string 'name'"
                )

            arguments = action.get("arguments", {})

            if not isinstance(arguments, dict):
                raise AgentError(
                    "Tool arguments must be an object"
                )

            return action

        raise AgentError(
            f"Unknown action type: {action_type}"
        )

    async def _execute_tool(self, tool_call: ToolCall) -> str:
        tool = self.tools.get(tool_call.name)

        if tool is None:
            return f"ERROR: unknown tool '{tool_call.name}'"

        try:
            result = tool.execute(**tool_call.arguments)
        except TypeError as exc:
            return f"ERROR: invalid arguments: {exc}"
        except ValueError as exc:
            return f"ERROR: {exc}"
        except Exception:
            return "ERROR: tool execution failed"

        return str(result)
