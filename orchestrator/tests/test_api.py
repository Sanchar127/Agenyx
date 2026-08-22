from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.main import app


class FakeQueue:
    def __init__(self) -> None:
        self.executions: dict[str, dict[str, str]] = {}

    def ping(self) -> bool:
        return True

    def create_execution(
        self,
        *,
        execution_id: str,
        intent: str,
    ) -> None:
        self.executions[execution_id] = {
            "execution_id": execution_id,
            "status": "queued",
            "intent": intent,
        }

    def enqueue(
        self,
        *,
        execution_id: str,
        intent: str,
    ) -> str:
        return "1-0"

    def get_execution(
        self,
        execution_id: str,
    ) -> dict[str, str]:
        return self.executions.get(
            execution_id,
            {},
        )


def test_health() -> None:
    queue = FakeQueue()

    test_app = app.__class__(
        title="test",
    )

    test_app.include_router(
        create_router(queue),
    )

    with TestClient(test_app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_agent_request_is_queued() -> None:
    queue = FakeQueue()

    test_app = app.__class__(
        title="test",
    )

    test_app.include_router(
        create_router(queue),
    )

    with TestClient(test_app) as client:
        response = client.post(
            "/v1/agent/run",
            json={
                "intent": "What is 25 * 17?",
            },
        )

    assert response.status_code == 202

    body = response.json()

    assert body["status"] == "queued"
    assert "execution_id" in body


def test_empty_intent_is_rejected() -> None:
    queue = FakeQueue()

    test_app = app.__class__(
        title="test",
    )

    test_app.include_router(
        create_router(queue),
    )

    with TestClient(test_app) as client:
        response = client.post(
            "/v1/agent/run",
            json={
                "intent": "",
            },
        )

    assert response.status_code == 422
