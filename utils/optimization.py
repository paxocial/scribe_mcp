#!/usr/bin/env python3
"""
Token optimization utilities and configured instances.

Provides centralized access to response formatter and token estimator
with configuration-driven defaults.
"""

from typing import Optional

from .response import ResponseFormatter, default_formatter as _default_formatter
from .tokens import TokenEstimator, token_estimator as _default_token_estimator


def get_response_formatter(
    token_warning_threshold: Optional[int] = None,
    compact_default_fields: Optional[list] = None
) -> ResponseFormatter:
    """
    Get a configured ResponseFormatter instance.

    Args:
        token_warning_threshold: Override default token warning threshold
        compact_default_fields: Override default compact mode fields

    Returns:
        Configured ResponseFormatter instance
    """
    # Import settings lazily to avoid circular imports
    try:
        from ..config.settings import settings
        threshold = token_warning_threshold or settings.token_warning_threshold
        fields = compact_default_fields or settings.default_field_selection
    except ImportError:
        # Fallback to defaults if settings not available
        threshold = token_warning_threshold or 4000
        fields = compact_default_fields or ["id", "message", "timestamp", "emoji", "agent"]

    formatter = ResponseFormatter(token_warning_threshold=threshold)
    if fields:
        formatter.COMPACT_DEFAULT_FIELDS = fields

    return formatter


def get_token_estimator(
    model: Optional[str] = None,
    daily_limit: Optional[int] = None,
    operation_limit: Optional[int] = None
) -> TokenEstimator:
    """
    Get a configured TokenEstimator instance.

    Args:
        model: Override default tokenizer model
        daily_limit: Override default daily token limit
        operation_limit: Override default operation token limit

    Returns:
        Configured TokenEstimator instance
    """
    # Import settings lazily to avoid circular imports
    try:
        from ..config.settings import settings
        tokenizer_model = model or settings.tokenizer_model
        daily = daily_limit or settings.token_daily_limit
        operation = operation_limit or settings.token_operation_limit
    except ImportError:
        # Fallback to defaults if settings not available
        tokenizer_model = model or "gpt-4"
        daily = daily_limit or 100000
        operation = operation_limit or 8000

    return TokenEstimator(
        model=tokenizer_model,
        daily_limit=daily,
        operation_limit=operation
    )


# Global configured instances (lazy-loaded)
_configured_formatter: Optional[ResponseFormatter] = None
_configured_token_estimator: Optional[TokenEstimator] = None


def get_configured_response_formatter() -> ResponseFormatter:
    """Get the globally configured ResponseFormatter instance."""
    global _configured_formatter
    if _configured_formatter is None:
        _configured_formatter = get_response_formatter()
    return _configured_formatter


def get_configured_token_estimator() -> TokenEstimator:
    """Get the globally configured TokenEstimator instance."""
    global _configured_token_estimator
    if _configured_token_estimator is None:
        _configured_token_estimator = get_token_estimator()
    return _configured_token_estimator


def reset_configured_instances():
    """Reset global configured instances (useful for testing)."""
    global _configured_formatter, _configured_token_estimator
    _configured_formatter = None
    _configured_token_estimator = None


# Export the configured instances for backward compatibility
configured_formatter = get_configured_response_formatter()
configured_token_estimator = get_configured_token_estimator()