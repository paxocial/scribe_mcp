#!/usr/bin/env python3
"""
Response optimization utilities for token reduction.

Provides compact/full response formatting, field selection,
and token estimation capabilities.
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
import json
from datetime import datetime
import os

# Import token estimator for accurate token counting
try:
    from .tokens import token_estimator
except ImportError:
    # Fallback if tokens module not available
    token_estimator = None

@dataclass
class PaginationInfo:
    """Pagination metadata for responses."""
    page: int
    page_size: int
    total_count: int
    has_next: bool
    has_prev: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total_count": self.total_count,
            "has_next": self.has_next,
            "has_prev": self.has_prev
        }


class ResponseFormatter:
    """Handles response formatting with compact/full modes and field selection."""

    # Compact field mappings (short aliases for common fields)
    COMPACT_FIELD_MAP = {
        "id": "i",
        "message": "m",
        "timestamp": "t",
        "ts": "t",
        "emoji": "e",
        "agent": "a",
        "meta": "mt",
        "status": "s",
        "raw_line": "r"
    }

    # Default fields for compact mode
    COMPACT_DEFAULT_FIELDS = ["id", "message", "timestamp", "emoji", "agent"]

    def __init__(self, token_warning_threshold: int = 4000):
        self.token_warning_threshold = token_warning_threshold

    def estimate_tokens(self, data: Union[Dict, List, str]) -> int:
        """
        Estimate token count for response data using tiktoken if available.
        """
        if token_estimator is not None:
            return token_estimator.estimate_tokens(data)
        else:
            # Fallback to basic estimation
            if isinstance(data, str):
                return len(data) // 4
            elif isinstance(data, (dict, list)):
                return len(json.dumps(data)) // 4
            else:
                return len(str(data)) // 4

    def format_entry(self, entry: Dict[str, Any], compact: bool = False,
                    fields: Optional[List[str]] = None,
                    include_metadata: bool = True) -> Dict[str, Any]:
        """
        Format a single log entry based on requested format.

        Args:
            entry: Raw entry data from storage
            compact: Use compact format with short field names
            fields: Specific fields to include (None = all fields)
            include_metadata: Whether to include metadata field
        """
        if compact:
            return self._format_compact_entry(entry, fields, include_metadata)
        else:
            return self._format_full_entry(entry, fields, include_metadata)

    def _format_full_entry(self, entry: Dict[str, Any], fields: Optional[List[str]],
                          include_metadata: bool) -> Dict[str, Any]:
        """Format entry in full format with optional field selection."""
        result = {}

        # Determine which fields to include
        if fields is None:
            fields_to_include = list(entry.keys())
        else:
            fields_to_include = fields

        # Copy requested fields
        for field in fields_to_include:
            if field in entry:
                if field == "meta" and not include_metadata:
                    continue
                result[field] = entry[field]

        return result

    def _format_compact_entry(self, entry: Dict[str, Any], fields: Optional[List[str]],
                            include_metadata: bool) -> Dict[str, Any]:
        """Format entry in compact format with short field names."""
        result = {}

        # Determine which fields to include
        if fields is None:
            fields_to_include = self.COMPACT_DEFAULT_FIELDS
        else:
            fields_to_include = fields

        # Map to compact field names
        for field in fields_to_include:
            if field not in entry:
                continue

            # Skip metadata if not requested
            if field == "meta" and not include_metadata:
                continue

            # Get compact field name
            compact_field = self.COMPACT_FIELD_MAP.get(field, field)

            # Format value for compact mode
            value = entry[field]
            if field == "timestamp" and isinstance(value, str):
                # Shorten timestamp format
                try:
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    value = dt.strftime("%Y-%m-%d")
                except:
                    pass  # Keep original if parsing fails
            elif field == "message" and isinstance(value, str) and len(value) > 100:
                # Truncate long messages in compact mode
                value = value[:97] + "..."

            result[compact_field] = value

        return result

    def format_response(self, entries: List[Dict[str, Any]],
                       compact: bool = False,
                       fields: Optional[List[str]] = None,
                       include_metadata: bool = True,
                       pagination: Optional[PaginationInfo] = None,
                       extra_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Format a complete response with entries and metadata.

        Args:
            entries: List of log entries
            compact: Use compact format
            fields: Field selection
            include_metadata: Include metadata in entries
            pagination: Pagination information
            extra_data: Additional response data (reminders, etc.)
        """
        # Format entries
        formatted_entries = [
            self.format_entry(entry, compact, fields, include_metadata)
            for entry in entries
        ]

        # Build response
        response = {
            "ok": True,
            "entries": formatted_entries,
            "count": len(formatted_entries)
        }

        # Add compact flag
        if compact:
            response["compact"] = True

        # Add pagination info
        if pagination:
            response["pagination"] = pagination.to_dict()

        # Add extra data
        if extra_data:
            response.update(extra_data)

        # Add token usage warning if needed
        estimated_tokens = self.estimate_tokens(response)
        if estimated_tokens > self.token_warning_threshold:
            response["token_warning"] = {
                "estimated_tokens": estimated_tokens,
                "threshold": self.token_warning_threshold,
                "suggestion": f"Use compact=True for ~70% token reduction"
            }

        return response

    def format_projects_response(self, projects: List[Dict[str, Any]],
                               compact: bool = False,
                               fields: Optional[List[str]] = None,
                               extra_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format response for list_projects tool."""
        # Format project entries
        if compact:
            # Compact project format with key fields only
            default_fields = ["name", "root", "progress_log"]
            formatted_projects = []
            for project in projects:
                compact_project = {}
                for field in fields or default_fields:
                    if field in project:
                        # Use first 3 chars of name as compact id
                        if field == "name":
                            compact_project["n"] = project[field]
                        elif field == "root":
                            compact_project["r"] = project[field]
                        elif field == "progress_log":
                            compact_project["p"] = project[field]
                formatted_projects.append(compact_project)
        else:
            # Full project format
            formatted_projects = [
                {k: v for k, v in project.items() if not fields or k in fields}
                for project in projects
            ]

        # Build response
        response = {
            "ok": True,
            "projects": formatted_projects,
            "count": len(formatted_projects)
        }

        if compact:
            response["compact"] = True

        # Add extra data
        if extra_data:
            response.update(extra_data)

        return response


def create_pagination_info(page: int, page_size: int, total_count: int) -> PaginationInfo:
    """Create pagination metadata."""
    has_next = (page * page_size) < total_count
    has_prev = page > 1

    return PaginationInfo(
        page=page,
        page_size=page_size,
        total_count=total_count,
        has_next=has_next,
        has_prev=has_prev
    )


# Default formatter instance
default_formatter = ResponseFormatter()