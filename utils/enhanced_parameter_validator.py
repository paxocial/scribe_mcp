"""Enhanced parameter validation framework for Scribe MCP tools.

This module provides centralized parameter validation with standardized
error messages and comprehensive validation rules.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

class ParameterValidationError(Exception):
    """Raised when parameter validation fails."""
    pass


class DocumentValidationError(Exception):
    """Raised when document validation fails."""
    pass


class EnhancedParameterValidator:
    """Centralized parameter validation with comprehensive rules."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name

    def validate_string_param(
        self,
        value: Any,
        param_name: str,
        required: bool = True,
        min_length: int = 1,
        max_length: Optional[int] = None,
        allowed_chars: Optional[str] = None,
        forbidden_patterns: Optional[List[str]] = None
    ) -> str:
        """Validate a string parameter with comprehensive checks."""

        # Check if value exists
        if value is None:
            if required:
                raise ParameterValidationError(
                    f"{self.tool_name}: {param_name} is required but not provided"
                )
            return ""

        # Check type
        if not isinstance(value, str):
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} must be a string, got {type(value).__name__}"
            )

        # Check length
        if len(value) < min_length:
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} must be at least {min_length} characters long"
            )

        if max_length is not None and len(value) > max_length:
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} must be no more than {max_length} characters long"
            )

        # Check allowed characters
        if allowed_chars is not None:
            for char in value:
                if char not in allowed_chars:
                    raise ParameterValidationError(
                        f"{self.tool_name}: {param_name} contains invalid character '{char}'. "
                        f"Allowed characters: {allowed_chars}"
                    )

        # Check forbidden patterns
        if forbidden_patterns is not None:
            for pattern in forbidden_patterns:
                if re.search(pattern, value):
                    raise ParameterValidationError(
                        f"{self.tool_name}: {param_name} contains forbidden pattern: {pattern}"
                    )

        return value

    def validate_enum_param(
        self,
        value: Any,
        param_name: str,
        allowed_values: List[str],
        required: bool = True
    ) -> str:
        """Validate an enum parameter against allowed values."""

        if value is None:
            if required:
                raise ParameterValidationError(
                    f"{self.tool_name}: {param_name} is required but not provided"
                )
            return ""

        if not isinstance(value, str):
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} must be a string, got {type(value).__name__}"
            )

        if value not in allowed_values:
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} must be one of {allowed_values}, got '{value}'"
            )

        return value

    def validate_comparison_operators(self, value: Any, param_name: str) -> Any:
        """Validate and properly escape comparison operators in string values."""

        if not isinstance(value, str):
            return value

        # Check for numeric comparison patterns that cause type errors
        numeric_comparison_pattern = r'^\s*\d+\.?\d*\s*[><=]+\s*\d+\.?\d*\s*$'

        if re.match(numeric_comparison_pattern, value.strip()):
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} contains numeric comparison '{value}' "
                "that should be handled as proper parameters, not as string content"
            )

        # Escape comparison operators in text content to prevent parsing issues
        escaped_value = value
        dangerous_patterns = [
            (r'(?<!\\)>', r'\>'),  # Escape > symbols
            (r'(?<!\\)<', r'\<'),  # Escape < symbols
        ]

        for pattern, replacement in dangerous_patterns:
            escaped_value = re.sub(pattern, replacement, escaped_value)

        return escaped_value

    def validate_metadata(
        self,
        metadata: Optional[Dict[str, Any]],
        param_name: str = "metadata"
    ) -> Dict[str, Any]:
        """Validate metadata dictionary with comprehensive checks."""

        if metadata is None:
            return {}

        if not isinstance(metadata, dict):
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} must be a dictionary, got {type(metadata).__name__}"
            )

        validated_metadata = {}

        for key, value in metadata.items():
            # Validate key
            if not isinstance(key, str):
                raise ParameterValidationError(
                    f"{self.tool_name}: {param_name} key must be a string, got {type(key).__name__}"
                )

            if len(key) == 0:
                raise ParameterValidationError(
                    f"{self.tool_name}: {param_name} keys cannot be empty"
                )

            # Validate and escape value
            if isinstance(value, str):
                escaped_value = self.validate_comparison_operators(value, f"{param_name}[{key}]")
                validated_metadata[key] = escaped_value
            elif isinstance(value, (int, float, bool, list, dict)):
                validated_metadata[key] = value
            else:
                raise ParameterValidationError(
                    f"{self.tool_name}: {param_name}[{key}] has unsupported type {type(value).__name__}"
                )

        return validated_metadata

    def validate_timestamp_param(
        self,
        value: Any,
        param_name: str,
        required: bool = False
    ) -> Optional[datetime]:
        """Validate timestamp parameter and convert to datetime."""

        if value is None:
            if required:
                raise ParameterValidationError(
                    f"{self.tool_name}: {param_name} is required but not provided"
                )
            return None

        if isinstance(value, datetime):
            return value

        if not isinstance(value, str):
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} must be a string or datetime, got {type(value).__name__}"
            )

        # Try to parse common timestamp formats
        timestamp_formats = [
            "%Y-%m-%d %H:%M:%S UTC",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d",
        ]

        for fmt in timestamp_formats:
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue

        raise ParameterValidationError(
            f"{self.tool_name}: {param_name} '{value}' is not a valid timestamp format"
        )

    def validate_list_param(
        self,
        value: Any,
        param_name: str,
        required: bool = True,
        item_type: Optional[type] = str,
        max_items: Optional[int] = None
    ) -> List[Any]:
        """Validate a list parameter with type and size checks."""

        if value is None:
            if required:
                raise ParameterValidationError(
                    f"{self.tool_name}: {param_name} is required but not provided"
                )
            return []

        if not isinstance(value, list):
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} must be a list, got {type(value).__name__}"
            )

        if max_items is not None and len(value) > max_items:
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} cannot have more than {max_items} items"
            )

        if item_type is not None:
            for i, item in enumerate(value):
                if not isinstance(item, item_type):
                    raise ParameterValidationError(
                        f"{self.tool_name}: {param_name}[{i}] must be {item_type.__name__}, "
                        f"got {type(item).__name__}"
                    )

        return value

    def validate_file_path_param(
        self,
        value: Any,
        param_name: str,
        required: bool = True,
        must_exist: bool = False,
        base_path: Optional[Path] = None
    ) -> Path:
        """Validate file path parameter with security checks."""

        if value is None:
            if required:
                raise ParameterValidationError(
                    f"{self.tool_name}: {param_name} is required but not provided"
                )
            return Path()

        if not isinstance(value, str):
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} must be a string, got {type(value).__name__}"
            )

        # Security: Check for path traversal attempts
        if '..' in value or value.startswith('/'):
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} contains potentially unsafe path: {value}"
            )

        # Convert to Path object
        path = Path(value)

        # Resolve relative to base path if provided
        if base_path is not None:
            path = base_path / path

        # Check existence if required
        if must_exist and not path.exists():
            raise ParameterValidationError(
                f"{self.tool_name}: {param_name} path does not exist: {path}"
            )

        return path

    def create_validation_error(
        self,
        message: str,
        param_name: Optional[str] = None,
        suggestion: Optional[str] = None
    ) -> ParameterValidationError:
        """Create a standardized validation error with optional suggestions."""

        error_msg = f"{self.tool_name}: {message}"

        if suggestion:
            error_msg += f" Suggestion: {suggestion}"

        return ParameterValidationError(error_msg)


# Tool-specific validator instances
def create_manage_docs_validator() -> EnhancedParameterValidator:
    """Create validator instance for manage_docs tool."""
    return EnhancedParameterValidator("manage_docs")


def create_append_entry_validator() -> EnhancedParameterValidator:
    """Create validator instance for append_entry tool."""
    return EnhancedParameterValidator("append_entry")


def create_query_entries_validator() -> EnhancedParameterValidator:
    """Create validator instance for query_entries tool."""
    return EnhancedParameterValidator("query_entries")


def create_generate_doc_templates_validator() -> EnhancedParameterValidator:
    """Create validator instance for generate_doc_templates tool."""
    return EnhancedParameterValidator("generate_doc_templates")


def create_read_recent_validator() -> EnhancedParameterValidator:
    """Create validator instance for read_recent tool."""
    return EnhancedParameterValidator("read_recent")


def create_set_project_validator() -> EnhancedParameterValidator:
    """Create validator instance for set_project tool."""
    return EnhancedParameterValidator("set_project")