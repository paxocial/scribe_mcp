"""Tool for enumerating known projects."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.project_utils import load_active_project
from scribe_mcp.utils.tokens import token_estimator
from scribe_mcp.utils.context_safety import ContextManager
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import LoggingContext, ProjectResolutionError


MINIMAL_FIELDS = ("name", "root", "progress_log")
COMPACT_FIELD_MAP = {"name": "n", "root": "r", "progress_log": "p", "docs": "d", "defaults": "df"}


class _ListProjectsHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_LIST_PROJECTS_HELPER = _ListProjectsHelper()


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
    agent_identity = server_module.get_agent_identity()
    agent_id = None
    if agent_identity:
        agent_id = await agent_identity.get_or_create_agent_id()

    try:
        context: LoggingContext = await _LIST_PROJECTS_HELPER.prepare_context(
            tool_name="list_projects",
            agent_id=agent_id,
            require_project=False,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        payload = _LIST_PROJECTS_HELPER.translate_project_error(exc)
        payload.setdefault("reminders", [])
        return payload

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

    active_project, current_name, recent = await load_active_project(server_module.state_manager)
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

    # Sort by name for stable ordering
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

    context_response = context_manager.prepare_response(
        items=projects_list,
        response_type="projects",
        include_test=include_test,
        page=page,
        page_size=effective_page_size,
        compact=compact
    )

    selected_fields = fields or list(MINIMAL_FIELDS)

    def _format_project(project: Dict[str, Any]) -> Dict[str, Any]:
        formatted: Dict[str, Any] = {}
        for field in selected_fields:
            if field not in project:
                continue
            key = COMPACT_FIELD_MAP.get(field, field) if compact else field
            formatted[key] = project[field]
        return formatted

    formatted_projects = [_format_project(project) for project in context_response["items"]]

    pagination_info = context_response["pagination"]
    total_available = context_response["total_available"]
    filtered_flag = context_response["filtered"]

    token_check = context_manager.token_guard.check_limits(
        {"projects": formatted_projects, "count": len(formatted_projects)}
    )

    context_safety = {
        "estimated_tokens": token_check.get("estimated_tokens", 0),
        "pagination_used": pagination_info["total_count"] > pagination_info["page_size"],
        "filtered": filtered_flag,
    }
    if compact:
        context_safety["compact_mode"] = True

    response = {
        "ok": True,
        "projects": formatted_projects,
        "count": len(formatted_projects),
        "pagination": pagination_info,
        "total_available": total_available,
        "filtered": filtered_flag,
        "recent_projects": list(recent),
        "active_project": (
            current_name
            if current_name
            else (context.project.get("name") if context.project else None)
        ),
        "context_safety": context_safety,
    }

    if token_check.get("warning"):
        response["token_warning"] = {
            "estimated_tokens": token_check["estimated_tokens"],
            "warning_threshold": context_manager.token_guard.warning_threshold,
            "message": token_check["message"],
            "suggestion": token_check["suggestion"],
        }
    elif token_check.get("critical"):
        response["token_critical"] = {
            "estimated_tokens": token_check["estimated_tokens"],
            "hard_limit": context_manager.token_guard.hard_limit,
            "message": token_check["message"],
            "suggestion": token_check["suggestion"],
        }

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

    return _LIST_PROJECTS_HELPER.apply_context_payload(response, context)
