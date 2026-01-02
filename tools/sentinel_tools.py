"""Sentinel mode toolset (append_event/open_bug/open_security/link_fix)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.utils.sentinel_logs import append_case_event, append_sentinel_event


def _require_sentinel_context():
    context = server_module.get_execution_context()
    if not context:
        raise ValueError("ExecutionContext missing")
    if context.mode != "sentinel":
        raise ValueError("Sentinel tool called outside sentinel mode")
    return context


@app.tool()
async def append_event(
    event_type: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append a general sentinel event to sentinel.jsonl."""
    context = _require_sentinel_context()
    payload = data if isinstance(data, dict) else {}
    append_sentinel_event(
        context,
        event_type=event_type,
        data=payload,
        log_type="sentinel",
        include_md=True,
    )
    return {"ok": True, "event_type": event_type}


@app.tool()
async def open_bug(
    title: str,
    symptoms: str,
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Open a BUG case with per-day stable ID."""
    context = _require_sentinel_context()
    case_id = append_case_event(
        context,
        kind="BUG",
        event_type="bug_opened",
        data={
            "title": title,
            "symptoms": symptoms,
            "affected_paths": affected_paths or [],
            "landing_status": "proposed",
        },
        include_md=True,
    )
    return {"ok": True, "case_id": case_id}


@app.tool()
async def open_security(
    title: str,
    symptoms: str,
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Open a SECURITY case with per-day stable ID."""
    context = _require_sentinel_context()
    case_id = append_case_event(
        context,
        kind="SEC",
        event_type="security_opened",
        data={
            "title": title,
            "symptoms": symptoms,
            "affected_paths": affected_paths or [],
            "landing_status": "proposed",
        },
        include_md=True,
    )
    return {"ok": True, "case_id": case_id}


@app.tool()
async def link_fix(
    case_id: str,
    execution_id: str,
    artifact_ref: str,
    landing_status: str,
) -> Dict[str, Any]:
    """Link a fix artifact to a BUG/SEC case."""
    context = _require_sentinel_context()
    case_id_upper = case_id.upper()
    if case_id_upper.startswith("BUG-"):
        event_type = "bug_fix_linked"
        kind = "BUG"
    elif case_id_upper.startswith("SEC-"):
        event_type = "security_fix_linked"
        kind = "SEC"
    else:
        return {"ok": False, "error": "case_id must start with BUG- or SEC-"}

    append_case_event(
        context,
        kind=kind,
        event_type=event_type,
        data={
            "case_id": case_id,
            "fix_link": {
                "execution_id": execution_id,
                "artifact_ref": artifact_ref,
            },
            "landing_status": landing_status,
        },
        include_md=True,
    )
    return {"ok": True, "case_id": case_id}
