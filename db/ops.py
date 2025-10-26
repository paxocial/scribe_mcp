"""Database helpers for Scribe MCP."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import asyncpg

from scribe_mcp.storage.models import ProjectRecord
from scribe_mcp.utils.time import format_utc, utcnow


async def upsert_project(
    pool: asyncpg.pool.Pool,
    *,
    name: str,
    repo_root: str,
    progress_log_path: str,
) -> ProjectRecord:
    """Insert or fetch a project entry."""
    query = """
        INSERT INTO scribe_projects (name, repo_root, progress_log_path)
        VALUES ($1, $2, $3)
        ON CONFLICT (name)
        DO UPDATE SET repo_root = EXCLUDED.repo_root,
                      progress_log_path = EXCLUDED.progress_log_path
        RETURNING id, name, repo_root, progress_log_path;
    """
    row = await pool.fetchrow(query, name, repo_root, progress_log_path)
    return ProjectRecord(
        id=row["id"],
        name=row["name"],
        repo_root=row["repo_root"],
        progress_log_path=row["progress_log_path"],
    )


async def fetch_project_by_name(
    pool: asyncpg.pool.Pool,
    *,
    name: str,
) -> Optional[ProjectRecord]:
    """Retrieve a project record by name."""
    query = """
        SELECT id, name, repo_root, progress_log_path
        FROM scribe_projects
        WHERE name = $1;
    """
    row = await pool.fetchrow(query, name)
    if not row:
        return None
    return ProjectRecord(
        id=row["id"],
        name=row["name"],
        repo_root=row["repo_root"],
        progress_log_path=row["progress_log_path"],
    )


async def list_projects(pool: asyncpg.pool.Pool) -> List[ProjectRecord]:
    """Return all registered projects."""
    query = """
        SELECT id, name, repo_root, progress_log_path
        FROM scribe_projects
        ORDER BY name;
    """
    rows = await pool.fetch(query)
    return [
        ProjectRecord(
            id=row["id"],
            name=row["name"],
            repo_root=row["repo_root"],
            progress_log_path=row["progress_log_path"],
        )
        for row in rows
    ]


async def insert_entry(
    pool: asyncpg.pool.Pool,
    *,
    entry_id: str,
    project_id: int,
    ts,
    emoji: str,
    agent: Optional[str],
    message: str,
    meta: Optional[Dict[str, Any]],
    raw_line: str,
    sha256: str,
) -> None:
    """Insert a log entry and bump metrics."""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO scribe_entries
                        (id, project_id, ts, emoji, agent, message, meta, raw_line, sha256)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id) DO NOTHING;
                    """,
                    entry_id,
                    project_id,
                    ts,
                    emoji,
                    agent,
                    message,
                    meta,
                    raw_line,
                    sha256,
                )
                await _update_metrics(conn, project_id, emoji)
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Database insert failed: {exc}") from exc


async def fetch_recent_entries(
    pool: asyncpg.pool.Pool,
    *,
    project_id: int,
    limit: int,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Fetch the last `limit` entries for a project."""
    filters = filters or {}
    clauses: List[str] = []
    params: List[Any] = []
    index = 1

    clauses.append(f"project_id = ${index}")
    params.append(project_id)
    index += 1

    agent = filters.get("agent")
    if agent:
        clauses.append(f"agent = ${index}")
        params.append(agent)
        index += 1

    emoji = filters.get("emoji")
    if emoji:
        clauses.append(f"emoji = ${index}")
        params.append(emoji)
        index += 1

    where_clause = " AND ".join(clauses) if clauses else "TRUE"
    limit_index = index
    params.append(limit)
    query = f"""
        SELECT id, ts, emoji, agent, message, meta, raw_line
        FROM scribe_entries
        WHERE {where_clause}
        ORDER BY ts DESC
        LIMIT ${limit_index};
    """
    rows = await pool.fetch(query, *params)
    result: List[Dict[str, Any]] = []
    for row in rows:
        ts_value = row["ts"]
        ts_str = format_utc(ts_value) if ts_value else None
        result.append(
            {
                "id": row["id"],
                "ts": ts_str,
                "emoji": row["emoji"],
                "agent": row["agent"],
                "message": row["message"],
                "meta": row["meta"],
                "raw_line": row["raw_line"],
            }
        )
    return result


async def query_entries(
    pool: asyncpg.pool.Pool,
    *,
    project_id: int,
    limit: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    agents: Optional[List[str]] = None,
    emojis: Optional[List[str]] = None,
    meta_filters: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Advanced search against scribe_entries."""
    limit = max(1, min(limit, 500))
    fetch_limit = min(max(limit * 3, limit), 1000)

    clauses: List[str] = ["project_id = $1"]
    params: List[Any] = [project_id]
    index = 2

    if start:
        clauses.append(f"ts >= ${index}")
        params.append(start)
        index += 1
    if end:
        clauses.append(f"ts <= ${index}")
        params.append(end)
        index += 1
    if agents:
        clauses.append(f"agent = ANY(${index})")
        params.append(agents)
        index += 1
    if emojis:
        clauses.append(f"emoji = ANY(${index})")
        params.append(emojis)
        index += 1
    if meta_filters:
        clauses.append(f"meta @> ${index}::jsonb")
        params.append(meta_filters)
        index += 1

    where_clause = " AND ".join(clauses)
    rows = await pool.fetch(
        f"""
        SELECT id, ts, emoji, agent, message, meta, raw_line
        FROM scribe_entries
        WHERE {where_clause}
        ORDER BY ts DESC
        LIMIT ${index};
        """,
        *params,
        fetch_limit,
    )
    output: List[Dict[str, Any]] = []
    for row in rows:
        ts_value = row["ts"]
        ts_str = format_utc(ts_value) if ts_value else None
        output.append(
            {
                "id": row["id"],
                "ts": ts_str,
                "emoji": row["emoji"],
                "agent": row["agent"],
                "message": row["message"],
                "meta": row["meta"],
                "raw_line": row["raw_line"],
            }
        )
    return output


async def record_doc_change(
    pool: asyncpg.pool.Pool,
    *,
    project_id: int,
    doc: str,
    section: Optional[str],
    action: str,
    agent: Optional[str],
    metadata: Optional[Dict[str, Any]],
    sha_before: str,
    sha_after: str,
) -> None:
    query_insert = """
        INSERT INTO doc_changes
            (project_id, doc_name, section, action, agent, metadata, sha_before, sha_after)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
    """
    query_prune = """
        DELETE FROM doc_changes
        WHERE id IN (
            SELECT id FROM doc_changes
            WHERE project_id = $1
            ORDER BY created_at DESC
            OFFSET 500
        );
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                query_insert,
                project_id,
                doc,
                section,
                action,
                agent,
                metadata,
                sha_before,
                sha_after,
            )
            await conn.execute(query_prune, project_id)


async def _update_metrics(
    conn: asyncpg.Connection,
    project_id: int,
    emoji: str,
) -> None:
    """Increment metrics counters based on emoji."""
    emoji_map = {
        "✅": "success_count",
        "⚠️": "warn_count",
        "❌": "error_count",
    }
    column = emoji_map.get(emoji)
    increment_columns = ["total_entries = total_entries + 1"]
    if column:
        increment_columns.append(f"{column} = {column} + 1")

    set_expr = ", ".join(increment_columns)
    await conn.execute(
        f"""
        INSERT INTO scribe_metrics (project_id, total_entries, last_update)
        VALUES ($1, 1, $2)
        ON CONFLICT (project_id)
        DO UPDATE SET {set_expr},
                      last_update = EXCLUDED.last_update;
        """,
        project_id,
        utcnow(),
    )


# Agent session and project context management operations
async def upsert_agent_session(
    pool: asyncpg.pool.Pool,
    *,
    agent_id: str,
    session_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Create or update an agent session."""
    query = """
        INSERT INTO agent_sessions (id, agent_id, started_at, last_active_at, status, metadata)
        VALUES ($1, $2, NOW(), NOW(), 'active', $3)
        ON CONFLICT (id) DO UPDATE SET
            last_active_at = EXCLUDED.last_active_at,
            status = 'active',
            metadata = EXCLUDED.metadata;
    """
    await pool.execute(query, session_id, agent_id, metadata)


async def heartbeat_session(pool: asyncpg.pool.Pool, *, session_id: str) -> None:
    """Update session last_active_at timestamp."""
    query = """
        UPDATE agent_sessions
        SET last_active_at = NOW()
        WHERE id = $1 AND status = 'active';
    """
    await pool.execute(query, session_id)


async def end_session(pool: asyncpg.pool.Pool, *, session_id: str) -> None:
    """Mark a session as expired."""
    query = """
        UPDATE agent_sessions
        SET status = 'expired', last_active_at = NOW()
        WHERE id = $1;
    """
    await pool.execute(query, session_id)


async def get_agent_project(pool: asyncpg.pool.Pool, *, agent_id: str) -> Optional[Dict[str, Any]]:
    """Get an agent's current project with version info."""
    query = """
        SELECT agent_id, project_name, version, updated_at, updated_by, session_id
        FROM agent_projects
        WHERE agent_id = $1;
    """
    row = await pool.fetchrow(query, agent_id)
    if not row:
        return None

    return {
        "agent_id": row["agent_id"],
        "project_name": row["project_name"],
        "version": row["version"],
        "updated_at": row["updated_at"].isoformat(),
        "updated_by": row["updated_by"],
        "session_id": row["session_id"]
    }


async def set_agent_project(
    pool: asyncpg.pool.Pool,
    *,
    agent_id: str,
    project_name: Optional[str],
    expected_version: Optional[int],
    updated_by: str,
    session_id: str,
) -> Dict[str, Any]:
    """Set an agent's current project with optimistic concurrency control."""

    if expected_version is not None:
        # Optimistic concurrency check
        query = """
            UPDATE agent_projects
            SET project_name = $2, version = version + 1, updated_at = NOW(),
                updated_by = $3, session_id = $4
            WHERE agent_id = $1 AND version = $5
            RETURNING agent_id, project_name, version, updated_at, updated_by, session_id;
        """
        try:
            row = await pool.fetchrow(query, agent_id, project_name, updated_by, session_id, expected_version)
        except asyncpg.NoDataReturned:
            from scribe_mcp.storage.base import ConflictError
            raise ConflictError(f"Version conflict for agent {agent_id}: expected version {expected_version}")

        return {
            "agent_id": row["agent_id"],
            "project_name": row["project_name"],
            "version": row["version"],
            "updated_at": row["updated_at"].isoformat(),
            "updated_by": row["updated_by"],
            "session_id": row["session_id"]
        }
    else:
        # First time or no version check
        query = """
            INSERT INTO agent_projects (agent_id, project_name, version, updated_by, session_id)
            VALUES ($1, $2, 1, $3, $4)
            ON CONFLICT (agent_id) DO UPDATE SET
                project_name = EXCLUDED.project_name,
                version = agent_projects.version + 1,
                updated_at = EXCLUDED.updated_at,
                updated_by = EXCLUDED.updated_by,
                session_id = EXCLUDED.session_id
            RETURNING agent_id, project_name, version, updated_at, updated_by, session_id;
        """
        row = await pool.fetchrow(query, agent_id, project_name, updated_by, session_id)

        return {
            "agent_id": row["agent_id"],
            "project_name": row["project_name"],
            "version": row["version"],
            "updated_at": row["updated_at"].isoformat(),
            "updated_by": row["updated_by"],
            "session_id": row["session_id"]
        }
