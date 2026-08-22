import os

import httpx
import pytest


OLLAMA_URL = os.getenv(
    "AGENTYX_LLM_BASE_URL",
    "http://localhost:11434/v1",
)


@pytest.mark.asyncio
async def test_ollama_chat_completion() -> None:
    payload = {
        "model": os.getenv(
            "AGENTYX_LLM_MODEL",
            "qwen2.5:7b",
        ),
        "messages": [
            {
                "role": "user",
                "content": "What is 25 * 17?",
            }
        ],
        "temperature": 0,
    }

    try:
        async with httpx.AsyncClient(
            timeout=120
        ) as client:
            response = await client.post(
                f"{OLLAMA_URL}/chat/completions",
                json=payload,
            )
    except httpx.HTTPError as exc:
        pytest.skip(
            f"Ollama unavailable: {exc}"
        )

    assert response.status_code == 200

    body = response.json()

    assert body["choices"]
    assert body["choices"][0]["message"]["content"]
