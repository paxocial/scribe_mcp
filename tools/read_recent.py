"""Tool for reading recent log entries."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.constants import STATUS_EMOJI
from scribe_mcp.tools.project_utils import load_active_project
from scribe_mcp import reminders
from scribe_mcp.utils.files import read_tail
from scribe_mcp.utils.response import default_formatter, create_pagination_info
from scribe_mcp.utils.tokens import token_estimator


@app.tool()
async def read_recent(
    n: Optional[Any] = None,
    filter: Optional[Dict[str, Any]] = None,
    page: int = 1,
    page_size: int = 50,
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_metadata: bool = True,
) -> Dict[str, Any]:
    """Return recent log entries with pagination and formatting options.

    Args:
        n: Legacy parameter for backward compatibility (max entries to return)
        filter: Optional filters to apply (agent, status, emoji)
        page: Page number for pagination (1-based)
        page_size: Number of entries per page
        compact: Use compact response format with short field names
        fields: Specific fields to include in response
        include_metadata: Include metadata field in entries

    Returns:
        Paginated response with recent entries and metadata
    """
    state_snapshot = await server_module.state_manager.record_tool("read_recent")
    project, _, recent = await load_active_project(server_module.state_manager)
    reminders_payload: List[Dict[str, Any]] = []
    if not project:
        return {
            "ok": False,
            "error": "No project configured.",
            "suggestion": "Invoke set_project before reading logs",
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }

    # Handle n parameter for backward compatibility
    if page == 1 and page_size == 50 and n is not None:
        # Legacy mode - use n as page_size
        try:
            limit_int = int(n) if n is not None else 50
        except (ValueError, TypeError):
            limit_int = 50
        page_size = max(1, min(limit_int, 200))
    else:
        # Pagination mode - ignore n
        page_size = max(1, min(page_size, 200))

    filters = filter or {}

    backend = server_module.storage_backend
    if backend:
        record = await backend.fetch_project(project["name"])
        if record:
            # Use pagination if available
            if hasattr(backend, 'fetch_recent_entries_paginated'):
                rows, total_count = await backend.fetch_recent_entries_paginated(
                    project=record,
                    page=page,
                    page_size=page_size,
                    filters=_normalise_filters(filters),
                )
                pagination_info = create_pagination_info(page, page_size, total_count)
            else:
                # Fallback to legacy method with offset
                offset = (page - 1) * page_size
                rows = await backend.fetch_recent_entries(
                    project=record,
                    limit=page_size,
                    filters=_normalise_filters(filters),
                    offset=offset,
                )
                # Get total count
                total_count = await backend.count_entries(
                    project=record,
                    filters=_normalise_filters(filters)
                )
                pagination_info = create_pagination_info(page, page_size, total_count)

            reminders_payload = await reminders.get_reminders(
                project,
                tool_name="read_recent",
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
                    operation="read_recent",
                    input_data={
                        "n": n,
                        "filter": filters,
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
    # Read more lines than needed to account for filtering
    fetch_limit = page_size * 3  # Fetch 3x to account for filter reductions
    all_lines = await read_tail(_progress_log_path(project), fetch_limit)
    all_lines = _apply_line_filters(all_lines, filters)

    # Apply pagination
    total_count = len(all_lines)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_lines = all_lines[start_idx:end_idx]

    pagination_info = create_pagination_info(page, page_size, total_count)

    reminders_payload = await reminders.get_reminders(
        project,
        tool_name="read_recent",
        state=state_snapshot,
    )

    # Convert lines to entry format for consistent response formatting
    from scribe_mcp.utils.logs import parse_log_line
    entries = []
    for line in paginated_lines:
        parsed = parse_log_line(line)
        if parsed:
            entries.append(parsed)
        else:
            # If parsing fails, include as raw line
            entries.append({"raw_line": line, "message": line})

    # Format response using the response formatter
    response = default_formatter.format_response(
        entries=entries,
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
            operation="read_recent",
            input_data={
                "n": n,
                "filter": filters,
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


def _normalise_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    normalised: Dict[str, Any] = {}
    if "agent" in filters and filters["agent"]:
        normalised["agent"] = str(filters["agent"])
    if "status" in filters and filters["status"]:
        status = str(filters["status"])
        normalised["emoji"] = STATUS_EMOJI.get(status, status)
    if "emoji" in filters and filters["emoji"]:
        normalised["emoji"] = str(filters["emoji"])
    return normalised


def _apply_line_filters(lines: List[str], filters: Dict[str, Any]) -> List[str]:
    agent = filters.get("agent")
    emoji = None
    if "emoji" in filters:
        emoji = filters["emoji"]
    elif "status" in filters:
        emoji = STATUS_EMOJI.get(filters["status"])

    def matches(line: str) -> bool:
        if agent and f"[Agent: {agent}]" not in line:
            return False
        if emoji and f"[{emoji}]" not in line:
            return False
        return True

    return [line for line in lines if matches(line)]


def _progress_log_path(project: Dict[str, Any]) -> Path:
    return Path(project["progress_log"])
