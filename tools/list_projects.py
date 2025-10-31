"""Tool for enumerating known projects."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.project_utils import load_active_project
from scribe_mcp import reminders
from scribe_mcp.utils.response import default_formatter
from scribe_mcp.utils.tokens import token_estimator
from scribe_mcp.utils.context_safety import ContextManager


@app.tool()
async def list_projects(
    limit: Optional[int] = 5,  # Changed default to 5 for context safety
    filter: Optional[str] = None,
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_test: bool = False,  # New parameter to control test project visibility
    page: int = 1,  # New pagination parameter
    page_size: Optional[int] = None,  # New pagination size override
) -> Dict[str, Any]:
    """Return projects registered in the database or state cache with intelligent filtering.

    Args:
        limit: Maximum number of projects to return (default: 5 for context safety)
        filter: Filter projects by name (case-insensitive substring match)
        compact: Use compact response format with short field names
        fields: Specific fields to include in response
        include_test: Include test/temp projects (default: False)
        page: Page number for pagination (default: 1)
        page_size: Number of items per page (default: 5 or limit if specified)

    Returns:
        Projects list with intelligent filtering, pagination, and context safety
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

    # Convert to list and apply name filter if provided
    projects_list = list(projects_map.values())
    if filter:
        filter_lower = filter.lower()
        projects_list = [
            project for project in projects_list
            if filter_lower in project.get("name", "").lower()
        ]

    # Sort by name
    projects_list.sort(key=lambda item: item["name"].lower())

    # Initialize context manager for intelligent filtering and pagination
    context_manager = ContextManager()

    # Determine page size (use explicit page_size, then limit, then default) with type conversion
    try:
        limit_int = int(limit) if limit is not None else None
    except (ValueError, TypeError):
        limit_int = None

    try:
        page_size_int = int(page_size) if page_size is not None else None
    except (ValueError, TypeError):
        page_size_int = None

    effective_page_size = page_size_int or limit_int or context_manager.paginator.default_page_size

    # Prepare context-safe response
    context_response = context_manager.prepare_response(
        items=projects_list,
        response_type="projects",
        include_test=include_test,
        page=page,
        page_size=effective_page_size,
        compact=compact
    )

    # Get reminders
    reminders_payload: List[Dict[str, Any]] = []
    if active_project:
        reminders_payload = await reminders.get_reminders(
            active_project,
            tool_name="list_projects",
            state=state_snapshot,
        )

    # Format project entries using existing formatter
    formatted_projects = []
    for project in context_response["items"]:
        formatted_project = {
            k: v for k, v in project.items()
            if not fields or k in fields
        }
        formatted_projects.append(formatted_project)

    # Build final response
    response = {
        "ok": True,
        "projects": formatted_projects,
        "count": len(formatted_projects),
        "pagination": context_response["pagination"],
        "total_available": context_response["total_available"],
        "filtered": context_response["filtered"],
        "recent_projects": list(recent),
        "active_project": active_project.get("name") if active_project else None,
        "reminders": reminders_payload,
        "context_safety": context_response["context_safety"]
    }

    # Add token warnings if needed
    if "token_warning" in context_response:
        response["token_warning"] = context_response["token_warning"]
    elif "token_critical" in context_response:
        response["token_critical"] = context_response["token_critical"]

    if compact:
        response["compact"] = True

    # Record token usage
    if token_estimator:
        token_estimator.record_operation(
            operation="list_projects",
            input_data={
                "limit": limit,
                "filter": filter,
                "compact": compact,
                "fields": fields,
                "include_test": include_test,
                "page": page,
                "page_size": effective_page_size
            },
            response=response,
            compact_mode=compact,
            page_size=len(formatted_projects)
        )

    return response
