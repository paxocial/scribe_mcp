"""Reusable mixin for logging-focused MCP tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from scribe_mcp.utils.response import default_formatter

from .logging_utils import (
    LoggingContext,
    ProjectResolutionError,
    ensure_metadata_requirements,
    resolve_logging_context,
)


class LoggingToolMixin:
    """Mixin providing convenience helpers for logging-oriented tools.

    The mixin assumes the concrete tool already provides a ``server_module``
    attribute (as exposed by ``BaseTool``) so it can tap into the shared state
    manager and reminder infrastructure.
    """

    server_module: Any  # Provided by BaseTool subclasses.

    async def prepare_context(
        self,
        *,
        tool_name: str,
        agent_id: Optional[str] = None,
        explicit_project: Optional[str] = None,
        require_project: bool = True,
        state_snapshot: Optional[Dict[str, Any]] = None,
    ) -> LoggingContext:
        """Resolve project, reminders, and state snapshot for a logging tool."""
        if not getattr(self, "server_module", None):
            raise RuntimeError("LoggingToolMixin requires 'server_module' attribute.")

        return await resolve_logging_context(
            tool_name=tool_name,
            server_module=self.server_module,
            agent_id=agent_id,
            explicit_project=explicit_project,
            require_project=require_project,
            state_snapshot=state_snapshot,
        )

    @staticmethod
    def apply_context_payload(
        response: Dict[str, Any],
        context: LoggingContext,
    ) -> Dict[str, Any]:
        """Attach reminders and recent projects to a tool response."""
        response.setdefault("recent_projects", list(context.recent_projects))
        response.setdefault("reminders", list(context.reminders))
        return response

    @staticmethod
    def error_response(
        message: str,
        *,
        suggestion: Optional[str] = None,
        context: Optional[LoggingContext] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate a standardized error payload."""
        payload: Dict[str, Any] = {"ok": False, "error": message}
        if suggestion:
            payload["suggestion"] = suggestion
        if extra:
            payload.update(extra)
        if context:
            LoggingToolMixin.apply_context_payload(payload, context)
        return payload

    @staticmethod
    def success_with_entries(
        *,
        entries,
        context: LoggingContext,
        compact: bool = False,
        fields: Optional[list[str]] = None,
        include_metadata: bool = True,
        pagination: Optional[Dict[str, Any]] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Format entries using the shared default formatter and attach context data."""
        response = default_formatter.format_response(
            entries=entries,
            compact=compact,
            fields=fields,
            include_metadata=include_metadata,
            pagination=pagination,
            extra_data=extra_data or {},
        )
        return LoggingToolMixin.apply_context_payload(response, context)

    @staticmethod
    def validate_metadata_requirements(
        log_definition: Dict[str, Any],
        meta_payload: Dict[str, Any],
    ) -> Optional[str]:
        """Delegate to the shared metadata requirement validator."""
        return ensure_metadata_requirements(log_definition, meta_payload)

    @staticmethod
    def translate_project_error(
        error: ProjectResolutionError,
    ) -> Dict[str, Any]:
        """Convert a ProjectResolutionError into a tool-friendly response dict."""
        payload = {"ok": False, "error": str(error)}
        if error.recent_projects:
            payload["recent_projects"] = list(error.recent_projects)
        return payload
