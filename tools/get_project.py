"""Tool for returning the currently active project."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path

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


async def _read_recent_progress_entries(progress_log_path: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Read last N entries from progress log.

    Args:
        progress_log_path: Path to PROGRESS_LOG.md file
        limit: Maximum number of recent entries to return (1-5)

    Returns:
        List of entry dicts with timestamp, emoji, agent, message
        (COMPLETE messages - NO truncation!)
    """
    if not progress_log_path or not Path(progress_log_path).exists():
        return []

    try:
        # Read the log file
        with open(progress_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # Parse entries (lines starting with '[')
        entries = []
        for line in lines:
            line = line.strip()
            if not line.startswith('['):
                continue

            # Parse entry format: [emoji] [timestamp] [Agent: name] [Project: name] message
            # Example: [ℹ️] [2026-01-03 09:53:42 UTC] [Agent: Orchestrator] [Project: xyz] Message here

            try:
                parts = line.split('] ', 4)  # Split on '] ' up to 5 parts
                if len(parts) < 5:
                    continue

                emoji = parts[0].strip('[')
                timestamp = parts[1].strip('[')
                agent_part = parts[2].strip('[')  # "Agent: name"
                # Skip project part (parts[3])
                message = parts[4]

                # Extract agent name
                agent = agent_part.replace('Agent: ', '') if 'Agent:' in agent_part else 'unknown'

                entries.append({
                    "emoji": emoji,
                    "timestamp": timestamp,
                    "agent": agent,
                    "message": message  # COMPLETE message - NO truncation!
                })
            except:
                continue

        # Return last N entries
        return entries[-limit:] if len(entries) > limit else entries

    except Exception:
        return []


async def _gather_doc_info(project: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gather document information for a project.

    Returns dict with architecture/phase_plan/checklist/progress info.
    """
    from utils.response import default_formatter

    progress_log = project.get('progress_log', '')
    if not progress_log or not Path(progress_log).exists():
        return {}

    dev_plan_dir = Path(progress_log).parent
    result = {}

    # Check standard documents
    arch_file = dev_plan_dir / "ARCHITECTURE_GUIDE.md"
    if arch_file.exists():
        result["architecture"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(arch_file)
        }

    phase_file = dev_plan_dir / "PHASE_PLAN.md"
    if phase_file.exists():
        result["phase_plan"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(phase_file)
        }

    checklist_file = dev_plan_dir / "CHECKLIST.md"
    if checklist_file.exists():
        result["checklist"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(checklist_file)
        }

    # Progress log - count entries
    prog_file = Path(progress_log)
    if prog_file.exists():
        try:
            with open(prog_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                entry_count = sum(1 for line in content.split('\n') if line.strip().startswith('['))
            result["progress"] = {"exists": True, "entries": entry_count}
        except:
            result["progress"] = {"exists": True, "entries": 0}

    return result


@app.tool()
async def get_project(project: Optional[str] = None, format: str = "structured") -> Dict[str, Any]:
    """Return the active project selection, resolving defaults when necessary.

    Args:
        project: Optional project name to retrieve
        format: Output format - "readable" (human-friendly), "structured" (full JSON), "compact" (minimal)
    """
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

    recent_projects = list(context.recent_projects)

    target_project = context.project if context.project else None
    current_name = target_project.get("name") if target_project else None

    exec_context = None
    if hasattr(server_module, "get_execution_context"):
        try:
            exec_context = server_module.get_execution_context()
        except Exception:
            exec_context = None

    if project:
        # Attempt to load explicit project request
        state = await server_module.state_manager.load()
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
        if exec_context and getattr(exec_context, "mode", None) in {"project", "sentinel"}:
            if not target_project:
                return _GET_PROJECT_HELPER.apply_context_payload(
                    _GET_PROJECT_HELPER.error_response(
                        "No session-scoped project configured.",
                        suggestion="Invoke set_project before using this tool",
                    ),
                    context,
                )
        if not target_project and not exec_context:
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

    # Enrich with doc status + per-log entry counts for quick situational awareness.
    try:
        if current_name:
            response.setdefault("meta", {})
            response["meta"]["docs_status"] = await _compute_doc_status(current_name)
            response["meta"]["log_entry_counts"] = await _compute_log_counts(response)
    except Exception:
        pass

    # Handle readable format with context hydration
    if format == "readable":
        from utils.response import default_formatter

        # Read last 5 progress log entries (COMPLETE, no truncation!)
        recent_entries = await _read_recent_progress_entries(
            target_project.get("progress_log", ""),
            limit=5
        )

        # Gather doc info
        docs_info = await _gather_doc_info(target_project)

        # Get activity summary from registry
        registry_info = _PROJECT_REGISTRY.get_project(current_name) if current_name else None

        activity_summary = {
            "total_entries": registry_info.total_entries if registry_info else 0,
            "last_entry_at": registry_info.last_entry_at if registry_info else None,
            "status": registry_info.status if registry_info else "unknown"
        }

        # Format using context formatter
        readable_content = default_formatter.format_project_context(
            target_project,
            recent_entries,
            docs_info,
            activity_summary
        )

        payload = {
            "ok": True,
            "project": response,
            "recent_entries": recent_entries,
            "readable_content": readable_content
        }

        return await default_formatter.finalize_tool_response(
            payload,
            format="readable",
            tool_name="get_project"
        )

    # For structured/compact formats, continue with existing logic
    payload = {
        "ok": True,
        "project": response,
        "recent_projects": recent_projects,
    }
    return _GET_PROJECT_HELPER.apply_context_payload(payload, context)
