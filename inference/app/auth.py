from fastapi import Header, HTTPException, status

from app.config import get_settings

async def require_service_auth(
    x_agenyx_service_key:str | None = Header(
        default=None,
    alias="X-Agenyx-Service-Key",
    ),
)->None:
    """Require a valid Agent to Inference service credential."""
    settings = get_settings()

    if not settings.service_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SERVICE_AUTH_NOT_CONFIGURED",
                "message": "Inference service authentication is not configured.",
            },

        )
    if x_agenyx_service_key != settings.service_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_SERVICE_CREDENTIAL",
                "message": "Invalid service authentication credential.",
            },
        )
