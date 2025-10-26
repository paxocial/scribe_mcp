"""Advanced querying for progress log entries."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.constants import STATUS_EMOJI
from scribe_mcp.tools.project_utils import load_active_project, load_project_config
from scribe_mcp.utils.logs import parse_log_line, read_all_lines
from scribe_mcp.utils.search import message_matches
from scribe_mcp.utils.time import coerce_range_boundary
from scribe_mcp import reminders

VALID_MESSAGE_MODES = {"substring", "regex"}
META_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


@app.tool()
async def query_entries(
    project: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    message: Optional[str] = None,
    message_mode: str = "substring",
    case_sensitive: bool = False,
    emoji: Optional[List[str]] = None,
    status: Optional[List[str]] = None,
    agents: Optional[List[str]] = None,
    meta_filters: Optional[Dict[str, Any]] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Search the project log with flexible filters."""
    state_snapshot = await server_module.state_manager.record_tool("query_entries")
    limit = max(1, min(limit, 500))
    message_mode = (message_mode or "substring").lower()
    if message_mode not in VALID_MESSAGE_MODES:
        return {"ok": False, "error": f"Unsupported message_mode '{message_mode}'."}

    if message and message_mode == "regex":
        try:
            re.compile(message)
        except re.error as exc:
            return {"ok": False, "error": f"Invalid regex for message filter: {exc}"}

    normalised_emoji = _resolve_emojis(emoji, status)
    meta_normalised, meta_error = _normalise_meta_filters(meta_filters)
    if meta_error:
        return {"ok": False, "error": meta_error}

    start_bound, start_error = _normalise_boundary(start, end=False)
    if start_error:
        return {"ok": False, "error": start_error}
    end_bound, end_error = _normalise_boundary(end, end=True)
    if end_error:
        return {"ok": False, "error": end_error}

    project_data, active_name, recent = await _resolve_project(project)
    reminders_payload: List[Dict[str, Any]] = []
    if not project_data:
        return {
            "ok": False,
            "error": f"Project '{project or active_name}' is not configured.",
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }

    backend = server_module.storage_backend
    if backend:
        record = await backend.fetch_project(project_data["name"])
        if not record:
            record = await backend.upsert_project(
                name=project_data["name"],
                repo_root=project_data["root"],
                progress_log_path=project_data["progress_log"],
            )
        rows = await backend.query_entries(
            project=record,
            limit=limit,
            start=start_bound.isoformat() if start_bound else None,
            end=end_bound.isoformat() if end_bound else None,
            agents=_clean_list(agents),
            emojis=normalised_emoji or None,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            meta_filters=meta_normalised or None,
        )
        reminders_payload = await reminders.get_reminders(
            project_data,
            tool_name="query_entries",
            state=state_snapshot,
        )
        return {
            "ok": True,
            "entries": rows,
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }

    return {
        "ok": True,
        "entries": await _query_file(
            project_data,
            limit=limit,
            start=start_bound,
            end=end_bound,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            agents=_clean_list(agents),
            emojis=normalised_emoji or None,
            meta_filters=meta_normalised or None,
        ),
        "recent_projects": list(recent),
        "reminders": await reminders.get_reminders(
            project_data,
            tool_name="query_entries",
            state=state_snapshot,
        ),
    }


async def _resolve_project(
    project_name: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Tuple[str, ...]]:
    if not project_name:
        return await load_active_project(server_module.state_manager)

    state = await server_module.state_manager.load()
    project = state.get_project(project_name)
    if project:
        return project, project_name, tuple(state.recent_projects)

    config = load_project_config(project_name)
    return config, project_name, tuple(state.recent_projects)


async def _query_file(
    project: Dict[str, Any],
    *,
    limit: int,
    start: Optional[datetime],
    end: Optional[datetime],
    message: Optional[str],
    message_mode: str,
    case_sensitive: bool,
    agents: Optional[List[str]],
    emojis: Optional[List[str]],
    meta_filters: Optional[Dict[str, str]],
) -> List[Dict[str, Any]]:
    path = Path(project["progress_log"])
    lines = await read_all_lines(path)
    results: List[Dict[str, Any]] = []

    def within_bounds(ts_str: Optional[str]) -> bool:
        if not ts_str:
            return False
        parsed = coerce_range_boundary(ts_str, end=False)
        if not parsed:
            return False
        if start and parsed < start:
            return False
        if end and parsed > end:
            return False
        return True

    agent_set = set(agents or [])
    emoji_set = set(emojis or [])

    for line in reversed(lines):
        parsed = parse_log_line(line)
        if not parsed:
            continue
        if (start or end) and not within_bounds(parsed.get("ts")):
            continue
        if agent_set and parsed.get("agent") not in agent_set:
            continue
        if emoji_set and parsed.get("emoji") not in emoji_set:
            continue
        if meta_filters and not _meta_matches(parsed.get("meta") or {}, meta_filters):
            continue
        if not message_matches(
            parsed.get("message"),
            message,
            mode=message_mode,
            case_sensitive=case_sensitive,
        ):
            continue
        results.append(parsed)
        if len(results) >= limit:
            break
    return results


def _resolve_emojis(
    emojis: Optional[List[str]],
    statuses: Optional[List[str]],
) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in emojis or []:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    for status in statuses or []:
        if not status:
            continue
        emoji = STATUS_EMOJI.get(status, STATUS_EMOJI.get(status.lower()))
        if not emoji:
            normalized = status.lower()
            emoji = STATUS_EMOJI.get(normalized)
        if emoji and emoji not in seen:
            result.append(emoji)
            seen.add(emoji)
    return result


def _clean_list(items: Optional[List[str]]) -> List[str]:
    if not items:
        return []
    return [item for item in (entry.strip() for entry in items) if item]


def _normalise_meta_filters(
    meta_filters: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, str], Optional[str]]:
    if not meta_filters:
        return {}, None
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


def _normalise_boundary(value: Optional[str], *, end: bool) -> Tuple[Optional[datetime], Optional[str]]:
    if value is None:
        return None, None
    parsed = coerce_range_boundary(value, end=end)
    if parsed is None:
        return None, f"Unable to parse timestamp '{value}'. Expected ISO8601 or 'YYYY-MM-DD HH:MM:SS UTC'."
    return parsed, None


def _meta_matches(
    entry_meta: Dict[str, str],
    filters: Dict[str, str],
) -> bool:
    for key, expected in filters.items():
        if entry_meta.get(key) != expected:
            return False
    return True
