from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings


settings = get_settings()

now = datetime.now(timezone.utc)

payload = {
    "sub": "local-developer",
    "iss": settings.jwt_issuer,
    "aud": settings.jwt_audience,
    "iat": now,
    "exp": now + timedelta(hours=1),
}

token = jwt.encode(
    payload,
    settings.jwt_secret,
    algorithm=settings.jwt_algorithm,
)

print(token)
