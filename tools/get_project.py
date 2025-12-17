"""Tool for returning the currently active project."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.project_utils import load_active_project, load_project_config
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import LoggingContext, ProjectResolutionError
from scribe_mcp.shared.project_registry import ProjectRegistry
from scribe_mcp.shared.logging_utils import resolve_log_definition
from scribe_mcp.config import log_config as log_config_module
from scribe_mcp.utils.logs import parse_log_line, read_all_lines


class _GetProjectHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_GET_PROJECT_HELPER = _GetProjectHelper()
_PROJECT_REGISTRY = ProjectRegistry()


async def _compute_doc_status(project_name: str) -> Dict[str, Any]:
    info = _PROJECT_REGISTRY.get_project(project_name)
    if not info:
        return {}
    docs_meta = (info.meta or {}).get("docs") or {}
    flags = docs_meta.get("flags") or {}
    return {
        "flags": flags,
        "baseline_hashes": docs_meta.get("baseline_hashes") or {},
        "current_hashes": docs_meta.get("current_hashes") or {},
        "last_update_at": docs_meta.get("last_update_at"),
        "update_count": docs_meta.get("update_count"),
    }


async def _count_log_entries(log_path) -> int:
    try:
        lines = await read_all_lines(log_path)
    except Exception:
        return 0
    count = 0
    for line in lines:
        if parse_log_line(line):
            count += 1
    return count


async def _compute_log_counts(project: Dict[str, Any]) -> Dict[str, Any]:
    counts: Dict[str, Any] = {}
    logs = log_config_module.load_log_config()
    for log_type in sorted(logs.keys()):
        try:
            path, _definition = resolve_log_definition(project, log_type)
            if not path.exists():
                counts[log_type] = 0
                continue
            counts[log_type] = await _count_log_entries(path)
        except Exception:
            continue
    return counts


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
            extra: Dict[str, Any] = {}
            try:
                last_known = _PROJECT_REGISTRY.get_last_known_project(candidates=recent_projects)
                if last_known and last_known.last_access_at:
                    from datetime import datetime, timezone

                    minutes_ago = int(
                        max(
                            0.0,
                            (datetime.now(timezone.utc) - last_known.last_access_at).total_seconds() / 60.0,
                        )
                    )
                    extra["last_known_project"] = last_known.project_name
                    extra["last_known_project_minutes_ago"] = minutes_ago
                    extra["last_known_project_last_access_at"] = last_known.last_access_at.isoformat()
            except Exception:
                extra = {}

            return _GET_PROJECT_HELPER.apply_context_payload(
                _GET_PROJECT_HELPER.error_response(
                    "No project configured.",
                    suggestion="Invoke set_project or add a config/projects/<name>.json entry",
                    extra=extra or None,
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
    # Enrich with doc status + per-log entry counts for quick situational awareness.
    try:
        if current_name:
            response.setdefault("meta", {})
            response["meta"]["docs_status"] = await _compute_doc_status(current_name)
            response["meta"]["log_entry_counts"] = await _compute_log_counts(response)
    except Exception:
        pass
    return _GET_PROJECT_HELPER.apply_context_payload(payload, context)
