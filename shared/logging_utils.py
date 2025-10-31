"""Shared logging utilities for Scribe MCP tools.

These helpers consolidate repeated normalization, project resolution, and
response-building logic that previously lived in multiple tool modules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, MutableMapping, Optional, Sequence, Tuple

from scribe_mcp import reminders

META_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(slots=True)
class LoggingContext:
    """Resolved context information required by most logging tools."""

    tool_name: str
    project: Optional[Dict[str, Any]]
    recent_projects: List[str]
    state_snapshot: Dict[str, Any]
    reminders: List[Dict[str, Any]]
    agent_id: Optional[str] = None


class ProjectResolutionError(RuntimeError):
    """Raised when a project is required but cannot be resolved."""

    def __init__(self, message: str, recent_projects: Optional[Sequence[str]] = None) -> None:
        super().__init__(message)
        self.recent_projects = list(recent_projects or [])


async def resolve_logging_context(
    *,
    tool_name: str,
    server_module,
    agent_id: Optional[str] = None,
    explicit_project: Optional[str] = None,
    require_project: bool = True,
    state_snapshot: Optional[Dict[str, Any]] = None,
) -> LoggingContext:
    """Resolve the active project and reminders for logging tools.

    Args:
        tool_name: Name of the invoking tool (used for reminders + logging).
        server_module: Reference to ``scribe_mcp.server`` module (provides state).
        agent_id: Optional agent identifier for agent-scoped project resolution.
        explicit_project: Optional project name override (as used by query tools).
        require_project: If True, raise ``ProjectResolutionError`` when no project found.
        state_snapshot: Optional state returned from ``state_manager.record_tool`` to avoid
            duplicate recording. When omitted the helper will record the tool automatically.
    """
    if state_snapshot is None:
        state_snapshot = await server_module.state_manager.record_tool(tool_name)

    project: Optional[Dict[str, Any]] = None
    recent_projects: List[str] = []

    # Primary path: agent-specific context if an agent_id is available.
    if agent_id:
        from scribe_mcp.tools.agent_project_utils import get_agent_project_data  # Imported lazily to avoid circular import.

        project, recent_projects = await get_agent_project_data(agent_id)

    # Fallback to explicit project request (e.g., query_entries search scopes).
    if not project and explicit_project:
        from scribe_mcp.tools.project_utils import load_project_config  # Lazy import.

        project = load_project_config(explicit_project)
        if project:
            # Maintain recent projects ordering with requested name first.
            recent_projects = [project["name"]]

    # Final fallback: use the state's active project snapshot.
    if not project:
        from scribe_mcp.tools.project_utils import load_active_project, load_project_config  # Lazy import.

        active_project, active_name, recent = await load_active_project(server_module.state_manager)
        project = active_project
        if recent_projects:
            # Ensure active project recents are appended without duplicates.
            for name in recent:
                if name not in recent_projects:
                    recent_projects.append(name)
        else:
            recent_projects = list(recent)
        if not project and active_name:
            # When an explicit project was requested but not found, attempt config lookup.
            project = load_project_config(active_name)

    if not project and require_project:
        raise ProjectResolutionError(
            "No project configured. Invoke set_project before using this tool.",
            recent_projects,
        )

    reminders_payload: List[Dict[str, Any]] = []
    if project:
        try:
            reminders_payload = await reminders.get_reminders(
                project,
                tool_name=tool_name,
                state=state_snapshot,
            )
        except Exception:
            # Reminders should never block tool execution; ignore failures.
            reminders_payload = []

    return LoggingContext(
        tool_name=tool_name,
        project=project,
        recent_projects=recent_projects,
        state_snapshot=state_snapshot,
        reminders=reminders_payload,
        agent_id=agent_id,
    )


def normalize_metadata(
    meta: Any,
    *,
    allow_pair_strings: bool = True,
) -> Tuple[Tuple[str, str], ...]:
    """Normalise metadata inputs into the append_entry tuple-of-tuples format."""
    if meta is None or meta == {}:
        return ()

    # Use shared parameter normalization utilities when possible.
    if isinstance(meta, str):
        parsed = _try_parse_json_like(meta)
        if isinstance(parsed, dict):
            meta = parsed
        elif isinstance(parsed, list):
            try:
                meta = dict(parsed)  # type: ignore[arg-type]
            except Exception:
                return (("parse_error", "Expected dict when decoding JSON metadata list"),)
        else:
            return _legacy_metadata_pairs(meta, allow_pair_strings)

    if isinstance(meta, tuple):
        # Allow callers to provide the canonical tuple format already.
        try:
            return tuple((str(k), str(v)) for k, v in meta)
        except Exception:
            return (("meta_error", "Invalid metadata tuple"),)

    if not isinstance(meta, dict):
        return (("parse_error", f"Expected dict or JSON string, got {type(meta).__name__}"),)

    try:
        normalised = []
        for key, value in sorted(meta.items()):
            normalised.append((_sanitize_meta_key(str(key)), _stringify(value)))
        return tuple(normalised)
    except Exception as exc:  # pragma: no cover - defensive catch for unknown edge cases
        return (("meta_error", str(exc)),)
def _try_parse_json_like(value: str) -> Optional[Any]:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _legacy_metadata_pairs(value: str, allow_pair_strings: bool) -> Tuple[Tuple[str, str], ...]:
    if not allow_pair_strings:
        return (("message", value),)

    if "=" in value:
        delimiter = "," if "," in value else " "
        pairs: List[Tuple[str, str]] = []
        for token in value.split(delimiter):
            token = token.strip()
            if not token:
                continue
            if "=" in token:
                key, raw = token.split("=", 1)
                pairs.append((_sanitize_meta_key(key.strip()), _clean_meta_value(raw.strip())))
            else:
                pairs.append(("message", _clean_meta_value(token)))
        if pairs:
            return tuple(pairs)
    return (("message", value),)


def normalize_meta_filters(
    meta_filters: Any,
) -> Tuple[Dict[str, str], Optional[str]]:
    """Normalize metadata filters used by query-style tools."""
    if not meta_filters:
        return {}, None

    if isinstance(meta_filters, str):
        parsed = _try_parse_json_like(meta_filters)
        if isinstance(parsed, dict):
            meta_filters = parsed
        else:
            return {}, "Invalid JSON in meta filters."

    if not isinstance(meta_filters, dict):
        return {}, "Meta filters must be a dictionary."

    normalised: Dict[str, str] = {}
    for key, value in meta_filters.items():
        if key is None:
            return {}, "Meta filter keys cannot be null."
        key_str = str(key).strip()
        if not key_str:
            return {}, "Meta filter keys cannot be empty."
        if not META_KEY_PATTERN.match(key_str):
            return {}, f"Meta filter key '{key}' contains unsupported characters."
        normalised[key_str] = str(value)
    return normalised, None


def clean_list(
    values: Any,
    *,
    coerce_lower: bool = True,
) -> List[str]:
    """Clean list-like input while supporting JSON/string payloads."""
    if values is None or values == []:
        return []

    items: List[str]
    if isinstance(values, str):
        parsed = _try_parse_json_like(values)
        if isinstance(parsed, list):
            values = parsed
        else:
            values = [values]

    if isinstance(values, list):
        items = values
    elif isinstance(values, tuple):
        items = list(values)
    else:
        items = [values]

    cleaned: List[str] = []
    seen = set()
    for entry in items:
        text = str(entry).strip()
        if not text:
            continue
        value = text.lower() if coerce_lower else text
        if value not in seen:
            cleaned.append(value)
            seen.add(value)
    return cleaned


def resolve_log_definition(
    project: Dict[str, Any],
    log_type: str,
    *,
    cache: Optional[MutableMapping[str, Tuple[Path, Dict[str, Any]]]] = None,
) -> Tuple[Path, Dict[str, Any]]:
    """Return the log file path and definition for a given project + log type."""
    from scribe_mcp.config import log_config as log_config_module  # Lazy import.

    log_key = (log_type or "progress").lower()
    if cache is not None and log_key in cache:
        return cache[log_key]

    definition = log_config_module.get_log_definition(log_key)
    path = log_config_module.resolve_log_path(project, definition)

    if cache is not None:
        cache[log_key] = (path, definition)

    return path, definition


def compose_log_line(
    *,
    emoji: str,
    timestamp: str,
    agent: str,
    project_name: str,
    message: str,
    meta_pairs: Tuple[Tuple[str, str], ...],
    entry_id: Optional[str] = None,
) -> str:
    """Compose a formatted log line with metadata pairs."""
    segments = [
        f"[{emoji}]",
        f"[{timestamp}]",
        f"[Agent: {agent}]",
        f"[Project: {project_name}]",
    ]

    if entry_id:
        segments.append(f"[ID: {entry_id}]")

    segments.append(message)
    base = " ".join(segments)
    if meta_pairs:
        meta_text = "; ".join(f"{key}={value}" for key, value in meta_pairs)
        return f"{base} | {meta_text}"
    return base


def ensure_metadata_requirements(
    definition: Dict[str, Any],
    meta_payload: Dict[str, Any],
) -> Optional[str]:
    """Validate metadata requirements defined in log configuration."""
    required = definition.get("metadata_requirements") or []
    missing = [key for key in required if key not in meta_payload]
    if missing:
        return f"Missing metadata for log entry: {', '.join(missing)}"
    return None


def default_status_emoji(
    *,
    explicit: Optional[str],
    status: Optional[str],
    project: Dict[str, Any],
) -> str:
    """Resolve the emoji that should prefix a log entry."""
    from scribe_mcp.tools.constants import STATUS_EMOJI  # Lazy import.

    if explicit:
        return explicit
    if status:
        emoji = STATUS_EMOJI.get(status) or STATUS_EMOJI.get(status.lower())
        if emoji:
            return emoji
    defaults = project.get("defaults") or {}
    return defaults.get("emoji") or STATUS_EMOJI["info"]


def _sanitize_meta_key(value: str) -> str:
    cleaned = value.replace(" ", "_").replace("|", "").strip()
    return cleaned or "meta_key"


def _clean_meta_value(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ").replace("|", " ")


def _stringify(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)):
        return _clean_meta_value(str(value))
    return _clean_meta_value(json.dumps(value, sort_keys=True))
