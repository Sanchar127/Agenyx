from __future__ import annotations

import uuid

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import agenyx_error_handler
from app.api.routes import create_router
from app.core.config import get_settings
from app.core.errors import AgenyxError


def create_test_app() -> FastAPI:
    app = FastAPI()

    app.add_exception_handler(
        AgenyxError,
        agenyx_error_handler,
    )

    app.include_router(
        create_router(
            lambda: None,
        )
    )

    return app


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def _decode_token(token: str) -> dict:
    settings = get_settings()

    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )


def test_signup_returns_token() -> None:
    app = create_test_app()
    email = _unique_email()

    with TestClient(app) as client:
        response = client.post(
            "/auth/email/signup",
            json={
                "email": email,
                "password": "supersecret123",
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600

    payload = _decode_token(body["access_token"])

    assert payload["sub"] == email.lower()
    assert payload["iss"] == get_settings().jwt_issuer
    assert payload["aud"] == get_settings().jwt_audience


def test_signup_with_existing_email_returns_conflict() -> None:
    app = create_test_app()
    email = _unique_email()

    with TestClient(app) as client:
        first = client.post(
            "/auth/email/signup",
            json={
                "email": email,
                "password": "supersecret123",
            },
        )

        second = client.post(
            "/auth/email/signup",
            json={
                "email": email,
                "password": "supersecret123",
            },
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "USER_ALREADY_EXISTS"


def test_login_returns_token_for_created_user() -> None:
    app = create_test_app()
    email = _unique_email()
    password = "supersecret123"

    with TestClient(app) as client:
        client.post(
            "/auth/email/signup",
            json={
                "email": email,
                "password": password,
            },
        )

        response = client.post(
            "/auth/email/login",
            json={
                "email": email,
                "password": password,
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_login_with_invalid_password_returns_401() -> None:
    app = create_test_app()
    email = _unique_email()

    with TestClient(app) as client:
        client.post(
            "/auth/email/signup",
            json={
                "email": email,
                "password": "supersecret123",
            },
        )

        response = client.post(
            "/auth/email/login",
            json={
                "email": email,
                "password": "wrongpassword1",
            },
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_with_unknown_email_returns_401() -> None:
    app = create_test_app()
    email = _unique_email()

    with TestClient(app) as client:
        response = client.post(
            "/auth/email/login",
            json={
                "email": email,
                "password": "supersecret123",
            },
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
