"""Connection pooling for asyncpg."""

from __future__ import annotations

import asyncio
from typing import Optional

import asyncpg

from scribe_mcp.config.settings import settings

_pool: Optional[asyncpg.pool.Pool] = None
_pool_lock = asyncio.Lock()


async def get_pool() -> Optional[asyncpg.pool.Pool]:
    """Return the active connection pool, initialising if necessary."""
    async with _pool_lock:
        if _pool or not settings.db_url:
            return _pool
        return await _initialise()


async def _initialise() -> Optional[asyncpg.pool.Pool]:
    global _pool
    if not settings.db_url:
        return None
    _pool = await asyncpg.create_pool(dsn=settings.db_url, min_size=1, max_size=10)
    return _pool


async def close_pool() -> None:
    """Close the active pool if it exists."""
    async with _pool_lock:
        global _pool
        if _pool:
            await _pool.close()
            _pool = None

