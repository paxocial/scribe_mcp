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

# Import estimation utilities
from .estimator import PaginationInfo, PaginationCalculator, TokenEstimator

# PaginationInfo is now imported from estimator utilities

# MCP types for CallToolResult (Issue #9962 fix)
# When we return CallToolResult with TextContent only (no structuredContent),
# Claude Code displays text cleanly with actual newlines instead of escaped \n
try:
    from mcp.types import CallToolResult, TextContent
    MCP_TYPES_AVAILABLE = True
except ImportError:
    # Fallback for environments without MCP SDK
    CallToolResult = None
    TextContent = None
    MCP_TYPES_AVAILABLE = False


def _get_use_ansi_colors() -> bool:
    """
    Get ANSI color setting from repo config.

    Phase 1.5/1.6: Load use_ansi_colors from .scribe/config/scribe.yaml
    Falls back to True (colors enabled by default) if config unavailable.
    """
    try:
        from scribe_mcp.config.repo_config import get_current_repo_config
        _, config = get_current_repo_config()
        return config.use_ansi_colors
    except Exception:
        # Fallback: colors enabled by default
        return True


class ResponseFormatter:
    """Handles response formatting with compact/full modes and field selection."""

    # Format constants (Phase 0)
    FORMAT_READABLE = "readable"
    FORMAT_STRUCTURED = "structured"
    FORMAT_COMPACT = "compact"
    FORMAT_BOTH = "both"  # TextContent + structuredContent (for when Issue #9962 is fixed)

    # ANSI color codes for enhanced readability in Claude Code
    ANSI_CYAN = "\033[36m"
    ANSI_GREEN = "\033[32m"
    ANSI_YELLOW = "\033[33m"
    ANSI_BLUE = "\033[34m"
    ANSI_MAGENTA = "\033[35m"
    ANSI_BOLD = "\033[1m"
    ANSI_DIM = "\033[2m"
    ANSI_RESET = "\033[0m"

    @property
    def USE_COLORS(self) -> bool:
        """
        Check if ANSI colors are enabled via repo config.

        Phase 1.5/1.6: Colors loaded from .scribe/config/scribe.yaml
        (use_ansi_colors setting). Enabled by default.
        """
        return _get_use_ansi_colors()

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
        self._token_estimator = TokenEstimator()

    def estimate_tokens(self, data: Union[Dict, List, str]) -> int:
        """
        Estimate token count for response data using TokenEstimator.
        """
        return self._token_estimator.estimate_tokens(data)

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

    # ==================== Phase 0: Readable Format Helper Methods ====================

    def _add_line_numbers(self, content: str, start: int = 1) -> str:
        """
        Add line numbers to content with optional green coloring.

        Format: "     1. Line content" (with green line numbers if colors enabled)

        Args:
            content: Text content to number
            start: Starting line number (default: 1)

        Returns:
            Line-numbered string with consistent padding
        """
        if not content:
            return ""

        lines = content.split('\n')
        if not lines:
            return ""

        # Calculate max line number for padding (minimum 5 chars to match Claude Read style)
        max_line = start + len(lines) - 1
        width = max(5, len(str(max_line)))  # Minimum 5 chars like Claude's "     1."

        # Color helpers (green line numbers)
        G = self.ANSI_GREEN if self.USE_COLORS else ""
        R = self.ANSI_RESET if self.USE_COLORS else ""

        # Format each line with right-aligned line number (green with dot separator)
        numbered_lines = []
        for i, line in enumerate(lines, start=start):
            line_num = str(i).rjust(width)
            numbered_lines.append(f"{G}{line_num}.{R} {line}")

        return '\n'.join(numbered_lines)

    def _create_header_box(self, title: str, metadata: Dict[str, Any]) -> str:
        """
        Create ASCII box header with title and metadata.

        Format:
        ╔══════════════════════════════════════════════════════════╗
        ║ TITLE                                                    ║
        ╟──────────────────────────────────────────────────────────╢
        ║ key1: value1                                             ║
        ║ key2: value2                                             ║
        ╚══════════════════════════════════════════════════════════╝

        Args:
            title: Header title text
            metadata: Dictionary of metadata key-value pairs

        Returns:
            Formatted ASCII box as string
        """
        # Calculate box width (default 80 chars)
        box_width = 80
        inner_width = box_width - 4  # Account for borders

        lines = []

        # Color helpers
        C = self.ANSI_CYAN if self.USE_COLORS else ""
        G = self.ANSI_GREEN if self.USE_COLORS else ""
        Y = self.ANSI_YELLOW if self.USE_COLORS else ""
        B = self.ANSI_BOLD if self.USE_COLORS else ""
        R = self.ANSI_RESET if self.USE_COLORS else ""

        # Top border
        lines.append(f"{C}╔" + "═" * (box_width - 2) + f"╗{R}")

        # Title line (centered, bold)
        title_display = f"{B}{title}{R}"
        # Account for ANSI codes in centering
        title_padded = f" {title_display} ".center(inner_width + len(B) + len(R))
        lines.append(f"{C}║{R} {title_padded} {C}║{R}")

        # Separator
        lines.append(f"{C}╟" + "─" * (box_width - 2) + f"╢{R}")

        # Metadata lines
        for key, value in metadata.items():
            # Format value
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)

            # Truncate if too long (account for color codes in calculation)
            raw_content = f"{key}: {value_str}"
            if len(raw_content) > inner_width:
                raw_content = raw_content[:inner_width - 3] + "..."
                # Also truncate value_str for colored output
                value_str = raw_content[len(key) + 2:]  # Skip "key: " part

            # Apply colors: key in green, value in default
            colored_content = f"{G}{key}:{R} {value_str}"
            # Calculate padding based on raw length (without ANSI codes)
            padding_needed = inner_width - len(raw_content)
            line_padded = f" {colored_content}{' ' * padding_needed} "
            lines.append(f"{C}║{R}{line_padded}{C}║{R}")

        # Bottom border
        lines.append(f"{C}╚" + "═" * (box_width - 2) + f"╝{R}")

        return '\n'.join(lines)

    def _create_footer_box(self, audit_data: Dict[str, Any],
                           reminders: Optional[List[Dict]] = None) -> str:
        """
        Create ASCII box footer with audit data and optional reminders.

        Format:
        ╔══════════════════════════════════════════════════════════╗
        ║ METADATA                                                 ║
        ╟──────────────────────────────────────────────────────────╢
        ║ audit_key1: value1                                       ║
        ║ audit_key2: value2                                       ║
        ╟──────────────────────────────────────────────────────────╢
        ║ REMINDERS                                                ║
        ║ • Reminder 1                                             ║
        ║ • Reminder 2                                             ║
        ╚══════════════════════════════════════════════════════════╝

        Args:
            audit_data: Dictionary of audit/metadata
            reminders: Optional list of reminder dictionaries

        Returns:
            Formatted ASCII box as string
        """
        box_width = 80
        inner_width = box_width - 4

        # Color helpers
        C = self.ANSI_CYAN if self.USE_COLORS else ""
        G = self.ANSI_GREEN if self.USE_COLORS else ""
        Y = self.ANSI_YELLOW if self.USE_COLORS else ""
        M = self.ANSI_MAGENTA if self.USE_COLORS else ""
        B = self.ANSI_BOLD if self.USE_COLORS else ""
        R = self.ANSI_RESET if self.USE_COLORS else ""

        lines = []

        # Top border
        lines.append(f"{C}╔" + "═" * (box_width - 2) + f"╗{R}")

        # Metadata section title
        title_display = f"{B}METADATA{R}"
        title_padded = f" {title_display} ".center(inner_width + len(B) + len(R))
        lines.append(f"{C}║{R} {title_padded} {C}║{R}")
        lines.append(f"{C}╟" + "─" * (box_width - 2) + f"╢{R}")

        # Audit data lines
        for key, value in audit_data.items():
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)

            raw_content = f"{key}: {value_str}"
            if len(raw_content) > inner_width:
                raw_content = raw_content[:inner_width - 3] + "..."
                value_str = raw_content.split(": ", 1)[1] if ": " in raw_content else value_str

            # Apply colors: key in yellow
            colored_content = f"{Y}{key}:{R} {value_str}"
            padding_needed = inner_width - len(raw_content)
            line_padded = f" {colored_content}{' ' * padding_needed} "
            lines.append(f"{C}║{R}{line_padded}{C}║{R}")

        # Reminders section (if provided)
        if reminders:
            lines.append(f"{C}╟" + "─" * (box_width - 2) + f"╢{R}")
            title_display = f"{B}REMINDERS{R}"
            title_padded = f" {title_display} ".center(inner_width + len(B) + len(R))
            lines.append(f"{C}║{R} {title_padded} {C}║{R}")

            for reminder in reminders:
                emoji = reminder.get('emoji', '•')
                message = reminder.get('message', '')
                line_content = f"{emoji} {message}"

                if len(line_content) > inner_width:
                    line_content = line_content[:inner_width - 3] + "..."

                line_padded = f" {line_content} ".ljust(inner_width + 2)
                lines.append(f"{C}║{R}{line_padded}{C}║{R}")

        # Bottom border
        lines.append(f"{C}╚" + "═" * (box_width - 2) + f"╝{R}")

        return '\n'.join(lines)

    def _format_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """
        Create aligned ASCII table.

        Format:
        ┌──────────┬──────────┬──────────┐
        │ Header1  │ Header2  │ Header3  │
        ├──────────┼──────────┼──────────┤
        │ value1   │ value2   │ value3   │
        │ value4   │ value5   │ value6   │
        └──────────┴──────────┴──────────┘

        Args:
            headers: List of column headers
            rows: List of row data (each row is list of strings)

        Returns:
            Formatted ASCII table as string
        """
        if not headers or not rows:
            return ""

        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        lines = []

        # Top border
        top = "┌" + "┬".join("─" * (w + 2) for w in col_widths) + "┐"
        lines.append(top)

        # Header row
        header_cells = [f" {h.ljust(col_widths[i])} " for i, h in enumerate(headers)]
        lines.append("│" + "│".join(header_cells) + "│")

        # Separator
        sep = "├" + "┼".join("─" * (w + 2) for w in col_widths) + "┤"
        lines.append(sep)

        # Data rows
        for row in rows:
            cells = [f" {str(row[i] if i < len(row) else '').ljust(col_widths[i])} "
                    for i in range(len(headers))]
            lines.append("│" + "│".join(cells) + "│")

        # Bottom border
        bottom = "└" + "┴".join("─" * (w + 2) for w in col_widths) + "┘"
        lines.append(bottom)

        return '\n'.join(lines)

    # ==================== Phase 0: Core Formatting Methods ====================

    def format_readable_file_content(self, data: Dict[str, Any]) -> str:
        """
        Format read_file output in readable format with line numbers and metadata boxes.

        Args:
            data: read_file response with 'scan', 'chunks', 'chunk', etc.

        Returns:
            Formatted string with header box, line-numbered content, footer box
        """
        # Extract scan metadata
        scan = data.get('scan', {})
        path = scan.get('repo_relative_path') or scan.get('absolute_path', 'unknown')
        mode = data.get('mode', 'unknown')

        # Build header metadata
        header_meta = {
            'path': path,
            'mode': mode,
            'lines': scan.get('line_count', 0),
            'size': scan.get('byte_size', 0),
            'encoding': scan.get('encoding', 'utf-8'),
            'sha256': scan.get('sha256', '')[:16] + '...' if scan.get('sha256') else 'unknown'
        }

        # Extract content based on mode
        content = ''
        start_line = 1

        if mode == 'scan_only':
            # No content for scan_only
            content = '[scan only - no content requested]'
        elif 'chunks' in data and data['chunks']:
            # Chunk mode - concatenate chunks
            chunks = data['chunks']
            content_parts = []
            for chunk in chunks:
                content_parts.append(chunk.get('content', ''))
            content = '\n'.join(content_parts)
            start_line = chunks[0].get('line_start', 1) if chunks else 1
        elif 'chunk' in data:
            # Line range or page mode
            chunk = data['chunk']
            content = chunk.get('content', '')
            start_line = chunk.get('line_start', 1)
        elif 'matches' in data:
            # Search mode
            matches = data['matches']
            if matches:
                content_parts = []
                for match in matches[:10]:  # Limit to first 10 matches
                    line_num = match.get('line_number', '?')
                    line_text = match.get('line', '').rstrip()
                    content_parts.append(f"[Line {line_num}] {line_text}")
                content = '\n'.join(content_parts)
                start_line = 1  # Search results don't use line numbering
            else:
                content = '[no matches found]'

        # Build footer metadata (audit info)
        footer_meta = {}
        if 'chunks' in data:
            footer_meta['chunks_returned'] = len(data['chunks'])
        if 'estimated_chunk_count' in scan:
            footer_meta['total_chunks'] = scan['estimated_chunk_count']
        if 'max_matches' in data:
            footer_meta['max_matches'] = data['max_matches']
            footer_meta['matches_found'] = len(data.get('matches', []))
        if data.get('page_number'):
            footer_meta['page'] = f"{data['page_number']} (size: {data.get('page_size', '?')})"

        # Get reminders if present
        reminders = data.get('reminders', [])

        # Build readable output
        parts = []
        parts.append(self._create_header_box("FILE CONTENT", header_meta))
        parts.append("")  # Blank line

        # Add line-numbered content (skip for scan_only)
        if mode != 'scan_only':
            parts.append(self._add_line_numbers(content, start_line))
        else:
            parts.append(content)

        parts.append("")  # Blank line
        parts.append(self._create_footer_box(footer_meta, reminders if reminders else None))

        return '\n'.join(parts)

    def format_readable_log_entries(self, entries: List[Dict], pagination: Dict, search_context: Optional[Dict] = None) -> str:
        """
        Format log entries in readable format with reasoning blocks.

        Phase 3a enhancements:
        - Parse and display meta.reasoning blocks as tree structure
        - Smarter message truncation with word boundaries
        - Compact timestamp format (HH:MM)
        - Better pagination display (Page X of Y)
        - ANSI colors enabled (config-driven, display-heavy tool)

        Phase 3b enhancements:
        - Optional search_context for query_entries (shows filters in header)
        - Different header for search results vs recent entries

        Args:
            entries: List of log entry dicts
            pagination: Pagination metadata
            search_context: Optional search filter context (for query_entries)

        Returns:
            Formatted string with header box, entries with reasoning, footer
        """
        if not entries:
            return "No log entries found."

        # Pagination info
        page = pagination.get('page', 1)
        page_size = pagination.get('page_size', len(entries))
        total_count = pagination.get('total_count', len(entries))
        total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 1

        # Build readable output
        parts = []

        # Header with pagination (different for search vs recent)
        use_colors = self.USE_COLORS
        is_search = search_context is not None

        if is_search:
            # Search results header with filter info
            if use_colors:
                header = f"{self.ANSI_BOLD}╔═══════════════════════════════════════════════════════════════╗{self.ANSI_RESET}\n"
                header += f"{self.ANSI_BOLD}║ 🔍 SEARCH RESULTS{self.ANSI_RESET}                   Found {len(entries)} of {total_count} matches {self.ANSI_BOLD}║{self.ANSI_RESET}\n"

                # Build filter summary
                filters = []
                if search_context.get('message'):
                    filters.append(f"message=\"{search_context['message']}\"")
                if search_context.get('status'):
                    filters.append(f"status={search_context['status']}")
                if search_context.get('agents'):
                    filters.append(f"agents={search_context['agents']}")
                if search_context.get('emoji'):
                    filters.append(f"emoji={search_context['emoji']}")

                if filters:
                    filter_str = " | ".join(filters)
                    # Truncate if too long
                    if len(filter_str) > 60:
                        filter_str = filter_str[:57] + "..."
                    header += f"{self.ANSI_BOLD}║{self.ANSI_RESET} {self.ANSI_DIM}Filter: {filter_str}{self.ANSI_RESET}\n"
                    header += f"{self.ANSI_BOLD}║{self.ANSI_RESET}                                                               {self.ANSI_BOLD}║{self.ANSI_RESET}\n"

                header += f"{self.ANSI_BOLD}╚═══════════════════════════════════════════════════════════════╝{self.ANSI_RESET}"
            else:
                header = "╔═══════════════════════════════════════════════════════════════╗\n"
                header += f"║ 🔍 SEARCH RESULTS                   Found {len(entries)} of {total_count} matches ║\n"

                # Build filter summary
                filters = []
                if search_context.get('message'):
                    filters.append(f"message=\"{search_context['message']}\"")
                if search_context.get('status'):
                    filters.append(f"status={search_context['status']}")
                if search_context.get('agents'):
                    filters.append(f"agents={search_context['agents']}")
                if search_context.get('emoji'):
                    filters.append(f"emoji={search_context['emoji']}")

                if filters:
                    filter_str = " | ".join(filters)
                    if len(filter_str) > 60:
                        filter_str = filter_str[:57] + "..."
                    header += f"║ Filter: {filter_str}\n"
                    header += "║                                                               ║\n"

                header += "╚═══════════════════════════════════════════════════════════════╝"
        else:
            # Recent entries header
            if use_colors:
                header = f"{self.ANSI_BOLD}╔═══════════════════════════════════════════════════════════════╗{self.ANSI_RESET}\n"
                header += f"{self.ANSI_BOLD}║ 📋 RECENT LOG ENTRIES{self.ANSI_RESET}                    Page {page} of {total_pages} ({len(entries)}/{total_count}) {self.ANSI_BOLD}║{self.ANSI_RESET}\n"
                header += f"{self.ANSI_BOLD}╚═══════════════════════════════════════════════════════════════╝{self.ANSI_RESET}"
            else:
                header = "╔═══════════════════════════════════════════════════════════════╗\n"
                header += f"║ 📋 RECENT LOG ENTRIES                    Page {page} of {total_pages} ({len(entries)}/{total_count}) ║\n"
                header += "╚═══════════════════════════════════════════════════════════════╝"

        parts.append(header)
        parts.append("")

        # Process entries - filter out tool_logs (audit entries, not for display)
        entries_with_reasoning = []
        for entry in entries:
            # Skip tool_logs entries - they're for audit, not display
            meta = entry.get('meta', {})
            if isinstance(meta, dict) and meta.get('log_type') == 'tool_logs':
                continue
            # Also skip by message pattern as fallback
            message_text = entry.get('message', '')
            if message_text.startswith('Tool call:'):
                continue

            # Support both 'timestamp' and 'ts' field names
            timestamp = entry.get('timestamp', '') or entry.get('ts', '')
            # Compact timestamp format (HH:MM)
            # Check UTC FIRST because 'UTC' contains 'T' which would match ISO check
            if 'UTC' in timestamp:
                # Handle "YYYY-MM-DD HH:MM:SS UTC" format
                ts_parts = timestamp.split(' ')
                if len(ts_parts) >= 3 and ts_parts[2] == 'UTC':
                    # Format: YYYY-MM-DD HH:MM:SS UTC
                    time_part = ts_parts[1]  # HH:MM:SS
                    timestamp = time_part.rsplit(':', 1)[0]  # Drop seconds -> HH:MM
            elif 'T' in timestamp and not timestamp.endswith('UTC'):
                # Handle ISO format: 2026-01-03T15:42:37.123456Z
                time_part = timestamp.split('T')[1].split('.')[0]  # HH:MM:SS
                timestamp = time_part.rsplit(':', 1)[0]  # Drop seconds -> HH:MM
            elif ' ' in timestamp:
                # Handle other space-separated formats
                ts_parts = timestamp.split(' ')
                if len(ts_parts) >= 2 and ':' in ts_parts[1]:
                    time_part = ts_parts[1]
                    timestamp = time_part.rsplit(':', 1)[0] if ':' in time_part else time_part

            agent = entry.get('agent', '')
            # Truncate UUID agents to first 8 chars
            if len(agent) > 15:
                agent = agent[:12] + '...'

            emoji = entry.get('emoji', '')
            status = entry.get('status', 'info')
            message = entry.get('message', '')
            # NO truncation - full messages for context rehydration

            # Format entry line
            if use_colors:
                entry_line = f"[{self.ANSI_CYAN}{emoji}{self.ANSI_RESET}] {self.ANSI_DIM}{timestamp}{self.ANSI_RESET} | {self.ANSI_BOLD}{agent}{self.ANSI_RESET} | {message}"
            else:
                entry_line = f"[{emoji}] {timestamp} | {agent} | {message}"

            parts.append(entry_line)

            # Check for reasoning block - display full content for context rehydration
            meta = entry.get('meta', {})
            reasoning = self._parse_reasoning_block(meta)
            if reasoning:
                entries_with_reasoning.append((timestamp, agent, message, reasoning))
                # Display reasoning tree inline - NO truncation
                if use_colors:
                    parts.append(f"    {self.ANSI_DIM}├─ Why: {reasoning.get('why', 'N/A')}{self.ANSI_RESET}")
                    parts.append(f"    {self.ANSI_DIM}├─ What: {reasoning.get('what', 'N/A')}{self.ANSI_RESET}")
                    parts.append(f"    {self.ANSI_DIM}└─ How: {reasoning.get('how', 'N/A')}{self.ANSI_RESET}")
                else:
                    parts.append(f"    ├─ Why: {reasoning.get('why', 'N/A')}")
                    parts.append(f"    ├─ What: {reasoning.get('what', 'N/A')}")
                    parts.append(f"    └─ How: {reasoning.get('how', 'N/A')}")

            parts.append("")  # Blank line between entries

        # Footer with file path
        parts.append("─" * 65)
        if use_colors:
            parts.append(f"{self.ANSI_DIM}📁 Progress log entries{self.ANSI_RESET}")
        else:
            parts.append("📁 Progress log entries")

        return '\n'.join(parts)

    def _truncate_message_smart(self, message: str, max_length: int = 100) -> str:
        """
        Truncate message at word boundary for better readability.

        Args:
            message: Message to truncate
            max_length: Maximum length before truncation

        Returns:
            Truncated message with ellipsis or original if short enough
        """
        if len(message) <= max_length:
            return message

        # Try to truncate at word boundary
        truncated = message[:max_length - 3]
        last_space = truncated.rfind(' ')

        # Only use word boundary if it's at least 70% of desired length
        if last_space > max_length * 0.7:
            truncated = truncated[:last_space]

        return truncated + "..."

    def format_readable_projects(self, projects: List[Dict], active: Optional[str] = None) -> str:
        """
        Format list_projects output in readable format.

        Args:
            projects: List of project dicts
            active: Name of active project (if any)

        Returns:
            Formatted string with header box, project table, footer
        """
        if not projects:
            return "No projects found."

        # Build header metadata
        header_meta = {
            'total_projects': len(projects),
            'active_project': active or 'none'
        }

        # Build table
        headers = ['Name', 'Status', 'Root', 'Last Entry']
        rows = []
        for project in projects:
            name = project.get('name', '')
            if name == active:
                name = f"* {name}"  # Mark active project

            status = project.get('lifecycle_status', 'unknown')
            root = project.get('root', '')[:40]  # Truncate long paths
            last_entry = project.get('last_entry_at', 'never')
            if 'T' in last_entry:
                last_entry = last_entry.split('T')[0]  # Date only

            rows.append([name, status, root, last_entry])

        # Build footer
        footer_meta = {'projects_shown': len(projects)}

        # Build readable output
        parts = []
        parts.append(self._create_header_box("PROJECTS", header_meta))
        parts.append("")
        parts.append(self._format_table(headers, rows))
        parts.append("")
        parts.append(self._create_footer_box(footer_meta))

        return '\n'.join(parts)

    def format_readable_confirmation(self, operation: str, data: Dict[str, Any]) -> str:
        """
        Format operation confirmations (append_entry, etc) in readable format.

        Args:
            operation: Operation name (e.g., "append_entry")
            data: Operation result data

        Returns:
            Formatted confirmation string
        """
        # Build header metadata
        header_meta = {
            'operation': operation,
            'status': 'success' if data.get('ok') else 'failed'
        }

        # Build main content
        parts = []
        parts.append(self._create_header_box("OPERATION RESULT", header_meta))
        parts.append("")

        # Operation-specific formatting
        if operation == "append_entry":
            message = data.get('written_line', data.get('message', ''))
            parts.append(f"✅ Entry written:")
            parts.append(f"   {message}")
            parts.append("")
            parts.append(f"Path: {data.get('path', 'unknown')}")

        # Build footer with audit data
        footer_meta = {}
        if 'id' in data:
            footer_meta['entry_id'] = data['id']
        if 'meta' in data:
            footer_meta['metadata'] = data['meta']

        reminders = data.get('reminders', [])

        parts.append("")
        parts.append(self._create_footer_box(footer_meta, reminders if reminders else None))

        return '\n'.join(parts)

    def format_readable_error(self, error: str, context: Dict[str, Any]) -> str:
        """
        Format error messages in readable format.

        Args:
            error: Error message
            context: Error context data

        Returns:
            Formatted error string
        """
        # Build header
        header_meta = {
            'status': 'ERROR',
            'type': context.get('error_type', 'unknown')
        }

        parts = []
        parts.append(self._create_header_box("ERROR", header_meta))
        parts.append("")
        parts.append(f"❌ {error}")
        parts.append("")

        # Add context if available
        if context:
            footer_meta = {k: v for k, v in context.items() if k != 'error_type'}
            parts.append(self._create_footer_box(footer_meta))

        return '\n'.join(parts)

    def _parse_reasoning_block(self, meta: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Parse reasoning block from meta.reasoning field.

        Args:
            meta: Metadata dictionary that may contain reasoning field

        Returns:
            Dictionary with why/what/how keys or None if not parseable
        """
        reasoning_raw = meta.get('reasoning')
        if not reasoning_raw:
            return None

        try:
            # Try parsing as JSON string
            if isinstance(reasoning_raw, str):
                reasoning = json.loads(reasoning_raw)
            elif isinstance(reasoning_raw, dict):
                reasoning = reasoning_raw
            else:
                return None

            # Validate it has the expected keys
            if isinstance(reasoning, dict) and any(k in reasoning for k in ['why', 'what', 'how']):
                return reasoning
        except (json.JSONDecodeError, TypeError):
            pass

        return None

    def format_readable_append_entry(self, data: Dict[str, Any]) -> str:
        """
        Format append_entry output in concise readable format.

        Design decisions (Phase 2 user-approved):
        - NO ANSI COLORS for this tool (USE_COLORS hardcoded to False)
        - Parse and display meta.reasoning block nicely
        - Show reminders only if present (conditional)
        - Single entry: Concise 4-5 line format
        - Bulk entry: Summary format with samples

        Args:
            data: append_entry response data

        Returns:
            Formatted string with concise or summary format
        """
        # CRITICAL: NO ANSI COLORS for append_entry (user-approved design)
        # Agents see ANSI codes as text clutter, humans don't need color for confirmations
        USE_COLORS = False

        # Detect mode: bulk or single entry
        is_bulk = "written_count" in data or "bulk_mode" in data

        if is_bulk:
            return self._format_bulk_append_entry(data, USE_COLORS)
        else:
            return self._format_single_append_entry(data, USE_COLORS)

    def _format_single_append_entry(self, data: Dict[str, Any], USE_COLORS: bool) -> str:
        """
        Format single append_entry in concise 4-5 line format.

        Format:
        ✅ Entry written to progress log

           [ℹ️] [2026-01-03 02:46:00 UTC] [Agent: ResearchAgent] Investigation complete

           Reasoning:
           ├─ Why: Need to understand append_entry structure
           ├─ What: Analyzed return values, usage patterns
           └─ How: Read source code, traced execution paths

        📁 .scribe/docs/dev_plans/project/PROGRESS_LOG.md

        ⏰ Reminders:
           • It's been 15 minutes since the last log entry.
        """
        parts = []

        # Line 1: Success indicator
        if data.get('ok'):
            parts.append("✅ Entry written to progress log")
        else:
            parts.append("❌ Entry write failed")

        # Line 2: Written line content (indented, subtle)
        written_line = data.get('written_line', '')
        if written_line:
            parts.append(f"   {written_line}")

        # Reasoning block (if present in metadata)
        meta = data.get('meta', {})
        reasoning = self._parse_reasoning_block(meta)
        if reasoning:
            parts.append("")  # Blank line before reasoning
            parts.append("   Reasoning:")
            if reasoning.get('why'):
                parts.append(f"   ├─ Why: {reasoning['why']}")
            if reasoning.get('what'):
                parts.append(f"   ├─ What: {reasoning['what']}")
            if reasoning.get('how'):
                parts.append(f"   └─ How: {reasoning['how']}")

        # Blank line
        parts.append("")

        # Path (with folder emoji)
        path = data.get('path', '')
        if path:
            # Make path repo-relative for conciseness
            if '/MCP_SPINE/scribe_mcp/' in path:
                path = path.split('/MCP_SPINE/scribe_mcp/', 1)[1]
            elif '/.scribe/' in path:
                path = '.' + path.split('/.scribe/', 1)[1].replace('/.scribe/', '.scribe/')
            parts.append(f"📁 {path}")

        # Reminders section (ONLY if reminders present)
        reminders = data.get('reminders', [])
        if reminders:
            parts.append("")
            parts.append("⏰ Reminders:")
            for reminder in reminders:
                emoji = reminder.get('emoji', '•')
                message = reminder.get('message', '')
                parts.append(f"   {emoji} {message}")

        return '\n'.join(parts)

    def _format_bulk_append_entry(self, data: Dict[str, Any], USE_COLORS: bool) -> str:
        """
        Format bulk append_entry in summary format.

        Format:
        ╔══════════════════════════════════════════════════════════╗
        ║ BULK APPEND RESULT                                       ║
        ╟──────────────────────────────────────────────────────────╢
        ║ status: partial success                                  ║
        ║ written: 15 / 18                                         ║
        ║ failed: 3                                                ║
        ║ performance: 45.2 items/sec                              ║
        ╚══════════════════════════════════════════════════════════╝

        ✅ Successfully Written (first 5 of 15):
             1. [ℹ️] Investigation started | phase=research
             2. [ℹ️] Found 14 tools in directory | count=14
             3. [✅] Analysis complete | confidence=0.95
             4. [ℹ️] Creating research document
             5. [✅] Research document created | size=15KB

        ❌ Failed Entries (3):
             7. Missing required field 'message'
            12. JSON parsing error in metadata
            15. Permission denied writing to log file

        ╔══════════════════════════════════════════════════════════╗
        ║ METADATA                                                 ║
        ╟──────────────────────────────────────────────────────────╢
        ║ paths: 2 log files written                               ║
        ║ • /home/austin/.scribe/.../PROGRESS_LOG.md               ║
        ║ • /home/austin/.scribe/.../BUG_LOG.md                    ║
        ╚══════════════════════════════════════════════════════════╝
        """
        parts = []
        box_width = 80

        # Header box
        written_count = data.get('written_count', 0)
        failed_count = data.get('failed_count', 0)
        total = written_count + failed_count
        status_text = "success" if failed_count == 0 else "partial success" if written_count > 0 else "failed"

        parts.append("╔" + "═" * (box_width - 2) + "╗")
        parts.append("║ BULK APPEND RESULT" + " " * (box_width - 22) + "║")
        parts.append("╟" + "─" * (box_width - 2) + "╢")
        parts.append(f"║ status: {status_text}".ljust(box_width - 1) + "║")
        parts.append(f"║ written: {written_count} / {total}".ljust(box_width - 1) + "║")
        parts.append(f"║ failed: {failed_count}".ljust(box_width - 1) + "║")

        # Add performance if available
        performance = data.get('performance', {})
        if performance and 'items_per_second' in performance:
            items_per_sec = performance['items_per_second']
            parts.append(f"║ performance: {items_per_sec:.1f} items/sec".ljust(box_width - 1) + "║")

        parts.append("╚" + "═" * (box_width - 2) + "╝")
        parts.append("")

        # Successfully written entries (first 5)
        written_lines = data.get('written_lines', [])
        if written_lines:
            sample_count = min(5, len(written_lines))
            parts.append(f"✅ Successfully Written (first {sample_count} of {written_count}):")
            for i, line in enumerate(written_lines[:5], 1):
                # Extract just the core message part (emoji + message)
                line_compact = self._extract_compact_log_line(line)
                parts.append(f"     {i}. {line_compact}")
            parts.append("")

        # Failed entries (ALL failures)
        failed_items = data.get('failed_items', [])
        if failed_items:
            parts.append(f"❌ Failed Entries ({failed_count}):")
            for item in failed_items:
                index = item.get('index', '?')
                error = item.get('error', 'Unknown error')
                parts.append(f"    {index}. {error}")
            parts.append("")

        # Footer metadata box
        parts.append("╔" + "═" * (box_width - 2) + "╗")
        parts.append("║ METADATA" + " " * (box_width - 12) + "║")
        parts.append("╟" + "─" * (box_width - 2) + "╢")

        # Paths
        paths = data.get('paths', [])
        if paths:
            parts.append(f"║ paths: {len(paths)} log file{'s' if len(paths) > 1 else ''} written".ljust(box_width - 1) + "║")
            for path in paths:
                # Shorten path for display
                display_path = path
                if '/MCP_SPINE/scribe_mcp/' in display_path:
                    display_path = '...' + display_path.split('/MCP_SPINE/scribe_mcp/', 1)[1]
                if len(display_path) > box_width - 8:
                    display_path = display_path[-(box_width - 11):].strip('/')
                    display_path = '...' + display_path
                parts.append(f"║ • {display_path}".ljust(box_width - 1) + "║")

        parts.append("╚" + "═" * (box_width - 2) + "╝")

        return '\n'.join(parts)

    def _extract_compact_log_line(self, full_line: str) -> str:
        """
        Extract compact version of log line for bulk display.

        From: "[ℹ️] [2026-01-03 02:46:00 UTC] [Agent: ResearchAgent] [Project: xyz] Investigation complete | confidence=0.95"
        To: "[ℹ️] Investigation complete | confidence=0.95"

        Args:
            full_line: Full log line with all metadata

        Returns:
            Compact version with emoji + message + key metadata
        """
        # Try to extract emoji and message part
        # Format: [emoji] [timestamp] [Agent: X] [Project: Y] message | meta
        # We need to skip first 4 bracket groups to get to message
        parts = full_line.split('] ', 4)  # Split on '] ' up to 5 parts
        if len(parts) >= 5:
            # parts[0] = "[ℹ️"
            # parts[1] = "[timestamp"
            # parts[2] = "[Agent: X"
            # parts[3] = "[Project: Y"
            # parts[4] = "message | meta" (no leading bracket)
            emoji = parts[0] + ']'  # e.g., "[ℹ️]"
            message_part = parts[4]  # Everything after [Project: Y]
            return f"{emoji} {message_part}"
        else:
            # Fallback: return first 80 chars
            return full_line[:80] + ('...' if len(full_line) > 80 else '')

    async def finalize_tool_response(
        self,
        data: Dict[str, Any],
        format: str = "readable",  # NOTE: readable is DEFAULT
        tool_name: str = ""
    ) -> Union[Dict[str, Any], "CallToolResult"]:
        """
        CRITICAL ROUTER: Logs tool call to tool_logs, then formats response.

        This method ensures complete audit trail by logging structured JSON
        BEFORE formatting for display.

        ISSUE #9962 FIX: When format="readable", we return CallToolResult with
        TextContent ONLY (no structuredContent). This forces Claude Code to
        display the text cleanly with actual newlines instead of escaped \\n.

        Args:
            data: Tool response data (always a dict)
            format: Output format - "readable", "structured", "compact", or "both"
            tool_name: Name of the tool being called

        Returns:
            - format="readable": CallToolResult with TextContent only (clean display)
            - format="both": CallToolResult with TextContent + structuredContent
            - format="structured"/"compact": Original data dict
            - Fallback to dict if MCP types unavailable
        """
        # STEP 1: Log to tool_logs (audit trail) - SKIP for append_entry to avoid recursion
        # append_entry calls finalize_tool_response, which would call append_entry again
        if tool_name != "append_entry":
            try:
                from tools.append_entry import append_entry

                await append_entry(
                    message=f"Tool call: {tool_name}",
                    log_type="tool_logs",
                    meta={
                        "tool": tool_name,
                        "format_requested": format,
                        "response_data": data,
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    },
                    format="structured"  # Use structured to avoid nested formatting
                )
            except Exception as e:
                # Log failure but don't block response
                print(f"Warning: Failed to log to tool_logs: {e}")

        # STEP 2: Format based on parameter
        if format == self.FORMAT_READABLE:
            # Check for errors first
            if data.get('ok') == False or 'error' in data:
                readable_content = self.format_readable_error(
                    data.get('error', 'Unknown error'),
                    data
                )
            # Route to appropriate readable formatter based on tool
            elif tool_name == "read_file":
                readable_content = self.format_readable_file_content(data)
            elif tool_name in ["read_recent", "query_entries"]:
                # Pass search context for query_entries to show filters
                search_context = None
                if tool_name == "query_entries":
                    # Extract search parameters from data (prefixed with search_)
                    search_context = {}
                    if 'search_message' in data:
                        search_context['message'] = data['search_message']
                    if 'search_status' in data:
                        search_context['status'] = data['search_status']
                    if 'search_agents' in data:
                        search_context['agents'] = data['search_agents']
                    if 'search_emoji' in data:
                        search_context['emoji'] = data['search_emoji']
                    # Always show search header for query_entries even if no filters
                    if not search_context:
                        search_context = {'_is_search': True}

                readable_content = self.format_readable_log_entries(
                    data.get('entries', []),
                    data.get('pagination', {}),
                    search_context=search_context if search_context else None
                )
            elif tool_name == "list_projects":
                readable_content = self.format_readable_projects(
                    data.get('projects', []),
                    data.get('active_project')
                )
            elif tool_name == "append_entry":
                readable_content = self.format_readable_append_entry(data)
            else:
                # Generic readable format for unknown tools
                readable_content = json.dumps(data, indent=2)

            # ISSUE #9962 FIX: Return CallToolResult with TextContent ONLY
            # This forces Claude Code to display text cleanly (no escaped \n)
            if MCP_TYPES_AVAILABLE and CallToolResult and TextContent:
                return CallToolResult(
                    content=[TextContent(type="text", text=readable_content)]
                    # NO structuredContent = Claude Code renders text cleanly!
                )
            else:
                # Fallback for environments without MCP SDK
                return {
                    "ok": True,
                    "format": "readable",
                    "content": readable_content,
                    "tool": tool_name
                }

        elif format == self.FORMAT_BOTH:
            # Build readable content (same logic as above)
            if data.get('ok') == False or 'error' in data:
                readable_content = self.format_readable_error(
                    data.get('error', 'Unknown error'),
                    data
                )
            elif tool_name == "read_file":
                readable_content = self.format_readable_file_content(data)
            elif tool_name in ["read_recent", "query_entries"]:
                # Pass search context for query_entries to show filters
                search_context = None
                if tool_name == "query_entries":
                    # Extract search parameters from data (prefixed with search_)
                    search_context = {}
                    if 'search_message' in data:
                        search_context['message'] = data['search_message']
                    if 'search_status' in data:
                        search_context['status'] = data['search_status']
                    if 'search_agents' in data:
                        search_context['agents'] = data['search_agents']
                    if 'search_emoji' in data:
                        search_context['emoji'] = data['search_emoji']
                    # Always show search header for query_entries even if no filters
                    if not search_context:
                        search_context = {'_is_search': True}

                readable_content = self.format_readable_log_entries(
                    data.get('entries', []),
                    data.get('pagination', {}),
                    search_context=search_context if search_context else None
                )
            elif tool_name == "list_projects":
                readable_content = self.format_readable_projects(
                    data.get('projects', []),
                    data.get('active_project')
                )
            elif tool_name == "append_entry":
                readable_content = self.format_readable_append_entry(data)
            else:
                readable_content = json.dumps(data, indent=2)

            # Return BOTH TextContent and structuredContent
            # (For when Issue #9962 is fixed, or for programmatic consumers)
            if MCP_TYPES_AVAILABLE and CallToolResult and TextContent:
                return CallToolResult(
                    content=[TextContent(type="text", text=readable_content)],
                    structuredContent=data  # Machine-readable data
                )
            else:
                return {
                    "ok": True,
                    "format": "both",
                    "content": readable_content,
                    "structured": data,
                    "tool": tool_name
                }

        elif format == self.FORMAT_COMPACT:
            # Return compact format (use existing compact logic if available)
            return data

        else:  # structured (default JSON)
            return data

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


# Global pagination calculator instance
_PAGINATION_CALCULATOR = PaginationCalculator()

def create_pagination_info(page: int, page_size: int, total_count: int) -> PaginationInfo:
    """Create pagination metadata using PaginationCalculator."""
    return _PAGINATION_CALCULATOR.create_pagination_info(page, page_size, total_count)


# Default formatter instance
default_formatter = ResponseFormatter()