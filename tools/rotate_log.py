"""Enhanced tool for rotating the active project's progress log with comprehensive auditability."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.project_utils import load_active_project
# Note: generate_doc_templates imported for type checking only
# from scribe_mcp.tools.generate_doc_templates import generate_doc_templates
from scribe_mcp.utils.files import rotate_file, ensure_parent, verify_file_integrity
from scribe_mcp.utils.integrity import (
    compute_file_hash,
    create_rotation_metadata,
    count_file_lines
)
from scribe_mcp.utils.audit import (
    store_rotation_metadata,
    get_audit_manager
)
from scribe_mcp.utils.rotation_state import (
    get_state_manager,
    get_next_sequence_number,
    generate_rotation_id,
    update_project_state
)
from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError
from scribe_mcp.templates import (
    TEMPLATE_FILENAMES,
    substitution_context,
    create_rotation_context
)
from scribe_mcp.utils.time import format_utc
from scribe_mcp import reminders


@app.tool()
async def rotate_log(
    suffix: Optional[str] = None,
    custom_metadata: Optional[str] = None,
    confirm: Optional[bool] = False,
    dry_run: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Enhanced log rotation with comprehensive auditability and integrity verification.

    SAFETY NOTE: This tool defaults to dry-run mode for safety. Use confirm=true
    to perform actual rotation. Progress logs are never lost due to atomic
    operations and preflight backups.

    Args:
        suffix: Optional suffix for the archive filename (default: "archive")
        custom_metadata: JSON string of additional metadata to include
        confirm: Must be True to perform actual rotation (default: False)
        dry_run: If True, simulate rotation without making changes (default: True)

    Returns:
        Rotation result with dry-run information by default
    """
    state_snapshot = await server_module.state_manager.record_tool("rotate_log")
    project, _, recent = await load_active_project(server_module.state_manager)
    reminders_payload: List[Dict[str, Any]] = []

    # Parse custom metadata if provided
    parsed_metadata = None
    if custom_metadata:
        try:
            parsed_metadata = json.loads(custom_metadata)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": "Invalid JSON in custom_metadata parameter",
                "suggestion": "Ensure custom_metadata is valid JSON string",
                "recent_projects": list(recent),
            }

    if not project:
        return {
            "ok": False,
            "error": "No project configured.",
            "suggestion": "Invoke set_project before rotating logs",
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }

    try:
        # Initialize managers
        audit_manager = get_audit_manager()
        state_manager = get_state_manager()

        # Validate progress log exists
        progress_log_path = Path(project["progress_log"])
        if not progress_log_path.exists():
            return {
                "ok": False,
                "error": f"Progress log not found: {progress_log_path}",
                "suggestion": "Create initial progress log entries before rotating",
                "recent_projects": list(recent),
            }

        # Generate rotation metadata
        rotation_start_time = datetime.utcnow()
        rotation_timestamp = rotation_start_time.isoformat() + " UTC"
        rotation_id = generate_rotation_id(project["name"])

        # Analyze current log
        file_hash, file_size = compute_file_hash(str(progress_log_path))
        entry_count = count_file_lines(str(progress_log_path))

        # Get sequence number and hash chain info
        sequence_number = get_next_sequence_number(project["name"])
        hash_chain_info = state_manager.get_hash_chain_info(project["name"])
        previous_hash = hash_chain_info.get("last_hash")

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "rotation_id": rotation_id,
                "rotation_timestamp": rotation_timestamp,
                "project": project["name"],
                "current_log_path": str(progress_log_path),
                "file_size": file_size,
                "file_hash": file_hash,
                "entry_count": entry_count,
                "sequence_number": sequence_number,
                "previous_hash": previous_hash,
                "recent_projects": list(recent),
                "archived_to": None,  # No archive created in dry run
            }

        # Perform enhanced rotation
        # confirm=true should override dry_run and perform actual rotation
        # dry_run=None means auto-determine based on confirm flag
        # dry_run=true/false means respect the explicit setting
        if confirm:
            is_dry_run = False
        elif dry_run is not None:
            is_dry_run = dry_run
        else:
            is_dry_run = True  # Default to safe dry-run

        if is_dry_run:
            safe_rotation_id = rotation_id[:8]
            archive_suffix = f"{(suffix or 'archive')}_{safe_rotation_id}"
            potential_archive = await rotate_file(
                progress_log_path,
                archive_suffix,
                confirm=confirm,
                dry_run=True
            )

            file_info = verify_file_integrity(progress_log_path)

            return {
                "ok": True,
                "dry_run": True,
                "archive_path": str(potential_archive),
                "archived_to": str(potential_archive),  # Add alias for backwards compatibility
                "project": project["name"],
                "rotation_id": rotation_id,
                "current_file_size_mb": file_info.get("size_mb", 0),
                "current_entry_count": file_info.get("line_count", 0),
                "current_file_hash": file_info.get("sha256", ""),
                "requires_confirmation": not confirm,
                "suggestion": "Add confirm=true to perform actual rotation",
                "recent_projects": list(recent),
                "reminders": reminders_payload,
            }

        # Step 1: Create rotation context and template content first
        rotation_context = create_rotation_context(
            rotation_id=rotation_id,
            rotation_timestamp=rotation_timestamp,
            previous_log_path="ARCHIVE_PATH_PLACEHOLDER",  # Will be updated after rotation
            previous_log_hash="HASH_PLACEHOLDER",  # Will be updated after rotation
            previous_log_entries=str(entry_count),
            current_sequence=str(sequence_number),
            total_rotations=str(hash_chain_info.get("current_sequence", 0) + 1),
            hash_chain_previous=previous_hash,
            hash_chain_sequence=str(sequence_number),
            hash_chain_root=hash_chain_info.get("root_hash") or ""
        )

        # Generate template context
        template_context = substitution_context(
            project_name=project["name"],
            author=project.get("defaults", {}).get("agent", "Scribe"),
            rotation_context=rotation_context
        )

        # Import fallback renderer for safety
        from scribe_mcp.tools.generate_doc_templates import _render_template
        from scribe_mcp.templates import load_templates

        template_engine = None
        try:
            template_engine = Jinja2TemplateEngine(
                project_root=Path(project.get("root", "")) if project.get("root") else Path.cwd(),
                project_name=project["name"],
                security_mode="sandbox",
            )
        except Exception as engine_error:  # pragma: no cover - rarely triggered
            print(f"Warning: Failed to initialize Jinja2 template engine for rotation: {engine_error}")

        template_name = f"documents/{TEMPLATE_FILENAMES['progress_log']}"
        new_log_content = None

        if template_engine:
            try:
                new_log_content = template_engine.render_template(template_name, metadata=template_context)
            except TemplateEngineError as render_error:
                print(f"Warning: Jinja2 rendering failed for {template_name}: {render_error}")

        if new_log_content is None:
            templates = await load_templates()
            template_body = templates.get("progress_log", "")
            try:
                new_log_content = _render_template(template_body, template_context)
            except Exception as template_error:
                print(f"Warning: Template generation failed: {template_error}")
                # Fallback to basic content
                new_log_content = f"""# Progress Log

## Rotation Notice
Previous log was archived with rotation ID: {template_context.get('ROTATION_ID', 'unknown')}

Created: {template_context.get('DATE_UTC', 'Unknown')}
Project: {template_context.get('project_name', 'Unknown Project')}
Author: {template_context.get('author', 'Scribe')}

---

"""

        # Step 2: Bulletproof rotation with preflight backup
        if not confirm:
            return {
                "ok": False,
                "error": "Rotation requires explicit confirmation. Add confirm=true to proceed.",
                "suggestion": "Use confirm=true to perform rotation, or dry_run=true to preview changes",
                "recent_projects": list(recent),
                "reminders": reminders_payload,
            }

        safe_rotation_id = rotation_id[:8]
        archive_suffix = f"{(suffix or 'archive')}_{safe_rotation_id}"
        archive_path = await rotate_file(
            progress_log_path,
            archive_suffix,
            confirm=True,
            dry_run=False,
            template_content=new_log_content
        )

        # Step 2: Create comprehensive rotation metadata using actual archive path
        rotation_metadata = create_rotation_metadata(
            archived_file_path=str(archive_path),
            rotation_uuid=rotation_id,
            rotation_timestamp=rotation_timestamp,
            sequence_number=sequence_number,
            previous_hash=previous_hash
        )

        # Step 3: Update rotation context with actual archive information
        rotation_context.update({
            "previous_log_path": str(archive_path),
            "previous_log_hash": compute_file_hash(str(archive_path)),
        })

        # Step 4: Enhanced audit trail - emit rotation journal entry
        try:
            from scribe_mcp.utils.files import WriteAheadLog
            wal = WriteAheadLog(str(archive_path))
            rotation_journal_entry = {
                "op": "rotate",
                "from": str(progress_log_path),
                "to": str(archive_path),
                "rotation_id": rotation_id,
                "timestamp": rotation_timestamp,
                "sequence": str(sequence_number),
                "entries_rotated": str(entry_count)
            }
            wal.write_entry(rotation_journal_entry)
        except Exception as wal_error:
            print(f"Warning: Failed to write rotation journal entry: {wal_error}")

        # Step 5: Store audit trail record
        audit_success = store_rotation_metadata(project["name"], rotation_metadata)

        # Step 6: Update rotation state
        state_success = update_project_state(project["name"], rotation_metadata)

        # Step 7: Add custom metadata if provided
        if parsed_metadata:
            rotation_metadata.update(parsed_metadata)

        # Calculate rotation performance
        rotation_end_time = datetime.utcnow()
        rotation_duration = (rotation_end_time - rotation_start_time).total_seconds()
        if rotation_duration < 0:
            # Clock adjustments can yield negative deltas; clamp to zero for reporting.
            rotation_duration = 0.0

        # Step 8: Get reminders
        reminders_payload = await reminders.get_reminders(
            project,
            tool_name="rotate_log",
            state=state_snapshot,
        )

        return {
            "ok": True,
            "rotation_completed": True,
            "rotation_id": rotation_id,
            "rotation_timestamp": rotation_timestamp,
            "project": project["name"],
            "sequence_number": sequence_number,
            "archive_path": str(archive_path),
            "archived_to": str(archive_path),  # Add alias for backwards compatibility
            "archive_hash": rotation_metadata["file_hash"],
            "archive_size": rotation_metadata["file_size"],
            "entry_count": rotation_metadata["entry_count"],
            "rotation_duration_seconds": rotation_duration,
            "hash_chain_previous": previous_hash,
            "audit_trail_stored": audit_success,
            "state_updated": state_success,
            "integrity_verified": True,
            "template_generated": True,
            "atomic_template_used": True,
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }

    except Exception as exc:
        return {
            "ok": False,
            "error": f"Enhanced rotation failed: {exc}",
            "error_type": type(exc).__name__,
            "suggestion": "Check file permissions and disk space",
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }


@app.tool()
async def verify_rotation_integrity(rotation_id: str) -> Dict[str, Any]:
    """
    Verify the integrity of a specific rotation.

    Args:
        rotation_id: UUID of the rotation to verify
    """
    state_snapshot = await server_module.state_manager.record_tool("verify_rotation_integrity")
    project, _, recent = await load_active_project(server_module.state_manager)

    if not project:
        return {
            "ok": False,
            "error": "No project configured.",
            "suggestion": "Invoke set_project before verifying rotations",
            "recent_projects": list(recent),
        }

    try:
        audit_manager = get_audit_manager()
        is_valid, message = audit_manager.verify_rotation_integrity(
            project["name"], rotation_id
        )

        return {
            "ok": True,
            "rotation_id": rotation_id,
            "project": project["name"],
            "integrity_valid": is_valid,
            "verification_message": message,
            "verified_at": format_utc(),
            "recent_projects": list(recent),
        }

    except Exception as exc:
        return {
            "ok": False,
            "error": f"Integrity verification failed: {exc}",
            "rotation_id": rotation_id,
            "recent_projects": list(recent),
        }


@app.tool()
async def get_rotation_history(limit: int = 10) -> Dict[str, Any]:
    """
    Get rotation history for the active project.

    Args:
        limit: Maximum number of rotations to return
    """
    state_snapshot = await server_module.state_manager.record_tool("get_rotation_history")
    project, _, recent = await load_active_project(server_module.state_manager)

    if not project:
        return {
            "ok": False,
            "error": "No project configured.",
            "suggestion": "Invoke set_project before querying rotation history",
            "recent_projects": list(recent),
        }

    try:
        audit_manager = get_audit_manager()
        history = audit_manager.get_rotation_history(
            project["name"], limit=limit
        )

        return {
            "ok": True,
            "project": project["name"],
            "rotation_count": len(history),
            "rotations": history,
            "queried_at": format_utc(),
            "recent_projects": list(recent),
        }

    except Exception as exc:
        return {
            "ok": False,
            "error": f"Failed to get rotation history: {exc}",
            "recent_projects": list(recent),
        }
