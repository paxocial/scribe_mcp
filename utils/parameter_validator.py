"""
Centralized parameter validation utilities for MCP tools.

This module extracts common validation patterns from monolithic MCP tools
to provide reusable, consistent validation across all tools.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union, Sequence


class ToolValidator:
    """
    Centralized validation utilities for MCP tool parameters.

    Extracts common validation patterns from append_entry.py, query_entries.py,
    and rotate_log.py to eliminate code duplication and ensure consistency.
    """

    @staticmethod
    def validate_message(message: str) -> Optional[str]:
        """
        Validate message content for MCP protocol compatibility.

        Extracted from append_entry.py _validate_message function.

        Args:
            message: Message content to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        if any(ch in message for ch in ("\n", "\r")):
            return "Message cannot contain newline characters."
        if "|" in message:
            return "Message cannot contain pipe characters."  # avoids delimiter collisions
        return None

    @staticmethod
    def validate_enum_value(
        value: str,
        allowed_values: set[str],
        field_name: str = "value"
    ) -> Optional[str]:
        """
        Validate that a value is in the allowed set.

        Extracted from query_entries.py validation patterns.

        Args:
            value: Value to validate
            allowed_values: Set of allowed values
            field_name: Name of the field being validated

        Returns:
            Error message if validation fails, None otherwise
        """
        normalized_value = value.lower() if value else ""
        if normalized_value not in allowed_values:
            return (
                f"Invalid {field_name} '{value}'. Must be one of: "
                f"{', '.join(sorted(allowed_values))}"
            )
        return None

    @staticmethod
    def validate_regex_pattern(pattern: str) -> Optional[str]:
        """
        Validate that a regex pattern is compilable.

        Extracted from query_entries.py regex validation.

        Args:
            pattern: Regex pattern to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        try:
            re.compile(pattern)
        except re.error as exc:
            return f"Invalid regex: {exc}"
        return None

    @staticmethod
    def validate_range(
        value: Union[int, float],
        min_val: Optional[Union[int, float]] = None,
        max_val: Optional[Union[int, float]] = None,
        field_name: str = "value"
    ) -> Optional[str]:
        """
        Validate that a numeric value is within the specified range.

        Extracted from query_entries.py relevance_threshold validation.

        Args:
            value: Numeric value to validate
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)
            field_name: Name of the field being validated

        Returns:
            Error message if validation fails, None otherwise
        """
        # Convert string to float if needed
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                return f"{field_name} must be a number, got '{value}'"

        if min_val is not None and value < min_val:
            return f"{field_name} must be at least {min_val}, got {value}"

        if max_val is not None and value > max_val:
            return f"{field_name} must be at most {max_val}, got {value}"

        return None

    @staticmethod
    def validate_timestamp(timestamp_utc: Optional[str]) -> Tuple[Optional[datetime], str, Optional[str]]:
        """
        Validate and parse timestamp string.

        Extracted from append_entry.py _resolve_timestamp function.

        Args:
            timestamp_utc: UTC timestamp string in format "YYYY-MM-DD HH:MM:SS UTC"

        Returns:
            Tuple of (parsed_datetime, normalized_timestamp, warning_message)
        """
        if not timestamp_utc:
            from scribe_mcp.utils.time import format_utc
            current = format_utc()
            return None, current, None

        parsed = ToolValidator._parse_timestamp(timestamp_utc)
        if parsed is None:
            from scribe_mcp.utils.time import format_utc
            fallback = format_utc()
            warning = "timestamp format invalid; using current time"
            return None, fallback, warning

        return parsed, timestamp_utc, None

    @staticmethod
    def _parse_timestamp(value: str) -> Optional[datetime]:
        """
        Parse timestamp string to datetime object.

        Extracted from append_entry.py _parse_timestamp function.

        Args:
            value: Timestamp string to parse

        Returns:
            Datetime object or None if parsing fails
        """
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def sanitize_identifier(value: str) -> str:
        """
        Sanitize identifier strings for safe usage.

        Extracted from append_entry.py _sanitize_identifier function.

        Args:
            value: Identifier string to sanitize

        Returns:
            Sanitized identifier string
        """
        sanitized = value.replace("[", "").replace("]", "").replace("|", "").strip()
        return sanitized or "Scribe"

    @staticmethod
    def validate_json_metadata(
        metadata_str: Optional[str],
        field_name: str = "metadata"
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Validate and parse JSON metadata string.

        Extracted from rotate_log.py _parse_custom_metadata function.

        Args:
            metadata_str: JSON string to parse
            field_name: Name of the field being validated

        Returns:
            Tuple of (parsed_dict, error_message)
        """
        if not metadata_str:
            return None, None

        # Try using parameter_normalizer first (preferred method)
        try:
            from scribe_mcp.tools.base.parameter_normalizer import normalize_dict_param
            normalized = normalize_dict_param(metadata_str, field_name)
            if isinstance(normalized, dict):
                return normalized, None
        except (ValueError, ImportError):
            pass

        # Fallback to direct JSON parsing
        try:
            parsed = json.loads(metadata_str)
            if isinstance(parsed, dict):
                return parsed, None
        except json.JSONDecodeError:
            pass

        return None, f"Invalid JSON in {field_name} parameter"

    @staticmethod
    def validate_list_parameter(
        value: Optional[Union[Sequence[str], str]],
        delimiter: str = ","
    ) -> List[str]:
        """
        Normalize and validate list parameters.

        Extracted from rotate_log.py _normalize_log_type_param function.

        Args:
            value: Parameter value to normalize (string or sequence)
            delimiter: Delimiter for splitting strings

        Returns:
            Normalized list of strings
        """
        if value is None:
            return []

        if isinstance(value, str):
            candidates = value.split(delimiter)
        else:
            candidates = value

        result: List[str] = []
        for candidate in candidates:
            text = str(candidate).strip().lower()
            if text:
                result.append(text)

        return result

    @staticmethod
    def validate_document_types(
        document_types: Optional[List[str]],
        allowed_types: set[str]
    ) -> Tuple[Optional[List[str]], Optional[str]]:
        """
        Validate document types against allowed set.

        Extracted from query_entries.py document_types validation.

        Args:
            document_types: List of document types to validate
            allowed_types: Set of allowed document types

        Returns:
            Tuple of (normalized_list, error_message)
        """
        if not document_types:
            return None, None

        normalized_types = ToolValidator.validate_list_parameter(document_types)
        invalid_types = [dt for dt in normalized_types if dt not in allowed_types]

        if invalid_types:
            error_msg = (
                f"Invalid document_types: {', '.join(invalid_types)}. "
                f"Must be one of: {', '.join(sorted(allowed_types))}"
            )
            return None, error_msg

        return normalized_types, None

    @staticmethod
    def validate_parameters_against_schema(
        parameters: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate parameters against a schema definition.

        New utility for comprehensive parameter validation.

        Args:
            parameters: Parameters to validate
            schema: Schema definition with validation rules

        Returns:
            Error message if validation fails, None otherwise
        """
        for field_name, field_schema in schema.items():
            field_value = parameters.get(field_name)

            # Check required fields
            if field_schema.get("required", False) and field_value is None:
                return f"Required parameter '{field_name}' is missing"

            # Skip validation if field is not provided and not required
            if field_value is None:
                continue

            # Type validation
            expected_type = field_schema.get("type")
            if expected_type and not isinstance(field_value, expected_type):
                type_name = expected_type.__name__
                return f"Parameter '{field_name}' must be of type {type_name}, got {type(field_value).__name__}"

            # Enum validation
            allowed_values = field_schema.get("allowed_values")
            if allowed_values:
                error = ToolValidator.validate_enum_value(str(field_value), allowed_values, field_name)
                if error:
                    return error

            # Range validation
            min_val = field_schema.get("min_value")
            max_val = field_schema.get("max_value")
            if min_val is not None or max_val is not None:
                error = ToolValidator.validate_range(field_value, min_val, max_val, field_name)
                if error:
                    return error

            # Regex validation
            regex_pattern = field_schema.get("regex_pattern")
            if regex_pattern and isinstance(field_value, str):
                error = ToolValidator.validate_regex_pattern(regex_pattern)
                if error:
                    return error
                # Test if value matches pattern
                if not re.match(regex_pattern, field_value):
                    return f"Parameter '{field_name}' does not match required pattern"

        return None

    @staticmethod
    def validate_metadata_requirements(
        log_definition: Dict[str, Any],
        meta_payload: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate metadata against log definition requirements.

        Extracted from shared.logging_utils.ensure_metadata_requirements.

        Args:
            log_definition: Log configuration definition
            meta_payload: Metadata payload to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        try:
            from scribe_mcp.shared.logging_utils import ensure_metadata_requirements
            return ensure_metadata_requirements(log_definition, meta_payload)
        except ImportError:
            # Fallback validation if shared utility not available
            required_metadata = log_definition.get("required_metadata", {})
            for key, requirement in required_metadata.items():
                if key not in meta_payload:
                    return f"Required metadata field '{key}' is missing"

            return None