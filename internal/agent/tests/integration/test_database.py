from __future__ import annotations

from sqlalchemy import text

from app.db.session import AsyncSessionFactory


async def test_database_connection() -> None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(text("SELECT 1"))

        assert result.scalar_one() == 1
