"""SQLite storage backend (default)."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.storage.models import (
    ProjectRecord, DevPlanRecord, PhaseRecord, MilestoneRecord,
    BenchmarkRecord, ChecklistRecord, PerformanceMetricsRecord,
    DocumentSectionRecord, CustomTemplateRecord, DocumentChangeRecord, SyncStatusRecord
)
from scribe_mcp.utils.time import format_utc, utcnow
from scribe_mcp.utils.search import message_matches

SQLITE_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = 5000


class SQLiteStorage(StorageBackend):
    """SQLite-backed persistence with lazy connections."""

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path).expanduser()
        self._init_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._initialised = False

    async def setup(self) -> None:
        await self._initialise()

    async def close(self) -> None:  # pragma: no cover - nothing persistent to close
        # Connections are short-lived; nothing to do.
        return None

    async def upsert_project(
        self,
        *,
        name: str,
        repo_root: str,
        progress_log_path: str,
    ) -> ProjectRecord:
        await self._initialise()
        async with self._write_lock:
            await self._execute(
            """
            INSERT INTO scribe_projects (name, repo_root, progress_log_path)
            VALUES (?, ?, ?)
            ON CONFLICT(name)
            DO UPDATE SET repo_root = excluded.repo_root,
                          progress_log_path = excluded.progress_log_path;
            """,
            (name, repo_root, progress_log_path),
        )
        row = await self._fetchone(
            """
            SELECT id, name, repo_root, progress_log_path
            FROM scribe_projects
            WHERE name = ?;
            """,
            (name,),
        )
        return ProjectRecord(
            id=row["id"],
            name=row["name"],
            repo_root=row["repo_root"],
            progress_log_path=row["progress_log_path"],
        )

    async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
        await self._initialise()
        row = await self._fetchone(
            """
            SELECT id, name, repo_root, progress_log_path
            FROM scribe_projects
            WHERE name = ?;
            """,
            (name,),
        )
        if not row:
            return None
        return ProjectRecord(
            id=row["id"],
            name=row["name"],
            repo_root=row["repo_root"],
            progress_log_path=row["progress_log_path"],
        )

    async def list_projects(self) -> List[ProjectRecord]:
        await self._initialise()
        rows = await self._fetchall(
            """
            SELECT id, name, repo_root, progress_log_path
            FROM scribe_projects
            ORDER BY name;
            """
        )
        records: List[ProjectRecord] = []
        for row in rows:
            records.append(
                ProjectRecord(
                    id=row["id"],
                    name=row["name"],
                    repo_root=row["repo_root"],
                    progress_log_path=row["progress_log_path"],
                )
            )
        return records

    async def delete_project(self, name: str) -> bool:
        """Delete a project and all associated data with proper cascade handling."""
        await self._initialise()

        # First check if project exists
        project = await self.fetch_project(name)
        if not project:
            return False

        async with self._write_lock:
            # Delete project and all related data using proper cascade order
            # SQLite foreign key constraints should handle most of this automatically,
            # but we'll be explicit for safety and clarity

            # Delete agent project associations
            await self._execute(
                "DELETE FROM agent_projects WHERE project_name = ?;",
                (name,),
            )

            # Delete global log entries for this project (if they exist)
            # Note: global_log_entries uses project_id, but table is currently empty
            # await self._execute(
            #     "DELETE FROM global_log_entries WHERE project_id = ?;",
            #     (name,),
            # )

            # Due to foreign key constraints with ON DELETE CASCADE,
            # deleting the project should automatically clean up:
            # - scribe_entries
            # - dev_plans -> phases -> milestones
            # - benchmarks, checklists, performance_metrics
            # - documents -> document_sections, document_changes
            # - custom_templates, sync_status
            # - scribe_metrics

            # Delete the main project record (this will cascade to related tables)
            await self._execute(
                "DELETE FROM scribe_projects WHERE name = ?;",
                (name,),
            )

            # Verify deletion
            remaining = await self._fetchone(
                "SELECT COUNT(*) as count FROM scribe_projects WHERE name = ?;",
                (name,),
            )

            return remaining["count"] == 0

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
        await self._initialise()
        ts_iso = ts.isoformat()
        meta_json = json.dumps(meta or {}, sort_keys=True)
        async with self._write_lock:
            await self._execute(
                """
                INSERT OR IGNORE INTO scribe_entries
                    (id, project_id, ts, emoji, agent, message, meta, raw_line, sha256, ts_iso)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    entry_id,
                    project.id,
                    format_utc(ts),
                    emoji,
                    agent,
                    message,
                    meta_json,
                    raw_line,
                    sha256,
                    ts_iso,
                ),
            )
            await self._execute(
                """
                INSERT INTO scribe_metrics (project_id, total_entries, success_count, warn_count, error_count, last_update)
                VALUES (?, 1, ?, ?, ?, ?)
                ON CONFLICT(project_id)
                DO UPDATE SET total_entries = scribe_metrics.total_entries + 1,
                              success_count = scribe_metrics.success_count + excluded.success_count,
                              warn_count = scribe_metrics.warn_count + excluded.warn_count,
                              error_count = scribe_metrics.error_count + excluded.error_count,
                              last_update = excluded.last_update;
                """,
                (
                    project.id,
                    1 if emoji == "✅" else 0,
                    1 if emoji == "⚠️" else 0,
                    1 if emoji == "❌" else 0,
                    utcnow().isoformat(),
                ),
            )

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
        await self._initialise()
        meta_json = json.dumps(metadata or {}, sort_keys=True)
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO doc_changes
                    (project_id, doc_name, section, action, agent, metadata, sha_before, sha_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    project.id,
                    doc,
                    section,
                    action,
                    agent,
                    meta_json,
                    sha_before,
                    sha_after,
                ),
            )
            await self._execute(
                """
                DELETE FROM doc_changes
                WHERE id IN (
                    SELECT id FROM doc_changes
                    WHERE project_id = ?
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET 500
                );
                """,
                (project.id,),
            )

    async def fetch_recent_entries(
        self,
        *,
        project: ProjectRecord,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        await self._initialise()
        filters = filters or {}
        clauses = ["project_id = ?"]
        params: List[Any] = [project.id]

        agent = filters.get("agent")
        if agent:
            clauses.append("agent = ?")
            params.append(agent)

        emoji = filters.get("emoji")
        if emoji:
            clauses.append("emoji = ?")
            params.append(emoji)

        where_clause = " AND ".join(clauses)
        rows = await self._fetchall(
            f"""
            SELECT id, ts, emoji, agent, message, meta, raw_line
            FROM scribe_entries
            WHERE {where_clause}
            ORDER BY ts_iso DESC
            LIMIT ? OFFSET ?;
            """,
            (*params, limit, offset),
        )
        results: List[Dict[str, Any]] = []
        for row in rows:
            meta_value = json.loads(row["meta"]) if row["meta"] else {}
            results.append(
                {
                    "id": row["id"],
                    "ts": row["ts"],
                    "emoji": row["emoji"],
                    "agent": row["agent"],
                    "message": row["message"],
                    "meta": meta_value,
                    "raw_line": row["raw_line"],
                }
            )
        return results

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
        await self._initialise()
        limit = max(1, min(limit, 500))
        fetch_limit = min(max(limit * 3, limit), 1000)

        clauses = ["project_id = ?"]
        params: List[Any] = [project.id]

        if start:
            clauses.append("ts_iso >= ?")
            params.append(start)
        if end:
            clauses.append("ts_iso <= ?")
            params.append(end)

        if agents:
            agent_placeholders = ", ".join("?" for _ in agents)
            clauses.append(f"agent IN ({agent_placeholders})")
            params.extend(agents)

        if emojis:
            emoji_placeholders = ", ".join("?" for _ in emojis)
            clauses.append(f"emoji IN ({emoji_placeholders})")
            params.extend(emojis)

        if meta_filters:
            for key, value in sorted(meta_filters.items()):
                clauses.append("json_extract(meta, ?) = ?")
                params.append(f"$.{key}")
                params.append(value)

        where_clause = " AND ".join(clauses)
        rows = await self._fetchall(
            f"""
            SELECT id, ts, ts_iso, emoji, agent, message, meta, raw_line
            FROM scribe_entries
            WHERE {where_clause}
            ORDER BY ts_iso DESC
            LIMIT ? OFFSET ?;
            """,
            (*params, fetch_limit, offset),
        )

        results: List[Dict[str, Any]] = []
        for row in rows:
            meta_value = json.loads(row["meta"]) if row["meta"] else {}
            entry = {
                "id": row["id"],
                "ts": row["ts"],
                "emoji": row["emoji"],
                "agent": row["agent"],
                "message": row["message"],
                "meta": meta_value,
                "raw_line": row["raw_line"],
            }
            if not message_matches(
                entry["message"],
                message,
                mode=message_mode,
                case_sensitive=case_sensitive,
            ):
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    async def count_entries(
        self,
        project: ProjectRecord,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Efficient count implementation using COUNT query."""
        await self._initialise()
        filters = filters or {}
        clauses = ["project_id = ?"]
        params: List[Any] = [project.id]

        agent = filters.get("agent")
        if agent:
            clauses.append("agent = ?")
            params.append(agent)

        emoji = filters.get("emoji")
        if emoji:
            clauses.append("emoji = ?")
            params.append(emoji)

        where_clause = " AND ".join(clauses)
        row = await self._fetchone(
            f"""
            SELECT COUNT(*) as count
            FROM scribe_entries
            WHERE {where_clause};
            """,
            tuple(params),
        )
        return row["count"] if row else 0

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
        """Efficient count for query_entries."""
        await self._initialise()

        clauses = ["project_id = ?"]
        params: List[Any] = [project.id]

        if start:
            clauses.append("ts_iso >= ?")
            params.append(start)
        if end:
            clauses.append("ts_iso <= ?")
            params.append(end)

        if agents:
            agent_placeholders = ", ".join("?" for _ in agents)
            clauses.append(f"agent IN ({agent_placeholders})")
            params.extend(agents)

        if emojis:
            emoji_placeholders = ", ".join("?" for _ in emojis)
            clauses.append(f"emoji IN ({emoji_placeholders})")
            params.extend(emojis)

        if meta_filters:
            for key, value in sorted(meta_filters.items()):
                clauses.append("json_extract(meta, ?) = ?")
                params.append(f"$.{key}")
                params.append(value)

        where_clause = " AND ".join(clauses)
        row = await self._fetchone(
            f"""
            SELECT COUNT(*) as count
            FROM scribe_entries
            WHERE {where_clause};
            """,
            tuple(params),
        )

        count = row["count"] if row else 0

        # Apply message filtering if needed (can't do this efficiently in SQL for complex patterns)
        if message:
            # Need to fetch and filter messages for counting
            # This is less efficient but necessary for message pattern matching
            fetch_limit = min(count, 10000)  # Limit to prevent excessive memory usage
            rows = await self._fetchall(
                f"""
                SELECT message
                FROM scribe_entries
                WHERE {where_clause}
                LIMIT ?;
                """,
                (*params, fetch_limit),
            )

            matching_count = 0
            for row in rows:
                if message_matches(
                    row["message"],
                    message,
                    mode=message_mode,
                    case_sensitive=case_sensitive,
                ):
                    matching_count += 1

            return matching_count

        return count

    async def _initialise(self) -> None:
        async with self._init_lock:
            if self._initialised:
                return
            await asyncio.to_thread(self._path.parent.mkdir, parents=True, exist_ok=True)
            await self._execute_many(
                [
                    """
                    CREATE TABLE IF NOT EXISTS scribe_projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        repo_root TEXT NOT NULL,
                        progress_log_path TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS scribe_entries (
                        id TEXT PRIMARY KEY,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        ts TEXT NOT NULL,
                        ts_iso TEXT NOT NULL,
                        emoji TEXT NOT NULL,
                        agent TEXT,
                        message TEXT NOT NULL,
                        meta TEXT,
                        raw_line TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS scribe_metrics (
                        project_id INTEGER PRIMARY KEY REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        total_entries INTEGER NOT NULL DEFAULT 0,
                        success_count INTEGER NOT NULL DEFAULT 0,
                        warn_count INTEGER NOT NULL DEFAULT 0,
                        error_count INTEGER NOT NULL DEFAULT 0,
                        last_update TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS agent_sessions (
                        id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_active_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        status TEXT NOT NULL CHECK (status IN ('active','expired')) DEFAULT 'active',
                        metadata TEXT
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent ON agent_sessions(agent_id);
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS agent_projects (
                        agent_id TEXT PRIMARY KEY,
                        project_name TEXT,
                        version INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_by TEXT,
                        session_id TEXT,
                        FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE SET NULL
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_projects_updated_at ON agent_projects(updated_at DESC);
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS agent_project_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        event_type TEXT NOT NULL CHECK (event_type IN ('project_set', 'project_switched', 'session_started', 'session_ended', 'conflict_detected')),
                        from_project TEXT,
                        to_project TEXT NOT NULL,
                        expected_version INTEGER,
                        actual_version INTEGER,
                        success BOOLEAN NOT NULL DEFAULT 1,
                        error_message TEXT,
                        metadata TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_project_events_agent_id ON agent_project_events(agent_id);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_project_events_created_at ON agent_project_events(created_at);
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS doc_changes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        doc_name TEXT NOT NULL,
                        section TEXT,
                        action TEXT NOT NULL,
                        agent TEXT,
                        metadata TEXT,
                        sha_before TEXT,
                        sha_after TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_doc_changes_project ON doc_changes(project_id, created_at DESC);
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS dev_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        project_name TEXT NOT NULL,
                        plan_type TEXT NOT NULL CHECK (plan_type IN ('architecture', 'phase_plan', 'checklist', 'progress_log')),
                        file_path TEXT NOT NULL,
                        version TEXT NOT NULL DEFAULT '1.0',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT,
                        UNIQUE(project_id, plan_type)
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS phases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        dev_plan_id INTEGER NOT NULL REFERENCES dev_plans(id) ON DELETE CASCADE,
                        phase_number INTEGER NOT NULL,
                        phase_name TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('planned', 'in_progress', 'completed', 'blocked')) DEFAULT 'planned',
                        start_date TEXT,
                        end_date TEXT,
                        deliverables_count INTEGER NOT NULL DEFAULT 0,
                        deliverables_completed INTEGER NOT NULL DEFAULT 0,
                        confidence_score REAL NOT NULL DEFAULT 0.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
                        metadata TEXT,
                        UNIQUE(project_id, phase_number)
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS milestones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL,
                        milestone_name TEXT NOT NULL,
                        description TEXT,
                        status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'overdue')) DEFAULT 'pending',
                        target_date TEXT,
                        completed_date TEXT,
                        evidence_url TEXT,
                        metadata TEXT
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS benchmarks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        benchmark_type TEXT NOT NULL CHECK (benchmark_type IN ('hash_performance', 'throughput', 'latency', 'stress_test', 'integrity', 'concurrency')),
                        test_name TEXT NOT NULL,
                        metric_name TEXT NOT NULL,
                        metric_value REAL NOT NULL,
                        metric_unit TEXT NOT NULL,
                        test_parameters TEXT,
                        environment_info TEXT,
                        test_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        requirement_target REAL,
                        requirement_met BOOLEAN NOT NULL DEFAULT FALSE
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS checklists (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL,
                        checklist_item TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'blocked')) DEFAULT 'pending',
                        acceptance_criteria TEXT NOT NULL,
                        proof_required BOOLEAN NOT NULL DEFAULT TRUE,
                        proof_url TEXT,
                        assignee TEXT,
                        priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        completed_at TEXT,
                        metadata TEXT
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS performance_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        metric_category TEXT NOT NULL CHECK (metric_category IN ('development', 'testing', 'deployment', 'operations')),
                        metric_name TEXT NOT NULL,
                        metric_value REAL NOT NULL,
                        metric_unit TEXT NOT NULL,
                        baseline_value REAL,
                        improvement_percentage REAL,
                        collection_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT
                    );
                    """,
                    # Indexes for performance
                    "CREATE INDEX IF NOT EXISTS idx_entries_project_ts ON scribe_entries(project_id, ts_iso DESC);",
                    "CREATE INDEX IF NOT EXISTS idx_dev_plans_project_type ON dev_plans(project_id, plan_type);",
                    "CREATE INDEX IF NOT EXISTS idx_phases_project_status ON phases(project_id, status);",
                    "CREATE INDEX IF NOT EXISTS idx_milestones_project_status ON milestones(project_id, status);",
                    "CREATE INDEX IF NOT EXISTS idx_benchmarks_project_type ON benchmarks(project_id, benchmark_type);",
                    "CREATE INDEX IF NOT EXISTS idx_benchmarks_timestamp ON benchmarks(test_timestamp DESC);",
                    "CREATE INDEX IF NOT EXISTS idx_checklists_project_status ON checklists(project_id, status);",
                    "CREATE INDEX IF NOT EXISTS idx_checklists_phase ON checklists(phase_id);",
                    "CREATE INDEX IF NOT EXISTS idx_metrics_project_category ON performance_metrics(project_id, metric_category);",
                    "CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON performance_metrics(collection_timestamp DESC);",
                    # Document Management 2.0 Tables
                    """
                    CREATE TABLE IF NOT EXISTS document_sections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        document_type TEXT NOT NULL,
                        section_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        file_hash TEXT NOT NULL,
                        metadata TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(project_id, document_type, section_id)
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS custom_templates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        template_name TEXT NOT NULL,
                        template_content TEXT NOT NULL,
                        variables TEXT,
                        is_global BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(project_id, template_name)
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS document_changes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        document_path TEXT NOT NULL,
                        change_type TEXT NOT NULL,
                        old_content_hash TEXT,
                        new_content_hash TEXT,
                        change_summary TEXT NOT NULL,
                        metadata TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS sync_status (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        file_path TEXT NOT NULL,
                        last_sync_at TEXT,
                        last_file_hash TEXT,
                        last_db_hash TEXT,
                        sync_status TEXT NOT NULL DEFAULT 'synced',
                        conflict_details TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(project_id, file_path)
                    );
                    """,
                    # Document Management 2.0 Indexes
                    "CREATE INDEX IF NOT EXISTS idx_document_sections_project ON document_sections(project_id);",
                    "CREATE INDEX IF NOT EXISTS idx_document_sections_updated ON document_sections(updated_at);",
                    "CREATE INDEX IF NOT EXISTS idx_document_changes_project ON document_changes(project_id);",
                    "CREATE INDEX IF NOT EXISTS idx_document_changes_created ON document_changes(created_at);",
                    "CREATE INDEX IF NOT EXISTS idx_sync_status_project ON sync_status(project_id);",
                    "CREATE INDEX IF NOT EXISTS idx_sync_status_status ON sync_status(sync_status);",
                    # Full-text search for document content
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS document_sections_fts
                    USING fts5(document_type, section_id, content, content=document_sections, content_rowid=id)
                    """,
                    """
                    CREATE TRIGGER IF NOT EXISTS document_sections_fts_insert
                    AFTER INSERT ON document_sections BEGIN
                        INSERT INTO document_sections_fts(rowid, document_type, section_id, content)
                        VALUES (new.id, new.document_type, new.section_id, new.content);
                    END
                    """,
                    """
                    CREATE TRIGGER IF NOT EXISTS document_sections_fts_delete
                    AFTER DELETE ON document_sections BEGIN
                        INSERT INTO document_sections_fts(document_sections_fts, rowid, document_type, section_id, content)
                        VALUES ('delete', old.id, old.document_type, old.section_id, old.content);
                    END
                    """,
                    """
                    CREATE TRIGGER IF NOT EXISTS document_sections_fts_update
                    AFTER UPDATE ON document_sections BEGIN
                        INSERT INTO document_sections_fts(document_sections_fts, rowid, document_type, section_id, content)
                        VALUES ('delete', old.id, old.document_type, old.section_id, old.content);
                        INSERT INTO document_sections_fts(rowid, document_type, section_id, content)
                        VALUES (new.id, new.document_type, new.section_id, new.content);
                    END
                    """,
                ]
            )
            self._initialised = True

    async def _execute(self, query: str, params: tuple[Any, ...]) -> None:
        await asyncio.to_thread(self._execute_sync, query, params)

    def _execute_sync(self, query: str, params: tuple[Any, ...]) -> None:
        conn = self._connect()
        try:
            conn.execute(query, params)
            conn.commit()
        finally:
            conn.close()

    async def _execute_many(self, statements: List[str]) -> None:
        await asyncio.to_thread(self._execute_many_sync, statements)

    def _execute_many_sync(self, statements: List[str]) -> None:
        conn = self._connect()
        try:
            for statement in statements:
                conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

    async def _fetchone(self, query: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        return await asyncio.to_thread(self._fetchone_sync, query, params)

    def _fetchone_sync(self, query: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        conn = self._connect()
        try:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return row
        finally:
            conn.close()

    async def _fetchall(self, query: str, params: tuple[Any, ...] | tuple = ()) -> List[sqlite3.Row]:
        return await asyncio.to_thread(self._fetchall_sync, query, params)

    def _fetchall_sync(self, query: str, params: tuple[Any, ...] | tuple = ()) -> List[sqlite3.Row]:
        conn = self._connect()
        try:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return rows
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=SQLITE_TIMEOUT_SECONDS,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")
        return conn

    # Development Plan Tracking Methods

    async def upsert_dev_plan(
        self,
        *,
        project_id: int,
        project_name: str,
        plan_type: str,
        file_path: str,
        version: str = "1.0",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DevPlanRecord:
        """Insert or update a development plan record."""
        await self._initialise()
        meta_json = json.dumps(metadata or {}, sort_keys=True)
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO dev_plans (project_id, project_name, plan_type, file_path, version, metadata, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, plan_type)
                DO UPDATE SET file_path = excluded.file_path,
                              version = excluded.version,
                              metadata = excluded.metadata,
                              updated_at = excluded.updated_at;
                """,
                (project_id, project_name, plan_type, file_path, version, meta_json, utcnow().isoformat()),
            )
        row = await self._fetchone(
            """
            SELECT id, project_id, project_name, plan_type, file_path, version, created_at, updated_at, metadata
            FROM dev_plans
            WHERE project_id = ? AND plan_type = ?;
            """,
            (project_id, plan_type),
        )
        return DevPlanRecord(
            id=row["id"],
            project_id=row["project_id"],
            project_name=row["project_name"],
            plan_type=row["plan_type"],
            file_path=row["file_path"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
        )

    async def upsert_phase(
        self,
        *,
        project_id: int,
        dev_plan_id: int,
        phase_number: int,
        phase_name: str,
        status: str = "planned",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        deliverables_count: int = 0,
        deliverables_completed: int = 0,
        confidence_score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PhaseRecord:
        """Insert or update a phase record."""
        await self._initialise()
        meta_json = json.dumps(metadata or {}, sort_keys=True)
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO phases (project_id, dev_plan_id, phase_number, phase_name, status,
                                 start_date, end_date, deliverables_count, deliverables_completed,
                                 confidence_score, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, phase_number)
                DO UPDATE SET phase_name = excluded.phase_name,
                              status = excluded.status,
                              start_date = excluded.start_date,
                              end_date = excluded.end_date,
                              deliverables_count = excluded.deliverables_count,
                              deliverables_completed = excluded.deliverables_completed,
                              confidence_score = excluded.confidence_score,
                              metadata = excluded.metadata;
                """,
                (project_id, dev_plan_id, phase_number, phase_name, status,
                 start_date, end_date, deliverables_count, deliverables_completed,
                 confidence_score, meta_json),
            )
        row = await self._fetchone(
            """
            SELECT id, project_id, dev_plan_id, phase_number, phase_name, status,
                   start_date, end_date, deliverables_count, deliverables_completed,
                   confidence_score, metadata
            FROM phases
            WHERE project_id = ? AND phase_number = ?;
            """,
            (project_id, phase_number),
        )
        return PhaseRecord(
            id=row["id"],
            project_id=row["project_id"],
            dev_plan_id=row["dev_plan_id"],
            phase_number=row["phase_number"],
            phase_name=row["phase_name"],
            status=row["status"],
            start_date=datetime.fromisoformat(row["start_date"]) if row["start_date"] else None,
            end_date=datetime.fromisoformat(row["end_date"]) if row["end_date"] else None,
            deliverables_count=row["deliverables_count"],
            deliverables_completed=row["deliverables_completed"],
            confidence_score=row["confidence_score"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
        )

    async def store_benchmark(
        self,
        *,
        project_id: int,
        benchmark_type: str,
        test_name: str,
        metric_name: str,
        metric_value: float,
        metric_unit: str,
        test_parameters: Optional[Dict[str, Any]] = None,
        environment_info: Optional[Dict[str, Any]] = None,
        requirement_target: Optional[float] = None,
    ) -> BenchmarkRecord:
        """Store a benchmark result."""
        await self._initialise()
        test_params_json = json.dumps(test_parameters or {}, sort_keys=True)
        env_info_json = json.dumps(environment_info or {}, sort_keys=True)
        requirement_met = (requirement_target is not None and
                          ((benchmark_type in ['throughput', 'hash_performance'] and metric_value >= requirement_target) or
                           (benchmark_type in ['latency', 'time'] and metric_value <= requirement_target) or
                           (requirement_target > 0 and metric_value <= requirement_target) or
                           (requirement_target < 0 and metric_value >= requirement_target)))

        row = await self._fetchone(
            """
            INSERT INTO benchmarks (project_id, benchmark_type, test_name, metric_name,
                                   metric_value, metric_unit, test_parameters, environment_info,
                                   requirement_target, requirement_met)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id, project_id, benchmark_type, test_name, metric_name, metric_value,
                    metric_unit, test_parameters, environment_info, test_timestamp,
                    requirement_target, requirement_met;
            """,
            (project_id, benchmark_type, test_name, metric_name, metric_value,
             metric_unit, test_params_json, env_info_json, requirement_target, requirement_met),
        )
        return BenchmarkRecord(
            id=row["id"],
            project_id=row["project_id"],
            benchmark_type=row["benchmark_type"],
            test_name=row["test_name"],
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            metric_unit=row["metric_unit"],
            test_parameters=json.loads(row["test_parameters"]) if row["test_parameters"] else None,
            environment_info=json.loads(row["environment_info"]) if row["environment_info"] else None,
            test_timestamp=datetime.fromisoformat(row["test_timestamp"]),
            requirement_target=row["requirement_target"],
            requirement_met=bool(row["requirement_met"]),
        )

    async def get_project_benchmarks(
        self,
        *,
        project_id: int,
        benchmark_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[BenchmarkRecord]:
        """Get benchmark results for a project."""
        await self._initialise()
        params = [project_id]
        query = """
            SELECT id, project_id, benchmark_type, test_name, metric_name, metric_value,
                   metric_unit, test_parameters, environment_info, test_timestamp,
                   requirement_target, requirement_met
            FROM benchmarks
            WHERE project_id = ?
        """

        if benchmark_type:
            query += " AND benchmark_type = ?"
            params.append(benchmark_type)

        query += " ORDER BY test_timestamp DESC LIMIT ?"
        params.append(limit)

        rows = await self._fetchall(query, tuple(params))
        results = []
        for row in rows:
            results.append(BenchmarkRecord(
                id=row["id"],
                project_id=row["project_id"],
                benchmark_type=row["benchmark_type"],
                test_name=row["test_name"],
                metric_name=row["metric_name"],
                metric_value=row["metric_value"],
                metric_unit=row["metric_unit"],
                test_parameters=json.loads(row["test_parameters"]) if row["test_parameters"] else None,
                environment_info=json.loads(row["environment_info"]) if row["environment_info"] else None,
                test_timestamp=datetime.fromisoformat(row["test_timestamp"]),
                requirement_target=row["requirement_target"],
                requirement_met=bool(row["requirement_met"]),
            ))
        return results

    async def store_performance_metric(
        self,
        *,
        project_id: int,
        metric_category: str,
        metric_name: str,
        metric_value: float,
        metric_unit: str,
        baseline_value: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PerformanceMetricsRecord:
        """Store a performance metric."""
        await self._initialise()
        meta_json = json.dumps(metadata or {}, sort_keys=True)

        # Calculate improvement percentage if baseline provided
        improvement_percentage = None
        if baseline_value is not None and baseline_value != 0:
            improvement_percentage = ((metric_value - baseline_value) / abs(baseline_value)) * 100

        row = await self._fetchone(
            """
            INSERT INTO performance_metrics (project_id, metric_category, metric_name,
                                           metric_value, metric_unit, baseline_value,
                                           improvement_percentage, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id, project_id, metric_category, metric_name, metric_value, metric_unit,
                    baseline_value, improvement_percentage, collection_timestamp, metadata;
            """,
            (project_id, metric_category, metric_name, metric_value,
             metric_unit, baseline_value, improvement_percentage, meta_json),
        )
        return PerformanceMetricsRecord(
            id=row["id"],
            project_id=row["project_id"],
            metric_category=row["metric_category"],
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            metric_unit=row["metric_unit"],
            baseline_value=row["baseline_value"],
            improvement_percentage=row["improvement_percentage"],
            collection_timestamp=datetime.fromisoformat(row["collection_timestamp"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
        )

    # Agent session and project context management methods
    async def upsert_agent_session(self, agent_id: str, session_id: str, metadata: Optional[Dict[str, Any]]) -> None:
        """Create or update an agent session."""
        await self._initialise()
        metadata_json = json.dumps(metadata or {}) if metadata else None
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO agent_sessions (id, agent_id, started_at, last_active_at, status, metadata)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'active', ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_active_at = CURRENT_TIMESTAMP,
                    status = 'active',
                    metadata = excluded.metadata;
                """,
                (session_id, agent_id, metadata_json)
            )

    async def heartbeat_session(self, session_id: str) -> None:
        """Update session last_active_at timestamp."""
        await self._initialise()
        async with self._write_lock:
            await self._execute(
                """
                UPDATE agent_sessions
                SET last_active_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'active';
                """,
                (session_id,)
            )

    async def end_session(self, session_id: str) -> None:
        """Mark a session as expired."""
        await self._initialise()
        async with self._write_lock:
            await self._execute(
                """
                UPDATE agent_sessions
                SET status = 'expired', last_active_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (session_id,)
            )

    async def get_agent_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get an agent's current project with version info."""
        await self._initialise()
        row = await self._fetchone(
            """
            SELECT agent_id, project_name, version, updated_at, updated_by, session_id
            FROM agent_projects
            WHERE agent_id = ?;
            """,
            (agent_id,)
        )
        if not row:
            return None

        return {
            "agent_id": row["agent_id"],
            "project_name": row["project_name"],
            "version": row["version"],
            "updated_at": row["updated_at"],
            "updated_by": row["updated_by"],
            "session_id": row["session_id"]
        }

    async def set_agent_project(self, agent_id: str, project_name: Optional[str], expected_version: Optional[int], updated_by: str, session_id: str) -> Dict[str, Any]:
        """Set an agent's current project with optimistic concurrency control."""
        await self._initialise()
        async with self._write_lock:
            if expected_version is not None:
                # Optimistic concurrency check
                cursor = await self._fetchone(
                    """
                    UPDATE agent_projects
                    SET project_name = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP,
                        updated_by = ?, session_id = ?
                    WHERE agent_id = ? AND version = ?
                    RETURNING agent_id, project_name, version, updated_at, updated_by, session_id;
                    """,
                    (project_name, updated_by, session_id, agent_id, expected_version)
                )
                if not cursor:
                    from scribe_mcp.storage.base import ConflictError
                    raise ConflictError(f"Version conflict for agent {agent_id}: expected version {expected_version}")
                result = cursor
            else:
                # First time or no version check
                await self._execute(
                    """
                    INSERT INTO agent_projects (agent_id, project_name, version, updated_by, session_id)
                    VALUES (?, ?, 1, ?, ?)
                    ON CONFLICT(agent_id) DO UPDATE SET
                        project_name = excluded.project_name,
                        version = version + 1,
                        updated_at = CURRENT_TIMESTAMP,
                        updated_by = excluded.updated_by,
                        session_id = excluded.session_id;
                    """,
                    (agent_id, project_name, updated_by, session_id)
                )
                result = await self.get_agent_project(agent_id)

            return result or await self.get_agent_project(agent_id)
