import os

os.environ["INFERENCE_SERVICE_API_KEY"] = "test-service-key"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-Agenyx-Service-Key": "test-service-key",
        },
    ) as client:
        assert client.headers["X-Agenyx-Service-Key"] == "test-service-key"
        yield client
