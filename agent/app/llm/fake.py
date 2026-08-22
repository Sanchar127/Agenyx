from typing import Any

from app.llm.base import LLMProvider


class FakeLLMProvider(LLMProvider):
    def __init__(
        self,
        responses: list[dict[str, Any]],
    ) -> None:
        self.responses = responses
        self.calls = 0

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self.calls >= len(self.responses):
            raise RuntimeError(
                "FakeLLMProvider has no more responses"
            )

        response = self.responses[self.calls]
        self.calls += 1

        return response
