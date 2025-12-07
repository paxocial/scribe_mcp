"""Tool for registering or selecting the active project."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.server import app
from scribe_mcp.tools.agent_project_utils import ensure_agent_session
from scribe_mcp.tools.project_utils import (
    list_project_configs,
    slugify_project_name,
)
from scribe_mcp.tools.base.parameter_normalizer import normalize_dict_param, normalize_list_param
from scribe_mcp.shared.logging_utils import LoggingContext, ProjectResolutionError
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.project_registry import ProjectRegistry
from scribe_mcp.shared.project_registry import ProjectRegistry


class _SetProjectHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_SET_PROJECT_HELPER = _SetProjectHelper()
_PROJECT_REGISTRY = ProjectRegistry()
_PROJECT_REGISTRY = ProjectRegistry()


@app.tool()
async def set_project(
    name: str,
    root: Optional[str] = None,
    progress_log: Optional[str] = None,
    defaults: Optional[Dict[str, Any]] = None,
    author: Optional[str] = None,
    overwrite_docs: bool = False,
    agent_id: Optional[str] = None,  # Agent identification (auto-detected if not provided)
    expected_version: Optional[int] = None,  # Optimistic concurrency control
    # Advanced parameters
    description: Optional[str] = None,  # Project description
    tags: Optional[List[str]] = None,  # Project tags
    template: Optional[str] = None,  # Custom template name
    auto_create_dirs: bool = True,  # Auto-create missing directories
    skip_validation: bool = False,  # Skip path validation for special cases
    # Reminder and notification settings
    reminder_settings: Optional[Dict[str, Any]] = None,
    notification_config: Optional[Dict[str, Any]] = None,
    # Quick emoji/agent settings (for convenience)
    emoji: Optional[str] = None,  # Default emoji for the project
    project_agent: Optional[str] = None,  # Default agent for the project (alias for agent_id)
) -> Dict[str, Any]:
    """Register the project (if needed) and mark it as the current context."""
    state_snapshot = await server_module.state_manager.record_tool("set_project")

    # Auto-detect agent ID if not provided
    if agent_id is None:
        agent_identity = server_module.get_agent_identity()
        if agent_identity:
            agent_id = await agent_identity.get_or_create_agent_id()
        else:
            agent_id = "Scribe"  # Fallback

    # Use BaseTool parameter normalization for consistent MCP framework handling
    if isinstance(defaults, str):
        try:
            # Try our standardized normalization first (handles MCP framework JSON serialization)
            normalized_defaults = normalize_dict_param(defaults, "defaults")
            if isinstance(normalized_defaults, dict):
                defaults = normalized_defaults
            else:
                # Fall back to original JSON parsing if normalization fails
                pass
        except ValueError:
            # FALLBACK: Use original JSON parsing logic
            try:
                import json
                defaults = json.loads(defaults)
                if not isinstance(defaults, dict):
                    defaults = {}
            except (json.JSONDecodeError, TypeError):
                defaults = {}

    # Update agent activity tracking
    agent_identity = server_module.get_agent_identity()
    if agent_identity:
        await agent_identity.update_agent_activity(
            agent_id, "set_project", {"project_name": name, "expected_version": expected_version}
        )

    # Use project_agent if provided (takes precedence over agent_id for this project)
    if project_agent:
        agent_id = project_agent

    base_context: LoggingContext = await _SET_PROJECT_HELPER.prepare_context(
        tool_name="set_project",
        agent_id=agent_id,
        require_project=False,
        state_snapshot=state_snapshot,
    )

    # Normalize tags parameter if provided
    if isinstance(tags, str):
        try:
            normalized_tags = normalize_list_param(tags, "tags")
            if isinstance(normalized_tags, list):
                tags = normalized_tags
            else:
                tags = [tags]  # Fallback: treat as single item
        except ValueError:
            tags = [tags]  # Fallback: treat as single item

    defaults = _normalise_defaults(defaults or {}, emoji, agent_id)
    try:
        resolved_root = _resolve_root(root)
    except ValueError as exc:
        return _SET_PROJECT_HELPER.apply_context_payload(
            _SET_PROJECT_HELPER.error_response(str(exc)),
            base_context,
        )

    docs_dir = _resolve_docs_dir(name, resolved_root)
    try:
        resolved_log = _resolve_log(progress_log, resolved_root, docs_dir)
    except ValueError as exc:
        return _SET_PROJECT_HELPER.apply_context_payload(
            _SET_PROJECT_HELPER.error_response(str(exc)),
            base_context,
        )

    validation = await _validate_project_paths(
        name=name,
        root_path=resolved_root,
        docs_dir=docs_dir,
        progress_log=resolved_log,
    )
    if not validation.get("ok", False):
        return _SET_PROJECT_HELPER.apply_context_payload(validation, base_context)

    resolved_root.mkdir(parents=True, exist_ok=True)

    # Bootstrap documentation scaffolds when missing
    doc_result = await _ensure_documents(name, author, overwrite_docs, resolved_root)
    if not doc_result.get("ok", False):
        return _SET_PROJECT_HELPER.apply_context_payload(doc_result, base_context)

    docs = {
        "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
        "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
        "checklist": str(docs_dir / "CHECKLIST.md"),
        "progress_log": str(resolved_log),
    }

    project_data = {
        "name": name,
        "root": str(resolved_root),
        "progress_log": str(resolved_log),
        "docs_dir": str(docs_dir),
        "docs": docs,
        "defaults": defaults,
        "author": author or defaults.get("agent") or "Scribe",
        # Optional metadata for richer project views
        "description": description,
        "tags": tags or [],
    }

    # Create/upsert project in database first
    backend = server_module.storage_backend
    project_record = None
    if backend:
        project_record = await backend.upsert_project(
            name=name,
            repo_root=str(resolved_root),
            progress_log_path=str(resolved_log),
        )

        # Best-effort Project Registry touch for this project (SQLite-first).
        try:
            _PROJECT_REGISTRY.ensure_project(
                project_record,
                description=description,
                tags=tags,
                meta={"source": "set_project"},
            )
            _PROJECT_REGISTRY.touch_access(project_record.name)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"⚠️  ProjectRegistry ensure/touch_access failed in set_project: {exc}")

        # Populate dev_plans table for core docs so lifecycle rules can see them.
        try:
            if hasattr(backend, "upsert_dev_plan") and project_record:
                from pathlib import Path as _Path

                core_docs = {
                    "architecture": docs.get("architecture"),
                    "phase_plan": docs.get("phase_plan"),
                    "checklist": docs.get("checklist"),
                    "progress_log": docs.get("progress_log"),
                }
                for plan_type, path_str in core_docs.items():
                    if not path_str:
                        continue
                    path_obj = _Path(path_str)
                    if not path_obj.exists():
                        continue
                    await backend.upsert_dev_plan(  # type: ignore[attr-defined]
                        project_id=project_record.id,
                        project_name=name,
                        plan_type=plan_type,
                        file_path=str(path_obj),
                        version="1.0",
                        metadata={"source": "set_project"},
                    )
        except Exception as exc:  # pragma: no cover - defensive
            print(f"⚠️  dev_plans upsert failed in set_project: {exc}")

        # Best-effort Project Registry touch for this project (SQLite-first).
        try:
            _PROJECT_REGISTRY.ensure_project(
                project_record,
                description=description,
                tags=tags,
                meta={"source": "set_project"},
            )
            _PROJECT_REGISTRY.touch_access(project_record.name)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"⚠️  ProjectRegistry ensure/touch_access failed in set_project: {exc}")

    # Use AgentContextManager for agent-scoped project context
    agent_manager = server_module.get_agent_context_manager()
    if agent_manager:
        try:
            # Ensure agent has an active session
            session_id = await ensure_agent_session(agent_id)
            if not session_id:
                # Fallback: create simple session
                import uuid
                session_id = str(uuid.uuid4())
                session_id = await agent_manager.start_session(agent_id, {"tool": "set_project"})

            # Set agent's current project with optimistic concurrency
            result = await agent_manager.set_current_project(
                agent_id=agent_id,
                project_name=name,
                session_id=session_id,
                expected_version=expected_version
            )

            # Update project_data with version info from database
            project_data["version"] = result.get("version", 1)
            project_data["updated_by"] = result.get("updated_by", agent_id)
            project_data["session_id"] = result.get("session_id", session_id)

        except Exception as e:
            # Fallback to legacy behavior if agent context fails
            print(f"⚠️  Agent context management failed: {e}")
            print("   💡 Falling back to legacy global state management")
    # Always mirror active project to JSON state for persistence across restarts

    state = await server_module.state_manager.set_current_project(
        name,
        project_data,
        agent_id=agent_id,
    )
    recent_projects = list(state.recent_projects)

    try:
        context_after = await _SET_PROJECT_HELPER.prepare_context(
            tool_name="set_project",
            agent_id=agent_id,
            explicit_project=name,
            require_project=False,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError:
        context_after = base_context

    response: Dict[str, Any] = {
        "ok": True,
        "project": project_data,
        "recent_projects": recent_projects,
        "generated": doc_result.get("files", []),
        "skipped": doc_result.get("skipped", []),
        **({"warnings": validation.get("warnings", [])} if validation.get("warnings") else {}),
    }
    if context_after.reminders:
        response["reminders"] = list(context_after.reminders)

    return _SET_PROJECT_HELPER.apply_context_payload(response, context_after)


def _resolve_root(root: Optional[str]) -> Path:
    base = settings.project_root.resolve()
    if not root:
        return base

    root_path = Path(root).expanduser()
    if not root_path.is_absolute():
        # Preserve relative-path compatibility while allowing roots outside the server repo
        root_path = (base / root_path).resolve()
    else:
        root_path = root_path.resolve()

    return root_path


def _resolve_docs_dir(name: str, root_path: Path) -> Path:
    slug = slugify_project_name(name)
    return (root_path / "docs" / "dev_plans" / slug).resolve()


def _resolve_log(log: Optional[str], root_path: Path, docs_dir: Path) -> Path:
    if not log:
        return (docs_dir / "PROGRESS_LOG.md").resolve()
    log_path = Path(log)
    if log_path.is_absolute():
        try:
            log_path.relative_to(root_path)
        except ValueError as exc:
            raise ValueError("Progress log must be within the project root.") from exc
        return log_path
    candidate = (root_path / log_path).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("Progress log must be within the project root.") from exc
    return candidate


def _normalise_defaults(
    defaults: Dict[str, Any],
    emoji_param: Optional[str] = None,
    agent_param: Optional[str] = None
) -> Dict[str, Any]:
    mapping = {}

    # Handle emoji from multiple sources (priority: emoji param > defaults > various default_*)
    emoji_value = emoji_param
    if not emoji_value:
        emoji_value = defaults.get("emoji") or defaults.get("default_emoji")
    if emoji_value:
        mapping["emoji"] = emoji_value

    # Handle agent from multiple sources (priority: agent_param > defaults > various default_*)
    agent_value = agent_param
    if not agent_value:
        agent_value = defaults.get("agent") or defaults.get("default_agent")
    if agent_value:
        mapping["agent"] = agent_value

    # Copy other defaults (excluding the ones we've already handled)
    for key, value in defaults.items():
        if (key not in ["emoji", "default_emoji", "agent", "default_agent"]) and value is not None:
            mapping[key] = value

    return mapping


async def _ensure_documents(
    name: str,
    author: Optional[str],
    overwrite: bool,
    root_path: Path,
) -> Dict[str, Any]:
    """
    Ensure project documentation exists with proper idempotency.

    This function checks if documentation already exists and skips generation
    unless explicitly requested to overwrite, making it truly idempotent.
    """
    from scribe_mcp.tools.project_utils import slugify_project_name

    # Resolve expected docs path
    slug = slugify_project_name(name)
    docs_dir = root_path / "docs" / "dev_plans" / slug

    # Check if docs already exist
    doc_files = {
        "architecture": docs_dir / "ARCHITECTURE_GUIDE.md",
        "phase_plan": docs_dir / "PHASE_PLAN.md",
        "checklist": docs_dir / "CHECKLIST.md",
        "progress_log": docs_dir / "PROGRESS_LOG.md"
    }

    existing_files = []
    missing_files = []

    for doc_type, file_path in doc_files.items():
        if file_path.exists() and file_path.stat().st_size > 0:
            existing_files.append(doc_type)
        else:
            missing_files.append(doc_type)

    # If all files exist and we're not overwriting, skip generation
    if not missing_files and not overwrite:
        return {
            "ok": True,
            "generated": [],
            "skipped": list(doc_files.keys()),
            "status": "docs_already_exist",
            "message": f"All documentation files already exist for project '{name}'"
        }

    # Generate missing files (or all if overwriting)
    from scribe_mcp.tools import generate_doc_templates as doc_templates

    result = await doc_templates.generate_doc_templates(
        project_name=name,
        author=author,
        overwrite=overwrite,
        base_dir=str(root_path),
    )

    # Add detailed status about what was done
    if result.get("ok"):
        result["idempotent_status"] = {
            "existing_files": existing_files,
            "missing_files_before": missing_files,
            "overwrite_requested": overwrite
        }

    return result


async def _validate_project_paths(
    *,
    name: str,
    root_path: Path,
    docs_dir: Path,
    progress_log: Path,
) -> Dict[str, Any]:
    """Ensure the provided paths do not collide with existing project definitions."""
    warnings: List[str] = []
    existing = await _gather_known_projects(skip=name)

    root_resolved = root_path.resolve()
    docs_resolved = docs_dir.resolve()
    log_resolved = progress_log.resolve()

    for other_name, paths in existing.items():
        if paths["progress_log"] == log_resolved:
            return {
                "ok": False,
                "error": f"Progress log '{log_resolved}' already belongs to project '{other_name}'.",
            }
        if paths["docs_dir"] == docs_resolved:
            return {
                "ok": False,
                "error": f"Docs directory '{docs_resolved}' already belongs to project '{other_name}'.",
            }
    root_parent = _first_existing_parent(root_resolved)
    if not os.access(root_parent, os.W_OK):
        return {
            "ok": False,
            "error": f"Insufficient permissions to write under '{root_parent}'.",
        }

    docs_parent = _first_existing_parent(docs_resolved)
    if not os.access(docs_parent, os.W_OK):
        return {
            "ok": False,
            "error": f"Insufficient permissions to write docs under '{docs_parent}'.",
        }

    log_parent = _first_existing_parent(log_resolved.parent)
    if not os.access(log_parent, os.W_OK):
        return {
            "ok": False,
            "error": f"Insufficient permissions to write progress log under '{log_parent}'.",
        }

    return {"ok": True, "warnings": warnings}


async def _gather_known_projects(skip: Optional[str]) -> Dict[str, Dict[str, Path]]:
    """Collect registered projects from state and configs."""
    collected: Dict[str, Dict[str, Path]] = {}
    state = await server_module.state_manager.load()
    for project_name, data in state.projects.items():
        if project_name == skip:
            continue
        paths = _extract_paths(data)
        if paths and not _is_temp_path(paths["root"]):
            collected[project_name] = paths

    for project_name, data in list_project_configs().items():
        if project_name == skip or project_name in collected:
            continue
        paths = _extract_paths(data)
        if paths and not _is_temp_path(paths["root"]):
            collected[project_name] = paths
    return collected


def _extract_paths(data: Dict[str, Any]) -> Optional[Dict[str, Path]]:
    try:
        root = Path(data["root"]).resolve()
        log = Path(data["progress_log"]).resolve()
    except (KeyError, TypeError):
        return None

    docs_dir_value = data.get("docs_dir")
    if docs_dir_value:
        docs_dir = Path(docs_dir_value).resolve()
    else:
        doc_entry = data.get("docs") or {}
        progress_path = doc_entry.get("progress_log")
        if progress_path:
            docs_dir = Path(progress_path).resolve().parent
        else:
            docs_dir = log.parent

    return {
        "root": root,
        "docs_dir": docs_dir,
        "progress_log": log,
    }


def _is_temp_path(path: Path) -> bool:
    """Filter out ephemeral tmp test projects to reduce noisy overlaps."""
    parts = {p.lower() for p in path.parts}
    return any(part.startswith("tmp_tests") or part == "tmp_tests" for part in parts)


def _overlaps(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _first_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            break
        current = current.parent
    return current
