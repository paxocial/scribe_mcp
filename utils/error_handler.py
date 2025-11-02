"""Error handling utilities for MCP tools.

This module provides standardized error handling patterns extracted from
append_entry.py, query_entries.py, and rotate_log.py to reduce code
duplication and provide consistent error responses across tools.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from scribe_mcp.shared.logging_utils import ProjectResolutionError


class ErrorHandler:
    """Centralized error handling utilities for MCP tools.

    Extracted from common patterns in append_entry.py, query_entries.py,
    and rotate_log.py to provide consistent error responses with
    appropriate suggestions and context.
    """

    @staticmethod
    def create_validation_error(
        error_message: str,
        suggestion: Optional[str] = None,
        alternative: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a standardized validation error response.

        Extracted from append_entry.py lines 404-422, query_entries.py lines 116-123,
        and rotate_log.py lines 464-470.

        Args:
            error_message: Human-readable error description
            suggestion: Helpful suggestion for fixing the error
            alternative: Alternative approach or workaround
            context: Additional context information

        Returns:
            Standardized error response dictionary
        """
        response: Dict[str, Any] = {
            "ok": False,
            "error": error_message,
        }

        if suggestion:
            response["suggestion"] = suggestion

        if alternative:
            response["alternative"] = alternative

        if context:
            response.update(context)

        return response

    @staticmethod
    def create_project_resolution_error(
        error: ProjectResolutionError,
        tool_name: str,
        suggestion: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a standardized project resolution error response.

        Extracted from append_entry.py lines 280-286, query_entries.py lines 208-215,
        and rotate_log.py lines 128-132.

        Args:
            error: The ProjectResolutionError exception
            tool_name: Name of the tool that encountered the error
            suggestion: Optional suggestion for fixing the issue

        Returns:
            Standardized project resolution error response
        """
        response: Dict[str, Any] = {
            "ok": False,
            "error": str(error),
            "suggestion": suggestion or f"Invoke set_project before using {tool_name}",
            "recent_projects": list(error.recent_projects),
        }

        return response

    @staticmethod
    def create_parameter_error(
        parameter_name: str,
        issue: str,
        expected: Optional[str] = None,
        received: Optional[Any] = None,
        suggestion: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a standardized parameter validation error.

        Extracted from query_entries.py lines 116-123, 132-146 and
        rotate_log.py lines 464-470.

        Args:
            parameter_name: Name of the invalid parameter
            issue: Description of what's wrong with the parameter
            expected: Description of expected value/type
            received: The actual value that was received
            suggestion: Optional suggestion for fixing the issue

        Returns:
            Standardized parameter error response
        """
        error_message = f"Invalid {parameter_name}: {issue}"

        if expected is not None and received is not None:
            error_message += f". Expected: {expected}, received: {received}"
        elif expected is not None:
            error_message += f". Expected: {expected}"

        return ErrorHandler.create_validation_error(
            error_message=error_message,
            suggestion=suggestion
        )

    @staticmethod
    def create_enum_error(
        parameter_name: str,
        invalid_value: str,
        valid_values: List[str],
        case_sensitive: bool = False
    ) -> Dict[str, Any]:
        """Create a standardized enum/choice validation error.

        Extracted from query_entries.py lines 116-117, 132-133.

        Args:
            parameter_name: Name of the parameter with invalid enum value
            invalid_value: The value that was provided
            valid_values: List of acceptable values
            case_sensitive: Whether the validation is case sensitive

        Returns:
            Standardized enum error response
        """
        if not case_sensitive:
            valid_values_str = ", ".join(sorted(valid_values))
            invalid_lower = invalid_value.lower() if invalid_value else "None"
            valid_lower = [v.lower() for v in valid_values]

            if invalid_lower not in valid_lower:
                # Find closest matches for helpful suggestion
                close_matches = ErrorHandler._find_close_matches(invalid_lower, valid_lower)
                suggestion = f"Must be one of: {valid_values_str}"
                if close_matches:
                    suggestion += f". Did you mean: {', '.join(close_matches)}?"
                else:
                    suggestion += f". Use one of: {valid_values_str}"
            else:
                # Case mismatch
                suggestion = f"Must be one of: {valid_values_str} (case sensitive)"
        else:
            valid_values_str = ", ".join(sorted(valid_values))
            suggestion = f"Must be one of: {valid_values_str}"

        return ErrorHandler.create_parameter_error(
            parameter_name=parameter_name,
            issue=f"Unsupported value '{invalid_value}'",
            expected=f"one of [{valid_values_str}]",
            suggestion=suggestion
        )

    @staticmethod
    def create_range_error(
        parameter_name: str,
        value: Union[int, float],
        min_value: Optional[Union[int, float]] = None,
        max_value: Optional[Union[int, float]] = None
    ) -> Dict[str, Any]:
        """Create a standardized range validation error.

        Extracted from query_entries.py lines 144-146.

        Args:
            parameter_name: Name of the parameter with invalid range value
            value: The value that was provided
            min_value: Minimum acceptable value
            max_value: Maximum acceptable value

        Returns:
            Standardized range error response
        """
        issue_parts = []
        expected_parts = []

        if min_value is not None and max_value is not None:
            issue_parts.append(f"value {value} is out of range")
            expected_parts.append(f"between {min_value} and {max_value}")
        elif min_value is not None:
            if value < min_value:
                issue_parts.append(f"value {value} is too small")
                expected_parts.append(f"≥ {min_value}")
        elif max_value is not None:
            if value > max_value:
                issue_parts.append(f"value {value} is too large")
                expected_parts.append(f"≤ {max_value}")

        suggestion = f"Value must be {' and '.join(expected_parts)}"

        return ErrorHandler.create_parameter_error(
            parameter_name=parameter_name,
            issue=". ".join(issue_parts),
            expected=" and ".join(expected_parts),
            suggestion=suggestion
        )

    @staticmethod
    def create_regex_error(
        pattern: str,
        regex_error: re.error
    ) -> Dict[str, Any]:
        """Create a standardized regex compilation error.

        Extracted from query_entries.py lines 119-123.

        Args:
            pattern: The invalid regex pattern
            regex_error: The regex compilation error

        Returns:
            Standardized regex error response
        """
        return ErrorHandler.create_parameter_error(
            parameter_name="message (regex mode)",
            issue=f"Invalid regular expression pattern: {regex_error}",
            received=pattern,
            suggestion="Check regex syntax and escape special characters properly"
        )

    @staticmethod
    def create_file_operation_error(
        operation: str,
        file_path: str,
        error: Exception
    ) -> Dict[str, Any]:
        """Create a standardized file operation error.

        Extracted from rotate_log.py lines 455-461, 474-480.

        Args:
            operation: Description of the file operation being attempted
            file_path: Path to the file that caused the error
            error: The original exception

        Returns:
            Standardized file operation error response
        """
        error_message = f"Unable to {operation}: {error}"
        suggestion = "Verify file permissions and that the path is accessible"

        if "not found" in str(error).lower():
            suggestion = f"Create the file or verify the path exists: {file_path}"
        elif "permission" in str(error).lower():
            suggestion = "Check file permissions and ensure write access"

        return ErrorHandler.create_validation_error(
            error_message=error_message,
            suggestion=suggestion,
            context={"file_path": file_path, "operation": operation}
        )

    @staticmethod
    def create_storage_error(
        operation: str,
        error: Exception,
        suggestion: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a standardized storage/database error.

        Extracted from append_entry.py lines 500-505.

        Args:
            operation: Description of the storage operation
            error: The original exception
            suggestion: Optional suggestion for recovery

        Returns:
            Standardized storage error response
        """
        error_message = f"Failed to {operation}: {error}"

        if suggestion is None:
            suggestion = "Check database connection and try again"

        return ErrorHandler.create_validation_error(
            error_message=error_message,
            suggestion=suggestion
        )

    @staticmethod
    def create_rate_limit_error(
        retry_after_seconds: int,
        window_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a standardized rate limiting error.

        Extracted from append_entry.py lines 589-598.

        Args:
            retry_after_seconds: Number of seconds to wait before retrying
            window_description: Optional description of the rate limit window

        Returns:
            Standardized rate limit error response
        """
        error_message = "Rate limit exceeded"
        if window_description:
            error_message += f" ({window_description})"

        suggestion = f"Wait {retry_after_seconds} seconds before making another request"

        return ErrorHandler.create_validation_error(
            error_message=error_message,
            suggestion=suggestion,
            context={"retry_after_seconds": retry_after_seconds}
        )

    @staticmethod
    def create_missing_requirement_error(
        requirement_type: str,
        missing_items: List[str],
        suggestion: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a standardized missing requirement error.

        Extracted from append_entry.py lines 293-299, rotate_log.py lines 155-159.

        Args:
            requirement_type: Type of requirement (e.g., "parameter", "log type")
            missing_items: List of missing items
            suggestion: Optional suggestion for fulfillment

        Returns:
            Standardized missing requirement error response
        """
        if len(missing_items) == 1:
            error_message = f"Missing required {requirement_type}: {missing_items[0]}"
        else:
            items_str = ", ".join(missing_items)
            error_message = f"Missing required {requirement_type}s: {items_str}"

        if suggestion is None:
            if len(missing_items) == 1:
                suggestion = f"Provide the required {requirement_type}: {missing_items[0]}"
            else:
                suggestion = f"Provide at least one of the required {requirement_type}s: {', '.join(missing_items)}"

        return ErrorHandler.create_validation_error(
            error_message=error_message,
            suggestion=suggestion
        )

    @staticmethod
    def handle_safe_operation(
        operation_name: str,
        operation_func,
        error_context: Optional[Dict[str, Any]] = None,
        fallback_result: Optional[Any] = None
    ) -> Tuple[bool, Any]:
        """Safely execute an operation with standardized error handling.

        This pattern is extracted from multiple try-catch blocks across
        the three tools where operations need to fail gracefully.

        Args:
            operation_name: Description of the operation for error messages
            operation_func: Function to execute
            error_context: Additional context for error reporting
            fallback_result: Result to return if operation fails

        Returns:
            Tuple of (success: bool, result: Any)
        """
        try:
            result = operation_func()
            return True, result
        except Exception as error:
            # Log error but don't fail the entire operation
            if error_context:
                error_context["operation"] = operation_name
                error_context["error"] = str(error)
            return False, fallback_result

    @staticmethod
    def _find_close_matches(target: str, candidates: List[str], max_matches: int = 3) -> List[str]:
        """Find close matches for a target string from candidates.

        Helper method for enum error suggestions.
        """
        target_lower = target.lower()
        matches = []

        for candidate in candidates:
            candidate_lower = candidate.lower()
            # Simple fuzzy matching - starts with or contains
            if (target_lower in candidate_lower or
                candidate_lower.startswith(target_lower[:3]) or
                target_lower.startswith(candidate_lower[:3])):
                matches.append(candidate)
                if len(matches) >= max_matches:
                    break

        return matches

    @staticmethod
    def create_warning_response(
        warning_message: str,
        original_response: Dict[str, Any],
        warning_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Add a warning to an otherwise successful response.

        Extracted from patterns where operations succeed but have
        notable issues that should be communicated to users.

        Args:
            warning_message: The warning message to include
            original_response: The original successful response
            warning_context: Additional context about the warning

        Returns:
            Response with warning added
        """
        response = original_response.copy()
        response["warning"] = warning_message

        if warning_context:
            response["warning_context"] = warning_context

        return response