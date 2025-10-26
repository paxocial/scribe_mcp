"""Core logic for managing project documentation updates."""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Import with absolute paths from scribe_mcp root
from scribe_mcp.utils.files import async_atomic_write, ensure_parent
from scribe_mcp.utils.time import utcnow
from scribe_mcp.templates import template_root
from scribe_mcp.tools.project_utils import slugify_project_name

# Setup logging for doc management operations
doc_logger = logging.getLogger(__name__)

FRAGMENT_DIR = (template_root().parent / "fragments").resolve()
SECTION_MARKER = "<!-- ID: {section} -->"


def _log_operation(
    level: str,
    operation: str,
    doc: str,
    section: Optional[str],
    action: str,
    file_path: Path,
    duration_ms: float,
    file_size_before: int,
    file_size_after: int,
    success: bool,
    error_message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Log document operations with structured data."""
    log_data = {
        "timestamp": time.time(),
        "operation": operation,
        "document": doc,
        "section": section,
        "action": action,
        "file_path": str(file_path),
        "duration_ms": duration_ms,
        "file_size_before": file_size_before,
        "file_size_after": file_size_after,
        "file_size_change": file_size_after - file_size_before,
        "success": success,
        "error_message": error_message,
        "metadata": metadata or {}
    }

    # Convert to JSON for structured logging
    log_message = json.dumps(log_data, separators=(',', ':'))

    if level == "error":
        doc_logger.error(f"Document operation failed: {operation} on {doc} - {error_message or 'Unknown error'}", extra={"structured_log": log_data})
    elif level == "warning":
        doc_logger.warning(f"Document operation warning: {operation} on {doc} - {error_message}", extra={"structured_log": log_data})
    elif level == "info":
        doc_logger.info(f"Document operation successful: {operation} on {doc}", extra={"structured_log": log_data})
    else:
        doc_logger.debug(f"Document operation: {operation} on {doc}", extra={"structured_log": log_data})


@dataclass
class DocChangeResult:
    doc: str
    section: Optional[str]
    action: str
    path: Path
    before_hash: str
    after_hash: str
    content_written: str
    diff_preview: str
    success: bool = True
    error_message: Optional[str] = None
    verification_passed: bool = False
    file_size_before: int = 0
    file_size_after: int = 0


class DocumentOperationError(Exception):
    """Raised when a document operation fails."""
    pass


class DocumentValidationError(Exception):
    """Raised when document validation fails."""
    pass


class DocumentVerificationError(Exception):
    """Raised when document write verification fails."""
    pass


async def apply_doc_change(
    project: Dict[str, Any],
    *,
    doc: str,
    action: str,
    section: Optional[str],
    content: Optional[str],
    template: Optional[str],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
) -> DocChangeResult:
    """Apply a document change with comprehensive error handling and verification."""
    start_time = time.time()

    try:
        # Validate inputs
        _validate_inputs(doc, action, section, content, template)

        # Resolve and validate document path
        doc_path = _resolve_doc_path(project, doc)
        await ensure_parent(doc_path)

        # Get original content and metadata
        original_text = ""
        file_size_before = 0
        if doc_path.exists():
            try:
                original_text = await asyncio.to_thread(doc_path.read_text, encoding="utf-8")
                file_size_before = doc_path.stat().st_size
            except (OSError, UnicodeDecodeError) as e:
                raise DocumentOperationError(f"Failed to read existing document {doc_path}: {e}")

        before_hash = _hash_text(original_text)

        # Render content
        try:
            rendered_content = await _render_content(project, content, template, metadata)
        except Exception as e:
            raise DocumentOperationError(f"Failed to render content: {e}")

        # Apply the change based on action
        try:
            if action == "replace_section":
                updated_text = _replace_section(original_text, section, rendered_content)
            elif action == "append":
                updated_text = _append_block(original_text, rendered_content)
            elif action == "status_update":
                updated_text = _toggle_checklist_status(original_text, section, metadata or {})
            else:
                raise ValueError(f"Unsupported action '{action}'.")
        except Exception as e:
            raise DocumentOperationError(f"Failed to apply {action} operation: {e}")

        after_hash = _hash_text(updated_text)

        # Generate diff preview
        diff_preview = "\n".join(
            difflib.unified_diff(
                original_text.splitlines(),
                updated_text.splitlines(),
                fromfile="before",
                tofile="after",
                lineterm="",
            )
        )

        # Apply changes to file system
        file_size_after = 0
        verification_passed = False

        if not dry_run:
            try:
                # Write the file
                await async_atomic_write(doc_path, updated_text, mode="w")

                # Verify the write was successful
                verification_passed = await _verify_file_write(doc_path, updated_text, after_hash)
                if not verification_passed:
                    raise DocumentVerificationError(f"File write verification failed for {doc_path}")

                file_size_after = doc_path.stat().st_size

                # Log successful operation
                duration_ms = (time.time() - start_time) * 1000
                _log_operation(
                    level="info",
                    operation="apply_doc_change",
                    doc=doc,
                    section=section,
                    action=action,
                    file_path=doc_path,
                    duration_ms=duration_ms,
                    file_size_before=file_size_before,
                    file_size_after=file_size_after,
                    success=True,
                    metadata={
                        "before_hash": before_hash,
                        "after_hash": after_hash,
                        "dry_run": dry_run
                    }
                )

            except Exception as e:
                # Attempt rollback if write failed
                try:
                    if original_text and doc_path.exists():
                        await async_atomic_write(doc_path, original_text, mode="w")
                        duration_ms = (time.time() - start_time) * 1000
                        _log_operation(
                            level="warning",
                            operation="apply_doc_change",
                            doc=doc,
                            section=section,
                            action=action,
                            file_path=doc_path,
                            duration_ms=duration_ms,
                            file_size_before=file_size_before,
                            file_size_after=file_size_before,  # Back to original
                            success=False,
                            error_message="Write failed, rolled back successfully",
                            metadata={"rollback": True, "original_error": str(e)}
                        )
                except Exception as rollback_error:
                    duration_ms = (time.time() - start_time) * 1000
                    _log_operation(
                        level="error",
                        operation="apply_doc_change",
                        doc=doc,
                        section=section,
                        action=action,
                        file_path=doc_path,
                        duration_ms=duration_ms,
                        file_size_before=file_size_before,
                        file_size_after=file_size_before,
                        success=False,
                        error_message=f"Write failed and rollback failed: {rollback_error}",
                        metadata={"rollback_failed": True, "original_error": str(e)}
                    )

                raise DocumentOperationError(f"Failed to write document {doc_path}: {e}")

        return DocChangeResult(
            doc=doc,
            section=section,
            action=action,
            path=doc_path,
            before_hash=before_hash,
            after_hash=after_hash,
            content_written=rendered_content,
            diff_preview=diff_preview,
            success=True,
            verification_passed=verification_passed,
            file_size_before=file_size_before,
            file_size_after=file_size_after,
        )

    except (DocumentValidationError, DocumentOperationError, DocumentVerificationError) as e:
        duration_ms = (time.time() - start_time) * 1000
        _log_operation(
            level="error",
            operation="apply_doc_change",
            doc=doc,
            section=section,
            action=action,
            file_path=Path(""),
            duration_ms=duration_ms,
            file_size_before=file_size_before,
            file_size_after=0,
            success=False,
            error_message=str(e),
            metadata={"error_type": type(e).__name__}
        )

        return DocChangeResult(
            doc=doc,
            section=section,
            action=action,
            path=Path(""),
            before_hash="",
            after_hash="",
            content_written="",
            diff_preview="",
            success=False,
            error_message=str(e),
            verification_passed=False,
            file_size_before=file_size_before,
            file_size_after=0,
        )
    except Exception as e:
        # Catch any unexpected errors
        duration_ms = (time.time() - start_time) * 1000
        _log_operation(
            level="error",
            operation="apply_doc_change",
            doc=doc,
            section=section,
            action=action,
            file_path=Path(""),
            duration_ms=duration_ms,
            file_size_before=file_size_before,
            file_size_after=0,
            success=False,
            error_message=f"Unexpected error: {e}",
            metadata={"error_type": type(e).__name__, "unexpected": True}
        )

        return DocChangeResult(
            doc=doc,
            section=section,
            action=action,
            path=Path(""),
            before_hash="",
            after_hash="",
            content_written="",
            diff_preview="",
            success=False,
            error_message=f"Unexpected error: {e}",
            verification_passed=False,
            file_size_before=file_size_before,
            file_size_after=0,
        )


def _resolve_doc_path(project: Dict[str, Any], doc_key: str) -> Path:
    """
    Resolve documentation path with safety assertions.

    Ensures all resolved paths remain within the repository sandbox
    and provides sensible fallbacks when explicit paths are not defined.
    """
    # Validate inputs
    if not doc_key:
        raise ValueError("doc_key cannot be empty")

    project_name = project.get("name")
    if not project_name:
        raise ValueError("project must have a name")

    project_root = Path(project.get("root", ""))
    if not project_root.exists():
        raise ValueError(f"Project root does not exist: {project_root}")

    # Try explicit paths first
    docs = project.get("docs") or {}
    target = docs.get(doc_key)
    if not target and doc_key == "progress_log":
        target = project.get("progress_log")

    if target:
        resolved_path = Path(target).resolve()
        # CRITICAL: Ensure path is within project sandbox
        try:
            resolved_path.relative_to(project_root)
        except ValueError as e:
            raise SecurityError(f"Document path {resolved_path} is outside project root {project_root}") from e

        doc_logger.debug(f"Resolved doc path for {doc_key} using explicit target: {resolved_path}")
        return resolved_path

    # Fallback to conventional structure
    docs_dir = docs.get("architecture")
    if docs_dir:
        docs_dir = Path(docs_dir).parent
    else:
        # Use conventional docs structure
        docs_dir = project_root / "docs" / "dev_plans" / slugify_project_name(project_name)

    filename = {
        "architecture": "ARCHITECTURE_GUIDE.md",
        "phase_plan": "PHASE_PLAN.md",
        "checklist": "CHECKLIST.md",
        "progress_log": "PROGRESS_LOG.md",
        "doc_log": "DOC_LOG.md",
        "security_log": "SECURITY_LOG.md",
        "bug_log": "BUG_LOG.md",
    }.get(doc_key, f"{doc_key.upper()}.md")

    resolved_path = (docs_dir / filename).resolve()

    # CRITICAL: Ensure fallback path is within project sandbox
    try:
        resolved_path.relative_to(project_root)
    except ValueError as e:
        raise SecurityError(f"Fallback document path {resolved_path} is outside project root {project_root}") from e

    doc_logger.debug(f"Resolved doc path for {doc_key} using fallback: {resolved_path}")
    return resolved_path


class SecurityError(RuntimeError):
    """Security violation when document paths escape project sandbox."""


async def _render_content(
    project: Dict[str, Any],
    content: Optional[str],
    template_name: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> str:
    """Render content using Jinja2 template engine with fallback to direct content."""
    if template_name:
        try:
            # Import template engine dynamically to avoid circular imports
            from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

            # Initialize template engine
            engine = Jinja2TemplateEngine(
                project_root=Path(project.get("root", "")),
                project_name=project.get("name", ""),
                security_mode="sandbox"
            )

            # Add timestamp to metadata
            enhanced_metadata = metadata.copy() if metadata else {}
            enhanced_metadata.update({
                "timestamp": utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            })

            # Render template
            rendered = engine.render_template(
                template_name=f"{template_name}.md",
                metadata=enhanced_metadata
            )

            doc_logger.debug(f"Successfully rendered template '{template_name}' using Jinja2 engine")
            return rendered

        except TemplateEngineError as e:
            doc_logger.error(f"Template engine error for '{template_name}': {e}")
            raise DocumentOperationError(f"Failed to render template '{template_name}': {e}")
        except Exception as e:
            doc_logger.error(f"Unexpected error rendering template '{template_name}': {e}")
            raise DocumentOperationError(f"Unexpected template error: {e}")

    if isinstance(content, str) and content.strip():
        # For direct content, still allow Jinja2 processing for variables
        try:
            from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

            engine = Jinja2TemplateEngine(
                project_root=Path(project.get("root", "")),
                project_name=project.get("name", ""),
                security_mode="sandbox"
            )

            enhanced_metadata = metadata.copy() if metadata else {}
            enhanced_metadata.update({
                "timestamp": utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            })

            rendered = engine.render_string(content.strip(), metadata=enhanced_metadata)
            doc_logger.debug(f"Successfully rendered content string using Jinja2 engine")
            return rendered

        except (TemplateEngineError, ImportError):
            # Fallback to original content if Jinja2 processing fails
            doc_logger.warning(f"Jinja2 processing failed, using raw content")
            return content.strip()

    raise ValueError("Either content or template must be provided.")


async def _load_fragment(name: str) -> str:
    fragment = (FRAGMENT_DIR / f"{name}.md").resolve()
    if not fragment.exists():
        raise FileNotFoundError(f"Template fragment '{name}' not found under {FRAGMENT_DIR}")
    return await asyncio.to_thread(fragment.read_text, encoding="utf-8")


def _replace_section(text: str, section: Optional[str], content: str) -> str:
    marker = SECTION_MARKER.format(section=section)
    idx = text.find(marker)
    if idx == -1:
        raise ValueError(f"Section '{section}' anchor not found (expected '{marker}').")
    start = idx + len(marker)
    # Skip newline right after marker
    if start < len(text) and text[start] == "\r":
        start += 1
    if start < len(text) and text[start] == "\n":
        start += 1
    next_marker = text.find("<!-- ID:", start)
    if next_marker == -1:
        next_marker = len(text)
    new_block = marker + "\n" + content.strip() + "\n"
    replacement = text[:idx] + new_block + text[next_marker:]
    return replacement


def _append_block(text: str, content: str) -> str:
    if not text.endswith("\n"):
        text += "\n"
    return text + content.strip() + "\n"


def _toggle_checklist_status(text: str, section: Optional[str], metadata: Dict[str, Any]) -> str:
    desired = metadata.get("status", "").lower()
    proof = metadata.get("proof")
    replacement = None

    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if section and section not in line:
            continue
        if "- [ ]" in line or "- [x]" in line:
            if desired in {"done", "completed", "complete"}:
                new_line = line.replace("- [ ]", "- [x]", 1)
            elif desired in {"pending", "todo"}:
                new_line = line.replace("- [x]", "- [ ]", 1)
            else:
                new_line = line
            if proof:
                new_line = new_line.split(" | ")[0] + f" | proof={proof}"
            lines[idx] = new_line
            replacement = True
            break
    if not replacement:
        raise ValueError(f"Could not find checklist line containing '{section}'.")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _validate_inputs(
    doc: str,
    action: str,
    section: Optional[str],
    content: Optional[str],
    template: Optional[str]
) -> None:
    """Validate input parameters for document operations."""
    if not doc or not isinstance(doc, str):
        raise DocumentValidationError("Document name must be a non-empty string")

    if not action or not isinstance(action, str):
        raise DocumentValidationError("Action must be a non-empty string")

    valid_actions = {"replace_section", "append", "status_update"}
    if action not in valid_actions:
        raise DocumentValidationError(f"Invalid action '{action}'. Must be one of: {valid_actions}")

    if action in {"replace_section", "status_update"} and (not section or not isinstance(section, str)):
        raise DocumentValidationError(f"Section parameter is required for {action} action")

    if not content and not template:
        raise DocumentValidationError("Either content or template must be provided")

    # Validate section ID format
    if section and not section.replace("_", "").replace("-", "").isalnum():
        raise DocumentValidationError(f"Invalid section ID '{section}'. Must contain only alphanumeric characters, hyphens, and underscores")


async def _verify_file_write(file_path: Path, expected_content: str, expected_hash: str) -> bool:
    """Verify that the file was written correctly."""
    try:
        # Check if file exists
        if not file_path.exists():
            return False

        # Read the actual content
        actual_content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")

        # Verify content matches exactly
        if actual_content != expected_content:
            doc_logger.error(f"Content mismatch in {file_path}: expected {len(expected_content)} chars, got {len(actual_content)} chars")
            return False

        # Verify hash matches
        actual_hash = _hash_text(actual_content)
        if actual_hash != expected_hash:
            doc_logger.error(f"Hash mismatch in {file_path}: expected {expected_hash[:8]}..., got {actual_hash[:8]}...")
            return False

        return True

    except Exception as e:
        doc_logger.error(f"Failed to verify file write for {file_path}: {e}")
        return False


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class DefaultDict(dict):
    """Helper to avoid KeyError when formatting template fragments."""

    def __init__(self, base: Dict[str, Any]):
        super().__init__(base)

    def __missing__(self, key: str) -> str:
        return ""
