"""Tool for reading recent log entries."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.constants import STATUS_EMOJI
from scribe_mcp.tools.project_utils import load_active_project
from scribe_mcp import reminders
from scribe_mcp.utils.files import read_tail


@app.tool()
async def read_recent(
    n: Optional[Any] = None,
    filter: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the last `n` entries for the active project, optionally filtered."""
    state_snapshot = await server_module.state_manager.record_tool("read_recent")
    project, _, recent = await load_active_project(server_module.state_manager)
    reminders_payload: List[Dict[str, Any]] = []
    if not project:
        return {
            "ok": False,
            "error": "No project configured.",
            "suggestion": "Invoke set_project before reading logs",
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }

    # Handle n parameter that might come as string from MCP interface
    try:
        limit_int = int(n) if n is not None else 50
    except (ValueError, TypeError):
        limit_int = 50

    limit = max(1, min(limit_int, 200))
    filters = filter or {}

    backend = server_module.storage_backend
    if backend:
        record = await backend.fetch_project(project["name"])
        if record:
            rows = await backend.fetch_recent_entries(
                project=record,
                limit=limit,
                filters=_normalise_filters(filters),
            )
            reminders_payload = await reminders.get_reminders(
                project,
                tool_name="read_recent",
                state=state_snapshot,
            )
            return {
                "ok": True,
                "entries": rows,
                "recent_projects": list(recent),
                "reminders": reminders_payload,
            }

    lines = await read_tail(_progress_log_path(project), limit)
    lines = _apply_line_filters(lines, filters)
    reminders_payload = await reminders.get_reminders(
        project,
        tool_name="read_recent",
        state=state_snapshot,
    )
    return {
        "ok": True,
        "entries": lines,
        "recent_projects": list(recent),
        "reminders": reminders_payload,
    }


def _normalise_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    normalised: Dict[str, Any] = {}
    if "agent" in filters and filters["agent"]:
        normalised["agent"] = str(filters["agent"])
    if "status" in filters and filters["status"]:
        status = str(filters["status"])
        normalised["emoji"] = STATUS_EMOJI.get(status, status)
    if "emoji" in filters and filters["emoji"]:
        normalised["emoji"] = str(filters["emoji"])
    return normalised


def _apply_line_filters(lines: List[str], filters: Dict[str, Any]) -> List[str]:
    agent = filters.get("agent")
    emoji = None
    if "emoji" in filters:
        emoji = filters["emoji"]
    elif "status" in filters:
        emoji = STATUS_EMOJI.get(filters["status"])

    def matches(line: str) -> bool:
        if agent and f"[Agent: {agent}]" not in line:
            return False
        if emoji and f"[{emoji}]" not in line:
            return False
        return True

    return [line for line in lines if matches(line)]


def _progress_log_path(project: Dict[str, Any]) -> Path:
    return Path(project["progress_log"])
