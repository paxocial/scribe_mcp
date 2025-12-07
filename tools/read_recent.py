"""Tool for reading recent log entries."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.constants import STATUS_EMOJI
from scribe_mcp.utils.files import read_tail
from scribe_mcp.utils.response import create_pagination_info
from scribe_mcp.utils.tokens import token_estimator
from scribe_mcp.utils.estimator import ParameterTypeEstimator
from scribe_mcp.utils.config_manager import TokenBudgetManager
from scribe_mcp.utils.error_handler import HealingErrorHandler
from scribe_mcp.shared.logging_utils import (
    ProjectResolutionError,
    resolve_logging_context,
)
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin


class _ReadRecentHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module
        self.token_budget_manager = TokenBudgetManager()
        self.parameter_estimator = ParameterTypeEstimator()
        self.error_handler = HealingErrorHandler()

    def heal_parameters_with_exception_handling(
        self,
        n: Optional[Any] = None,
        page: int = 1,
        page_size: int = 50,
        compact: bool = False,
        fields: Optional[List[str]] = None,
        include_metadata: bool = True
    ) -> tuple[dict, bool]:
        """
        Heal parameters using Phase 1 exception handling utilities.

        Args:
            All read_recent parameters

        Returns:
            Tuple of (healed_params_dict, healing_applied_bool)
        """
        healing_applied = False
        healing_messages = []

        healed_params = {}

        # Heal n parameter (could have comparison operator bug)
        if n is not None:
            healed_n, n_healed, n_message = self.parameter_estimator.heal_comparison_operator_bug(
                n, "n"
            )
            if n_healed:
                healing_applied = True
                healing_messages.append(n_message)
                # Try to convert to int for page_size calculation
                try:
                    healed_n = int(healed_n)
                except (ValueError, TypeError):
                    healed_n = 50  # fallback
            healed_params["n"] = healed_n
        else:
            healed_params["n"] = None

        # Heal page parameter
        healed_page, page_healed, page_message = self.parameter_estimator.heal_comparison_operator_bug(
            page, "page"
        )
        if page_healed:
            healing_applied = True
            healing_messages.append(page_message)
            try:
                healed_page = max(1, int(healed_page))
            except (ValueError, TypeError):
                healed_page = 1
        else:
            try:
                healed_page = max(1, int(page))
            except (ValueError, TypeError):
                healed_page = 1
        healed_params["page"] = healed_page

        # Heal page_size parameter
        healed_page_size, page_size_healed, page_size_message = self.parameter_estimator.heal_comparison_operator_bug(
            page_size, "page_size"
        )
        if page_size_healed:
            healing_applied = True
            healing_messages.append(page_size_message)
            try:
                healed_page_size = max(1, min(int(healed_page_size), 200))
            except (ValueError, TypeError):
                healed_page_size = 50
        else:
            try:
                healed_page_size = max(1, min(int(page_size), 200))
            except (ValueError, TypeError):
                healed_page_size = 50
        healed_params["page_size"] = healed_page_size

        # Heal compact parameter
        if isinstance(compact, str):
            healed_compact = compact.lower() in ("true", "1", "yes")
            if healed_compact != compact:
                healing_applied = True
                healing_messages.append(f"Converted compact parameter from '{compact}' to boolean {healed_compact}")
        else:
            healed_compact = bool(compact)
        healed_params["compact"] = healed_compact

        # Heal fields parameter
        if fields is not None:
            if isinstance(fields, str):
                # Convert comma-separated string to list
                healed_fields = [field.strip() for field in fields.split(",") if field.strip()]
                healing_applied = True
                healing_messages.append(f"Converted fields from string to list: {healed_fields}")
            elif isinstance(fields, list):
                healed_fields = fields
            else:
                healed_fields = None
                healing_applied = True
                healing_messages.append(f"Invalid fields parameter type {type(fields)}, using None")
        else:
            healed_fields = None
        healed_params["fields"] = healed_fields

        # Heal include_metadata parameter
        if isinstance(include_metadata, str):
            healed_include_metadata = include_metadata.lower() in ("true", "1", "yes")
            if healed_include_metadata != include_metadata:
                healing_applied = True
                healing_messages.append(f"Converted include_metadata from '{include_metadata}' to boolean {healed_include_metadata}")
        else:
            healed_include_metadata = bool(include_metadata)
        healed_params["include_metadata"] = healed_include_metadata

        return healed_params, healing_applied, healing_messages


_READ_RECENT_HELPER = _ReadRecentHelper()


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

    # Apply Phase 1 exception healing to all parameters
    try:
        healed_params, healing_applied, healing_messages = _READ_RECENT_HELPER.heal_parameters_with_exception_handling(
            n=n, page=page, page_size=page_size, compact=compact, fields=fields, include_metadata=include_metadata
        )

        # Update parameters with healed values
        n = healed_params["n"]
        page = healed_params["page"]
        page_size = healed_params["page_size"]
        compact = healed_params["compact"]
        fields = healed_params["fields"]
        include_metadata = healed_params["include_metadata"]

    except Exception as healing_error:
        # If healing fails completely, use safe defaults
        healed_params = {"n": None, "page": 1, "page_size": 50, "compact": False, "fields": None, "include_metadata": True}
        healing_applied = False
        healing_messages = [f"Parameter healing failed: {str(healing_error)}, using safe defaults"]
        n = None
        page = 1
        page_size = 50
        compact = False
        fields = None
        include_metadata = True

    try:
        context = await _READ_RECENT_HELPER.prepare_context(
            tool_name="read_recent",
            agent_id=None,
            require_project=True,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        base_response = {
            "ok": False,
            "error": "No project configured.",
            "suggestion": "Invoke set_project before reading logs",
            "recent_projects": list(exc.recent_projects),
            "reminders": [],
        }

        # Add healing information if parameters were healed
        if healing_applied:
            base_response["parameter_healing"] = {
                "applied": True,
                "messages": healing_messages,
                "original_parameters": {"n": n, "page": page, "page_size": page_size}
            }

        return base_response

    project = context.project or {}

    # Handle n parameter for backward compatibility (using healed values)
    if page == 1 and page_size == 50 and n is not None:
        # Legacy mode - use n as page_size (already healed)
        limit_int = int(n) if n is not None else 50
        page_size = max(1, min(limit_int, 200))
    else:
        # Pagination mode - ignore n (already healed)
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

            response = _READ_RECENT_HELPER.success_with_entries(
                entries=rows,
                context=context,
                compact=compact,
                fields=fields,
                include_metadata=include_metadata,
                pagination=pagination_info,
                extra_data={},
            )

            # Apply Phase 1 token budget management
            try:
                # Use enhanced token budget management
                managed_response, token_count, items_truncated = _READ_RECENT_HELPER.token_budget_manager.apply_token_budget_to_response(
                    response_data=response,
                    token_limit=None,  # Use default budget
                    preserve_structure=True
                )

                # Add healing information to response if parameters were healed
                if healing_applied:
                    managed_response["parameter_healing"] = {
                        "applied": True,
                        "messages": healing_messages,
                        "original_parameters": {"n": healed_params["n"], "page": healed_params["page"], "page_size": healed_params["page_size"]}
                    }

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
                            "backend": "database"
                        },
                        response=managed_response,
                        compact_mode=compact,
                        page_size=page_size
                    )

                return managed_response

            except Exception as token_error:
                # Fallback: return original response with healing info
                if healing_applied:
                    response["parameter_healing"] = {
                        "applied": True,
                        "messages": healing_messages,
                        "original_parameters": {"n": healed_params["n"], "page": healed_params["page"], "page_size": healed_params["page_size"]},
                        "token_budget_error": str(token_error)
                    }

                # Record token usage with fallback
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
                            "backend": "database",
                            "token_budget_fallback": True
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

    response = _READ_RECENT_HELPER.success_with_entries(
        entries=entries,
        context=context,
        compact=compact,
        fields=fields,
        include_metadata=include_metadata,
        pagination=pagination_info,
        extra_data={},
    )

    # Apply Phase 1 token budget management for file-based fallback
    try:
        # Use enhanced token budget management
        managed_response, token_count, items_truncated = _READ_RECENT_HELPER.token_budget_manager.apply_token_budget_to_response(
            response_data=response,
            token_limit=None,  # Use default budget
            preserve_structure=True
        )

        # Add healing information to response if parameters were healed
        if healing_applied:
            managed_response["parameter_healing"] = {
                "applied": True,
                "messages": healing_messages,
                "original_parameters": {"n": healed_params["n"], "page": healed_params["page"], "page_size": healed_params["page_size"]}
            }

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
                response=managed_response,
                compact_mode=compact,
                page_size=page_size
            )

        return managed_response

    except Exception as token_error:
        # Fallback: return original response with healing info
        if healing_applied:
            response["parameter_healing"] = {
                "applied": True,
                "messages": healing_messages,
                "original_parameters": {"n": healed_params["n"], "page": healed_params["page"], "page_size": healed_params["page_size"]},
                "token_budget_error": str(token_error)
            }

        # Record token usage with fallback
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
                    "backend": "file",
                    "token_budget_fallback": True
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
