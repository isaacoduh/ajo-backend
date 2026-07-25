"""Database session dependency helpers."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import session_scope


async def get_session() -> AsyncIterator[AsyncSession]:
    async for session in session_scope():
        yield session

