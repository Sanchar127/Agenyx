from datetime import datetime, timedelta, timezone
from hmac import compare_digest
from secrets import token_hex
from typing import Any

import jwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.errors import InvalidCredentialsError, UserAlreadyExistsError


security = HTTPBearer()

_ACCESS_TOKEN_TTL = timedelta(hours=1)
_PASSWORD_HASH_ITERATIONS = 100_000


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Issue a signed Agenyx access token for the given subject.
    """

    settings = get_settings()

    if expires_delta is None:
        expires_delta = _ACCESS_TOKEN_TTL

    now = datetime.now(timezone.utc)

    payload = {
        "sub": subject,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + expires_delta,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def _hash_password(password: str, salt: str) -> str:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode("utf-8"),
        iterations=_PASSWORD_HASH_ITERATIONS,
    )

    derived_key = kdf.derive(password.encode("utf-8"))

    return f"{salt}:{derived_key.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    salt, expected_hex = stored_hash.split(":", 1)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode("utf-8"),
        iterations=_PASSWORD_HASH_ITERATIONS,
    )

    derived_key = kdf.derive(password.encode("utf-8"))

    return compare_digest(derived_key.hex(), expected_hex)


class InMemoryUserCredentialStore:
    """
    Temporary in-memory user credential store.

    TODO: replace with a persistent user store as part of the
    database-backed authentication work.
    """

    def __init__(self) -> None:
        self._users: dict[str, tuple[str, str]] = {}

    def add_user(
        self,
        email: str,
        password: str,
    ) -> str:
        key = email.strip().lower()

        if key in self._users:
            raise UserAlreadyExistsError(
                "A user with this email already exists.",
            )

        salt = token_hex(16)
        self._users[key] = (key, _hash_password(password, salt))

        return key

    def verify_user(
        self,
        email: str,
        password: str,
    ) -> str | None:
        key = email.strip().lower()

        record = self._users.get(key)

        if record is None:
            return None

        user_id, password_hash = record

        if not _verify_password(password, password_hash):
            return None

        return user_id


user_credential_store = InMemoryUserCredentialStore()


def verify_token(
    credentials: HTTPAuthorizationCredentials,
) -> dict[str, Any]:
    settings = get_settings()

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN",
                "message": "Invalid or expired authentication token",
            },
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN",
                "message": "Invalid authentication token",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
