import pytest
from fastapi import HTTPException

from app.auth import require_service_auth
from app.config import get_settings

@pytest.fixture(autouse=True)
def configure_settings(monkeypatch):
    monkeypatch.setenv("INFERENCE_SERVICE_API_KEY", "test-service-key")
    get_settings.cache_clear()  # Clear cached settings to apply new environment variable

@pytest.mark.asyncio
async def test_missing_service_key_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        await require_service_auth(None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "INVALID_SERVICE_CREDENTIAL"

@pytest.mark.asyncio
async def test_invalid_service_key_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        await require_service_auth("wrong-key")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "INVALID_SERVICE_CREDENTIAL"

@pytest.mark.asyncio
async def test_valid_service_key_is_accepted():
    # This should not raise an exception
    result = await require_service_auth("test-service-key")

    assert result is None  # The function returns None on success
