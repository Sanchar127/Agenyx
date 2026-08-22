from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import create_router
from app.core.config import get_settings
from app.queue.client import TaskQueue


settings = get_settings()
queue = TaskQueue(settings)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    """Initialize queue infrastructure."""

    queue.ensure_consumer_group()

    yield

    queue.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(
    create_router(queue),
)
