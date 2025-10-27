"""Tool for enumerating known projects."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.project_utils import load_active_project
from scribe_mcp import reminders
from scribe_mcp.utils.response import default_formatter
from scribe_mcp.utils.tokens import token_estimator


@app.tool()
async def list_projects(
    limit: Optional[int] = None,
    filter: Optional[str] = None,
    compact: bool = False,
    fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return projects registered in the database or state cache.

    Args:
        limit: Maximum number of projects to return
        filter: Filter projects by name (case-insensitive substring match)
        compact: Use compact response format with short field names
        fields: Specific fields to include in response

    Returns:
        Projects list with optional filtering and formatting
    """
    state_snapshot = await server_module.state_manager.record_tool("list_projects")
    state = await server_module.state_manager.load()
    projects_map: Dict[str, Dict[str, Any]] = {}

    backend = server_module.storage_backend
    if backend:
        records = await backend.list_projects()
        for record in records:
            projects_map[record.name] = {
                "name": record.name,
                "root": record.repo_root,
                "progress_log": record.progress_log_path,
            }

    for name, data in state.projects.items():
        existing = projects_map.get(name, {"name": name})
        if data.get("root"):
            existing["root"] = data["root"]
        if data.get("progress_log"):
            existing["progress_log"] = data["progress_log"]
        if data.get("docs"):
            existing["docs"] = data["docs"]
        if data.get("defaults"):
            existing["defaults"] = data["defaults"]
        projects_map[name] = existing

    active_project, _, recent = await load_active_project(server_module.state_manager)
    if active_project and active_project["name"] not in projects_map:
        projects_map[active_project["name"]] = {
            "name": active_project["name"],
            "root": active_project.get("root"),
            "progress_log": active_project.get("progress_log"),
            "docs": active_project.get("docs"),
            "defaults": active_project.get("defaults"),
        }

    # Convert to list and apply filters
    projects_list = list(projects_map.values())

    # Apply name filter if provided
    if filter:
        filter_lower = filter.lower()
        projects_list = [
            project for project in projects_list
            if filter_lower in project.get("name", "").lower()
        ]

    # Sort by name
    ordered = sorted(projects_list, key=lambda item: item["name"].lower())

    # Apply limit if provided
    if limit is not None and limit > 0:
        ordered = ordered[:limit]

    # Get reminders
    reminders_payload: List[Dict[str, Any]] = []
    if active_project:
        reminders_payload = await reminders.get_reminders(
            active_project,
            tool_name="list_projects",
            state=state_snapshot,
        )

    # Format response using the projects formatter
    response = default_formatter.format_projects_response(
        projects=ordered,
        compact=compact,
        fields=fields,
        extra_data={
            "recent_projects": list(recent),
            "active_project": active_project.get("name") if active_project else None,
            "reminders": reminders_payload,
        }
    )

    # Record token usage
    if token_estimator:
        token_estimator.record_operation(
            operation="list_projects",
            input_data={
                "limit": limit,
                "filter": filter,
                "compact": compact,
                "fields": fields
            },
            response=response,
            compact_mode=compact,
            page_size=len(ordered)
        )

    return response
