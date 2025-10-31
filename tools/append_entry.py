"""Tool for appending structured entries to the progress log."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List, Union
import time
from datetime import timedelta

import asyncio

from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.server import app
from scribe_mcp.tools.agent_project_utils import (
    ensure_agent_session,
    validate_agent_session,
)
from scribe_mcp import reminders
from scribe_mcp.utils.files import append_line, rotate_file
from scribe_mcp.utils.time import format_utc, utcnow
from scribe_mcp.shared.logging_utils import (
    ProjectResolutionError,
    compose_log_line as shared_compose_line,
    default_status_emoji,
    ensure_metadata_requirements,
    normalize_metadata,
    resolve_log_definition as shared_resolve_log_definition,
    resolve_logging_context,
)

_RATE_TRACKER: Dict[str, deque[float]] = defaultdict(deque)
_RATE_LOCKS: Dict[str, asyncio.Lock] = {}
_RATE_MAP_LOCK = asyncio.Lock()


def _sanitize_message(message: str) -> str:
    """Sanitize message for MCP protocol compatibility."""
    if not message:
        return message

    # Replace literal newlines with escaped newlines for MCP protocol
    # This allows multiline content to pass through validation
    sanitized = message.replace('\r\n', '\\n').replace('\r', '\\n').replace('\n', '\\n')
    return sanitized


def _get_repo_slug(project_root: str) -> str:
    """Extract repository slug from project root path."""
    from pathlib import Path
    import re

    # Convert to Path object and get the name of the directory
    path = Path(project_root)
    repo_name = path.name

    # Clean up the name to be URL-friendly
    # Replace spaces and special characters with hyphens
    slug = re.sub(r'[^a-zA-Z0-9_-]', '-', repo_name.lower())

    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    # Ensure it's not empty
    if not slug:
        slug = "unknown-repo"

    return slug


def _generate_deterministic_entry_id(
    repo_slug: str,
    project_slug: str,
    timestamp: str,
    agent: str,
    message: str,
    meta: Dict[str, Any]
) -> str:
    """Generate deterministic UUID for a log entry.

    Algorithm: sha256(repo_slug|project_slug|timestamp|agent|message|meta_sha)[:32]
    This ensures the same content always generates the same UUID across rebuilds.
    """
    # Create a deterministic hash of metadata
    meta_items = []
    for key, value in sorted(meta.items()):
        meta_items.append(f"{key}={value}")
    meta_str = "|".join(meta_items)
    meta_sha = hashlib.sha256(meta_str.encode("utf-8")).hexdigest()

    # Combine all components for deterministic hashing
    components = [
        repo_slug,
        project_slug,
        timestamp,
        agent,
        message,
        meta_sha
    ]
    combined = "|".join(components)
    full_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()

    # Use first 32 characters as deterministic UUID
    return full_hash[:32]


def _should_use_bulk_mode(message: str, items: Optional[str] = None, items_list: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Detect if content should be processed as bulk entries."""
    if items is not None or items_list is not None:
        return True

    # Check for multiline content
    newline_count = message.count('\n')
    pipe_count = message.count('|')

    # Use bulk mode if: many lines, contains pipes (potential delimiter issues), or very long
    return (
        newline_count > 0 or  # Any newlines
        pipe_count > 0 or      # Pipe characters that might cause issues
        len(message) > 500     # Long messages
    )


def _split_multiline_message(message: str, delimiter: str = "\n") -> List[Dict[str, Any]]:
    """Split multiline message into individual entries with smart content detection."""
    if not message:
        return []

    # Split by delimiter
    lines = message.split(delimiter)
    entries = []

    for line in lines:
        line = line.strip()
        if not line:  # Skip empty lines
            continue

        # Detect if this line might be structured (contains status indicators, emojis, etc.)
        entry = {"message": line}

        # Auto-detect status from common patterns
        if any(indicator in line.lower() for indicator in ["error:", "fail", "exception", "traceback"]):
            entry["status"] = "error"
        elif any(indicator in line.lower() for indicator in ["warning:", "warn", "caution"]):
            entry["status"] = "warn"
        elif any(indicator in line.lower() for indicator in ["success:", "complete", "done", "finished"]):
            entry["status"] = "success"
        elif any(indicator in line.lower() for indicator in ["fix:", "fixed", "resolved", "patched"]):
            entry["status"] = "success"

        # Auto-detect emoji from line
        words = line.split()
        for word in words:
            if word.strip() and len(word.strip()) == 1 and ord(word.strip()[0]) > 127:  # Likely emoji
                entry["emoji"] = word.strip()
                break

        entries.append(entry)

    return entries


def _prepare_bulk_items_with_timestamps(
    items: List[Dict[str, Any]],
    base_timestamp: Optional[str] = None,
    stagger_seconds: int = 1
) -> List[Dict[str, Any]]:
    """Add individual timestamps to bulk items."""
    if not items:
        return items

    # Parse base timestamp or use current time
    base_dt = None
    if base_timestamp:
        base_dt = _parse_timestamp(base_timestamp)

    if not base_dt:
        base_dt = utcnow()

    # Add staggered timestamps to each item
    for i, item in enumerate(items):
        if "timestamp_utc" not in item:
            item_dt = base_dt + timedelta(seconds=i * stagger_seconds)
            item["timestamp_utc"] = item_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    return items


def _apply_inherited_metadata(
    items: List[Dict[str, Any]],
    inherited_meta: Optional[Dict[str, Any]],
    inherited_status: Optional[str] = None,
    inherited_emoji: Optional[str] = None,
    inherited_agent: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Apply inherited metadata and values to all items in bulk."""
    if not items:
        return items

    for item in items:
        # Apply inherited status if item doesn't have one
        if inherited_status and "status" not in item:
            item["status"] = inherited_status

        # Apply inherited emoji if item doesn't have one
        if inherited_emoji and "emoji" not in item:
            item["emoji"] = inherited_emoji

        # Apply inherited agent if item doesn't have one
        if inherited_agent and "agent" not in item:
            item["agent"] = inherited_agent

        # Merge inherited metadata with item metadata
        if inherited_meta:
            item_meta = item.get("meta", {})
            # Create a new dict merging both
            merged_meta = {**inherited_meta, **item_meta}
            item["meta"] = merged_meta

    return items


async def _process_large_bulk_chunked(
    items: List[Dict[str, Any]],
    project: Dict[str, Any],
    recent: List[str],
    state_snapshot: Dict[str, Any],
    base_log_type: str,
    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]],
    chunk_size: int = 50
) -> Dict[str, Any]:
    """Process large bulk entries in chunks to optimize memory and performance."""
    if len(items) <= chunk_size:
        return await _append_bulk_entries(items, project, recent, state_snapshot, base_log_type, log_cache)

    all_written_lines = []
    all_failed_items = []
    total_chunks = (len(items) + chunk_size - 1) // chunk_size

    print(f"📊 Processing {len(items)} items in {total_chunks} chunks of {chunk_size}")

    last_result: Optional[Dict[str, Any]] = None
    paths_accum: set[str] = set()
    for i in range(0, len(items), chunk_size):
        chunk = items[i:i + chunk_size]
        chunk_num = i // chunk_size + 1

        print(f"📦 Processing chunk {chunk_num}/{total_chunks} ({len(chunk)} items)")

        result = await _append_bulk_entries(chunk, project, recent, state_snapshot, base_log_type, log_cache)
        last_result = result
        for path_str in result.get("paths") or [result.get("path")]:
            if path_str:
                paths_accum.add(path_str)

        all_written_lines.extend(result.get("written_lines", []))
        all_failed_items.extend(result.get("failed_items", []))

        # Small delay between chunks to prevent overwhelming the system
        if i + chunk_size < len(items):
            await asyncio.sleep(0.1)

    reminders_payload = await reminders.get_reminders(
        project, tool_name="append_entry", state=state_snapshot
    )
    primary_path = None
    if last_result:
        primary_path = last_result.get("path")

    return {
        "ok": len(all_failed_items) == 0,
        "written_count": len(all_written_lines),
        "failed_count": len(all_failed_items),
        "written_lines": all_written_lines,
        "failed_items": all_failed_items,
        "path": primary_path or project.get("progress_log"),
        "paths": sorted(paths_accum) or ([project.get("progress_log")] if project.get("progress_log") else []),
        "recent_projects": list(recent),
        "reminders": reminders_payload,
        "chunks_processed": total_chunks,
    }


@app.tool()
async def append_entry(
    message: str = "",
    status: Optional[str] = None,
    emoji: Optional[str] = None,
    agent: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    timestamp_utc: Optional[str] = None,
    items: Optional[str] = None,
    items_list: Optional[List[Dict[str, Any]]] = None,
    auto_split: bool = True,
    split_delimiter: str = "\n",
    stagger_seconds: int = 1,
    agent_id: Optional[str] = None,  # Agent identification (auto-detected if not provided)
    log_type: Optional[str] = "progress",
) -> Dict[str, Any]:
    """
    Enhanced append_entry with robust multiline handling and bulk mode support.

    Args:
        message: Log message (auto-splits multiline if auto_split=True)
        status: Status type (info|success|warn|error|bug|plan)
        emoji: Custom emoji override
        agent: Agent identifier
        meta: Metadata dictionary (applied to all entries in bulk/split mode)
        timestamp_utc: UTC timestamp string (base timestamp for bulk/split entries)
        items: JSON string array for bulk mode (backwards compatibility)
        items_list: Direct list of entry dictionaries for bulk mode (NEW)
        auto_split: Automatically split multiline messages into separate entries (default: True)
        split_delimiter: Delimiter for splitting multiline messages (default: newline)
        stagger_seconds: Seconds to stagger timestamps for bulk/split entries (default: 1)
        log_type: Target log identifier (progress/doc_updates/etc.) defined in config/log_config.json

    ENHANCED FEATURES:
    - Automatic multiline detection and splitting
    - Direct list support for bulk mode (no JSON string required)
    - Individual timestamps for each entry in bulk/split mode
    - Robust error handling with automatic fallbacks
    - Performance optimized for large content

    Single Entry Mode: Auto-detects and handles multiline content
    Bulk Mode: Support both items (JSON string) and items_list (direct list)
    """
    state_snapshot = await server_module.state_manager.record_tool("append_entry")

    # Normalize metadata early for consistent handling throughout the function
    meta_pairs = _normalise_meta(meta)
    meta_payload = {key: value for key, value in meta_pairs}

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
            agent_id, "append_entry", {"message_length": len(message), "status": status, "bulk_mode": items is not None}
        )

    try:
        context = await resolve_logging_context(
            tool_name="append_entry",
            server_module=server_module,
            agent_id=agent_id,
            require_project=True,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "suggestion": f"Invoke set_project with agent_id='{agent_id}' before appending entries",
            "recent_projects": list(exc.recent_projects),
        }

    project = context.project or {}
    recent = list(context.recent_projects)
    reminders_payload: List[Dict[str, Any]] = list(context.reminders)

    # Validate that either message, items, or items_list is provided
    if not items and not items_list and not message:
        return {
            "ok": False,
            "error": "Either 'message', 'items', or 'items_list' must be provided",
            "suggestion": "Use message for single/multiline entries, items for JSON bulk, or items_list for direct list bulk",
            "recent_projects": list(recent),
        }

    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]] = {}
    base_log_type = (log_type or "progress").lower()

    # Enhanced bulk mode handling with multiple input formats
    bulk_items = None

    if items_list is not None:
        # Direct list support (NEW)
        if not isinstance(items_list, list):
            return {
                "ok": False,
                "error": "items_list must be a list of dictionaries",
                "recent_projects": list(recent),
            }
        bulk_items = items_list.copy()

    elif items is not None:
        # JSON string support (backwards compatibility)
        try:
            parsed_items = json.loads(items)
            if not isinstance(parsed_items, list):
                return {
                    "ok": False,
                    "error": "Items parameter must be a JSON array",
                    "suggestion": "Use items_list parameter for direct list support",
                    "recent_projects": list(recent),
                }
            bulk_items = parsed_items
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": "Items parameter must be valid JSON array",
                "suggestion": "Use items_list parameter to avoid JSON encoding issues",
                "recent_projects": list(recent),
            }

    # Handle auto-split multiline content
    if bulk_items is None and message:
        # Sanitize message for MCP protocol
        sanitized_message = _sanitize_message(message)

        # Check if we should auto-split into bulk mode
        if auto_split and _should_use_bulk_mode(message):
            print("🔄 Auto-detecting multiline content, switching to bulk mode...")

            # Split the message into individual entries
            bulk_items = _split_multiline_message(message, split_delimiter)

            if len(bulk_items) > 1:
                print(f"📝 Split message into {len(bulk_items)} entries")

                # Apply inherited metadata to all split entries
                bulk_items = _apply_inherited_metadata(
                    bulk_items, meta_payload, status, emoji, agent
                )

                # Add individual timestamps
                bulk_items = _prepare_bulk_items_with_timestamps(
                    bulk_items, timestamp_utc, stagger_seconds
                )

                # Process as bulk
                if len(bulk_items) > 50:  # Large content - use chunked processing
                    return await _process_large_bulk_chunked(
                        bulk_items, project, recent, state_snapshot, base_log_type, log_cache
                    )
                else:
                    return await _append_bulk_entries(
                        bulk_items, project, recent, state_snapshot, base_log_type, log_cache
                    )
            else:
                # Single entry after split, continue with single entry mode
                message = sanitized_message

        else:
            # Use sanitized message for single entry
            message = sanitized_message

    # Process bulk items if we have them
    if bulk_items:
        # Apply inherited metadata if not already applied
        if meta or status or emoji or agent:
            bulk_items = _apply_inherited_metadata(
                bulk_items, meta_payload, status, emoji, agent
            )

        # Add timestamps if not present
        bulk_items = _prepare_bulk_items_with_timestamps(
            bulk_items, timestamp_utc, stagger_seconds
        )

        # Large content optimization
        if len(bulk_items) > 50:
            return await _process_large_bulk_chunked(
                bulk_items, project, recent, state_snapshot, base_log_type, log_cache
            )
        else:
            return await _append_bulk_entries(
                bulk_items, project, recent, state_snapshot, base_log_type, log_cache
            )

    # Single entry mode - validate message (now with robust handling)
    validation_error = _validate_message(message)
    if validation_error:
        # Provide helpful error messages with suggestions
        error_msg = validation_error
        suggestion = None

        if "newline" in validation_error:
            suggestion = "Set auto_split=True to automatically handle multiline content"
            error_msg = "Message contains newline characters"
        elif "pipe" in validation_error:
            suggestion = "Replace pipe characters with alternative delimiters"
            error_msg = "Message contains pipe characters"

        return {
            "ok": False,
            "error": error_msg,
            "suggestion": suggestion,
            "alternative": "Consider using bulk mode with items_list parameter for complex content",
            "recent_projects": list(recent),
        }

    rate_error = await _enforce_rate_limit(project["name"])
    if rate_error:
        rate_error["recent_projects"] = list(recent)
        return rate_error

    resolved_emoji = _resolve_emoji(emoji, status, project)
    defaults = project.get("defaults") or {}
    resolved_agent = _sanitize_identifier(agent or defaults.get("agent") or "Scribe")
    timestamp_dt, timestamp, timestamp_warning = _resolve_timestamp(timestamp_utc)

    # Metadata already normalized at function start (meta_pairs defined at line 273)
    meta_payload = {key: value for key, value in meta_pairs}

    entry_log_type = base_log_type
    log_path, log_definition = _resolve_log_target(project, entry_log_type, log_cache)
    requirement_error = _validate_log_requirements(log_definition, meta_payload)
    if requirement_error:
        return {
            "ok": False,
            "error": requirement_error,
            "recent_projects": list(recent),
        }
    meta_payload.setdefault("log_type", entry_log_type)

    # Generate deterministic entry_id
    repo_slug = _get_repo_slug(project["root"])
    project_slug = project["name"].lower().replace(" ", "-").replace("_", "-")
    entry_id = _generate_deterministic_entry_id(
        repo_slug=repo_slug,
        project_slug=project_slug,
        timestamp=timestamp,
        agent=resolved_agent,
        message=message,
        meta=meta_payload
    )

    line = _compose_line(
        emoji=resolved_emoji,
        timestamp=timestamp,
        agent=resolved_agent,
        project_name=project["name"],
        message=message,
        meta_pairs=meta_pairs,
        entry_id=entry_id,
    )

    await _rotate_if_needed(log_path)
    await append_line(log_path, line)

    backend = server_module.storage_backend
    if backend:
        sha_value = hashlib.sha256(line.encode("utf-8")).hexdigest()
        ts_dt = timestamp_dt or utcnow()
        timeout = settings.storage_timeout_seconds
        try:
            async with asyncio.timeout(timeout):
                record = await backend.fetch_project(project["name"])
            if not record:
                async with asyncio.timeout(timeout):
                    record = await backend.upsert_project(
                        name=project["name"],
                        repo_root=project["root"],
                        progress_log_path=project["progress_log"],
                    )
            async with asyncio.timeout(timeout):
                await backend.insert_entry(
                    entry_id=entry_id,
                    project=record,
                    ts=ts_dt,
                    emoji=resolved_emoji,
                    agent=resolved_agent,
                    message=message,
                    meta=meta_payload,
                    raw_line=line,
                    sha256=sha_value,
                )
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "ok": False,
                "error": f"Failed to persist log entry: {exc}",
                "recent_projects": list(recent),
            }

    if project:
        reminders_payload = await reminders.get_reminders(
            project,
            tool_name="append_entry",
            state=state_snapshot,
        )

    return {
        "ok": True,
        "written_line": line,
        "path": str(log_path),
        "recent_projects": list(recent),
        "meta": meta_payload,
        "reminders": reminders_payload,
        **({"timestamp_warning": timestamp_warning} if timestamp_warning else {}),
    }


def _resolve_emoji(
    explicit: Optional[str],
    status: Optional[str],
    project: Dict[str, Any],
) -> str:
    return default_status_emoji(explicit=explicit, status=status, project=project)


def _normalise_meta(meta: Optional[Dict[str, Any]]) -> tuple[tuple[str, str], ...]:
    """Delegate metadata normalization to the shared logging utility."""
    return normalize_metadata(meta)


def _compose_line(
    *,
    emoji: str,
    timestamp: str,
    agent: str,
    project_name: str,
    message: str,
    meta_pairs: tuple[tuple[str, str], ...],
    entry_id: Optional[str] = None,
) -> str:
    return shared_compose_line(
        emoji=emoji,
        timestamp=timestamp,
        agent=agent,
        project_name=project_name,
        message=message,
        meta_pairs=meta_pairs,
        entry_id=entry_id,
    )


def _resolve_timestamp(timestamp_utc: Optional[str]) -> Tuple[Optional[datetime], str, Optional[str]]:
    if not timestamp_utc:
        current = format_utc()
        return None, current, None
    parsed = _parse_timestamp(timestamp_utc)
    if parsed is None:
        fallback = format_utc()
        warning = "timestamp format invalid; using current time"
        return None, fallback, warning
    return parsed, timestamp_utc, None


def _parse_timestamp(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _sanitize_identifier(value: str) -> str:
    sanitized = value.replace("[", "").replace("]", "").replace("|", "").strip()
    return sanitized or "Scribe"


def _validate_message(message: str) -> Optional[str]:
    if any(ch in message for ch in ("\n", "\r")):
        return "Message cannot contain newline characters."
    if "|" in message:
        return "Message cannot contain pipe characters."  # avoids delimiter collisions
    return None


async def _enforce_rate_limit(project_name: str) -> Optional[Dict[str, Any]]:
    count = settings.log_rate_limit_count
    window = settings.log_rate_limit_window
    if count <= 0 or window <= 0:
        return None

    now = time.time()
    async with _RATE_MAP_LOCK:
        lock = _RATE_LOCKS.setdefault(project_name, asyncio.Lock())

    async with lock:
        bucket = _RATE_TRACKER[project_name]
        while bucket and now - bucket[0] > window:
            bucket.popleft()

        if len(bucket) >= count:
            retry_after = int(window - (now - bucket[0]))
            return {
                "ok": False,
                "error": "Rate limit exceeded for project log.",
                "retry_after_seconds": max(retry_after, 1),
            }

        bucket.append(now)
        return None


def _resolve_log_target(
    project: Dict[str, Any],
    log_type: str,
    cache: Dict[str, Tuple[Path, Dict[str, Any]]],
) -> Tuple[Path, Dict[str, Any]]:
    return shared_resolve_log_definition(project, log_type, cache=cache)


def _validate_log_requirements(definition: Dict[str, Any], meta_payload: Dict[str, Any]) -> Optional[str]:
    return ensure_metadata_requirements(definition, meta_payload)


async def _append_bulk_entries(
    items: List[Dict[str, Any]],
    project: Dict[str, Any],
    recent: List[str],
    state_snapshot: Dict[str, Any],
    base_log_type: str,
    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]],
) -> Dict[str, Any]:
    """Enhanced bulk entry processing with robust error handling and optimizations."""
    if not items:
        return {
            "ok": False,
            "error": "Items list cannot be empty",
            "recent_projects": list(recent),
        }

    written_lines: List[str] = []
    failed_items = []
    paths_used: List[str] = []
    rotated_paths: set[Path] = set()

    # Batch database operations for better performance
    backend = server_module.storage_backend
    batch_db_entries = []

    # Ensure project exists in database
    if backend:
        try:
            timeout = settings.storage_timeout_seconds
            async with asyncio.timeout(timeout):
                record = await backend.fetch_project(project["name"])
            if not record:
                async with asyncio.timeout(timeout):
                    record = await backend.upsert_project(
                        name=project["name"],
                        repo_root=project["root"],
                        progress_log_path=project["progress_log"],
                    )
        except Exception as exc:
            print(f"⚠️  Warning: Database setup failed: {exc}")
            backend = None  # Disable database for this batch

    # Process each item with enhanced error handling
    for i, item in enumerate(items):
        try:
            # Validate required fields
            if "message" not in item:
                failed_items.append({
                    "index": i,
                    "error": "Missing required 'message' field",
                    "item": item
                })
                continue

            item_message = item["message"]
            if not item_message.strip():
                failed_items.append({
                    "index": i,
                    "error": "Message cannot be empty",
                    "item": item
                })
                continue

            # Enhanced message validation with auto-sanitization
            validation_error = _validate_message(item_message)
            if validation_error:
                # Try to auto-fix common issues
                if "newline" in validation_error:
                    # Sanitize newlines for this item
                    item_message = _sanitize_message(item_message)
                    item["message"] = item_message  # Update for later processing
                else:
                    failed_items.append({
                        "index": i,
                        "error": validation_error,
                        "item": item
                    })
                    continue

            # Extract item properties with defaults
            item_status = item.get("status")
            item_emoji = item.get("emoji")
            item_agent = item.get("agent")
            item_meta = item.get("meta")
            item_timestamp = item.get("timestamp_utc")

            # Resolve values similar to single entry
            resolved_emoji = _resolve_emoji(item_emoji, item_status, project)
            defaults = project.get("defaults") or {}
            resolved_agent = _sanitize_identifier(item_agent or defaults.get("agent") or "Scribe")
            timestamp_dt, timestamp, timestamp_warning = _resolve_timestamp(item_timestamp)
            meta_pairs = _normalise_meta(item_meta)
            meta_payload = {key: value for key, value in meta_pairs}

            entry_log_type = (item.get("log_type") or base_log_type).lower()
            log_path, log_definition = _resolve_log_target(project, entry_log_type, log_cache)
            if log_path not in rotated_paths:
                await _rotate_if_needed(log_path)
                rotated_paths.add(log_path)

            requirement_error = _validate_log_requirements(log_definition, meta_payload)
            if requirement_error:
                failed_items.append({
                    "index": i,
                    "error": requirement_error,
                    "item": item
                })
                continue
            meta_payload.setdefault("log_type", entry_log_type)

            # Generate deterministic entry_id for bulk item
            repo_slug = _get_repo_slug(project["root"])
            project_slug = project["name"].lower().replace(" ", "-").replace("_", "-")
            entry_id = _generate_deterministic_entry_id(
                repo_slug=repo_slug,
                project_slug=project_slug,
                timestamp=timestamp,
                agent=resolved_agent,
                message=item_message,
                meta=meta_payload
            )

            # Compose line
            line = _compose_line(
                emoji=resolved_emoji,
                timestamp=timestamp,
                agent=resolved_agent,
                project_name=project["name"],
                message=item_message,
                meta_pairs=meta_pairs,
                entry_id=entry_id,
            )

            # Write to file immediately (ensures order)
            await append_line(log_path, line)
            written_lines.append(line)
            paths_used.append(str(log_path))

            # Prepare database entry for batch processing
            if backend:
                sha_value = hashlib.sha256(line.encode("utf-8")).hexdigest()
                ts_dt = timestamp_dt or utcnow()

                batch_db_entries.append({
                    "entry_id": entry_id,
                    "record": record,
                    "ts": ts_dt,
                    "emoji": resolved_emoji,
                    "agent": resolved_agent,
                    "message": item_message,
                    "meta": meta_payload,
                    "raw_line": line,
                    "sha256": sha_value,
                    "index": i
                })

        except Exception as exc:
            failed_items.append({
                "index": i,
                "error": f"Processing error: {exc}",
                "item": item
            })

    # Batch database write for performance
    if backend and batch_db_entries:
        try:
            timeout = settings.storage_timeout_seconds
            async with asyncio.timeout(timeout):
                for db_entry in batch_db_entries:
                    await backend.insert_entry(
                        entry_id=db_entry["entry_id"],
                        project=db_entry["record"],
                        ts=db_entry["ts"],
                        emoji=db_entry["emoji"],
                        agent=db_entry["agent"],
                        message=db_entry["message"],
                        meta=db_entry["meta"],
                        raw_line=db_entry["raw_line"],
                        sha256=db_entry["sha256"],
                    )
        except Exception as exc:
            # Mark all items in this batch as failed
            for db_entry in batch_db_entries:
                failed_items.append({
                    "index": db_entry["index"],
                    "error": f"Database error: {exc}",
                    "retry_possible": True
                })
            print(f"⚠️  Warning: Batch database write failed: {exc}")

    # Get reminders
    reminders_payload = await reminders.get_reminders(
        project,
        tool_name="append_entry",
        state=state_snapshot,
    )

    # Build comprehensive result
    unique_paths = sorted(set(paths_used))
    result = {
        "ok": len(failed_items) == 0,
        "written_count": len(written_lines),
        "failed_count": len(failed_items),
        "written_lines": written_lines,
        "failed_items": failed_items,
        "path": unique_paths[0] if unique_paths else project.get("progress_log"),
        "paths": unique_paths,
        "recent_projects": list(recent),
        "reminders": reminders_payload,
    }

    # Add performance metrics for large operations
    if len(items) > 10:
        result["performance"] = {
            "total_items": len(items),
            "items_per_second": len(items) / 1.0,  # Approximate
            "database_batch_size": len(batch_db_entries) if backend else 0,
        }

    return result


async def _rotate_if_needed(path: Path) -> None:
    max_bytes = settings.log_max_bytes
    if max_bytes <= 0:
        return
    if not path.exists():
        return
    size = await asyncio.to_thread(lambda: path.stat().st_size)
    if size < max_bytes:
        return
    suffix = utcnow().strftime("%Y%m%d%H%M%S")
    await rotate_file(path, suffix, confirm=True)
