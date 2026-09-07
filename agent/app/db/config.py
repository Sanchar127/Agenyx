from __future__ import annotations

import os


def get_database_url() -> str:
    url = os.getenv("AGENTYX_DATABASE_URL")

    if not url:
        raise RuntimeError(
            "AGENTYX_DATABASE_URL is not configured"
        )

    return url
