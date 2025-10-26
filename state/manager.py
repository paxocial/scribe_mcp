"""Persistence of lightweight state for the MCP server."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.config.settings import settings
from scribe_mcp.utils.time import parse_utc, utcnow


TOOL_HISTORY_LIMIT = 10


@dataclass
class State:
    current_project: Optional[str]
    projects: Dict[str, Dict[str, Any]]
    recent_projects: List[str]
    recent_tools: List[Dict[str, str]] = field(default_factory=list)
    last_activity_at: Optional[str] = None
    session_started_at: Optional[str] = None
    version: int = 0
    last_updated_by: Optional[str] = None
    operation_timestamp: Optional[str] = None
    agent_state: Dict[str, Any] = field(default_factory=dict)

    def get_project(self, name: Optional[str]) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        return self.projects.get(name)

    def with_project(self, name: Optional[str], data: Optional[Dict[str, Any]]) -> "State":
        projects = dict(self.projects)
        if name and data:
            projects[name] = data
        recent = list(self.recent_projects)
        if name:
            recent = [name] + [item for item in recent if item != name]
            limit = settings.recent_projects_limit
            recent = recent[:limit]
        return State(
            current_project=name,
            projects=projects,
            recent_projects=recent,
            recent_tools=list(self.recent_tools),
            last_activity_at=self.last_activity_at,
            session_started_at=self.session_started_at,
            version=self.version,
            last_updated_by=self.last_updated_by,
            operation_timestamp=self.operation_timestamp,
            agent_state=self.agent_state,
        )


class StateManager:
    """Load and persist the server's state file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path or settings.default_state_path)
        self._lock = asyncio.Lock()
        self._temp_suffix = ".tmp"

    async def load(self) -> State:
        """Read state from disk or return defaults."""
        async with self._lock:
            data = await asyncio.to_thread(self._read_json)
            return State(
                current_project=data.get("current_project"),
                projects=data.get("projects", {}),
                recent_projects=data.get("recent_projects", []),
                recent_tools=_normalise_tool_history(data.get("recent_tools", [])),
                last_activity_at=data.get("last_activity_at"),
                session_started_at=data.get("session_started_at"),
                version=data.get("version", 0),
                last_updated_by=data.get("last_updated_by"),
                operation_timestamp=data.get("operation_timestamp"),
                agent_state=data.get("agent_state", {}),
            )

    async def persist(self, state: State) -> None:
        """Write the full state to disk."""
        await self._write_state(state)

    async def record_tool(self, tool_name: str) -> State:
        """Track the most recent tool invocations."""
        async with self._lock:
            data = await asyncio.to_thread(self._read_json)
            now = utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

            recent_tools = _normalise_tool_history(data.get("recent_tools", []))
            filtered = [item for item in recent_tools if item.get("name") != tool_name]
            filtered.insert(0, {"name": tool_name, "ts": now})
            limited = filtered[: TOOL_HISTORY_LIMIT]

            last_activity = data.get("last_activity_at")
            session_started = data.get("session_started_at")
            reset_threshold = settings.reminder_idle_minutes
            warm_start = session_started

            if last_activity:
                try:
                    last_dt = parse_utc(last_activity)
                    if last_dt:
                        idle_minutes = (utcnow() - last_dt).total_seconds() / 60
                        if idle_minutes >= reset_threshold:
                            warm_start = now
                except Exception:
                    warm_start = now
            else:
                warm_start = now

            data["recent_tools"] = limited
            data["last_activity_at"] = now
            data["session_started_at"] = warm_start
            await asyncio.to_thread(self._write_json, data)
            return State(
                current_project=data.get("current_project"),
                projects=data.get("projects", {}),
                recent_projects=data.get("recent_projects", []),
                recent_tools=limited,
                last_activity_at=now,
                session_started_at=warm_start,
            )

    async def set_current_project(
        self,
        name: Optional[str],
        project_data: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
    ) -> State:
        """Persist the active project name and optional project metadata with atomic versioning."""
        async with self._lock:
            existing = await asyncio.to_thread(self._read_json)
            projects = existing.get("projects", {})
            recent = existing.get("recent_projects", [])
            recent_tools = _normalise_tool_history(existing.get("recent_tools", []))
            last_activity = existing.get("last_activity_at")
            session_started = existing.get("session_started_at")

            # Version tracking for concurrent operations
            current_version = existing.get("version", 0)
            new_version = current_version + 1

            if project_data:
                projects[name] = project_data  # type: ignore[index]
            if name:
                recent = [name] + [item for item in recent if item != name]
                recent = recent[: settings.recent_projects_limit]

            data = {
                "current_project": name,
                "projects": projects,
                "recent_projects": recent,
                "recent_tools": recent_tools,
                "last_activity_at": last_activity,
                "session_started_at": session_started,
                "version": new_version,
                "last_updated_by": agent_id,
                "operation_timestamp": utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            }
            # Atomic write with temp file
            await asyncio.to_thread(self._write_json_atomic, data)
            return State(
                current_project=name,
                projects=projects,
                recent_projects=recent,
                recent_tools=list(recent_tools),
                last_activity_at=last_activity,
                session_started_at=session_started,
                version=new_version,
                last_updated_by=agent_id,
                operation_timestamp=data["operation_timestamp"],
                agent_state=data.get("agent_state", {}),
            )

    def _read_json(self) -> Dict[str, Any]:
        target = self._path
        if not target.exists():
            return self._read_backup()
        try:
            with target.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return self._read_backup()

    def _write_json(self, data: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(self._path.suffix + self._temp_suffix)
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        temp_path.replace(self._path)

    def _write_json_atomic(self, data: Dict[str, Any]) -> None:
        """Enhanced atomic write with version tracking and backup."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Create versioned temp file
        version = data.get("version", 0)
        temp_path = self._path.with_suffix(f"{self._path.suffix}.tmp.{version}")

        # Write to temp file first
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())  # Force write to disk

        # Atomic rename
        temp_path.replace(self._path)

        # Cleanup old temp files
        self._cleanup_old_temp_files()

    def _cleanup_old_temp_files(self) -> None:
        """Clean up old versioned temp files."""
        try:
            state_dir = self._path.parent
            pattern = f"{self._path.name}.tmp.*"
            for temp_file in state_dir.glob(pattern):
                # Only clean up files older than current version
                if temp_file.stat().st_mtime < (utcnow().timestamp() - 300):  # 5 minutes old
                    temp_file.unlink()
        except Exception:
            pass  # Don't fail cleanup

    def _read_backup(self) -> Dict[str, Any]:
        backup = self._path.with_suffix(self._path.suffix + self._temp_suffix)
        if not backup.exists():
            return {}
        try:
            with backup.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return {}

    async def _write_state(self, state: State) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._write_json,
                {
                    "current_project": state.current_project,
                    "projects": state.projects,
                    "recent_projects": state.recent_projects,
                    "recent_tools": state.recent_tools,
                    "last_activity_at": state.last_activity_at,
                    "session_started_at": state.session_started_at,
                    "version": state.version,
                    "last_updated_by": state.last_updated_by,
                    "operation_timestamp": state.operation_timestamp,
                    "agent_state": state.agent_state,
                },
            )

    async def update_project_metadata(self, name: str, updates: Dict[str, Any]) -> State:
        """Merge metadata into a stored project entry."""
        async with self._lock:
            data = await asyncio.to_thread(self._read_json)
            projects = data.get("projects", {})
            project = projects.get(name, {})
            project.update(updates)
            projects[name] = project
            data["projects"] = projects
            await asyncio.to_thread(self._write_json, data)
            return State(
                current_project=data.get("current_project"),
                projects=projects,
                recent_projects=data.get("recent_projects", []),
                recent_tools=_normalise_tool_history(data.get("recent_tools", [])),
                last_activity_at=data.get("last_activity_at"),
                session_started_at=data.get("session_started_at"),
            )


def _normalise_tool_history(raw: Any) -> List[Dict[str, str]]:
    history: List[Dict[str, str]] = []
    if not isinstance(raw, list):
        return history
    for item in raw:
        if isinstance(item, dict) and "name" in item:
            name = str(item.get("name"))
            ts = str(item.get("ts") or "")
        else:
            name = str(item)
            ts = ""
        history.append({"name": name, "ts": ts})
    return history[:TOOL_HISTORY_LIMIT]
