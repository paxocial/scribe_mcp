"""Storage backend factory and helpers."""

from __future__ import annotations

from typing import Optional

from scribe_mcp.config.settings import settings
from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.storage.postgres import PostgresStorage
from scribe_mcp.storage.sqlite import SQLiteStorage


def create_storage_backend() -> Optional[StorageBackend]:
    """Instantiate the configured storage backend."""
    backend_name = settings.storage_backend
    if backend_name == "postgres" and settings.db_url:
        return PostgresStorage(settings.db_url)
    if backend_name == "sqlite":
        return SQLiteStorage(settings.sqlite_path)
    # Fallback: if postgres requested but no URL, default to sqlite
    if settings.db_url:
        return PostgresStorage(settings.db_url)
    return SQLiteStorage(settings.sqlite_path)
