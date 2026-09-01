from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan, settings


@pytest.mark.asyncio
async def test_application_lifespan_closes_providers():
    with patch(
        "app.main.provider_registry.close",
        new_callable=AsyncMock,
    ) as mock_close:
        async with lifespan(app):
            pass

        mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_application_lifespan_startup_and_shutdown_logs():
    with patch(
        "app.main.provider_registry.close",
        new_callable=AsyncMock,
    ), patch(
        "app.main.logger"
    ) as mock_logger:

        async with lifespan(app):
            mock_logger.info.assert_any_call(
                "Inference service starting",
                extra={
                    "app_name": app.title,
                    "app_version": app.version,
                    "providers": settings.providers,
                    "default_model": settings.default_model,
                },
            )

        mock_logger.info.assert_any_call(
            "Inference service shutting down"
        )

        mock_logger.info.assert_any_call(
            "Inference providers closed"
        )


@pytest.mark.asyncio
async def test_application_can_serve_requests():
    with patch(
        "app.main.provider_registry.close",
        new_callable=AsyncMock,
    ):
        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:

            response = await client.get(
                "/health"
            )

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
    }


@pytest.mark.asyncio
async def test_lifespan_closes_registry_after_application_usage():
    with patch(
        "app.main.provider_registry.close",
        new_callable=AsyncMock,
    ) as mock_close:

        async with lifespan(app):

            transport = ASGITransport(
                app=app
            )

            async with AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:

                response = await client.get(
                    "/health"
                )

                assert response.status_code == 200

        mock_close.assert_awaited_once()
