"""Advanced querying for progress log entries."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.constants import STATUS_EMOJI
from scribe_mcp.tools.project_utils import load_project_config
from scribe_mcp.utils.config_manager import ConfigManager, validate_enum_value, validate_range
from scribe_mcp.utils.logs import parse_log_line, read_all_lines
from scribe_mcp.utils.search import message_matches
from scribe_mcp.utils.time import coerce_range_boundary
from scribe_mcp.utils.response import create_pagination_info
from scribe_mcp.utils.tokens import token_estimator
from scribe_mcp.utils.estimator import PaginationCalculator
from scribe_mcp.utils.bulk_processor import BulkProcessor
from scribe_mcp.utils.error_handler import ErrorHandler
from scribe_mcp.tools.config.query_entries_config import QueryEntriesConfig
from scribe_mcp.shared.logging_utils import (
    LoggingContext,
    ProjectResolutionError,
    clean_list as shared_clean_list,
    normalize_meta_filters,
    resolve_logging_context,
)
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin

VALID_MESSAGE_MODES = {"substring", "regex", "exact"}
VALID_SEARCH_SCOPES = {"project", "global", "all_projects", "research", "bugs", "all"}
VALID_DOCUMENT_TYPES = {"progress", "research", "architecture", "bugs", "global"}

# Global configuration manager for parameter handling
_CONFIG_MANAGER = ConfigManager("query_entries")

# Global pagination calculator
_PAGINATION_CALCULATOR = PaginationCalculator()


class _QueryEntriesHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_HELPER = _QueryEntriesHelper()


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
    # Phase 4 Enhanced Search Parameters
    search_scope: str = "project",  # "project"|"global"|"all_projects"|"research"|"bugs"|"all"
    document_types: Optional[List[str]] = None,  # ["progress", "research", "architecture", "bugs", "global"]
    include_outdated: bool = True,  # Include warnings for stale info
    verify_code_references: bool = False,  # Check if mentioned code still exists
    time_range: Optional[str] = None,  # "last_30d", "last_7d", "today", etc.
    relevance_threshold: float = 0.0,  # 0.0-1.0 relevance scoring threshold
    max_results: Optional[int] = None,  # Override for limit (deprecated but kept for compatibility)
    config: Optional[QueryEntriesConfig] = None,  # Configuration object for dual parameter support
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
        # Phase 4 Enhanced Search Parameters
        search_scope: Search scope - "project", "global", "all_projects", "research", "bugs", or "all"
        document_types: Filter by document types - ["progress", "research", "architecture", "bugs", "global"]
        include_outdated: Include outdated information with warnings
        verify_code_references: Check if mentioned code still exists
        time_range: Time range filter - "last_30d", "last_7d", "today", etc.
        relevance_threshold: Minimum relevance score (0.0-1.0) for results
        max_results: Override maximum results (deprecated, use limit/page_size instead)
        config: Configuration object for dual parameter support. If provided, legacy parameters
               take precedence when both are specified.

    Returns:
        Paginated response with entries and metadata
    """
    state_snapshot = await server_module.state_manager.record_tool("query_entries")

    # === DUAL PARAMETER SUPPORT ===
    # Create configuration from legacy parameters first
    legacy_config = QueryEntriesConfig.from_legacy_params(
        project=project,
        start=start,
        end=end,
        message=message,
        message_mode=message_mode,
        case_sensitive=case_sensitive,
        emoji=emoji,
        status=status,
        agents=agents,
        meta_filters=meta_filters,
        limit=limit,
        page=page,
        page_size=page_size,
        compact=compact,
        fields=fields,
        include_metadata=include_metadata,
        search_scope=search_scope,
        document_types=document_types,
        include_outdated=include_outdated,
        verify_code_references=verify_code_references,
        time_range=time_range,
        relevance_threshold=relevance_threshold,
        max_results=max_results
    )

    # Merge with provided config if available, with legacy parameters taking precedence
    if config is not None:
        # Create final config by merging config values with legacy parameter overrides
        # Start with config values, then override with non-default legacy parameters
        merge_params = {}

        # Helper function to determine if a legacy parameter should override the config
        def should_override(legacy_value, default_value):
            if legacy_value is None:
                return False
            if isinstance(legacy_value, bool):
                return legacy_value != default_value
            if isinstance(legacy_value, (int, float)):
                return legacy_value != default_value
            if isinstance(legacy_value, str):
                return legacy_value != default_value
            return True  # For lists/dicts, any non-None value should override

        # Apply legacy parameter precedence
        merge_params['project'] = legacy_config.project if should_override(project, None) else config.project
        merge_params['start'] = legacy_config.start if should_override(start, None) else config.start
        merge_params['end'] = legacy_config.end if should_override(end, None) else config.end
        merge_params['message'] = legacy_config.message if should_override(message, None) else config.message
        merge_params['message_mode'] = legacy_config.message_mode if should_override(message_mode, "substring") else config.message_mode
        merge_params['case_sensitive'] = legacy_config.case_sensitive if should_override(case_sensitive, False) else config.case_sensitive
        merge_params['emoji'] = legacy_config.emoji if should_override(emoji, None) else config.emoji
        merge_params['status'] = legacy_config.status if should_override(status, None) else config.status
        merge_params['agents'] = legacy_config.agents if should_override(agents, None) else config.agents
        merge_params['meta_filters'] = legacy_config.meta_filters if should_override(meta_filters, None) else config.meta_filters
        merge_params['limit'] = legacy_config.limit if should_override(limit, 50) else config.limit
        merge_params['page'] = legacy_config.page if should_override(page, 1) else config.page
        merge_params['page_size'] = legacy_config.page_size if should_override(page_size, 50) else config.page_size
        merge_params['compact'] = legacy_config.compact if should_override(compact, False) else config.compact
        merge_params['fields'] = legacy_config.fields if should_override(fields, None) else config.fields
        merge_params['include_metadata'] = legacy_config.include_metadata if should_override(include_metadata, True) else config.include_metadata
        merge_params['search_scope'] = legacy_config.search_scope if should_override(search_scope, "project") else config.search_scope
        merge_params['document_types'] = legacy_config.document_types if should_override(document_types, None) else config.document_types
        merge_params['include_outdated'] = legacy_config.include_outdated if should_override(include_outdated, True) else config.include_outdated
        merge_params['verify_code_references'] = legacy_config.verify_code_references if should_override(verify_code_references, False) else config.verify_code_references
        merge_params['time_range'] = legacy_config.time_range if should_override(time_range, None) else config.time_range
        merge_params['relevance_threshold'] = legacy_config.relevance_threshold if should_override(relevance_threshold, 0.0) else config.relevance_threshold
        merge_params['max_results'] = legacy_config.max_results if should_override(max_results, None) else config.max_results

        final_config = QueryEntriesConfig(**merge_params)
    else:
        final_config = legacy_config

    # Validate the final configuration
    is_valid, error_response = final_config.validate()
    if not is_valid:
        # Ensure error response has correct MCP interface structure
        if "ok" not in error_response:
            error_response["ok"] = False
        return error_response

    # Extract validated parameters from final config
    project = final_config.project
    start = final_config.start
    end = final_config.end
    message = final_config.message
    message_mode = final_config.message_mode
    case_sensitive = final_config.case_sensitive
    emoji = final_config.emoji
    status = final_config.status
    agents = final_config.agents
    meta_filters = final_config.meta_filters
    limit = final_config.limit
    page = final_config.page
    page_size = final_config.page_size
    compact = final_config.compact
    fields = final_config.fields
    include_metadata = final_config.include_metadata
    search_scope = final_config.search_scope
    document_types = final_config.document_types
    include_outdated = final_config.include_outdated
    verify_code_references = final_config.verify_code_references
    time_range = final_config.time_range
    relevance_threshold = final_config.relevance_threshold
    max_results = final_config.max_results
    # === END DUAL PARAMETER SUPPORT ===

    # Handle pagination vs legacy limit
    # Ensure page and page_size are integers
    page = int(page) if isinstance(page, str) else page
    page_size = int(page_size) if isinstance(page_size, str) else page_size
    limit = int(limit) if isinstance(limit, str) else limit

    if page > 1 or page_size != 50:
        # Use pagination mode
        limit = None  # Ignore limit in pagination mode
    else:
        # Use legacy mode for backward compatibility
        limit = max(1, min(limit or 50, 500))
        page_size = limit

    # Apply normalizations that were previously done in validation
    # These are now handled by QueryEntriesConfig validation

    # Resolve emojis and normalize meta filters (still needed for function logic)
    normalised_emoji = _resolve_emojis(emoji, status)
    meta_normalised, meta_error = normalize_meta_filters(meta_filters)
    if meta_error:
        return ErrorHandler.create_validation_error(
            error_message=meta_error,
            context={"parameter": "meta_filters"}
        )

    # Handle max_results override for backward compatibility
    if max_results is not None:
        limit = max_results
        page_size = min(page_size, max_results)

    start_bound, start_error = _normalise_boundary(start, end=False)
    if start_error:
        return {"ok": False, "error": start_error}
    end_bound, end_error = _normalise_boundary(end, end=True)
    if end_error:
        return {"ok": False, "error": end_error}

    context: Optional[LoggingContext] = None

    # Handle cross-project search for enhanced scopes
    if search_scope != "project":
        # Cross-project search mode
        projects_to_search = await _resolve_cross_project_projects(search_scope, document_types)
        if not projects_to_search:
            return {
                "ok": False,
                "error": f"No projects found for search_scope '{search_scope}' with document_types {document_types or []}",
                "recent_projects": [],
                "reminders": [],
            }

        # Use cross-project search logic
        return await _handle_cross_project_search(
            projects=projects_to_search,
            search_scope=search_scope,
            document_types=document_types,
            start_bound=start_bound,
            end_bound=end_bound,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            agents=_clean_list(agents),
            emojis=normalised_emoji or None,
            meta_filters=meta_normalised or None,
            page=page,
            page_size=page_size,
            compact=compact,
            fields=fields,
            include_metadata=include_metadata,
            verify_code_references=verify_code_references,
            relevance_threshold=relevance_threshold,
            state_snapshot=state_snapshot,
            helper=_HELPER,
            context=None,
        )

    # Single project mode (existing behavior)
    try:
        context = await _HELPER.prepare_context(
            tool_name="query_entries",
            agent_id=None,
            explicit_project=project,
            require_project=True,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        error_response = ErrorHandler.create_project_resolution_error(
            error=exc,
            tool_name="query_entries"
        )
        error_response["reminders"] = []
        return error_response

    project_data = context.project or {}

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

        response = _HELPER.success_with_entries(
            entries=rows,
            context=context,
            compact=compact,
            fields=fields,
            include_metadata=include_metadata,
            pagination=pagination_info,
            extra_data={},
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
    start_idx, end_idx = _PAGINATION_CALCULATOR.calculate_pagination_indices(page, page_size, total_count)
    paginated_entries = all_entries[start_idx:end_idx]

    pagination_info = create_pagination_info(page, page_size, total_count)

    response = _HELPER.success_with_entries(
        entries=paginated_entries,
        context=context,
        compact=compact,
        fields=fields,
        include_metadata=include_metadata,
        pagination=pagination_info,
        extra_data={},
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


async def _resolve_cross_project_projects(
    search_scope: str,
    document_types: Optional[List[str]],
) -> List[Dict[str, Any]]:
    """Resolve projects to search based on search scope and document types."""
    state = await server_module.state_manager.load()
    projects: List[Dict[str, Any]] = []

    if search_scope == "all_projects":
        # Search all configured projects
        for project_name in state.projects:
            # Try to get complete project data from state first
            project_dict = state.get_project(project_name)
            if project_dict:
                # If project data is incomplete, load from config
                if not project_dict.get("progress_log"):
                    fallback_project = load_project_config(project_name)
                    if fallback_project:
                        project_dict = fallback_project
                        project_dict["name"] = project_name
                    else:
                        # Skip projects without valid config
                        continue
                else:
                    # Ensure name is set
                    project_dict["name"] = project_name
                projects.append(project_dict)

    elif search_scope == "global":
        # Search only the global log
        # Return a special project config for global log
        global_config = {
            "name": "global",
            "progress_log": "docs/GLOBAL_PROGRESS_LOG.md",
            "docs_dir": "docs",
            "root": "."
        }
        projects.append(global_config)

    elif search_scope in ["research", "bugs", "all"]:
        # Search specific document types across all projects
        for project_name in state.projects:
            # Try to get complete project data from state first
            project_dict = state.get_project(project_name)
            if project_dict:
                # If project data is incomplete, load from config
                if not project_dict.get("progress_log"):
                    fallback_project = load_project_config(project_name)
                    if fallback_project:
                        project_dict = fallback_project
                        project_dict["name"] = project_name
                    else:
                        # Skip projects without valid config
                        continue
                else:
                    # Ensure name is set
                    project_dict["name"] = project_name
                # Check if project has the requested document types
                if _project_has_document_types(project_dict, document_types, search_scope):
                    projects.append(project_dict)

        # Always include global log for these scopes
        global_config = {
            "name": "global",
            "progress_log": "docs/GLOBAL_PROGRESS_LOG.md",
            "docs_dir": "docs",
            "root": "."
        }
        projects.append(global_config)

    return projects


def _project_has_document_types(
    project: Dict[str, Any],
    document_types: Optional[List[str]],
    search_scope: str
) -> bool:
    """Check if a project has the requested document types."""
    if not document_types and search_scope != "all":
        return True

    docs_dir = Path(project.get("docs_dir", ""))

    # Check for specific document types
    for doc_type in document_types or []:
        if doc_type == "research":
            if (docs_dir / "research").exists():
                return True
        elif doc_type == "architecture":
            if (docs_dir / "ARCHITECTURE_GUIDE.md").exists():
                return True
        elif doc_type == "bugs":
            if (docs_dir / "BUG_LOG.md").exists():
                return True
        elif doc_type == "global":
            # Skip global log for individual projects
            continue
        elif doc_type == "progress":
            # All projects have progress logs
            return True

    return search_scope == "all"  # For "all" scope, include all projects


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


async def _handle_cross_project_search(
    projects: List[Dict[str, Any]],
    search_scope: str,
    document_types: Optional[List[str]],
    start_bound: Optional[datetime],
    end_bound: Optional[datetime],
    message: Optional[str],
    message_mode: str,
    case_sensitive: bool,
    agents: Optional[List[str]],
    emojis: Optional[List[str]],
    meta_filters: Optional[Dict[str, str]],
    page: int,
    page_size: int,
    compact: bool,
    fields: Optional[List[str]],
    include_metadata: bool,
    verify_code_references: bool,
    relevance_threshold: float,
    state_snapshot: Dict[str, Any],
    helper: LoggingToolMixin,
    context: Optional[LoggingContext],
) -> Dict[str, Any]:
    """Handle cross-project search with result aggregation and pagination."""
    all_results: List[Dict[str, Any]] = []
    project_context: Dict[str, Dict[str, Any]] = {}

    # Search each project and collect results
    for project in projects:
        project_results = await _search_single_project(
            project=project,
            document_types=document_types,
            start_bound=start_bound,
            end_bound=end_bound,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            agents=agents,
            emojis=emojis,
            meta_filters=meta_filters,
            verify_code_references=verify_code_references,
            relevance_threshold=relevance_threshold,
        )

        # Add project context to each result
        for result in project_results:
            result["project_name"] = project["name"]
            result["project_root"] = project.get("root", "")
            if include_metadata:
                result["project_context"] = {
                    "docs_dir": project.get("docs_dir", ""),
                    "progress_log": project.get("progress_log", ""),
                }

        all_results.extend(project_results)
        project_context[project["name"]] = project

    # Apply relevance scoring and sorting
    if relevance_threshold > 0.0:
        all_results = _apply_relevance_scoring(
            all_results,
            message,
            relevance_threshold
        )

    # Sort by relevance score (descending) then timestamp (most recent first)
    all_results.sort(key=lambda x: (
        x.get("relevance_score", 0.0),
        x.get("timestamp", "")
    ), reverse=True)

    # Apply pagination
    total_count = len(all_results)
    start_idx, end_idx = _PAGINATION_CALCULATOR.calculate_pagination_indices(page, page_size, total_count)
    paginated_results = all_results[start_idx:end_idx]

    # Create pagination info
    pagination_info = create_pagination_info(page, page_size, total_count)

    if context is None:
        context = await helper.prepare_context(
            tool_name="query_entries",
            agent_id=None,
            explicit_project=None,
            require_project=False,
            state_snapshot=state_snapshot,
        )

    response = helper.success_with_entries(
        entries=paginated_results,
        context=context,
        compact=compact,
        fields=fields,
        include_metadata=include_metadata,
        pagination=pagination_info,
        extra_data={
            "search_scope": search_scope,
            "document_types": document_types,
            "projects_searched": list(project_context.keys()),
            "total_results_across_projects": total_count,
        },
    )

    # Record token usage
    if token_estimator:
        token_estimator.record_operation(
            operation="query_entries_cross_project",
            input_data={
                "search_scope": search_scope,
                "document_types": document_types,
                "projects_count": len(projects),
                "page": page,
                "page_size": page_size,
                "compact": compact,
                "fields": fields,
                "include_metadata": include_metadata,
                "verify_code_references": verify_code_references,
                "relevance_threshold": relevance_threshold,
            },
            response=response,
            compact_mode=compact,
            page_size=page_size
        )

    return response


async def _search_single_project(
    project: Dict[str, Any],
    document_types: Optional[List[str]],
    start_bound: Optional[datetime],
    end_bound: Optional[datetime],
    message: Optional[str],
    message_mode: str,
    case_sensitive: bool,
    agents: Optional[List[str]],
    emojis: Optional[List[str]],
    meta_filters: Optional[Dict[str, str]],
    verify_code_references: bool,
    relevance_threshold: float,
) -> List[Dict[str, Any]]:
    """Search a single project including its document types."""
    results: List[Dict[str, Any]] = []

    # Search main progress log
    if not document_types or "progress" in document_types:
        progress_results = await _query_file(
            project=project,
            limit=None,  # Get all, we'll paginate later
            start=start_bound,
            end=end_bound,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            agents=agents,
            emojis=emojis,
            meta_filters=meta_filters,
        )
        results.extend(progress_results)

    # Search other document types
    docs_dir = Path(project.get("docs_dir", ""))

    if document_types:
        if "research" in document_types:
            research_results = await _search_research_documents(
                docs_dir, start_bound, end_bound, message, message_mode,
                case_sensitive, agents, emojis, meta_filters
            )
            results.extend(research_results)

        if "architecture" in document_types:
            arch_results = await _search_architecture_documents(
                docs_dir, start_bound, end_bound, message, message_mode,
                case_sensitive, agents, emojis, meta_filters
            )
            results.extend(arch_results)

        if "bugs" in document_types:
            bug_results = await _search_bug_documents(
                docs_dir, start_bound, end_bound, message, message_mode,
                case_sensitive, agents, emojis, meta_filters
            )
            results.extend(bug_results)

        if "global" in document_types and project["name"] == "global":
            # Global log already handled as progress log for global project
            pass

    # Apply code reference verification if requested
    if verify_code_references:
        results = _verify_code_references_in_results(results)

    # Add basic relevance scoring
    results = _calculate_basic_relevance(results, message)

    return results


async def _search_research_documents(
    docs_dir: Path,
    start_bound: Optional[datetime],
    end_bound: Optional[datetime],
    message: Optional[str],
    message_mode: str,
    case_sensitive: bool,
    agents: Optional[List[str]],
    emojis: Optional[List[str]],
    meta_filters: Optional[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Search research documents in the research/ subdirectory."""
    results: List[Dict[str, Any]] = []
    research_dir = docs_dir / "research"

    if not research_dir.exists():
        return results

    # Find all research markdown files
    for research_file in research_dir.glob("RESEARCH_*.md"):
        try:
            content = await read_all_lines(research_file)
            # Parse research documents and extract searchable content
            research_results = _parse_research_document(
                research_file, content, start_bound, end_bound,
                message, message_mode, case_sensitive, agents, emojis, meta_filters
            )
            results.extend(research_results)
        except Exception as e:
            # Log error but continue with other files
            continue

    return results


async def _search_architecture_documents(
    docs_dir: Path,
    start_bound: Optional[datetime],
    end_bound: Optional[datetime],
    message: Optional[str],
    message_mode: str,
    case_sensitive: bool,
    agents: Optional[List[str]],
    emojis: Optional[List[str]],
    meta_filters: Optional[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Search architecture guide documents."""
    results: List[Dict[str, Any]] = []
    arch_file = docs_dir / "ARCHITECTURE_GUIDE.md"

    if not arch_file.exists():
        return results

    try:
        content = await read_all_lines(arch_file)
        arch_results = _parse_markdown_document(
            arch_file, content, "architecture", start_bound, end_bound,
            message, message_mode, case_sensitive, agents, emojis, meta_filters
        )
        results.extend(arch_results)
    except Exception:
        pass

    return results


async def _search_bug_documents(
    docs_dir: Path,
    start_bound: Optional[datetime],
    end_bound: Optional[datetime],
    message: Optional[str],
    message_mode: str,
    case_sensitive: bool,
    agents: Optional[List[str]],
    emojis: Optional[List[str]],
    meta_filters: Optional[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Search bug report documents."""
    results: List[Dict[str, Any]] = []
    bug_file = docs_dir / "BUG_LOG.md"

    if not bug_file.exists():
        return results

    try:
        content = await read_all_lines(bug_file)
        bug_results = _parse_markdown_document(
            bug_file, content, "bugs", start_bound, end_bound,
            message, message_mode, case_sensitive, agents, emojis, meta_filters
        )
        results.extend(bug_results)
    except Exception:
        pass

    return results


def _parse_research_document(
    file_path: Path,
    content: List[str],
    start_bound: Optional[datetime],
    end_bound: Optional[datetime],
    message: Optional[str],
    message_mode: str,
    case_sensitive: bool,
    agents: Optional[List[str]],
    emojis: Optional[List[str]],
    meta_filters: Optional[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Parse research document into searchable entries."""
    results: List[Dict[str, Any]] = []

    # Extract sections from research document
    current_section = ""
    section_content = []

    for line in content:
        if line.startswith("# "):
            # New top-level section
            if current_section and section_content:
                result = _create_document_entry(
                    file_path, current_section, section_content,
                    "research", start_bound, end_bound, message,
                    message_mode, case_sensitive, agents, emojis, meta_filters
                )
                if result:
                    results.append(result)

            current_section = line.strip()
            section_content = []
        elif line.strip():
            section_content.append(line)

    # Don't forget the last section
    if current_section and section_content:
        result = _create_document_entry(
            file_path, current_section, section_content,
            "research", start_bound, end_bound, message,
            message_mode, case_sensitive, agents, emojis, meta_filters
        )
        if result:
            results.append(result)

    return results


def _parse_markdown_document(
    file_path: Path,
    content: List[str],
    doc_type: str,
    start_bound: Optional[datetime],
    end_bound: Optional[datetime],
    message: Optional[str],
    message_mode: str,
    case_sensitive: bool,
    agents: Optional[List[str]],
    emojis: Optional[List[str]],
    meta_filters: Optional[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Parse generic markdown document into searchable entries."""
    results: List[Dict[str, Any]] = []

    # Split document into sections based on headers
    current_section = ""
    section_content = []

    for line in content:
        if line.startswith("#"):
            # New section
            if current_section and section_content:
                result = _create_document_entry(
                    file_path, current_section, section_content,
                    doc_type, start_bound, end_bound, message,
                    message_mode, case_sensitive, agents, emojis, meta_filters
                )
                if result:
                    results.append(result)

            current_section = line.strip()
            section_content = []
        elif line.strip():
            section_content.append(line)

    # Process final section
    if current_section and section_content:
        result = _create_document_entry(
            file_path, current_section, section_content,
            doc_type, start_bound, end_bound, message,
            message_mode, case_sensitive, agents, emojis, meta_filters
        )
        if result:
            results.append(result)

    return results


def _create_document_entry(
    file_path: Path,
    section: str,
    content: List[str],
    doc_type: str,
    start_bound: Optional[datetime],
    end_bound: Optional[datetime],
    message: Optional[str],
    message_mode: str,
    case_sensitive: bool,
    agents: Optional[List[str]],
    emojis: Optional[List[str]],
    meta_filters: Optional[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """Create a searchable entry from document section."""
    # Combine section and content for searching
    full_text = section + "\n" + "\n".join(content)

    # Apply message filtering
    if message and not message_matches(
        full_text, message, mode=message_mode, case_sensitive=case_sensitive
    ):
        return None

    # Extract metadata from content if possible
    meta = {"document_type": doc_type, "source_file": str(file_path)}

    # Apply other filters (simplified for document entries)
    if agents and not any(agent in full_text for agent in agents):
        return None

    if emojis and not any(emoji in full_text for emoji in emojis):
        return None

    if meta_filters:
        for key, value in meta_filters.items():
            if key not in meta or str(meta[key]) != str(value):
                return None

    # Create entry
    return {
        "timestamp": format_utc(),  # Use current time for document entries
        "message": section.strip(),
        "agent": "DocumentParser",
        "emoji": "📄",
        "status": "info",
        "meta": meta,
        "content": full_text,
        "relevance_score": 0.5,  # Default relevance for document entries
    }


def _verify_code_references_in_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Verify code file references exist and add warnings for broken ones."""
    updated_results = []

    for result in results:
        # Look for file path patterns in the message or content
        text_content = result.get("message", "") + " " + result.get("content", "")

        # Find potential file references
        import re
        file_pattern = r'[\w\-/\.]+\.(py|js|ts|md|json|yaml|yml|sql|sh|bash|zsh)$'
        potential_files = re.findall(file_pattern, text_content, re.IGNORECASE)

        verified_result = result.copy()
        broken_refs = []

        for file_ref in potential_files:
            # Try to find the file in the current project
            if not _verify_file_exists(file_ref):
                broken_refs.append(file_ref)

        if broken_refs:
            verified_result["meta"] = verified_result.get("meta", {})
            verified_result["meta"]["broken_code_references"] = broken_refs
            verified_result["meta"]["code_reference_verification"] = "failed"

            # Add warning emoji if code references are broken
            if result.get("emoji") != "⚠️":
                verified_result["emoji"] = "⚠️"
        else:
            verified_result["meta"] = verified_result.get("meta", {})
            verified_result["meta"]["code_reference_verification"] = "passed"

        updated_results.append(verified_result)

    return updated_results


def _verify_file_exists(file_ref: str) -> bool:
    """Check if a referenced file exists in the current codebase."""
    from pathlib import Path

    # Try different common locations
    potential_paths = [
        Path(file_ref),  # Relative to current
        Path("scribe_mcp") / file_ref,  # In scribe_mcp
        Path("scribe_mcp/tools") / file_ref,  # In tools
        Path("scribe_mcp/storage") / file_ref,  # In storage
        Path("docs") / file_ref,  # In docs
        Path("tests") / file_ref,  # In tests
    ]

    for path in potential_paths:
        if path.exists():
            return True

    return False


def _calculate_basic_relevance(results: List[Dict[str, Any]], query_message: Optional[str]) -> List[Dict[str, Any]]:
    """Calculate basic relevance scores for search results."""
    if not query_message:
        # Default relevance for non-message queries
        for result in results:
            result["relevance_score"] = 0.5
        return results

    query_terms = query_message.lower().split()

    for result in results:
        score = 0.0
        text = (result.get("message", "") + " " + result.get("content", "")).lower()

        # Score based on term frequency
        for term in query_terms:
            if term in text:
                score += 1.0

        # Bonus for exact phrase matches
        if query_message.lower() in text:
            score += 2.0

        # Bonus for recent entries (higher score for newer entries)
        timestamp = result.get("timestamp", "")
        if timestamp:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace(" UTC", ""))
                days_ago = (datetime.now(dt.tzinfo) - dt).days
                if isinstance(days_ago, int):
                    if days_ago <= 7:
                        score += 0.5
                    elif days_ago <= 30:
                        score += 0.25
            except:
                pass

        result["relevance_score"] = min(score / len(query_terms) if query_terms else 0.5, 1.0)

    return results


def _apply_relevance_scoring(results: List[Dict[str, Any]], query_message: Optional[str], threshold: float) -> List[Dict[str, Any]]:
    """Apply relevance threshold filtering using BulkProcessor utility."""
    return BulkProcessor.filter_by_relevance_threshold(results, threshold, "relevance_score")


def _resolve_emojis(
    emojis: Optional[List[str]],
    statuses: Optional[List[str]],
) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in shared_clean_list(emojis, coerce_lower=False):
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    for status in shared_clean_list(statuses, coerce_lower=True):
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
    return shared_clean_list(items, coerce_lower=False)


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
