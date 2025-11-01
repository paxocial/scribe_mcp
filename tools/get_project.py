"""Tool for returning the currently active project."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.project_utils import load_active_project, load_project_config
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import LoggingContext, ProjectResolutionError


class _GetProjectHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_GET_PROJECT_HELPER = _GetProjectHelper()


@app.tool()
async def get_project(project: Optional[str] = None) -> Dict[str, Any]:
    """Return the active project selection, resolving defaults when necessary."""
    state_snapshot = await server_module.state_manager.record_tool("get_project")
    agent_identity = server_module.get_agent_identity()
    agent_id = None
    if agent_identity:
        agent_id = await agent_identity.get_or_create_agent_id()

    try:
        context: LoggingContext = await _GET_PROJECT_HELPER.prepare_context(
            tool_name="get_project",
            agent_id=agent_id,
            explicit_project=project,
            require_project=False,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        payload = _GET_PROJECT_HELPER.translate_project_error(exc)
        payload.setdefault(
            "suggestion",
            "Invoke set_project or add a config/projects/<name>.json entry",
        )
        payload.setdefault("reminders", [])
        return payload

    state = await server_module.state_manager.load()
    recent_projects = list(state.recent_projects)

    target_project = context.project if context.project else None
    current_name = target_project.get("name") if target_project else None

    if project:
        # Attempt to load explicit project request
        project_data = state.get_project(project)
        if not project_data and context.project and context.project.get("name") == project:
            project_data = context.project
        if not project_data:
            config_project = load_project_config(project)
            if config_project:
                project_data = config_project
        if not project_data:
            return _GET_PROJECT_HELPER.apply_context_payload(
                _GET_PROJECT_HELPER.error_response(
                    f"Project '{project}' not found.",
                    suggestion="Ensure the project is registered via set_project or exists in config/projects/",
                ),
                context,
            )
        target_project = dict(project_data)
        current_name = project
    else:
        if not target_project:
            active_project, current_name, recent = await load_active_project(server_module.state_manager)
            if active_project:
                target_project = dict(active_project)
                recent_projects = list(recent)
        if not target_project:
            return _GET_PROJECT_HELPER.apply_context_payload(
                _GET_PROJECT_HELPER.error_response(
                    "No project configured.",
                    suggestion="Invoke set_project or add a config/projects/<name>.json entry",
                ),
                context,
            )

    response = dict(target_project)
    response.setdefault("meta", {})
    if current_name:
        response["meta"]["current_project"] = current_name

    payload = {
        "ok": True,
        "project": response,
        "recent_projects": recent_projects,
    }
    return _GET_PROJECT_HELPER.apply_context_payload(payload, context)
