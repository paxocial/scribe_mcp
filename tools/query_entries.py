"""Advanced querying for progress log entries."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.constants import STATUS_EMOJI
from scribe_mcp.tools.project_utils import load_active_project, load_project_config
from scribe_mcp.utils.logs import parse_log_line, read_all_lines
from scribe_mcp.utils.search import message_matches
from scribe_mcp.utils.time import coerce_range_boundary
from scribe_mcp.utils.response import default_formatter, create_pagination_info
from scribe_mcp.utils.tokens import token_estimator
from scribe_mcp import reminders

VALID_MESSAGE_MODES = {"substring", "regex", "exact"}
META_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


@app.tool()
async def query_entries(
    project: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    message: Optional[str] = None,
    message_mode: str = "substring",
    case_sensitive: bool = False,
    emoji: Optional[List[str]] = None,
    status: Optional[List[str]] = None,
    agents: Optional[List[str]] = None,
    meta_filters: Optional[Dict[str, Any]] = None,
    limit: int = 50,
    page: int = 1,
    page_size: int = 50,
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_metadata: bool = True,
) -> Dict[str, Any]:
    """Search the project log with flexible filters and pagination.

    Args:
        project: Project name (uses active project if None)
        start: Start timestamp filter
        end: End timestamp filter
        message: Message text filter
        message_mode: How to match message (substring, regex, exact)
        case_sensitive: Case sensitive message matching
        emoji: Filter by emoji(s)
        status: Filter by status(es) (mapped to emojis)
        agents: Filter by agent name(s)
        meta_filters: Filter by metadata key/value pairs
        limit: Maximum results to return (legacy, for backward compatibility)
        page: Page number for pagination (1-based)
        page_size: Number of results per page
        compact: Use compact response format with short field names
        fields: Specific fields to include in response
        include_metadata: Include metadata field in entries

    Returns:
        Paginated response with entries and metadata
    """
    state_snapshot = await server_module.state_manager.record_tool("query_entries")

    # Handle pagination vs legacy limit
    if page > 1 or page_size != 50:
        # Use pagination mode
        limit = None  # Ignore limit in pagination mode
    else:
        # Use legacy mode for backward compatibility
        limit = max(1, min(limit or 50, 500))
        page_size = limit
    message_mode = (message_mode or "substring").lower()
    if message_mode not in VALID_MESSAGE_MODES:
        return {"ok": False, "error": f"Unsupported message_mode '{message_mode}'."}

    if message and message_mode == "regex":
        try:
            re.compile(message)
        except re.error as exc:
            return {"ok": False, "error": f"Invalid regex for message filter: {exc}"}

    normalised_emoji = _resolve_emojis(emoji, status)
    meta_normalised, meta_error = _normalise_meta_filters(meta_filters)
    if meta_error:
        return {"ok": False, "error": meta_error}

    start_bound, start_error = _normalise_boundary(start, end=False)
    if start_error:
        return {"ok": False, "error": start_error}
    end_bound, end_error = _normalise_boundary(end, end=True)
    if end_error:
        return {"ok": False, "error": end_error}

    project_data, active_name, recent = await _resolve_project(project)
    reminders_payload: List[Dict[str, Any]] = []
    if not project_data:
        return {
            "ok": False,
            "error": f"Project '{project or active_name}' is not configured.",
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }

    backend = server_module.storage_backend
    if backend:
        record = await backend.fetch_project(project_data["name"])
        if not record:
            record = await backend.upsert_project(
                name=project_data["name"],
                repo_root=project_data["root"],
                progress_log_path=project_data["progress_log"],
            )

        # Use pagination if available
        if hasattr(backend, 'query_entries_paginated'):
            rows, total_count = await backend.query_entries_paginated(
                project=record,
                page=page,
                page_size=page_size,
                start=start_bound.isoformat() if start_bound else None,
                end=end_bound.isoformat() if end_bound else None,
                agents=_clean_list(agents),
                emojis=normalised_emoji or None,
                message=message,
                message_mode=message_mode,
                case_sensitive=case_sensitive,
                meta_filters=meta_normalised or None,
            )
            pagination_info = create_pagination_info(page, page_size, total_count)
        else:
            # Fallback to legacy method
            offset = (page - 1) * page_size
            rows = await backend.query_entries(
                project=record,
                limit=page_size,
                start=start_bound.isoformat() if start_bound else None,
                end=end_bound.isoformat() if end_bound else None,
                agents=_clean_list(agents),
                emojis=normalised_emoji or None,
                message=message,
                message_mode=message_mode,
                case_sensitive=case_sensitive,
                meta_filters=meta_normalised or None,
                offset=offset,
            )
            # Get total count (less efficient fallback)
            total_count = await backend.count_query_entries(
                project=record,
                start=start_bound.isoformat() if start_bound else None,
                end=end_bound.isoformat() if end_bound else None,
                agents=_clean_list(agents),
                emojis=normalised_emoji or None,
                message=message,
                message_mode=message_mode,
                case_sensitive=case_sensitive,
                meta_filters=meta_normalised or None,
            )
            pagination_info = create_pagination_info(page, page_size, total_count)

        reminders_payload = await reminders.get_reminders(
            project_data,
            tool_name="query_entries",
            state=state_snapshot,
        )

        # Format response using the response formatter
        response = default_formatter.format_response(
            entries=rows,
            compact=compact,
            fields=fields,
            include_metadata=include_metadata,
            pagination=pagination_info,
            extra_data={
                "recent_projects": list(recent),
                "reminders": reminders_payload,
            }
        )

        # Record token usage
        if token_estimator:
            token_estimator.record_operation(
                operation="query_entries",
                input_data={
                    "project": project,
                    "start": start,
                    "end": end,
                    "message": message,
                    "page": page,
                    "page_size": page_size,
                    "compact": compact,
                    "fields": fields,
                    "include_metadata": include_metadata
                },
                response=response,
                compact_mode=compact,
                page_size=page_size
            )

        return response

    # File-based fallback with pagination
    all_entries = await _query_file(
        project_data,
        limit=None,  # Get all matching entries
        start=start_bound,
        end=end_bound,
        message=message,
        message_mode=message_mode,
        case_sensitive=case_sensitive,
        agents=_clean_list(agents),
        emojis=normalised_emoji or None,
        meta_filters=meta_normalised or None,
    )

    # Apply pagination to file-based results
    total_count = len(all_entries)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_entries = all_entries[start_idx:end_idx]

    pagination_info = create_pagination_info(page, page_size, total_count)

    reminders_payload = await reminders.get_reminders(
        project_data,
        tool_name="query_entries",
        state=state_snapshot,
    )

    # Format response using the response formatter
    response = default_formatter.format_response(
        entries=paginated_entries,
        compact=compact,
        fields=fields,
        include_metadata=include_metadata,
        pagination=pagination_info,
        extra_data={
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }
    )

    # Record token usage
    if token_estimator:
        token_estimator.record_operation(
            operation="query_entries",
            input_data={
                "project": project,
                "start": start,
                "end": end,
                "message": message,
                "page": page,
                "page_size": page_size,
                "compact": compact,
                "fields": fields,
                "include_metadata": include_metadata,
                "backend": "file"
            },
            response=response,
            compact_mode=compact,
            page_size=page_size
        )

    return response


async def _resolve_project(
    project_name: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Tuple[str, ...]]:
    if not project_name:
        return await load_active_project(server_module.state_manager)

    state = await server_module.state_manager.load()
    project = state.get_project(project_name)
    if project:
        return project, project_name, tuple(state.recent_projects)

    config = load_project_config(project_name)
    return config, project_name, tuple(state.recent_projects)


async def _query_file(
    project: Dict[str, Any],
    *,
    limit: Optional[int],
    start: Optional[datetime],
    end: Optional[datetime],
    message: Optional[str],
    message_mode: str,
    case_sensitive: bool,
    agents: Optional[List[str]],
    emojis: Optional[List[str]],
    meta_filters: Optional[Dict[str, str]],
) -> List[Dict[str, Any]]:
    path = Path(project["progress_log"])
    lines = await read_all_lines(path)
    results: List[Dict[str, Any]] = []

    def within_bounds(ts_str: Optional[str]) -> bool:
        if not ts_str:
            return False
        parsed = coerce_range_boundary(ts_str, end=False)
        if not parsed:
            return False
        if start and parsed < start:
            return False
        if end and parsed > end:
            return False
        return True

    agent_set = set(agents or [])
    emoji_set = set(emojis or [])

    for line in reversed(lines):
        parsed = parse_log_line(line)
        if not parsed:
            continue
        if (start or end) and not within_bounds(parsed.get("ts")):
            continue
        if agent_set and parsed.get("agent") not in agent_set:
            continue
        if emoji_set and parsed.get("emoji") not in emoji_set:
            continue
        if meta_filters and not _meta_matches(parsed.get("meta") or {}, meta_filters):
            continue
        if not message_matches(
            parsed.get("message"),
            message,
            mode=message_mode,
            case_sensitive=case_sensitive,
        ):
            continue
        results.append(parsed)
        if limit is not None and len(results) >= limit:
            break
    return results


def _resolve_emojis(
    emojis: Optional[List[str]],
    statuses: Optional[List[str]],
) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in emojis or []:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    for status in statuses or []:
        if not status:
            continue
        emoji = STATUS_EMOJI.get(status, STATUS_EMOJI.get(status.lower()))
        if not emoji:
            normalized = status.lower()
            emoji = STATUS_EMOJI.get(normalized)
        if emoji and emoji not in seen:
            result.append(emoji)
            seen.add(emoji)
    return result


def _clean_list(items: Optional[List[str]]) -> List[str]:
    if not items:
        return []
    return [item for item in (entry.strip() for entry in items) if item]


def _normalise_meta_filters(
    meta_filters: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, str], Optional[str]]:
    if not meta_filters:
        return {}, None
    normalised: Dict[str, str] = {}
    for key, value in meta_filters.items():
        if key is None:
            return {}, "Meta filter keys cannot be null."
        key_str = str(key).strip()
        if not key_str:
            return {}, "Meta filter keys cannot be empty."
        if not META_KEY_PATTERN.match(key_str):
            return {}, f"Meta filter key '{key}' contains unsupported characters."
        normalised[key_str] = str(value)
    return normalised, None


def _normalise_boundary(value: Optional[str], *, end: bool) -> Tuple[Optional[datetime], Optional[str]]:
    if value is None:
        return None, None
    parsed = coerce_range_boundary(value, end=end)
    if parsed is None:
        return None, f"Unable to parse timestamp '{value}'. Expected ISO8601 or 'YYYY-MM-DD HH:MM:SS UTC'."
    return parsed, None


def _meta_matches(
    entry_meta: Dict[str, str],
    filters: Dict[str, str],
) -> bool:
    for key, expected in filters.items():
        if entry_meta.get(key) != expected:
            return False
    return True
