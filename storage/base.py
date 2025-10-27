"""Abstract interface for storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp.storage.models import ProjectRecord


class ConflictError(Exception):
    """Raised when an optimistic concurrency conflict occurs."""
    pass


class StorageBackend(ABC):
    """Unified interface for persistence layers."""

    async def setup(self) -> None:
        """Perform any startup work. Optional for some backends."""

    async def close(self) -> None:
        """Release held resources."""

    @abstractmethod
    async def upsert_project(
        self,
        *,
        name: str,
        repo_root: str,
        progress_log_path: str,
    ) -> ProjectRecord:
        """Insert or update a project row and return the record."""

    @abstractmethod
    async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
        """Return the project by name when present."""

    @abstractmethod
    async def list_projects(self) -> List[ProjectRecord]:
        """Return all known projects."""

    @abstractmethod
    async def insert_entry(
        self,
        *,
        entry_id: str,
        project: ProjectRecord,
        ts: datetime,
        emoji: str,
        agent: Optional[str],
        message: str,
        meta: Optional[Dict[str, Any]],
        raw_line: str,
        sha256: str,
    ) -> None:
        """Insert a progress log entry and update metrics."""

    async def record_doc_change(
        self,
        project: ProjectRecord,
        *,
        doc: str,
        section: Optional[str],
        action: str,
        agent: Optional[str],
        metadata: Optional[Dict[str, Any]],
        sha_before: str,
        sha_after: str,
    ) -> None:
        """Record a documentation change (optional for storage backends)."""

    @abstractmethod
    async def fetch_recent_entries(
        self,
        *,
        project: ProjectRecord,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return recent entries for the given project."""

    async def fetch_recent_entries_paginated(
        self,
        *,
        project: ProjectRecord,
        page: int = 1,
        page_size: int = 50,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Return recent entries with pagination metadata.

        Args:
            project: Project to fetch entries for
            page: Page number (1-based)
            page_size: Number of entries per page
            filters: Optional filters to apply

        Returns:
            Tuple of (entries, total_count)
        """
        # Calculate offset
        offset = (page - 1) * page_size

        # Fetch entries for this page
        entries = await self.fetch_recent_entries(
            project=project,
            limit=page_size,
            filters=filters,
            offset=offset
        )

        # Get total count (this varies by backend implementation)
        total_count = await self.count_entries(project, filters)

        return entries, total_count

    async def count_entries(
        self,
        project: ProjectRecord,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Count total entries matching filters.
        Default implementation - can be overridden by backends for better performance.
        """
        # Default implementation - fetch all and count (inefficient)
        # Backends should override this with proper COUNT queries
        all_entries = await self.fetch_recent_entries(
            project=project,
            limit=10000,  # Large limit to get most entries
            filters=filters
        )
        return len(all_entries)

    async def query_entries(
        self,
        *,
        project: ProjectRecord,
        limit: int,
        start: Optional[str] = None,
        end: Optional[str] = None,
        agents: Optional[List[str]] = None,
        emojis: Optional[List[str]] = None,
        message: Optional[str] = None,
        message_mode: str = "substring",
        case_sensitive: bool = False,
        meta_filters: Optional[Dict[str, str]] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Advanced log query for the given project."""

    async def query_entries_paginated(
        self,
        *,
        project: ProjectRecord,
        page: int = 1,
        page_size: int = 50,
        start: Optional[str] = None,
        end: Optional[str] = None,
        agents: Optional[List[str]] = None,
        emojis: Optional[List[str]] = None,
        message: Optional[str] = None,
        message_mode: str = "substring",
        case_sensitive: bool = False,
        meta_filters: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Advanced log query with pagination.

        Args:
            project: Project to query
            page: Page number (1-based)
            page_size: Number of entries per page
            Other parameters: same as query_entries

        Returns:
            Tuple of (entries, total_count)
        """
        # Calculate offset
        offset = (page - 1) * page_size

        # Query entries for this page
        entries = await self.query_entries(
            project=project,
            limit=page_size,
            start=start,
            end=end,
            agents=agents,
            emojis=emojis,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            meta_filters=meta_filters,
            offset=offset
        )

        # Get total count
        total_count = await self.count_query_entries(
            project=project,
            start=start,
            end=end,
            agents=agents,
            emojis=emojis,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            meta_filters=meta_filters
        )

        return entries, total_count

    async def count_query_entries(
        self,
        *,
        project: ProjectRecord,
        start: Optional[str] = None,
        end: Optional[str] = None,
        agents: Optional[List[str]] = None,
        emojis: Optional[List[str]] = None,
        message: Optional[str] = None,
        message_mode: str = "substring",
        case_sensitive: bool = False,
        meta_filters: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Count total entries matching query criteria.
        Default implementation - can be overridden by backends for better performance.
        """
        # Default implementation - query all and count (inefficient)
        # Backends should override this with proper COUNT queries
        all_entries = await self.query_entries(
            project=project,
            limit=10000,  # Large limit to get most entries
            start=start,
            end=end,
            agents=agents,
            emojis=emojis,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            meta_filters=meta_filters
        )
        return len(all_entries)

    # Agent session and project context management
    @abstractmethod
    async def upsert_agent_session(self, agent_id: str, session_id: str, metadata: Optional[Dict[str, Any]]) -> None:
        """Create or update an agent session."""

    @abstractmethod
    async def heartbeat_session(self, session_id: str) -> None:
        """Update session last_active_at timestamp."""

    @abstractmethod
    async def end_session(self, session_id: str) -> None:
        """Mark a session as expired."""

    @abstractmethod
    async def get_agent_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get an agent's current project with version info."""

    @abstractmethod
    async def set_agent_project(self, agent_id: str, project_name: Optional[str], expected_version: Optional[int], updated_by: str, session_id: str) -> Dict[str, Any]:
        """Set an agent's current project with optimistic concurrency control."""
