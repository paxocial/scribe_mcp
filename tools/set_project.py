"""Tool for registering or selecting the active project."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.server import app
from scribe_mcp.tools.agent_project_utils import (
    ensure_agent_session,
    validate_agent_session,
)
from scribe_mcp.tools.project_utils import (
    list_project_configs,
    slugify_project_name,
)
from scribe_mcp import reminders


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

    # Update agent activity tracking
    agent_identity = server_module.get_agent_identity()
    if agent_identity:
        await agent_identity.update_agent_activity(
            agent_id, "set_project", {"project_name": name, "expected_version": expected_version}
        )

    defaults = _normalise_defaults(defaults or {})
    try:
        resolved_root = _resolve_root(root)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "reminders": []}

    docs_dir = _resolve_docs_dir(name, resolved_root)
    try:
        resolved_log = _resolve_log(progress_log, resolved_root, docs_dir)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "reminders": []}

    validation = await _validate_project_paths(
        name=name,
        root_path=resolved_root,
        docs_dir=docs_dir,
        progress_log=resolved_log,
    )
    if not validation.get("ok", False):
        return {**validation, "reminders": []}

    resolved_root.mkdir(parents=True, exist_ok=True)

    # Bootstrap documentation scaffolds when missing
    doc_result = await _ensure_documents(name, author, overwrite_docs, resolved_root)
    if not doc_result.get("ok", False):
        return doc_result

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
            state = await server_module.state_manager.set_current_project(name, project_data, agent_id=agent_id)
    else:
        # Fallback to legacy behavior
        state = await server_module.state_manager.set_current_project(name, project_data, agent_id=agent_id)

    reminders_payload = await reminders.get_reminders(
        project_data,
        tool_name="set_project",
        state=state_snapshot,
    )

    # Get recent projects from state manager (always available for UI continuity)
    try:
        current_state = await server_module.state_manager.load()
        recent_projects = current_state.recent_projects
    except Exception:
        recent_projects = []

    return {
        "ok": True,
        "project": project_data,
        "recent_projects": recent_projects,
        "generated": doc_result.get("files", []),
        "skipped": doc_result.get("skipped", []),
        "reminders": reminders_payload,
        **({"warnings": validation.get("warnings", [])} if validation.get("warnings") else {}),
    }


def _resolve_root(root: Optional[str]) -> Path:
    base = settings.project_root.resolve()
    if not root:
        return base

    root_path = Path(root)
    if not root_path.is_absolute():
        root_path = (base / root_path).resolve()

    try:
        root_path.relative_to(base)
    except ValueError as exc:
        raise ValueError("Project root must reside within the repository root.") from exc

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


def _normalise_defaults(defaults: Dict[str, Any]) -> Dict[str, Any]:
    mapping = {}
    if "emoji" in defaults and defaults["emoji"]:
        mapping["emoji"] = defaults["emoji"]
    if "agent" in defaults and defaults["agent"]:
        mapping["agent"] = defaults["agent"]
    if "default_emoji" in defaults and defaults["default_emoji"]:
        mapping["emoji"] = defaults["default_emoji"]
    if "default_agent" in defaults and defaults["default_agent"]:
        mapping["agent"] = defaults["default_agent"]
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
        if _overlaps(root_resolved, paths["root"]):
            warnings.append(
                f"Project '{other_name}' shares overlapping root '{paths['root']}'."
            )

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
        if paths:
            collected[project_name] = paths

    for project_name, data in list_project_configs().items():
        if project_name == skip or project_name in collected:
            continue
        paths = _extract_paths(data)
        if paths:
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
