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
from pathlib import Path
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
        Format read_file output in readable format with simple header, content first, metadata at bottom.

        Args:
            data: read_file response with 'scan', 'chunks', 'chunk', etc.

        Returns:
            Formatted string with one-line header, line-numbered content, metadata footer
        """
        # Extract scan metadata
        scan = data.get('scan', {})
        path = scan.get('repo_relative_path') or scan.get('absolute_path', 'unknown')
        mode = data.get('mode', 'unknown')

        # Get filename from path
        import os
        filename = os.path.basename(path)

        # Extract content based on mode and determine line range
        content = ''
        start_line = 1
        end_line = 1
        total_lines = scan.get('line_count', 0)

        if mode == 'scan_only':
            # No content for scan_only
            content = '[scan only - no content requested]'
            line_range = 'scan only'
        elif 'chunks' in data and data['chunks']:
            # Chunk mode - concatenate chunks
            chunks = data['chunks']
            content_parts = []
            for chunk in chunks:
                content_parts.append(chunk.get('content', ''))
            content = '\n'.join(content_parts)
            start_line = chunks[0].get('line_start', 1) if chunks else 1
            end_line = chunks[-1].get('line_end', start_line) if chunks else start_line
            line_range = f"{start_line}-{end_line}"
        elif 'chunk' in data:
            # Line range or page mode
            chunk = data['chunk']
            content = chunk.get('content', '')
            start_line = chunk.get('line_start', 1)
            end_line = chunk.get('line_end', start_line)
            line_range = f"{start_line}-{end_line}"
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
                line_range = f"{len(matches)} matches"
            else:
                content = '[no matches found]'
                line_range = '0 matches'
        else:
            line_range = 'unknown'

        # Build readable output with simple one-line header
        parts = []

        # ONE-LINE HEADER: "READ FILE filename.xyz | Lines read: 100-243"
        parts.append(f"READ FILE {filename} | Lines read: {line_range}")
        parts.append("")  # Blank line

        # CONTENT FIRST (with line numbers)
        if mode != 'scan_only' and content != '[no matches found]':
            parts.append(self._add_line_numbers(content, start_line))
        else:
            parts.append(content)

        # METADATA AT BOTTOM
        parts.append("")  # Blank line before metadata
        parts.append("─" * 63)  # Separator line

        # Build metadata lines
        metadata_lines = []
        metadata_lines.append(f"Path: {path}")
        metadata_lines.append(f"Size: {scan.get('byte_size', 0)} bytes | Total lines: {total_lines} | Encoding: {scan.get('encoding', 'utf-8')}")

        # Add mode-specific metadata
        if 'chunks' in data and len(data['chunks']) > 1:
            metadata_lines.append(f"Chunks: {len(data['chunks'])} of {scan.get('estimated_chunk_count', '?')}")
        if data.get('page_number'):
            metadata_lines.append(f"Page: {data['page_number']} (size: {data.get('page_size', '?')})")
        if 'max_matches' in data:
            metadata_lines.append(f"Matches: {len(data.get('matches', []))} of {data.get('max_matches', '?')} max")

        # Add SHA256 (truncated)
        if scan.get('sha256'):
            metadata_lines.append(f"SHA256: {scan['sha256'][:16]}...")

        parts.extend(metadata_lines)

        # Add reminders if present
        reminders = data.get('reminders', [])
        if reminders:
            parts.append("")
            parts.append("⏰ Reminders:")
            for reminder in reminders:
                parts.append(f"   • {reminder.get('message', '')}")

        return '\n'.join(parts)

    def format_readable_log_entries(self, entries: List[Dict], pagination: Dict, search_context: Optional[Dict] = None, project_name: Optional[str] = None) -> str:
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
            # Recent entries header with project name
            if use_colors:
                header = f"{self.ANSI_BOLD}╔═══════════════════════════════════════════════════════════════╗{self.ANSI_RESET}\n"
                if project_name:
                    header += f"{self.ANSI_BOLD}║ 📋 RECENT LOG ENTRIES ({project_name}){self.ANSI_RESET} Page {page} of {total_pages} ({len(entries)}/{total_count}) {self.ANSI_BOLD}║{self.ANSI_RESET}\n"
                else:
                    header += f"{self.ANSI_BOLD}║ 📋 RECENT LOG ENTRIES{self.ANSI_RESET}                    Page {page} of {total_pages} ({len(entries)}/{total_count}) {self.ANSI_BOLD}║{self.ANSI_RESET}\n"
                header += f"{self.ANSI_BOLD}╚═══════════════════════════════════════════════════════════════╝{self.ANSI_RESET}"
            else:
                header = "╔═══════════════════════════════════════════════════════════════╗\n"
                if project_name:
                    # Calculate padding to right-align the page info
                    title_with_project = f"📋 RECENT LOG ENTRIES ({project_name})"
                    page_info = f"Page {page} of {total_pages} ({len(entries)}/{total_count})"
                    # Total width is 63 (between the ║ characters)
                    padding = 63 - len(title_with_project) - len(page_info) - 2  # -2 for spaces
                    if padding < 1:
                        padding = 1
                    header += f"║ {title_with_project}{' ' * padding}{page_info} ║\n"
                else:
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

    def _format_relative_time(self, timestamp: str) -> str:
        """
        Convert timestamp to relative time string.

        Examples:
            "2026-01-03T08:15:30Z" → "2 hours ago" (if now is 10:15)
            "2026-01-02T10:00:00Z" → "1 day ago"
            "2025-12-20T14:30:00Z" → "2 weeks ago"

        Args:
            timestamp: ISO 8601 timestamp string (UTC)

        Returns:
            Relative time string or original timestamp if parsing fails
        """
        try:
            # Parse ISO 8601 formats: "YYYY-MM-DDTHH:MM:SSZ" or "YYYY-MM-DD HH:MM:SS UTC"
            # Check for UTC suffix first before checking for ISO T separator
            if timestamp.upper().endswith(' UTC'):
                # Space-separated format with UTC suffix (case-insensitive)
                # Remove the last 4 characters (' UTC' or ' utc')
                ts_clean = timestamp[:-4]
                ts_dt = datetime.strptime(ts_clean, '%Y-%m-%d %H:%M:%S')
            elif 'T' in timestamp:
                # ISO format with T separator (YYYY-MM-DDTHH:MM:SS)
                ts_clean = timestamp.replace('Z', '').replace('+00:00', '')
                ts_dt = datetime.fromisoformat(ts_clean)
            else:
                # Try generic ISO parsing
                ts_dt = datetime.fromisoformat(timestamp)

            # Calculate time delta from now
            now = datetime.utcnow()
            delta = now - ts_dt

            # Format based on magnitude
            total_seconds = delta.total_seconds()

            if total_seconds < 60:
                return "just now"
            elif total_seconds < 3600:  # < 60 minutes
                minutes = int(total_seconds / 60)
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            elif total_seconds < 7200:  # < 2 hours
                return "1 hour ago"
            elif total_seconds < 86400:  # < 24 hours
                hours = int(total_seconds / 3600)
                return f"{hours} hours ago"
            elif total_seconds < 172800:  # < 2 days
                return "1 day ago"
            elif total_seconds < 604800:  # < 7 days
                days = int(total_seconds / 86400)
                return f"{days} days ago"
            elif total_seconds < 1209600:  # < 14 days
                return "1 week ago"
            elif total_seconds < 2592000:  # < 30 days
                weeks = int(total_seconds / 604800)
                return f"{weeks} weeks ago"
            elif total_seconds < 5184000:  # < 60 days
                return "1 month ago"
            else:
                months = int(total_seconds / 2592000)
                return f"{months} months ago"
        except (ValueError, AttributeError, TypeError):
            # Return original timestamp on parsing failure
            return timestamp

    def _get_doc_line_count(self, file_path: Union[str, Path]) -> int:
        """
        Get line count for a file using efficient method.

        Uses stat-based approach when possible, falls back to line counting.

        Args:
            file_path: Absolute or relative path to file

        Returns:
            Number of lines in file, or 0 if file doesn't exist
        """
        try:
            # Convert to Path object
            path = Path(file_path)

            # Check if file exists
            if not path.exists() or not path.is_file():
                return 0

            # Efficient line counting
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return sum(1 for _ in f)
        except (OSError, PermissionError):
            # Return 0 on any file access errors
            return 0

    def _detect_custom_content(self, docs_dir: Union[str, Path]) -> Dict[str, Any]:
        """
        Detect custom documents in project dev plan directory.

        Scans for:
        - research/ directory and file count
        - bugs/ directory (if present in dev plan)
        - .jsonl files (TOOL_LOG.jsonl, etc.)

        Args:
            docs_dir: Path to project dev plan directory
                      (e.g., .scribe/docs/dev_plans/project_name/)

        Returns:
            Dictionary with custom content info:
            {
                "research_files": 3,
                "bugs_present": False,
                "jsonl_files": ["TOOL_LOG.jsonl"]
            }
        """
        # Initialize result
        result = {
            "research_files": 0,
            "bugs_present": False,
            "jsonl_files": []
        }

        try:
            # Convert to Path object
            path = Path(docs_dir)

            # Check if directory exists
            if not path.exists() or not path.is_dir():
                return result

            # Scan for research directory
            research_dir = path / "research"
            if research_dir.exists() and research_dir.is_dir():
                result["research_files"] = len(list(research_dir.glob("*.md")))

            # Check for bugs directory (note: bugs are usually at .scribe/docs/bugs/, not in dev plan)
            bugs_dir = path / "bugs"
            result["bugs_present"] = bugs_dir.exists() and bugs_dir.is_dir()

            # Find .jsonl files in dev plan root
            result["jsonl_files"] = [f.name for f in path.glob("*.jsonl")]

            return result
        except (OSError, PermissionError):
            # Return empty result on directory access errors
            return result

    def format_projects_table(
        self,
        projects: List[Dict[str, Any]],
        active_name: Optional[str],
        pagination: Dict[str, Any],
        filters: Dict[str, Any]
    ) -> str:
        """
        Format multiple projects as minimal table with pagination.

        Used when filter results in 2+ projects.

        Args:
            projects: List of project dicts (from list_projects query)
            active_name: Name of currently active project (for ⭐ marker)
            pagination: Dict with page, page_size, total_count, total_pages
            filters: Dict with name, status, tags, order_by, direction

        Returns:
            Formatted table string (~200 tokens)
        """
        # Extract pagination values
        page = pagination.get('page', 1)
        total_pages = pagination.get('total_pages', 1)
        total_count = pagination.get('total_count', len(projects))
        page_size = pagination.get('page_size', len(projects))

        # ANSI color support
        if self.USE_COLORS:
            CYAN = self.ANSI_CYAN
            GREEN = self.ANSI_GREEN
            RESET = self.ANSI_RESET
        else:
            CYAN = GREEN = RESET = ""

        lines = []

        # Header box
        header_text = f"📋 PROJECTS - {total_count} total (Page {page} of {total_pages}, showing {len(projects)})"
        lines.append(f"{CYAN}╔{'═' * 58}╗{RESET}")
        lines.append(f"{CYAN}║{RESET} {header_text:<56} {CYAN}║{RESET}")
        lines.append(f"{CYAN}╚{'═' * 58}╝{RESET}")
        lines.append("")

        # Table headers
        lines.append(f"{GREEN}NAME{' ' * 26}STATUS{' ' * 6}  ENTRIES  LAST ACTIVITY{RESET}")
        lines.append("─" * 70)

        # Table rows
        for project in projects:
            name = project.get('name', 'unknown')
            status = project.get('status') or project.get('lifecycle_status', 'unknown')
            total_entries = project.get('total_entries', 0)
            last_entry_at = project.get('last_entry_at')

            # Active project marker
            if name == active_name:
                prefix = "⭐ "
            else:
                prefix = "  "

            # Truncate long names to fit 30 char column (minus 3 for prefix/star)
            display_name = name[:27] if len(name) > 27 else name
            name_col = f"{prefix}{display_name:<28}"

            # Status column (12 chars)
            status_col = f"{status:<12}"

            # Entries column (8 chars, right-aligned)
            entries_col = f"{total_entries:>8}"

            # Last activity column (15 chars)
            if last_entry_at:
                activity = self._format_relative_time(last_entry_at)
            else:
                activity = "never"
            activity_col = f"{activity:<15}"

            lines.append(f"{name_col}{status_col}{entries_col}  {activity_col}")

        lines.append("")

        # Footer: Pagination info
        if total_pages > 1:
            next_page = page + 1 if page < total_pages else page
            lines.append(f"📄 Page {page} of {total_pages} | Use page={next_page} to see more")
        else:
            lines.append(f"📄 Page {page} of {total_pages}")

        # Footer: Filter info
        filter_parts = []
        if filters.get('name'):
            filter_parts.append(f"name=\"{filters['name']}\"")
        if filters.get('status'):
            filter_parts.append(f"status={filters['status']}")
        if filters.get('tags'):
            filter_parts.append(f"tags={filters['tags']}")
        filter_str = " | ".join(filter_parts) if filter_parts else "none"

        order_by = filters.get('order_by', 'last_entry_at')
        direction = filters.get('direction', 'desc')
        lines.append(f"🔍 Filter: {filter_str} | Sort: {order_by} ({direction})")

        # Footer: Tip
        if filters.get('name'):
            lines.append("💡 Tip: Use filter=\"exact_name\" to see details")
        else:
            lines.append("💡 Tip: Add filter=\"scribe\" to narrow results, or filter=\"exact_name\" to see details")

        return "\n".join(lines)

    def format_project_detail(
        self,
        project: Dict[str, Any],
        registry_info: Optional[Any],
        docs_info: Dict[str, Any]
    ) -> str:
        """
        Format single project with full details (deep dive).

        Used when filter results in exactly 1 project.

        Args:
            project: Project dict from list_projects
            registry_info: ProjectRecord from registry (or None)
            docs_info: Dict with document information:
                      {
                          "architecture": {"exists": True, "lines": 1274, "modified": True},
                          "phase_plan": {"exists": True, "lines": 542, "modified": False},
                          "checklist": {"exists": True, "lines": 356, "modified": False},
                          "progress": {"exists": True, "entries": 298},
                          "custom": {
                              "research_files": 3,
                              "bugs_present": False,
                              "jsonl_files": ["TOOL_LOG.jsonl"]
                          }
                      }

        Returns:
            Formatted detail view string (~400 tokens)
        """
        # ANSI color support
        if self.USE_COLORS:
            CYAN = self.ANSI_CYAN
            GREEN = self.ANSI_GREEN
            YELLOW = self.ANSI_YELLOW
            RESET = self.ANSI_RESET
        else:
            CYAN = GREEN = YELLOW = RESET = ""

        lines = []

        # Extract project name
        name = project.get('name', 'unknown')

        # Header box
        filter_hint = project.get('_filter_used', '')
        header_text = f"📁 PROJECT DETAIL: {name}"
        lines.append(f"{CYAN}╔{'═' * 58}╗{RESET}")
        lines.append(f"{CYAN}║{RESET} {header_text:<56} {CYAN}║{RESET}")
        if filter_hint:
            subtitle = f'(1 match found for filter: "{filter_hint}")'
            lines.append(f"{CYAN}║{RESET} {subtitle:<56} {CYAN}║{RESET}")
        lines.append(f"{CYAN}╚{'═' * 58}╝{RESET}")
        lines.append("")

        # Status line
        status = project.get('status') or project.get('lifecycle_status', 'unknown')
        is_active = project.get('_is_active', False)
        if is_active:
            lines.append(f"Status: {GREEN}{status} ⭐ (active){RESET}")
        else:
            lines.append(f"Status: {status}")

        # Location info
        root = project.get('root', 'N/A')
        progress_log = project.get('progress_log', '')
        if progress_log:
            # Extract dev plan directory from progress log path
            from pathlib import Path
            dev_plan_dir = str(Path(progress_log).parent)
        else:
            dev_plan_dir = 'N/A'

        lines.append(f"Root: {root}")
        lines.append(f"Dev Plan: {dev_plan_dir}")
        lines.append("")

        # Activity section
        lines.append("📊 Activity:")

        # Total entries
        if registry_info:
            total_entries = getattr(registry_info, 'total_entries', project.get('total_entries', 0))

            # Try to get per-log-type breakdown from project dict
            progress_count = project.get('entry_counts', {}).get('progress', total_entries)
            doc_updates_count = project.get('entry_counts', {}).get('doc_updates', 0)
            bugs_count = project.get('entry_counts', {}).get('bugs', 0)

            if doc_updates_count > 0 or bugs_count > 0:
                lines.append(f"  • Total Entries: {total_entries} (progress: {progress_count}, doc_updates: {doc_updates_count}, bugs: {bugs_count})")
            else:
                lines.append(f"  • Total Entries: {total_entries}")

            # Last entry timestamp
            last_entry_at = getattr(registry_info, 'last_entry_at', None)
            if last_entry_at:
                relative = self._format_relative_time(last_entry_at)
                utc_str = last_entry_at.strftime('%Y-%m-%d %H:%M UTC') if hasattr(last_entry_at, 'strftime') else str(last_entry_at)
                lines.append(f"  • Last Entry: {relative} ({utc_str})")

            # Last access
            last_access_at = getattr(registry_info, 'last_access_at', None)
            if last_access_at:
                relative = self._format_relative_time(last_access_at)
                lines.append(f"  • Last Access: {relative}")

            # Created
            created_at = getattr(registry_info, 'created_at', None)
            if created_at:
                relative = self._format_relative_time(created_at)
                lines.append(f"  • Created: {relative}")
        else:
            # Fallback to project dict
            total_entries = project.get('total_entries', 0)
            lines.append(f"  • Total Entries: {total_entries}")

        lines.append("")

        # Documents section
        lines.append("📄 Documents:")

        # Architecture
        arch_info = docs_info.get('architecture', {})
        if arch_info.get('exists'):
            lines_count = arch_info.get('lines', 0)
            if arch_info.get('modified'):
                lines.append(f"  {YELLOW}⚠️  ARCHITECTURE_GUIDE.md ({lines_count} lines, modified){RESET}")
            else:
                lines.append(f"  {GREEN}✓{RESET} ARCHITECTURE_GUIDE.md ({lines_count} lines)")

        # Phase plan
        phase_info = docs_info.get('phase_plan', {})
        if phase_info.get('exists'):
            lines_count = phase_info.get('lines', 0)
            if phase_info.get('modified'):
                lines.append(f"  {YELLOW}⚠️  PHASE_PLAN.md ({lines_count} lines, modified){RESET}")
            else:
                lines.append(f"  {GREEN}✓{RESET} PHASE_PLAN.md ({lines_count} lines)")

        # Checklist
        checklist_info = docs_info.get('checklist', {})
        if checklist_info.get('exists'):
            lines_count = checklist_info.get('lines', 0)
            if checklist_info.get('modified'):
                lines.append(f"  {YELLOW}⚠️  CHECKLIST.md ({lines_count} lines, modified){RESET}")
            else:
                lines.append(f"  {GREEN}✓{RESET} CHECKLIST.md ({lines_count} lines)")

        # Progress log
        progress_info = docs_info.get('progress', {})
        if progress_info.get('exists'):
            entries_count = progress_info.get('entries', 0)
            lines.append(f"  {GREEN}✓{RESET} PROGRESS_LOG.md ({entries_count} entries)")

        # Custom content section (only if present)
        custom_info = docs_info.get('custom', {})
        research_files = custom_info.get('research_files', 0)
        jsonl_files = custom_info.get('jsonl_files', [])

        if research_files > 0 or jsonl_files:
            lines.append("")
            lines.append("📁 Custom Content:")

            if research_files > 0:
                lines.append(f"  • research/ ({research_files} files)")

            for jsonl_file in jsonl_files:
                lines.append(f"  • {jsonl_file} (present)")

        # Tags
        tags = project.get('tags', [])
        if tags:
            lines.append("")
            tags_str = ", ".join(tags)
            lines.append(f"🏷️  Tags: {tags_str}")

        # Docs status warning
        any_modified = (
            arch_info.get('modified', False) or
            phase_info.get('modified', False) or
            checklist_info.get('modified', False)
        )
        if any_modified:
            lines.append(f"{YELLOW}⚠️  Docs Status: Architecture modified - not ready for work{RESET}")

        # Footer tip
        lines.append("")
        lines.append("💡 Use get_project() to see recent progress entries")

        return "\n".join(lines)

    def format_no_projects_found(self, filters: Dict[str, Any]) -> str:
        """
        Format helpful empty state when no projects match filters.

        Args:
            filters: Dict with name, status, tags filter values

        Returns:
            Formatted empty state string (~100 tokens)
        """
        # ANSI color support
        if self.USE_COLORS:
            CYAN = self.ANSI_CYAN
            RESET = self.ANSI_RESET
        else:
            CYAN = RESET = ""

        lines = []

        # Build filter summary for header
        filter_parts = []
        if filters.get('name'):
            filter_parts.append(f"\"{filters['name']}\"")
        if filters.get('status'):
            filter_parts.append(f"status={filters['status']}")
        if filters.get('tags'):
            filter_parts.append(f"tags={filters['tags']}")

        if filter_parts:
            filter_summary = filter_parts[0] if len(filter_parts) == 1 else "multiple filters"
        else:
            filter_summary = "none"

        # Header box
        header_text = f"📋 PROJECTS - 0 matches for filter: {filter_summary}"
        lines.append(f"{CYAN}╔{'═' * 58}╗{RESET}")
        lines.append(f"{CYAN}║{RESET} {header_text:<56} {CYAN}║{RESET}")
        lines.append(f"{CYAN}╚{'═' * 58}╝{RESET}")
        lines.append("")

        # Message
        lines.append("No projects found matching your criteria.")
        lines.append("")

        # Active filters section
        lines.append("🔍 Active Filters:")
        if filters.get('name'):
            lines.append(f"  • Name: \"{filters['name']}\"")
        if filters.get('status'):
            lines.append(f"  • Status: {filters['status']}")
        if filters.get('tags'):
            lines.append(f"  • Tags: {filters['tags']}")

        lines.append("")

        # Suggestions
        lines.append("💡 Try:")
        lines.append("  • Remove filters: list_projects()")
        lines.append("  • Broader search: list_projects(filter=\"scribe\")")
        lines.append("  • Check status: list_projects(status=[\"planning\", \"in_progress\"])")

        return "\n".join(lines)

    def format_project_context(
        self,
        project: Dict[str, Any],
        recent_entries: List[Dict[str, Any]],
        docs_info: Dict[str, Any],
        activity: Dict[str, Any]
    ) -> str:
        """
        Format current project context with recent activity.

        Shows "Where am I?" information: location, documents, recent work.

        Args:
            project: Project dict with name, root, progress_log
            recent_entries: Last 1-5 progress log entries (COMPLETE, no truncation!)
            docs_info: Dict with document information:
                      {
                          "architecture": {"exists": True, "lines": 1274},
                          "phase_plan": {"exists": True, "lines": 542},
                          "checklist": {"exists": True, "lines": 356},
                          "progress": {"exists": True, "entries": 298}
                      }
            activity: Dict with activity summary:
                     {
                         "status": "in_progress",
                         "total_entries": 298,
                         "last_entry_at": "2026-01-03T08:15:30Z"
                     }

        Returns:
            Formatted context string (~300 tokens with 1-5 recent entries)
        """
        lines = []
        use_colors = self.USE_COLORS

        # ANSI color codes
        CYAN = "\033[96m" if use_colors else ""
        BOLD = "\033[1m" if use_colors else ""
        DIM = "\033[2m" if use_colors else ""
        RESET = "\033[0m" if use_colors else ""

        # Header box
        project_name = project.get('name', 'unknown')
        header_text = f" 🎯 CURRENT PROJECT: {project_name} "
        box_width = max(58, len(header_text) + 4)

        lines.append(f"{CYAN}╔{'═' * (box_width - 2)}╗{RESET}")
        lines.append(f"{CYAN}║{RESET}{BOLD}{header_text:<{box_width - 2}}{RESET}{CYAN}║{RESET}")
        lines.append(f"{CYAN}╚{'═' * (box_width - 2)}╝{RESET}")
        lines.append("")

        # Location section
        lines.append(f"{BOLD}📂 Location:{RESET}")
        root_path = project.get('root', 'unknown')
        lines.append(f"  Root: {root_path}")

        # Extract dev plan path from progress_log
        progress_log = project.get('progress_log', '')
        if progress_log:
            # From: /path/to/.scribe/docs/dev_plans/project_name/PROGRESS_LOG.md
            # To: .scribe/docs/dev_plans/project_name/
            if '/.scribe/docs/dev_plans/' in progress_log:
                dev_plan_path = progress_log.split('PROGRESS_LOG.md')[0]
                # Make relative if it starts with root_path
                if dev_plan_path.startswith(root_path):
                    dev_plan_path = dev_plan_path[len(root_path):].lstrip('/')
                lines.append(f"  Dev Plan: {dev_plan_path}")

        lines.append("")

        # Documents section
        lines.append(f"{BOLD}📄 Documents:{RESET}")

        # Show only existing documents
        doc_mapping = {
            "architecture": "ARCHITECTURE_GUIDE.md",
            "phase_plan": "PHASE_PLAN.md",
            "checklist": "CHECKLIST.md",
            "progress": "PROGRESS_LOG.md"
        }

        for doc_key, doc_name in doc_mapping.items():
            doc_data = docs_info.get(doc_key, {})
            if doc_data.get('exists', False):
                if doc_key == 'progress':
                    entry_count = doc_data.get('entries', 0)
                    lines.append(f"  • {doc_name} ({entry_count} entries)")
                else:
                    line_count = doc_data.get('lines', 0)
                    lines.append(f"  • {doc_name} ({line_count} lines)")

        lines.append("")

        # Recent Activity section
        lines.append(f"{BOLD}📊 Recent Activity{RESET} (last {len(recent_entries) if recent_entries else 0} entries):")

        if not recent_entries:
            lines.append("  No entries yet - new project")
        else:
            for idx, entry in enumerate(recent_entries, 1):
                # Extract timestamp (HH:MM format)
                timestamp = entry.get('timestamp', '') or entry.get('ts', '')
                timestamp_display = ""

                # Check UTC FIRST (because 'UTC' contains 'T')
                if 'UTC' in timestamp:
                    # "YYYY-MM-DD HH:MM:SS UTC" → "HH:MM"
                    ts_parts = timestamp.split(' ')
                    if len(ts_parts) >= 3 and ts_parts[2] == 'UTC':
                        time_part = ts_parts[1]  # HH:MM:SS
                        timestamp_display = time_part.rsplit(':', 1)[0]  # Drop seconds
                    else:
                        timestamp_display = timestamp
                elif 'T' in timestamp and not timestamp.endswith('UTC'):
                    # "2026-01-03T15:42:37.123456Z" → "15:42"
                    time_part = timestamp.split('T')[1].split('.')[0]  # HH:MM:SS
                    timestamp_display = time_part.rsplit(':', 1)[0]  # Drop seconds
                else:
                    timestamp_display = timestamp  # Fallback

                # Extract emoji and agent
                emoji = entry.get('emoji', 'ℹ️')
                agent = entry.get('agent', 'Unknown')

                # Truncate agent if too long
                if len(agent) > 15:
                    agent = agent[:12] + "..."

                # Get FULL message (NO truncation!)
                message = entry.get('message', '')

                # Format entry line
                emoji_part = f"{CYAN}[{emoji}]{RESET}" if use_colors else f"[{emoji}]"
                time_part = f"{DIM}{timestamp_display}{RESET}" if use_colors else timestamp_display
                agent_part = f"{BOLD}{agent}{RESET}" if use_colors else agent

                lines.append(f"    {idx}. {emoji_part} {time_part} | {agent_part} | {message}")

            # Add hint if showing fewer than 5 entries
            if len(recent_entries) < 5:
                lines.append("")
                lines.append("💡 Use read_recent(limit=20) for more entries")

        lines.append("")

        # Footer status line
        status = activity.get('status', 'unknown')
        total_entries = activity.get('total_entries', 0)
        last_entry_at = activity.get('last_entry_at', '')

        if last_entry_at:
            relative_time = self._format_relative_time(last_entry_at)
            lines.append(f"⏰ Status: {status} | Entries: {total_entries} | Last: {relative_time}")
        else:
            lines.append(f"⏰ Status: {status} | Entries: {total_entries}")

        return "\n".join(lines)

    def format_project_sitrep_new(
        self,
        project: Dict[str, Any],
        docs_created: Dict[str, str]
    ) -> str:
        """
        Format SITREP for newly created project.

        Shows: location, created documents with template info, next steps.

        Args:
            project: Project dict with name, root, progress_log
            docs_created: Dict mapping doc type to path:
                         {
                             "architecture": "/path/to/ARCHITECTURE_GUIDE.md",
                             "phase_plan": "/path/to/PHASE_PLAN.md",
                             "checklist": "/path/to/CHECKLIST.md",
                             "progress_log": "/path/to/PROGRESS_LOG.md"
                         }

        Returns:
            Formatted SITREP string (~150 tokens)
        """
        lines = []
        project_name = project.get('name', 'unknown')

        # Header box
        if self.USE_COLORS:
            header_title = f"{self.COLORS['header_title']}✨ NEW PROJECT CREATED: {project_name}{self.COLORS['reset']}"
        else:
            header_title = f"✨ NEW PROJECT CREATED: {project_name}"

        lines.append("╔══════════════════════════════════════════════════════════╗")
        lines.append(f"║ {header_title:<58}║")
        lines.append("╚══════════════════════════════════════════════════════════╝")
        lines.append("")

        # Location section
        lines.append("📂 Location:")
        lines.append(f"  Root: {project.get('root', 'unknown')}")

        # Extract dev plan path from progress_log
        progress_log = project.get('progress_log', '')
        dev_plan = ''
        if 'PROGRESS_LOG.md' in progress_log:
            dev_plan = progress_log.replace('PROGRESS_LOG.md', '')
            # Convert to relative path if it's under the root
            root = project.get('root', '')
            if root and dev_plan.startswith(root):
                dev_plan = dev_plan[len(root):].lstrip('/')
        lines.append(f"  Dev Plan: {dev_plan}")
        lines.append("")

        # Documents Created section
        lines.append("📄 Documents Created:")

        # Define doc order and labels
        doc_labels = {
            'architecture': 'ARCHITECTURE_GUIDE.md',
            'phase_plan': 'PHASE_PLAN.md',
            'checklist': 'CHECKLIST.md',
            'progress_log': 'PROGRESS_LOG.md'
        }

        for doc_key in ['architecture', 'phase_plan', 'checklist', 'progress_log']:
            if doc_key in docs_created:
                doc_path = docs_created[doc_key]
                doc_label = doc_labels[doc_key]

                if doc_key == 'progress_log':
                    # Special case: progress log shows as "empty, ready for entries"
                    lines.append(f"  ✓ {doc_label} (empty, ready for entries)")
                else:
                    # Get line count for templates
                    line_count = self._get_doc_line_count(doc_path)
                    lines.append(f"  ✓ {doc_label} (template, {line_count} lines)")

        lines.append("")

        # Footer
        lines.append("🎯 Status: planning (new project)")
        lines.append("💡 Next: Start with research or architecture phase")

        return "\n".join(lines)

    def format_project_sitrep_existing(
        self,
        project: Dict[str, Any],
        inventory: Dict[str, Any],
        activity: Dict[str, Any]
    ) -> str:
        """
        Format SITREP for existing project activation.

        Shows: location, inventory (docs + custom content), activity, warnings.

        Args:
            project: Project dict with name, root, progress_log
            inventory: Dict with project inventory:
                      {
                          "docs": {
                              "architecture": {"exists": True, "lines": 1274, "modified": True},
                              "phase_plan": {"exists": True, "lines": 542, "modified": False},
                              "checklist": {"exists": True, "lines": 356, "modified": False},
                              "progress": {"exists": True, "entries": 298}
                          },
                          "custom": {
                              "research_files": 3,
                              "bugs_present": False,
                              "jsonl_files": ["TOOL_LOG.jsonl"]
                          }
                      }
            activity: Dict with activity summary:
                     {
                         "status": "in_progress",
                         "total_entries": 298,
                         "last_entry_at": "2026-01-03T08:15:30Z",
                         "per_log_counts": {
                             "progress": 298,
                             "doc_updates": 13,
                             "bugs": 0
                         }
                     }

        Returns:
            Formatted SITREP string (~250 tokens)
        """
        lines = []
        project_name = project.get('name', 'unknown')

        # Header box
        if self.USE_COLORS:
            header_title = f"{self.COLORS['header_title']}📌 PROJECT ACTIVATED: {project_name}{self.COLORS['reset']}"
        else:
            header_title = f"📌 PROJECT ACTIVATED: {project_name}"

        lines.append("╔══════════════════════════════════════════════════════════╗")
        lines.append(f"║ {header_title:<58}║")
        lines.append("╚══════════════════════════════════════════════════════════╝")
        lines.append("")

        # Location section
        lines.append("📂 Location:")
        lines.append(f"  Root: {project.get('root', 'unknown')}")

        # Extract dev plan path from progress_log
        progress_log = project.get('progress_log', '')
        dev_plan = ''
        if 'PROGRESS_LOG.md' in progress_log:
            dev_plan = progress_log.replace('PROGRESS_LOG.md', '')
            # Convert to relative path if it's under the root
            root = project.get('root', '')
            if root and dev_plan.startswith(root):
                dev_plan = dev_plan[len(root):].lstrip('/')
        lines.append(f"  Dev Plan: {dev_plan}")
        lines.append("")

        # Existing Project Inventory section
        lines.append("📊 Existing Project Inventory:")

        # Status
        status = activity.get('status', 'unknown')
        status_annotation = ""
        if status == "in_progress":
            status_annotation = " (active work)"
        lines.append(f"  • Status: {status}{status_annotation}")

        # Total Entries with per-log breakdown
        total_entries = activity.get('total_entries', 0)
        per_log_counts = activity.get('per_log_counts', {})

        # Build per-log breakdown string (only show non-zero counts)
        breakdown_parts = []
        for log_type in sorted(per_log_counts.keys()):
            count = per_log_counts[log_type]
            if count > 0:
                breakdown_parts.append(f"{log_type}: {count}")

        breakdown_str = ", ".join(breakdown_parts) if breakdown_parts else ""
        if breakdown_str:
            lines.append(f"  • Total Entries: {total_entries} ({breakdown_str})")
        else:
            lines.append(f"  • Total Entries: {total_entries}")

        # Last Activity (relative time)
        last_entry_at = activity.get('last_entry_at')
        if last_entry_at:
            relative_time = self._format_relative_time(last_entry_at)
            lines.append(f"  • Last Activity: {relative_time}")

        lines.append("")

        # Documents section
        docs = inventory.get('docs', {})
        doc_count = sum(1 for doc_info in docs.values() if doc_info.get('exists', False))
        lines.append(f"📄 Documents ({doc_count} total):")

        # Define doc order and labels
        doc_labels = {
            'architecture': 'ARCHITECTURE_GUIDE.md',
            'phase_plan': 'PHASE_PLAN.md',
            'checklist': 'CHECKLIST.md',
            'progress': 'PROGRESS_LOG.md'
        }

        for doc_key in ['architecture', 'phase_plan', 'checklist', 'progress']:
            if doc_key in docs:
                doc_info = docs[doc_key]
                if not doc_info.get('exists', False):
                    continue

                doc_label = doc_labels[doc_key]
                is_modified = doc_info.get('modified', False)

                if doc_key == 'progress':
                    # Progress log shows entries count
                    entries = doc_info.get('entries', 0)
                    prefix = "⚠️" if is_modified else "✓"
                    modifier = ", modified recently" if is_modified else ""
                    lines.append(f"  {prefix} {doc_label} ({entries} entries{modifier})")
                else:
                    # Other docs show line count
                    line_count = doc_info.get('lines', 0)
                    prefix = "⚠️" if is_modified else "✓"
                    modifier = ", modified recently" if is_modified else ""
                    lines.append(f"  {prefix} {doc_label} ({line_count} lines{modifier})")

        lines.append("")

        # Custom Documents section (only if present)
        custom = inventory.get('custom', {})
        has_custom_content = False
        custom_lines = []

        research_files = custom.get('research_files', 0)
        if research_files > 0:
            has_custom_content = True
            custom_lines.append(f"  • research/ ({research_files} files)")

        jsonl_files = custom.get('jsonl_files', [])
        if jsonl_files:
            has_custom_content = True
            for jsonl_file in jsonl_files:
                custom_lines.append(f"  • {jsonl_file} (present)")

        if has_custom_content:
            lines.append("📁 Custom Documents:")
            lines.extend(custom_lines)
            lines.append("")

        # Footer tip
        lines.append("💡 Context: Continuing active development - review recent progress entries")

        return "\n".join(lines)

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

        # Line 1: Success indicator with project name
        project_name = data.get('project_name', '')
        if data.get('ok'):
            if project_name:
                parts.append(f"✅ Entry written to progress log ({project_name})")
            else:
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
            # PRIORITY 1: Check if integration code already populated readable_content
            # (Used by list_projects, get_project, set_project with new formatters)
            if 'readable_content' in data:
                readable_content = data['readable_content']
            # PRIORITY 2: Check for errors
            elif data.get('ok') == False or 'error' in data:
                readable_content = self.format_readable_error(
                    data.get('error', 'Unknown error'),
                    data
                )
            # PRIORITY 3: Route to appropriate readable formatter based on tool
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
                    search_context=search_context if search_context else None,
                    project_name=data.get('project_name')
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
            # PRIORITY 1: Check if integration code already populated readable_content
            if 'readable_content' in data:
                readable_content = data['readable_content']
            # PRIORITY 2: Check for errors
            elif data.get('ok') == False or 'error' in data:
                readable_content = self.format_readable_error(
                    data.get('error', 'Unknown error'),
                    data
                )
            # PRIORITY 3: Route to appropriate readable formatter
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
                    search_context=search_context if search_context else None,
                    project_name=data.get('project_name')
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