from __future__ import annotations

import json
from typing import Any

from app.agent_runtime.domain import (
    AgentDecision,
    DecisionType,
    ExecutionContext,
)
from app.core.errors import AgentProtocolError
from app.tools.registry import ToolRegistry


class Planner:
    """
    Production planning boundary for the agent runtime.

    The Planner converts a raw inference response into an
    Agenyx-owned AgentDecision.

    Responsibilities:
    - validate the inference response structure
    - extract the assistant message
    - determine whether the model produced a final answer
      or requested a tool
    - validate tool-call structure
    - safely parse tool arguments
    - verify requested tools exist
    - perform execution-context validation
    - return an AgentDecision

    The Planner does NOT:
    - call the LLM
    - execute tools
    - access the sandbox
    - select models
    - perform model routing
    - persist state
    - perform HTTP operations
    - implement business-specific tool behavior

    Architectural boundary:

        Inference response
                |
                v
             Planner
                |
                v
          AgentDecision
                |
                v
           AgentRuntime
                |
                v
             Sandbox
    """

    def __init__(
        self,
        *,
        tools: ToolRegistry,
    ) -> None:
        self.tools = tools

    def plan(
        self,
        *,
        response: dict[str, Any],
        context: ExecutionContext,
    ) -> AgentDecision:
        """
        Convert one inference response into one AgentDecision.

        The Planner intentionally produces exactly one decision per
        inference response.

        Supported decisions:

            FINAL
                The model produced a final textual response.

            TOOL_CALL
                The model requested one valid registered tool.

        CONTINUE and FAIL are part of the domain model and will be
        introduced when the runtime has explicit semantics for them.
        """

        self._validate_context(context)

        message = self._extract_message(response)

        tool_calls = self._extract_tool_calls(message)

        if tool_calls:
            return self._plan_tool_call(
                tool_calls[0],
                context=context,
            )

        return self._plan_final_response(message)

    @staticmethod
    def _validate_context(
        context: ExecutionContext,
    ) -> None:
        """
        Validate the minimum context required for planning.

        ExecutionContext is intentionally validated at the Planner
        boundary because future planning policies will depend on it.
        """

        if not isinstance(context, ExecutionContext):
            raise AgentProtocolError(
                "Planner requires a valid ExecutionContext"
            )

        if context.execution is None:
            raise AgentProtocolError(
                "Execution context is missing execution"
            )

        if context.current_step < 0:
            raise AgentProtocolError(
                "Execution context contains invalid current step"
            )

    @staticmethod
    def _extract_message(
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Extract the assistant message from an OpenAI-compatible
        inference response.

        Expected structure:

            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "...",
                            "tool_calls": [...]
                        }
                    }
                ]
            }
        """

        if not isinstance(response, dict):
            raise AgentProtocolError(
                "Inference response must be an object"
            )

        choices = response.get("choices")

        if not isinstance(choices, list):
            raise AgentProtocolError(
                "Inference response 'choices' must be a list"
            )

        if not choices:
            raise AgentProtocolError(
                "Inference response does not contain choices"
            )

        choice = choices[0]

        if not isinstance(choice, dict):
            raise AgentProtocolError(
                "Inference response contains invalid choice"
            )

        message = choice.get("message")

        if not isinstance(message, dict):
            raise AgentProtocolError(
                "Inference response does not contain message"
            )

        role = message.get("role")

        if role is not None:
            if not isinstance(role, str):
                raise AgentProtocolError(
                    "Inference message role must be a string"
                )

            if role != "assistant":
                raise AgentProtocolError(
                    "Inference response message must have "
                    "role 'assistant'"
                )

        return message

    @staticmethod
    def _extract_tool_calls(
        message: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Extract and validate the model's tool_calls field.

        Missing tool_calls means the model is attempting to provide
        a final response.
        """

        tool_calls = message.get("tool_calls")

        if tool_calls is None:
            return []

        if not isinstance(tool_calls, list):
            raise AgentProtocolError(
                "Inference message 'tool_calls' must be a list"
            )

        if len(tool_calls) > 1:
            raise AgentProtocolError(
                "Inference returned multiple tool calls; "
                "Agenyx currently supports exactly one "
                "tool call per agent step"
            )

        if not tool_calls:
            return []

        tool_call = tool_calls[0]

        if not isinstance(tool_call, dict):
            raise AgentProtocolError(
                "Tool call must be an object"
            )

        return [tool_call]

    @staticmethod
    def _plan_final_response(
        message: dict[str, Any],
    ) -> AgentDecision:
        """
        Convert an assistant message without a tool call into a
        final AgentDecision.
        """

        content = message.get("content")

        if content is None:
            raise AgentProtocolError(
                "Inference returned neither tool calls nor content"
            )

        if not isinstance(content, str):
            raise AgentProtocolError(
                "Inference message content must be a string"
            )

        content = content.strip()

        if not content:
            raise AgentProtocolError(
                "Inference returned empty content"
            )

        return AgentDecision(
            type=DecisionType.FINAL,
            content=content,
        )

    def _plan_tool_call(
        self,
        tool_call: dict[str, Any],
        *,
        context: ExecutionContext,
    ) -> AgentDecision:
        """
        Validate one model tool call and convert it into an
        Agenyx AgentDecision.
        """

        call_id = self._extract_call_id(tool_call)

        function = self._extract_function(tool_call)

        name = self._extract_tool_name(function)

        arguments = self._extract_arguments(
            function=function,
            tool_name=name,
        )

        self._validate_tool(
            name=name,
            arguments=arguments,
            context=context,
        )

        return AgentDecision(
            type=DecisionType.TOOL_CALL,
            tool_name=name,
            arguments=arguments,
            call_id=call_id,
        )

    @staticmethod
    def _extract_call_id(
        tool_call: dict[str, Any],
    ) -> str:
        """
        Extract the provider-generated tool call ID.

        The ID is required because the subsequent tool result must
        be correlated with the model's original tool request.
        """

        call_id = tool_call.get("id")

        if not isinstance(call_id, str):
            raise AgentProtocolError(
                "Tool call has no valid ID"
            )

        call_id = call_id.strip()

        if not call_id:
            raise AgentProtocolError(
                "Tool call has no valid ID"
            )

        return call_id

    @staticmethod
    def _extract_function(
        tool_call: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Extract the function section from an OpenAI-compatible
        tool call.
        """

        function = tool_call.get("function")

        if not isinstance(function, dict):
            raise AgentProtocolError(
                "Tool call has invalid function"
            )

        return function

    @staticmethod
    def _extract_tool_name(
        function: dict[str, Any],
    ) -> str:
        """
        Extract and normalize the requested tool name.
        """

        name = function.get("name")

        if not isinstance(name, str):
            raise AgentProtocolError(
                "Tool call has no valid name"
            )

        name = name.strip()

        if not name:
            raise AgentProtocolError(
                "Tool call has no valid name"
            )

        return name

    @staticmethod
    def _extract_arguments(
        *,
        function: dict[str, Any],
        tool_name: str,
    ) -> dict[str, Any]:
        """
        Parse the model's JSON-encoded tool arguments.

        Tool arguments must always decode into a JSON object.

        Examples of valid arguments:

            "{}"

            '{"expression": "25 * 17"}'

        Invalid:

            '[]'

            '"hello"'

            '123'

            'invalid json'
        """

        raw_arguments = function.get(
            "arguments",
            "{}",
        )

        if not isinstance(raw_arguments, str):
            raise AgentProtocolError(
                f"Invalid arguments for tool '{tool_name}': "
                "arguments must be a JSON string"
            )

        raw_arguments = raw_arguments.strip()

        if not raw_arguments:
            raw_arguments = "{}"

        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise AgentProtocolError(
                f"Invalid JSON arguments for tool "
                f"'{tool_name}'"
            ) from exc

        if not isinstance(arguments, dict):
            raise AgentProtocolError(
                f"Arguments for tool '{tool_name}' "
                "must be a JSON object"
            )

        return arguments

    def _validate_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> None:
        """
        Validate that the requested tool is allowed to proceed
        to the execution layer.
        """

        if not self.tools.has(name):
            raise AgentProtocolError(
                f"Unknown tool requested by model: '{name}'"
            )

        self._validate_tool_arguments(
            name=name,
            arguments=arguments,
        )

        self._validate_context_policy(
            name=name,
            arguments=arguments,
            context=context,
        )

    @staticmethod
    def _validate_tool_arguments(
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> None:
        """
        Basic argument validation.

        The ToolRegistry currently owns the tool definitions but
        does not yet expose a dedicated runtime schema validator.

        Once the registry exposes a formal schema-validation
        interface, this method should delegate to it.

        For now we enforce the important invariant that arguments
        are a dictionary and contain no obviously invalid structure.
        """

        if not isinstance(arguments, dict):
            raise AgentProtocolError(
                f"Arguments for tool '{name}' must be an object"
            )

    @staticmethod
    def _validate_context_policy(
        *,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> None:
        """
        Context-aware policy boundary.

        This is where execution policy will eventually live.

        Planned production policies include:

        - maximum calls per execution
        - per-tool call limits
        - repeated-call detection
        - tool budgets
        - execution deadlines
        - permission checks
        - tenant/user authorization
        - tool risk classification
        - idempotency requirements
        - sandbox restrictions
        - failure-loop detection
        """

        if context.current_step <= 0:
            raise AgentProtocolError(
                f"Invalid execution step for tool '{name}'"
            )

        # Keep the interface explicit until policy components are
        # introduced. These values will be consumed by future
        # execution-policy validation.
        _ = arguments
