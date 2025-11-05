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
from scribe_mcp.utils.parameter_validator import (
    ToolValidator,
    BulletproofParameterCorrector,
)
import re

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


class DocumentVerificationError(Exception):
    """Raised when document write verification fails."""
    pass


class DocumentValidationError(Exception):
    """Raised when document validation fails."""
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
    file_size_before = 0

    try:
        # Validate and correct inputs (bulletproof - never fails)
        doc, action, section, content, template, metadata = _validate_and_correct_inputs(
            doc, action, section, content, template, metadata
        )

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

        # Render content when required
        rendered_content: Optional[str] = None
        if action in {"replace_section", "append"}:
            try:
                rendered_content = await _render_content(project, content, template, metadata)
            except Exception as e:
                raise DocumentOperationError(f"Failed to render content: {e}")

        # Apply the change based on action
        try:
            if action == "replace_section":
                assert rendered_content is not None
                updated_text = _replace_section(original_text, section, rendered_content)
            elif action == "append":
                assert rendered_content is not None
                meta_payload = metadata if isinstance(metadata, dict) else {}
                position_value = meta_payload.get("position", "after")
                updated_text = _append_block(
                    original_text,
                    rendered_content,
                    section=section,
                    position=str(position_value),
                )
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
    # Handle case where metadata comes as JSON string from MCP framework
    if metadata is None:
        metadata = {}
    elif isinstance(metadata, str):
        try:
            import json
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    # Check if template_name is actually a fallback content string from parameter validator
    # Common fallback strings that should be treated as content, not template names
    fallback_strings = {"No message provided", "Invalid message format", "Empty message"}

    if template_name and template_name in fallback_strings:
        # Treat fallback strings as content, not template names
        if content is None:
            content = template_name
        template_name = None

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
        doc_logger.warning(
            "Section anchor missing; auto-appending '%s' to document.",
            section,
            extra={"section": section, "action": "replace_section"},
        )
        prefix = text.rstrip()
        if prefix:
            prefix = prefix + "\n\n"
        return prefix + marker + "\n" + content.strip() + "\n"
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


def _append_block(text: str, content: str, section: Optional[str] = None, position: str = "after") -> str:
    normalized = content.strip()
    if not normalized:
        return text

    if not section:
        if not text.endswith("\n"):
            text += "\n"
        if normalized:
            return text + normalized + "\n"
        return text

    marker = SECTION_MARKER.format(section=section)
    idx = text.find(marker)
    if idx == -1:
        doc_logger.warning(
            "Append anchor '%s' missing; creating new block.",
            section,
            extra={"section": section, "action": "append"},
        )
        prefix = text.rstrip()
        if prefix:
            prefix = prefix + "\n\n"
        return prefix + marker + "\n" + normalized + "\n"

    after_marker = idx + len(marker)
    while after_marker < len(text) and text[after_marker] in "\r\n":
        after_marker += 1
    next_marker = text.find("<!-- ID:", after_marker)
    if next_marker == -1:
        next_marker = len(text)

    position = position.lower()
    if position == "before":
        insertion_point = idx
    elif position in {"inside", "within", "start"}:
        insertion_point = after_marker
    else:
        insertion_point = next_marker

    prefix = text[:insertion_point]
    suffix = text[insertion_point:]

    insertion = normalized
    if insertion and not insertion.endswith("\n"):
        insertion += "\n"

    if prefix and not prefix.endswith("\n"):
        insertion = "\n" + insertion
    if suffix and not suffix.startswith("\n"):
        insertion = insertion + "\n"

    return prefix + insertion + suffix


def _toggle_checklist_status(text: str, section: Optional[str], metadata: Dict[str, Any]) -> str:
    desired_raw = metadata.get("status")
    desired = desired_raw.lower().strip() if isinstance(desired_raw, str) else None
    proof = metadata.get("proof")
    label = metadata.get("label") or metadata.get("item") or metadata.get("text") or metadata.get("title")

    done_states = {"done", "completed", "complete", "true", "yes", "checked", "finished"}
    pending_states = {"pending", "todo", "not done", "open", "incomplete", "undone"}

    def resolve_token(existing_line: Optional[str]) -> str:
        if desired in done_states:
            return "[x]"
        if desired in pending_states:
            return "[ ]"
        if existing_line:
            return "[x]" if "- [x]" in existing_line else "[ ]"
        return "[x]"

    lines = text.splitlines()
    section_marker = SECTION_MARKER.format(section=section) if section else None
    section_start_idx: Optional[int] = None
    section_end_idx: int = len(lines)

    if section_marker:
        for idx, line in enumerate(lines):
            if line.strip() == section_marker:
                section_start_idx = idx
                break
        if section_start_idx is not None:
            for idx in range(section_start_idx + 1, len(lines)):
                stripped = lines[idx].strip()
                if stripped.startswith("<!-- ID:") and stripped != section_marker:
                    section_end_idx = idx
                    break
        else:
            # Auto-heal missing anchor: append new section with checklist entry.
            doc_logger.warning(
                "Checklist section anchor '%s' missing; creating new block.",
                section,
                extra={"section": section, "action": "status_update"},
            )
            token = resolve_token(None)
            entry_label = label or (section.replace("_", " ").title() if section else "Checklist item")
            new_line = f"- {token} {entry_label}"
            if proof:
                new_line += f" | proof={proof}"
            prefix = text.rstrip()
            if prefix:
                prefix = prefix + "\n\n"
            return prefix + section_marker + "\n" + new_line + "\n"

    replacement = False
    search_start = (section_start_idx + 1) if section_start_idx is not None else 0
    search_end = section_end_idx

    for idx in range(search_start, search_end):
        line = lines[idx]
        if "- [ ]" not in line and "- [x]" not in line:
            continue

        token = resolve_token(line)
        if "- [x]" in line:
            new_line = line.replace("- [x]", f"- {token}", 1)
        else:
            new_line = line.replace("- [ ]", f"- {token}", 1)

        parts = new_line.split(" | ")
        prefix = parts[0].rstrip()
        other_tokens = [part for part in parts[1:] if not part.startswith("proof=")]
        if proof:
            other_tokens.append(f"proof={proof}")
        new_line = " | ".join([prefix] + other_tokens) if other_tokens else prefix
        lines[idx] = new_line
        replacement = True
        break

    if not replacement:
        token = resolve_token(None)
        entry_label = label or (section.replace("_", " ").title() if section else "Checklist item")
        new_line = f"- {token} {entry_label}"
        if proof:
            new_line += f" | proof={proof}"
        insertion_index = search_end
        lines.insert(insertion_index, new_line)
        replacement = True

    updated_text = "\n".join(lines)
    if text.endswith("\n"):
        return updated_text + "\n"
    return updated_text


def _validate_comparison_symbols(value: Any) -> bool:
    """Validate that comparison symbols in strings are properly handled."""
    if not isinstance(value, str):
        return True

    # Check for patterns that look like they're meant to be numeric comparisons
    # These are the cases that typically cause "not supported between str and float" errors
    import re

    # Pattern: numeric value followed by comparison operator followed by numeric value
    # e.g., "5 > 3", "10.5 <= 20", etc.
    numeric_comparison_pattern = r'^\s*\d+\.?\d*\s*[><=]+\s*\d+\.?\d*\s*$'

    if re.match(numeric_comparison_pattern, value.strip()):
        # This looks like a numeric comparison that should be handled elsewhere
        return False

    # Also check for problematic metadata values that might be compared as numbers
    if value.strip().isdigit() or (value.replace('.', '', 1).isdigit() and '.' in value):
        # Pure numeric values might cause issues in string vs numeric comparisons
        return True  # Allow these, but be cautious

    return True


def _validate_and_correct_inputs(
    doc: str,
    action: str,
    section: Optional[str],
    content: Optional[str],
    template: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> tuple[str, str, Optional[str], Optional[str], Optional[str], Dict[str, Any]]:
    """
    Bulletproof parameter validation and correction that NEVER fails.

    Returns corrected parameters tuple: (doc, action, section, content, template, metadata)
    """
    # Define validation schema
    validation_schema = {
        "doc": {
            "type": str,
            "required": True,
            "allowed_values": {"architecture", "phase_plan", "checklist", "implementation", "research", "bugs"},
            "default": "implementation"
        },
        "action": {
            "type": str,
            "required": True,
            "allowed_values": {"replace_section", "append", "status_update", "list_sections", "batch",
                             "create_research_doc", "create_bug_report", "create_review_report", "create_agent_report_card"},
            "default": "append"
        },
        "section": {
            "type": str,
            "required": False,
            "default": None
        },
        "content": {
            "type": str,
            "required": False,
            "default": None
        },
        "template": {
            "type": str,
            "required": False,
            "default": None
        },
        "metadata": {
            "type": dict,
            "required": False,
            "default": {}
        }
    }

    # Apply bulletproof parameter correction
    input_params = {
        "doc": doc,
        "action": action,
        "section": section,
        "content": content,
        "template": template,
        "metadata": metadata
    }

    corrected_params = BulletproofParameterCorrector.ensure_parameter_validity(input_params, validation_schema)

    # Apply business logic corrections
    corrected_doc = corrected_params["doc"]
    corrected_action = corrected_params["action"]
    corrected_section = corrected_params["section"]
    corrected_content = corrected_params["content"]
    corrected_template = corrected_params["template"]
    corrected_metadata = corrected_params["metadata"]

    # Special handling for different actions
    if corrected_action == "list_sections":
        return corrected_doc, corrected_action, None, None, None, {}

    if corrected_action == "batch":
        # Ensure metadata has operations list
        if not isinstance(corrected_metadata, dict):
            corrected_metadata = {}

        if "operations" not in corrected_metadata or not corrected_metadata["operations"]:
            corrected_metadata["operations"] = []

        if not isinstance(corrected_metadata["operations"], list):
            corrected_metadata["operations"] = [corrected_metadata["operations"]]

        return corrected_doc, corrected_action, None, None, None, corrected_metadata

    # Section validation for actions that need it
    if corrected_action in {"replace_section", "status_update"}:
        if not corrected_section:
            corrected_section = "main_content"

        # Sanitize section ID - keep only alphanumeric, hyphens, underscores
        import re
        sanitized_section = re.sub(r'[^a-zA-Z0-9_-]', '', corrected_section)
        if not sanitized_section:
            sanitized_section = "main_content"
        corrected_section = sanitized_section

    # Content/template handling
    if corrected_action == "status_update":
        # For status updates, ensure metadata has required fields
        if not isinstance(corrected_metadata, dict):
            corrected_metadata = {}

        if not any(key in corrected_metadata for key in ["status", "proof", "completed"]):
            corrected_metadata["status"] = "in_progress"

        # Clear content and template for status updates
        corrected_content = None
        corrected_template = None
    else:
        # For other actions, ensure we have either content or template
        if not corrected_content and not corrected_template:
            corrected_content = f"## {corrected_action.replace('_', ' ').title()}\n\nContent placeholder."

    return corrected_doc, corrected_action, corrected_section, corrected_content, corrected_template, corrected_metadata


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
_SLUG_CLEANER = re.compile(r"[^0-9a-z_]+")


def slugify_project_name(name: str) -> str:
    """Return a filesystem-friendly slug; duplicated here to avoid circular imports during tests."""
    normalised = name.strip().lower().replace(" ", "_")
    return _SLUG_CLEANER.sub("_", normalised).strip("_") or "project"
