#!/usr/bin/env python3
"""Lightweight probe runner for Scribe MCP tools.

Inspired by council_probe, this script lets you call any registered Scribe tool
with explicit payloads (no inline python hacks or MCP reloads). It is intended
for manual/interactive testing and quick smoke runs of individual tools.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

# Ensure imports work regardless of cwd.
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

# Keep Scribe paths predictable for probes (no writes to ~/.scribe unless requested).
os.environ.setdefault("SCRIBE_ROOT", str(REPO_ROOT))
os.environ.setdefault("SCRIBE_STATE_PATH", str(REPO_ROOT / "tmp_state_probe.json"))
os.environ.setdefault("PYTHONPATH", os.pathsep.join([str(REPO_ROOT.parent), os.environ.get("PYTHONPATH", "")]))

# Tool imports
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.tools.delete_project import delete_project
from scribe_mcp.tools.generate_doc_templates import generate_doc_templates
from scribe_mcp.tools.get_project import get_project
from scribe_mcp.tools.list_projects import list_projects
from scribe_mcp.tools.manage_docs import manage_docs
from scribe_mcp.tools.query_entries import query_entries
from scribe_mcp.tools.read_recent import read_recent
from scribe_mcp.tools.rotate_log import rotate_log
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.tools.vector_search import vector_search


# Optional rich formatting
try:
    from rich import print as rprint
    from rich.panel import Panel
except Exception:  # pragma: no cover - rich might be unavailable
    rprint = print
    Panel = None  # type: ignore


ToolFn = Callable[..., Any]


TOOL_RUNNERS: dict[str, ToolFn] = {
    "set_project": set_project,
    "get_project": get_project,
    "list_projects": list_projects,
    "append_entry": append_entry,
    "query_entries": query_entries,
    "read_recent": read_recent,
    "rotate_log": rotate_log,
    "manage_docs": manage_docs,
    "generate_doc_templates": generate_doc_templates,
    "delete_project": delete_project,
    "vector_search": vector_search,
}


def _json_or_str(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    try:
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    return None


def _parse_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_payload_file(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    payload_path = Path(path)
    if not payload_path.exists():
        raise FileNotFoundError(f"Payload file not found: {payload_path}")
    with payload_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("Payload file must contain a JSON object.")
        return data


def _build_payload(tool: str, args: "ProbeArgs") -> Dict[str, Any]:
    """Construct a best-effort payload for the requested tool using CLI args."""
    if args.payload:
        return dict(args.payload)

    # Per-tool defaults with sensible knobs for manual overrides.
    if tool == "set_project":
        payload: Dict[str, Any] = {
            "name": args.project,
        }
        if args.root:
            payload["root"] = args.root
        if args.defaults:
            payload["defaults"] = args.defaults
        return payload

    if tool == "append_entry":
        meta = _json_or_str(args.meta) or {}
        payload = {
            "message": args.message or "Probe entry",
            "status": args.status,
            "emoji": args.emoji,
            "agent": args.agent,
            "meta": meta,
            "log_type": args.log_type,
            "project": args.project,
        }
        return payload

    if tool == "query_entries":
        payload = {
            "project": args.project,
            "message": args.message,
            "limit": args.limit,
            "page": args.page,
            "page_size": args.page_size,
            "search_scope": args.search_scope,
            "document_types": _parse_list(args.document_types),
            "include_metadata": not args.compact,
            "compact": args.compact,
        }
        return payload

    if tool == "read_recent":
        return {
            "project": args.project,
            "n": args.limit,
            "compact": args.compact,
            "include_metadata": not args.compact,
        }

    if tool == "rotate_log":
        return {
            "project": args.project,
            "log_type": args.log_type or "progress",
            "confirm": args.confirm_rotate,
            "dry_run": args.dry_run,
        }

    if tool == "manage_docs":
        metadata = _json_or_str(args.meta) or {}
        return {
            "action": args.doc_action,
            "doc": args.doc,
            "section": args.section,
            "content": args.doc_content,
            "template": args.template,
            "metadata": metadata,
            "dry_run": args.dry_run,
            "doc_name": args.doc_name,
            "target_dir": args.target_dir,
            "project": args.project,
        }

    if tool == "generate_doc_templates":
        return {"project": args.project, "overwrite": False}

    if tool == "delete_project":
        return {"name": args.project, "mode": "archive", "confirm": False}

    if tool == "vector_search":
        return {
            "project": args.project,
            "query": args.message or "test query",
            "limit": args.limit or 5,
        }

    if tool == "get_project":
        return {}

    if tool == "list_projects":
        return {}

    return {}


async def _run_tool(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    runner = TOOL_RUNNERS.get(name)
    if runner is None:
        raise ValueError(f"Unknown tool: {name}")
    result = runner(**payload)
    if asyncio.iscoroutine(result):
        return await result  # type: ignore[return-value]
    return result  # type: ignore[return-value]


def _print(title: str, payload: Dict[str, Any]) -> None:
    if Panel:
        rprint(Panel(json.dumps(payload, indent=2, ensure_ascii=False), title=title, expand=False))
    else:
        rprint(f"\n=== {title} ===\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n")


@dataclass
class ProbeArgs:
    tools: Iterable[str]
    project: str
    message: Optional[str]
    status: str
    emoji: str
    agent: str
    meta: Optional[str]
    log_type: Optional[str]
    limit: Optional[int]
    page: int
    page_size: int
    search_scope: str
    document_types: Optional[str]
    compact: bool
    confirm_rotate: bool
    dry_run: bool
    doc_action: str
    doc: str
    section: Optional[str]
    doc_content: Optional[str]
    template: Optional[str]
    doc_name: Optional[str]
    target_dir: Optional[str]
    root: Optional[str]
    defaults: Optional[Dict[str, Any]]
    payload: Optional[Dict[str, Any]]


def parse_args(argv: list[str]) -> ProbeArgs:
    parser = argparse.ArgumentParser(description="Scribe MCP probe runner")
    parser.add_argument(
        "--tools",
        default="set_project,query_entries",
        help="Comma-separated list of tools to invoke (e.g., set_project,append_entry,query_entries,manage_docs).",
    )
    parser.add_argument("--project", default="mcp_connection_test")
    parser.add_argument("--message", help="Message/query text for append_entry/query_entries/vector_search.")
    parser.add_argument("--status", default="info", help="Status for append_entry.")
    parser.add_argument("--emoji", default="🧪", help="Emoji for append_entry.")
    parser.add_argument("--agent", default="ScribeProbe", help="Agent name for append_entry.")
    parser.add_argument("--meta", help="JSON metadata string for append_entry/manage_docs.")
    parser.add_argument("--log-type", help="Log type for append_entry/rotate_log (default progress).")
    parser.add_argument("--limit", type=int, help="Limit for query_entries/read_recent/vector_search.")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument(
        "--search-scope",
        default="project",
        help="Search scope for query_entries (project|global|all_projects|research|bugs|all).",
    )
    parser.add_argument("--document-types", help="Comma-separated document types for query_entries.")
    parser.add_argument("--compact", action="store_true", help="Use compact response for query_entries/read_recent.")
    parser.add_argument("--confirm-rotate", action="store_true", help="Set confirm=True for rotate_log.")
    parser.add_argument("--dry-run", action="store_true", help="Enable dry_run for rotate_log/manage_docs.")
    parser.add_argument("--doc-action", default="status_update", help="manage_docs action.")
    parser.add_argument("--doc", default="architecture", help="manage_docs doc type.")
    parser.add_argument("--section", help="manage_docs target section.")
    parser.add_argument("--doc-content", help="manage_docs content.")
    parser.add_argument("--template", help="manage_docs template name.")
    parser.add_argument("--doc-name", help="manage_docs doc_name override.")
    parser.add_argument("--target-dir", help="manage_docs target_dir override.")
    parser.add_argument("--root", help="Root override for set_project.")
    parser.add_argument("--defaults-json", help="JSON string for set_project defaults.")
    parser.add_argument("--payload-file", help="JSON file with explicit payload (applies to all selected tools).")

    args_ns = parser.parse_args(argv)
    defaults = _json_or_str(args_ns.defaults_json)
    payload = _load_payload_file(args_ns.payload_file)

    tools = [tool.strip() for tool in args_ns.tools.split(",") if tool.strip()]
    return ProbeArgs(
        tools=tools,
        project=args_ns.project,
        message=args_ns.message,
        status=args_ns.status,
        emoji=args_ns.emoji,
        agent=args_ns.agent,
        meta=args_ns.meta,
        log_type=args_ns.log_type,
        limit=args_ns.limit,
        page=args_ns.page,
        page_size=args_ns.page_size,
        search_scope=args_ns.search_scope,
        document_types=args_ns.document_types,
        compact=args_ns.compact,
        confirm_rotate=args_ns.confirm_rotate,
        dry_run=args_ns.dry_run,
        doc_action=args_ns.doc_action,
        doc=args_ns.doc,
        section=args_ns.section,
        doc_content=args_ns.doc_content,
        template=args_ns.template,
        doc_name=args_ns.doc_name,
        target_dir=args_ns.target_dir,
        root=args_ns.root,
        defaults=defaults,
        payload=payload,
    )


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])

    results: list[tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    for tool in args.tools:
        payload = _build_payload(tool, args)
        _print(f"Payload: {tool}", payload)
        try:
            result = await _run_tool(tool, payload)
            results.append((tool, payload, result))
        except Exception as exc:  # pragma: no cover - manual probe mode
            results.append((tool, payload, {"ok": False, "error": str(exc)}))

    for tool, payload, result in results:
        _print(f"Result: {tool}", result if isinstance(result, dict) else {"result": result})


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
