"""Configuration management utilities for MCP tools.

This module provides standardized configuration management patterns extracted
from append_entry.py, query_entries.py, and rotate_log.py to reduce code
duplication and improve maintainability.

Key patterns extracted:
- Parameter defaults with fallback chains
- Settings merging and validation
- Enum validation with allowed values
- Configuration file loading with caching
- Response payload building
- JSON parameter normalization
- Range/boundary validation
- Template context creation
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Note: parameter normalization handled by tools to avoid circular imports


class ConfigManager:
    """
    Centralized configuration management utilities for MCP tools.

    Extracted from common patterns in append_entry.py, query_entries.py,
    and rotate_log.py to provide standardized configuration handling.
    """

    def __init__(self, logger_name: Optional[str] = None):
        """Initialize ConfigManager with optional logger."""
        self.logger = logging.getLogger(logger_name or __name__)

    def apply_parameter_defaults(
        self,
        params: Dict[str, Any],
        defaults: Dict[str, Any],
        required_keys: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Apply parameter defaults using fallback chain pattern.

        Extracted from append_entry.py and rotate_log.py pattern:
        agent or defaults.get("agent") or "Scribe"

        Args:
            params: Input parameters
            defaults: Default values dictionary
            required_keys: List of keys that must be present

        Returns:
            Parameters with defaults applied

        Raises:
            ValueError: If required keys are missing
        """
        if required_keys:
            missing_keys = [key for key in required_keys if key not in params and key not in defaults]
            if missing_keys:
                raise ValueError(f"Missing required parameters: {', '.join(missing_keys)}")

        result = params.copy()

        # Apply defaults for missing values
        for key, default_value in defaults.items():
            if key not in result or result[key] is None:
                result[key] = default_value

        return result

    def resolve_fallback_chain(
        self,
        *values: Optional[Any],
        default: Optional[Any] = None
    ) -> Any:
        """
        Resolve value using fallback chain pattern.

        Example: resolve_fallback_chain(agent, defaults.get("agent"), "Scribe")

        Args:
            *values: Values to check in order
            default: Final fallback value

        Returns:
            First non-None value or default
        """
        for value in values:
            if value is not None:
                return value
        return default

    def merge_project_settings(
        self,
        project_config: Dict[str, Any],
        tool_defaults: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Merge project configuration with tool-specific defaults.

        Extracted from pattern used across all three tools for merging
        project defaults with tool-specific settings.

        Args:
            project_config: Project configuration dictionary
            tool_defaults: Tool-specific default values

        Returns:
            Merged configuration dictionary
        """
        merged = project_config.copy()

        # Get project defaults if they exist
        project_defaults = merged.get("defaults", {})

        # Apply tool defaults
        if tool_defaults:
            project_defaults = {**tool_defaults, **project_defaults}
            merged["defaults"] = project_defaults

        return merged

    def validate_enum_value(
        self,
        value: str,
        allowed_values: List[str],
        param_name: str
    ) -> str:
        """
        Validate enum parameter against allowed values.

        Extracted from query_entries.py pattern for validating
        search_scope, document_types, and other enum parameters.

        Args:
            value: Value to validate
            allowed_values: List of valid values
            param_name: Parameter name for error messages

        Returns:
            Validated value (lowercase)

        Raises:
            ValueError: If value is not in allowed_values
        """
        if not isinstance(value, str):
            raise ValueError(f"{param_name} must be a string, got {type(value).__name__}")

        normalized_value = value.lower()
        if normalized_value not in allowed_values:
            raise ValueError(
                f"Invalid {param_name} '{value}'. "
                f"Must be one of: {', '.join(sorted(allowed_values))}"
            )

        return normalized_value

    def validate_range(
        self,
        value: Union[int, float],
        min_val: Optional[Union[int, float]] = None,
        max_val: Optional[Union[int, float]] = None,
        param_name: str = "parameter"
    ) -> Union[int, float]:
        """
        Validate numeric parameter within range boundaries.

        Extracted from query_entries.py relevance_threshold validation
        and rotate_log.py parameter validation.

        Args:
            value: Value to validate
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            param_name: Parameter name for error messages

        Returns:
            Validated numeric value

        Raises:
            ValueError: If value is out of range
        """
        # Convert string to numeric if needed
        if isinstance(value, str):
            try:
                if '.' in value:
                    value = float(value)
                else:
                    value = int(value)
            except ValueError:
                raise ValueError(f"{param_name} must be numeric, got '{value}'")

        if min_val is not None and value < min_val:
            raise ValueError(f"{param_name} must be >= {min_val}, got {value}")

        if max_val is not None and value > max_val:
            raise ValueError(f"{param_name} must be <= {max_val}, got {value}")

        return value

    def build_response_payload(
        self,
        base_payload: Dict[str, Any],
        **updates
    ) -> Dict[str, Any]:
        """
        Build response payload with safe update pattern.

        Extracted from rotate_log.py pattern for building consistent
        error responses and success payloads.

        Args:
            base_payload: Base response dictionary
            **updates: Key-value pairs to update

        Returns:
            Updated payload dictionary
        """
        payload = base_payload.copy()

        for key, value in updates.items():
            if key == "ok":
                # AND the ok status to preserve False
                payload["ok"] = payload.get("ok", True) and bool(value)
            else:
                payload[key] = value

        return payload

    def apply_response_defaults(
        self,
        payload: Dict[str, Any],
        defaults: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Apply response defaults using setdefault pattern.

        Extracted from rotate_log.py pattern for ensuring consistent
        response structure with default values.

        Args:
            payload: Response payload to update
            defaults: Default values to apply

        Returns:
            Updated payload with defaults applied
        """
        if defaults:
            for key, value in defaults.items():
                payload.setdefault(key, value)

        # Standard response defaults
        payload.setdefault("ok", False)
        payload.setdefault("reminders", [])

        return payload

    def normalize_json_parameter(
        self,
        param: Optional[Union[Dict[str, Any], str]],
        param_name: str = "parameter"
    ) -> Optional[Dict[str, Any]]:
        """
        Normalize JSON-serialized parameter using robust parsing.

        Extracted from append_entry.py metadata parsing and
        rotate_log.py custom_metadata parsing.

        Args:
            param: Parameter value (dict or JSON string)
            param_name: Parameter name for error messages

        Returns:
            Normalized dict or None

        Raises:
            ValueError: If parameter is invalid JSON
        """
        if not param:
            return None

        # If already a dict, return as-is
        if isinstance(param, dict):
            return param

        # If string, try to parse as JSON
        if isinstance(param, str):
            try:
                parsed = json.loads(param)
                if isinstance(parsed, dict):
                    return parsed
                else:
                    raise ValueError(f"{param_name} must be a JSON object, got {type(parsed).__name__}")
            except json.JSONDecodeError as e:
                raise ValueError(f"{param_name} contains invalid JSON: {e}")

        raise ValueError(f"{param_name} must be a dict or JSON string, got {type(param).__name__}")

    def create_template_context(
        self,
        project_name: str,
        author: Optional[str] = None,
        **additional_context
    ) -> Dict[str, Any]:
        """
        Create template context dictionary with standard fields.

        Extracted from rotate_log.py pattern for generating
        consistent template contexts.

        Args:
            project_name: Project name
            author: Author name (defaults to "Scribe")
            **additional_context: Additional context variables

        Returns:
            Template context dictionary
        """
        context = {
            "project_name": project_name,
            "author": author or "Scribe",
        }
        context.update(additional_context)
        return context

    def load_config_with_cache(
        self,
        config_path: Path,
        default_config: Optional[Dict[str, Any]] = None,
        cache_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Load configuration file with caching support.

        Extracted from log_config.py pattern for cached configuration
        loading with fallback to defaults.

        Args:
            config_path: Path to configuration file
            default_config: Default configuration if file doesn't exist
            cache_key: Optional cache key for LRU caching

        Returns:
            Loaded configuration dictionary
        """
        @lru_cache(maxsize=1)
        def _load_cached():
            if not config_path.exists():
                self.logger.info(f"Creating default config at {config_path}")
                if default_config:
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(config_path, 'w') as f:
                        json.dump(default_config, f, indent=2)
                return default_config or {}

            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
            except (json.JSONDecodeError, IOError) as e:
                self.logger.error(f"Failed to load config from {config_path}: {e}")
                return default_config or {}

        if cache_key:
            return _load_cached()
        else:
            return _load_cached.__wrapped__()

    def validate_and_normalize_list(
        self,
        param: Optional[Union[List[str], str]],
        delimiter: str = ",",
        param_name: str = "parameter"
    ) -> List[str]:
        """
        Validate and normalize list parameter with delimiter splitting.

        Extracted from query_entries.py pattern for handling
        comma-separated parameters and list normalization.

        Args:
            param: Parameter value (list or delimited string)
            delimiter: Delimiter for string splitting
            param_name: Parameter name for error messages

        Returns:
            Normalized list of strings
        """
        if not param:
            return []

        # If already a list, return cleaned version
        if isinstance(param, list):
            return [str(item).strip() for item in param if item is not None]

        # If string, split by delimiter
        if isinstance(param, str):
            if not param.strip():
                return []
            return [item.strip() for item in param.split(delimiter) if item.strip()]

        raise ValueError(f"{param_name} must be a list or delimited string, got {type(param).__name__}")

    def apply_configuration_overrides(
        self,
        base_config: Dict[str, Any],
        overrides: Dict[str, Any],
        allowed_overrides: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Apply configuration overrides with optional allowlist.

        Extracted from settings.py pattern for applying environment
        and runtime configuration overrides.

        Args:
            base_config: Base configuration dictionary
            overrides: Override values to apply
            allowed_overrides: List of keys that can be overridden

        Returns:
            Updated configuration dictionary
        """
        result = base_config.copy()

        for key, value in overrides.items():
            if allowed_overrides:
                # With allowlist: only override existing keys
                if key not in result:
                    continue
                if key not in allowed_overrides:
                    self.logger.warning(f"Ignoring disallowed override: {key}")
                    continue
                result[key] = value
            else:
                # No allowlist: allow both overrides and additions
                result[key] = value

        return result


# Global config manager instance for backward compatibility
_default_config_manager = ConfigManager()

# Convenience functions for common patterns
def apply_parameter_defaults(
    params: Dict[str, Any],
    defaults: Dict[str, Any],
    required_keys: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Apply parameter defaults using global ConfigManager."""
    return _default_config_manager.apply_parameter_defaults(params, defaults, required_keys)


def resolve_fallback_chain(*values: Optional[Any], default: Optional[Any] = None) -> Any:
    """Resolve value using fallback chain with global ConfigManager."""
    return _default_config_manager.resolve_fallback_chain(*values, default=default)


def validate_enum_value(value: str, allowed_values: List[str], param_name: str) -> str:
    """Validate enum parameter with global ConfigManager."""
    return _default_config_manager.validate_enum_value(value, allowed_values, param_name)


def validate_range(
    value: Union[int, float],
    min_val: Optional[Union[int, float]] = None,
    max_val: Optional[Union[int, float]] = None,
    param_name: str = "parameter"
) -> Union[int, float]:
    """Validate numeric parameter range with global ConfigManager."""
    return _default_config_manager.validate_range(value, min_val, max_val, param_name)


def build_response_payload(base_payload: Dict[str, Any], **updates) -> Dict[str, Any]:
    """Build response payload with global ConfigManager."""
    return _default_config_manager.build_response_payload(base_payload, **updates)


def apply_response_defaults(payload: Dict[str, Any], defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Apply response defaults with global ConfigManager."""
    return _default_config_manager.apply_response_defaults(payload, defaults)