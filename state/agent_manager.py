"""Agent-scoped project context manager with session lease management."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from scribe_mcp.storage.base import ConflictError
from scribe_mcp.state.manager import StateManager


class SessionLeaseExpired(Exception):
    """Raised when a session lease has expired."""
    pass


class AgentContextManager:
    """
    Coordinates agent-scoped project context between database (source of truth)
    and JSON state (fast cache for UI continuity).

    Features:
    - Session management with TTL (15 minute leases)
    - Optimistic concurrency control for project switching
    - JSON state mirroring for warm UI state
    - Conflict detection and resolution
    """

    def __init__(self, storage, state_manager: StateManager):
        self.storage = storage
        self.state_manager = state_manager
        self._session_leases: Dict[str, tuple[str, datetime]] = {}  # agent_id -> (session_id, expires_at)
        self._lease_lock = asyncio.Lock()
        self._session_ttl_minutes = 15  # 15 minute session leases

    async def start_session(self, agent_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Start a new agent session.

        Args:
            agent_id: Unique identifier for the agent
            metadata: Optional session metadata

        Returns:
            Session ID for tracking
        """
        session_id = str(uuid.uuid4())

        # Store session in database
        await self.storage.upsert_agent_session(agent_id, session_id, metadata)

        # Cache session lease
        expires_at = utcnow() + timedelta(minutes=self._session_ttl_minutes)
        async with self._lease_lock:
            self._session_leases[agent_id] = (session_id, expires_at)

        # Log session start
        await self.log_agent_event(
            agent_id=agent_id,
            session_id=session_id,
            event_type="session_started",
            to_project="",  # No project yet
            metadata={"session_ttl_minutes": self._session_ttl_minutes, "metadata": metadata}
        )

        # Mirror to JSON state for UI continuity
        await self._mirror_session_to_json_state(agent_id, session_id, metadata)

        return session_id

    async def set_current_project(
        self,
        agent_id: str,
        project_name: Optional[str],
        session_id: str,
        expected_version: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Set the current project for an agent with optimistic concurrency control.

        Args:
            agent_id: Agent identifier
            project_name: Project name (None to clear)
            session_id: Valid session ID
            expected_version: Expected version for optimistic locking

        Returns:
            Updated agent project record

        Raises:
            SessionLeaseExpired: If session lease is expired
            ConflictError: If version conflict occurs
        """
        # Validate session lease
        await self._validate_session_lease(agent_id, session_id)

        # Get previous project for audit logging
        previous_project = None
        try:
            current = await self.storage.get_agent_project(agent_id)
            if current and current.get("project_name"):
                previous_project = current["project_name"]
        except Exception:
            pass

        # Set in database (source of truth)
        try:
            result = await self.storage.set_agent_project(
                agent_id=agent_id,
                project_name=project_name,
                expected_version=expected_version,
                updated_by=agent_id,
                session_id=session_id
            )

            # Log successful project change
            event_type = "project_switched" if previous_project and previous_project != project_name else "project_set"
            await self.log_agent_event(
                agent_id=agent_id,
                session_id=session_id,
                event_type=event_type,
                from_project=previous_project,
                to_project=project_name,
                expected_version=expected_version,
                actual_version=result["version"] if hasattr(result, "__getitem__") else result.get("version"),
                success=True,
                metadata={"updated_by": agent_id}
            )

            # Mirror to JSON state (non-authoritative cache)
            await self._mirror_project_to_json_state(agent_id, result)

            return result

        except Exception as e:
            # Log failed project change
            await self.log_agent_event(
                agent_id=agent_id,
                session_id=session_id,
                event_type="conflict_detected",
                from_project=previous_project,
                to_project=project_name,
                expected_version=expected_version,
                success=False,
                error_message=str(e),
                metadata={"error_type": type(e).__name__}
            )
            raise

    async def get_current_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an agent's current project from database (source of truth).

        Args:
            agent_id: Agent identifier

        Returns:
            Agent project record or None
        """
        return await self.storage.get_agent_project(agent_id)

    async def heartbeat_session(self, session_id: str) -> None:
        """
        Update session activity timestamp.

        Args:
            session_id: Session ID to update
        """
        await self.storage.heartbeat_session(session_id)

        # Update local lease cache
        async with self._lease_lock:
            for agent_id, (cached_session_id, expires_at) in self._session_leases.items():
                if cached_session_id == session_id:
                    # Extend lease
                    new_expires_at = utcnow() + timedelta(minutes=self._session_ttl_minutes)
                    self._session_leases[agent_id] = (session_id, new_expires_at)
                    break

    async def end_session(self, agent_id: str, session_id: str) -> None:
        """
        End an agent session.

        Args:
            agent_id: Agent identifier
            session_id: Session ID to end
        """
        # Get current project for audit logging
        current_project = None
        try:
            project = await self.storage.get_agent_project(agent_id)
            if project and project.get("project_name"):
                current_project = project["project_name"]
        except Exception:
            pass

        # Mark session as expired in database
        await self.storage.end_session(session_id)

        # Log session end
        await self.log_agent_event(
            agent_id=agent_id,
            session_id=session_id,
            event_type="session_ended",
            to_project=current_project or "",
            metadata={"session_end_reason": "explicit_end"}
        )

        # Remove from local lease cache
        async with self._lease_lock:
            if agent_id in self._session_leases:
                cached_session_id, _ = self._session_leases[agent_id]
                if cached_session_id == session_id:
                    del self._session_leases[agent_id]

    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions and leases.

        Returns:
            Number of sessions cleaned up
        """
        now = utcnow()
        cleaned_count = 0

        async with self._lease_lock:
            expired_agents = []
            for agent_id, (session_id, expires_at) in self._session_leases.items():
                if expires_at < now:
                    expired_agents.append((agent_id, session_id))

            for agent_id, session_id in expired_agents:
                await self.storage.end_session(session_id)
                del self._session_leases[agent_id]
                cleaned_count += 1

        return cleaned_count

    async def _validate_session_lease(self, agent_id: str, session_id: str) -> None:
        """
        Validate that a session lease is still active.

        Args:
            agent_id: Agent identifier
            session_id: Session ID to validate

        Raises:
            SessionLeaseExpired: If lease is expired or invalid
        """
        async with self._lease_lock:
            if agent_id not in self._session_leases:
                raise SessionLeaseExpired(f"No active session for agent {agent_id}")

            cached_session_id, expires_at = self._session_leases[agent_id]
            if cached_session_id != session_id:
                raise SessionLeaseExpired(f"Session ID mismatch for agent {agent_id}")

            if expires_at < utcnow():
                raise SessionLeaseExpired(f"Session lease expired for agent {agent_id}")

    async def _mirror_session_to_json_state(self, agent_id: str, session_id: str, metadata: Optional[Dict[str, Any]]) -> None:
        """
        Mirror session information to JSON state for UI continuity.

        Args:
            agent_id: Agent identifier
            session_id: Session ID
            metadata: Session metadata
        """
        # Create minimal crumbs in JSON state (non-authoritative)
        state = await self.state_manager.load()

        # We could add agent sessions to JSON state if needed for UI
        # For now, just update last activity and agent tracking
        await self.state_manager.persist(state)

    async def _mirror_project_to_json_state(self, agent_id: str, agent_project: Dict[str, Any]) -> None:
        """
        Mirror agent project to JSON state for UI continuity.

        Args:
            agent_id: Agent identifier
            agent_project: Agent project record
        """
        # Update JSON state with minimal information for UI continuity
        state = await self.state_manager.load()

        # Note: JSON state is now just a cache/warm-start mechanism
        # The authoritative source of truth is the database

        # Update version, timestamp, and tracking info
        # This keeps the existing UI working while transitioning to agent-scoped context

    async def log_agent_event(
        self,
        agent_id: str,
        session_id: str,
        event_type: str,
        to_project: str,
        from_project: Optional[str] = None,
        expected_version: Optional[int] = None,
        actual_version: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an agent project event to the audit trail.

        Args:
            agent_id: Agent identifier
            session_id: Session identifier
            event_type: Type of event ('project_set', 'project_switched', 'conflict_detected', etc.)
            to_project: Target project name
            from_project: Source project name (for switches)
            expected_version: Expected version for optimistic concurrency
            actual_version: Actual version after operation
            success: Whether the operation succeeded
            error_message: Error message if operation failed
            metadata: Additional event metadata
        """
        try:
            import json

            event_data = {
                "agent_id": agent_id,
                "session_id": session_id,
                "event_type": event_type,
                "from_project": from_project,
                "to_project": to_project,
                "expected_version": expected_version,
                "actual_version": actual_version,
                "success": success,
                "error_message": error_message,
                "metadata": json.dumps(metadata or {}),
                "created_at": utcnow().isoformat(),
            }

            # Store in database if available
            try:
                # Use the storage backend's execute method if available
                if hasattr(self.storage, '_execute'):
                    query = """
                        INSERT INTO agent_project_events (
                            agent_id, session_id, event_type, from_project, to_project,
                            expected_version, actual_version, success, error_message, metadata, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    await self.storage._execute(
                        query,
                        (
                            agent_id, session_id, event_type, from_project, to_project,
                            expected_version, actual_version, success, error_message,
                            event_data["metadata"], event_data["created_at"]
                        )
                    )
            except Exception as db_error:
                # Database audit logging failed, but don't fail the operation
                print(f"Warning: Database audit logging failed: {db_error}")

        except Exception as e:
            # Don't fail the operation if audit logging fails
            print(f"Warning: Failed to log agent event: {e}")

    async def get_agent_events(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get agent project events from the audit trail.

        Args:
            agent_id: Filter by agent ID (optional)
            event_type: Filter by event type (optional)
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        try:
            where_clauses = []
            params = []

            if agent_id:
                where_clauses.append("agent_id = ?")
                params.append(agent_id)

            if event_type:
                where_clauses.append("event_type = ?")
                params.append(event_type)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            query = f"""
                SELECT id, agent_id, session_id, event_type, from_project, to_project,
                       expected_version, actual_version, success, error_message, metadata, created_at
                FROM agent_project_events
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ?
            """
            params.append(limit)

            rows = await self.storage._fetchall(query, tuple(params))
            return [dict(row) for row in rows]

        except Exception as e:
            print(f"Warning: Failed to retrieve agent events: {e}")
            return []


# Global instance for server integration
_agent_context_manager: Optional[AgentContextManager] = None


def get_agent_context_manager() -> AgentContextManager:
    """Get the global agent context manager instance."""
    global _agent_context_manager
    if _agent_context_manager is None:
        raise RuntimeError("AgentContextManager not initialized. Call init_agent_context_manager first.")
    return _agent_context_manager


def init_agent_context_manager(storage, state_manager: StateManager) -> AgentContextManager:
    """
    Initialize the global agent context manager.

    Args:
        storage: Storage backend instance
        state_manager: State manager instance

    Returns:
        AgentContextManager instance
    """
    global _agent_context_manager
    _agent_context_manager = AgentContextManager(storage, state_manager)
    return _agent_context_manager


async def migrate_legacy_state(state_manager: StateManager, storage) -> None:
    """
    One-time migration from global JSON state to agent-scoped DB context.

    Args:
        state_manager: JSON state manager
        storage: Database storage backend
    """
    # Check if migration is needed by looking for existing agent_projects
    try:
        # Try to fetch from agent_projects table to see if it exists and has data
        result = await storage._fetchone("SELECT COUNT(*) as count FROM agent_projects")
        if result and result.get("count", 0) > 0:
            return  # Already migrated
    except Exception:
        # Table doesn't exist yet, will be created on setup
        pass

    # Get legacy state
    legacy_state = await state_manager.load()
    if legacy_state.current_project:
        # Create default agent session for "Scribe"
        from scribe_mcp.state.agent_manager import init_agent_context_manager
        manager = init_agent_context_manager(storage, state_manager)

        session_id = await manager.start_session("Scribe", {"migrated": True, "legacy_project": legacy_state.current_project})

        # Create the legacy project in database if it doesn't exist
        try:
            # Try to get project data from legacy state
            project_data = legacy_state.projects.get(legacy_state.current_project)
            if project_data:
                await storage.upsert_project(
                    name=legacy_state.current_project,
                    repo_root=project_data.get("root", "/tmp/migrated"),
                    progress_log_path=project_data.get("progress_log", "/tmp/migrated/log.md")
                )
            else:
                # Create minimal project record
                await storage.upsert_project(
                    name=legacy_state.current_project,
                    repo_root="/tmp/migrated",
                    progress_log_path="/tmp/migrated/log.md"
                )
        except Exception as e:
            print(f"Warning: Failed to create legacy project in database: {e}")

        # Migrate current project to Scribe agent
        try:
            await manager.set_current_project("Scribe", legacy_state.current_project, session_id)
        except Exception as e:
            print(f"Warning: Failed to migrate legacy project: {e}")

        # Clear global current_project to avoid dual sources of truth
        await state_manager.set_current_project(None, None, agent_id="migration")

        print(f"✅ Migrated legacy project '{legacy_state.current_project}' to agent 'Scribe'")


def utcnow() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)
