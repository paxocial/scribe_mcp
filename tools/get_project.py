"""Tool for returning the currently active project."""

from __future__ import annotations

from typing import Any, Dict, List

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.project_utils import load_active_project
from scribe_mcp import reminders


@app.tool()
async def get_project() -> Dict[str, Any]:
    """Return the active project selection, resolving defaults when necessary."""
    state_snapshot = await server_module.state_manager.record_tool("get_project")
    project, current_name, recent = await load_active_project(server_module.state_manager)
    reminders_payload: List[Dict[str, Any]] = []
    if not project:
        return {
            "ok": False,
            "error": "No project configured.",
            "suggestion": "Invoke set_project or add a config/projects/<name>.json entry",
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }
    response = dict(project)
    response.setdefault("meta", {})
    response["meta"]["current_project"] = current_name
    reminders_payload = await reminders.get_reminders(
        project,
        tool_name="get_project",
        state=state_snapshot,
    )
    return {
        "ok": True,
        "project": response,
        "recent_projects": list(recent),
        "reminders": reminders_payload,
    }
