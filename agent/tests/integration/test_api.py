
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.agent_runtime.runtime import AgentRuntime
from app.llm.fake import FakeLLMProvider
from app.main import app
from app.sandbox.client import ToolSandboxClient
from app.tools.builtin import create_tool_registry


def tool_call_response(
    name: str,
    arguments: str,
    call_id: str = "call-1",
) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": arguments,
                            },
                        }
                    ],
                },
            }
        ],
    }


def final_response(answer: str) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": answer,
                },
            }
        ],
    }


class FakeToolSandbox(ToolSandboxClient):
    """Test sandbox that executes registered tools in-process."""

    def __init__(self) -> None:
        self.tools = create_tool_registry()

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        return self.tools.execute(
            name,
            arguments,
        )


def test_health() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_agent_api_executes_tool() -> None:
    fake_llm = FakeLLMProvider(
        [
            tool_call_response(
                "calculator",
                '{"expression":"25 * 17"}',
            ),
            final_response(
                "The answer is 425.",
            ),
        ]
    )

    sandbox = FakeToolSandbox()

    runtime = AgentRuntime(
        llm=fake_llm,
        tools=create_tool_registry(),
        max_steps=8,
        sandbox=sandbox,
    )

    app.dependency_overrides.clear()

    # Replace the application's runtime with our deterministic
    # test runtime.
    import app.main as main_module

    original_runtime = main_module.runtime
    main_module.runtime = runtime

    try:
        client = TestClient(app)

        response = client.post(
            "/v1/agent/run",
            json={
                "intent": "What is 25 * 17?",
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["status"] == "success"
        assert body["answer"] == "The answer is 425."
        assert body["steps"] == 2

        assert len(body["tool_calls"]) == 1
        assert body["tool_calls"][0]["name"] == "calculator"
        assert body["tool_calls"][0]["result"] == "425"

    finally:
        main_module.runtime = original_runtime
        app.dependency_overrides.clear()


def test_agent_api_validates_empty_intent() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/agent/run",
        json={
            "intent": "",
        },
    )

    assert response.status_code == 422
