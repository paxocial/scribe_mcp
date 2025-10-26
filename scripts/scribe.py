#!/usr/bin/env python3
"""Utility for appending structured progress log entries."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scribe_mcp.tools.project_utils import slugify_project_name
from scribe_mcp.config.log_config import get_log_definition, resolve_log_path

PROJECTS_DIR = ROOT_DIR / "config" / "projects"
DEFAULT_PROJECT_NAME = os.environ.get("SCRIBE_DEFAULT_PROJECT", "scribe_mcp")

STATUS_EMOJI = {
    "info": "ℹ️",
    "success": "✅",
    "warn": "⚠️",
    "error": "❌",
    "bug": "🐞",
    "plan": "🧭",
}

def load_config(path: Path) -> Dict[str, Any]:
    config = _normalise_config(_read_json(path), ROOT_DIR)
    if not config:
        raise SystemExit(f"Config file is missing required fields: {path}")
    return config


def parse_meta(pairs: Iterable[str]) -> Tuple[Tuple[str, str], ...]:
    extracted = []
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"Meta value must be key=value, received: {pair}")
        key, value = pair.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key:
            raise SystemExit("Meta key cannot be empty.")
        extracted.append((key, value))
    return tuple(extracted)


def format_entry(
    message: str,
    emoji: str,
    agent: Optional[str],
    project_name: Optional[str],
    meta: Tuple[Tuple[str, str], ...],
    timestamp: Optional[str],
) -> str:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if not emoji:
        emoji = "📝"

    segments = [f"[{emoji}]", f"[{timestamp}]"]

    if agent:
        segments.append(f"[Agent: {agent}]")

    if project_name:
        segments.append(f"[Project: {project_name}]")

    entry = " ".join(segments) + f" {message}"

    if meta:
        meta_str = "; ".join(f"{key}={value}" for key, value in meta)
        entry += f" | {meta_str}"

    return entry


def append_log(path: Path, entry: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
        if not entry.endswith("\n"):
            handle.write("\n")


def log_progress(
    message: str,
    *,
    emoji: Optional[str] = None,
    status: Optional[str] = None,
    agent: Optional[str] = None,
    meta: Optional[Mapping[str, Any]] = None,
    config_path: Optional[Path] = None,
    config_data: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None,
    dry_run: bool = False,
    log_type: str = "progress",
) -> str:
    if config_data is None:
        if not config_path:
            raise ValueError("Either config_path or config_data must be provided.")
        config = load_config(config_path)
    else:
        config = config_data

    progress_log = config.get("progress_log")
    if not progress_log:
        raise ValueError("Config file is missing 'progress_log'.")

    project_name = config.get("name") or config.get("project_name")
    defaults = config.get("defaults") or {}
    default_emoji = defaults.get("emoji", config.get("default_emoji", "📝"))
    default_agent = defaults.get("agent", config.get("default_agent"))

    resolved_emoji = emoji
    if not resolved_emoji and status:
        resolved_emoji = STATUS_EMOJI.get(status)
    if not resolved_emoji:
        resolved_emoji = default_emoji
    if not resolved_emoji:
        raise ValueError("Emoji is required; provide emoji/status or set default_emoji.")

    resolved_agent = agent or default_agent

    meta_dict = {}
    if meta:
        meta_dict = {str(key): str(value) for key, value in meta.items()}
    meta_dict.setdefault("log_type", log_type)

    log_definition = get_log_definition(log_type)
    missing = [
        field for field in log_definition.get("metadata_requirements", []) or []
        if field not in meta_dict
    ]
    if missing:
        raise ValueError(f"Missing metadata for log '{log_type}': {', '.join(missing)}")

    meta_pairs: Tuple[Tuple[str, str], ...] = tuple(meta_dict.items())

    entry = format_entry(
        message=message,
        emoji=resolved_emoji,
        agent=resolved_agent,
        project_name=project_name,
        meta=meta_pairs,
        timestamp=timestamp,
    )

    root_dir = config.get("root")
    if root_dir:
        root_path = Path(root_dir)
        if not root_path.is_absolute():
            root_path = (ROOT_DIR / root_path).resolve()
        else:
            root_path = root_path.resolve()
    else:
        root_path = ROOT_DIR

    project_payload = {
        "name": project_name or slugify_project_name(progress_log),
        "root": str(root_path),
        "progress_log": progress_log,
        "docs_dir": config.get("docs_dir"),
    }
    log_path = resolve_log_path(project_payload, log_definition)

    if dry_run:
        return entry

    append_log(log_path, entry)
    return entry


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append a formatted entry to the project progress log."
    )
    parser.add_argument("message", nargs="?", help="Primary log message.")
    status_help = ", ".join(f"{name!r}" for name in STATUS_EMOJI)
    parser.add_argument(
        "-e",
        "--emoji",
        help="Emoji or short indicator to include in the entry.",
    )
    parser.add_argument(
        "-s",
        "--status",
        choices=sorted(STATUS_EMOJI),
        help=f"Named status mapped to an emoji ({status_help}).",
    )
    parser.add_argument(
        "-a",
        "--agent",
        help="Name of the agent or component producing the entry.",
    )
    parser.add_argument(
        "-m",
        "--meta",
        action="append",
        default=[],
        help="Additional metadata as key=value pairs. Option may be repeated.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to project config JSON file.",
    )
    parser.add_argument(
        "--log",
        dest="log_type",
        default="progress",
        help="Log type key defined in config/log_config.json (default: progress).",
    )
    parser.add_argument(
        "-p",
        "--project",
        help="Project config name under config/projects (e.g., 'scribe_mcp').",
    )
    parser.add_argument(
        "-t",
        "--timestamp",
        help="Override timestamp text (default: current UTC time).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the formatted entry without writing to disk.",
    )
    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="List available project configs and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])

    if args.list_projects:
        configs = discover_project_configs()
        if not configs:
            print("No project configs found under config/projects.")
        else:
            for name, info in configs.items():
                print(f"{name}\t{info['progress_log']}")
        return

    if not args.message:
        raise SystemExit("Message is required unless --list-projects is used.")

    if not args.message:
        raise SystemExit("Message is required unless --list-projects is used.")

    config_path: Optional[Path] = args.config
    config_data: Optional[Dict[str, Any]] = None

    if config_path is None:
        if args.project:
            config_path = PROJECTS_DIR / f"{args.project}.json"
        else:
            config_path = PROJECTS_DIR / f"{DEFAULT_PROJECT_NAME}.json"

    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    if args.config is None:
        config_data = _normalise_config(_read_json(config_path), ROOT_DIR)
        if not config_data:
            raise SystemExit(f"Config file is missing required fields: {config_path}")
    else:
        config_data = load_config(config_path)

    meta = parse_meta(args.meta)

    try:
        entry = log_progress(
            message=args.message,
            emoji=args.emoji,
            status=args.status,
            agent=args.agent,
            meta=dict(meta),
            config_path=config_path,
            config_data=config_data,
            timestamp=args.timestamp,
            dry_run=args.dry_run,
            log_type=args.log_type,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if args.dry_run:
        print(entry)
    else:
        project_payload = {
            "name": config_data.get("name"),
            "root": config_data.get("root"),
            "progress_log": config_data.get("progress_log"),
            "docs_dir": config_data.get("docs_dir"),
        }
        log_definition = get_log_definition(args.log_type)
        log_path = resolve_log_path(project_payload, log_definition)
        print(f"Wrote entry to {log_path}:")
        print(entry)


def discover_project_configs() -> Dict[str, Dict[str, Any]]:
    configs: Dict[str, Dict[str, Any]] = {}
    if PROJECTS_DIR.exists():
        for path in sorted(PROJECTS_DIR.glob("*.json")):
            data = _normalise_config(_read_json(path), ROOT_DIR)
            if data:
                configs[data["name"]] = data
    return configs


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _normalise_config(data: Dict[str, Any], base_root: Path) -> Optional[Dict[str, Any]]:
    if not data:
        return None
    name = data.get("name") or data.get("project_name")
    if not name:
        return None

    root_value = data.get("root")
    if root_value:
        root_path = Path(root_value)
        if not root_path.is_absolute():
            root_path = (base_root / root_path).resolve()
        else:
            root_path = root_path.resolve()
    else:
        root_path = base_root

    docs_value = data.get("docs_dir")
    if docs_value:
        docs_path = Path(docs_value)
        if not docs_path.is_absolute():
            docs_path = (root_path / docs_path).resolve()
        else:
            docs_path = docs_path.resolve()
    else:
        slug = slugify_project_name(name)
        docs_path = (root_path / "docs" / "dev_plans" / slug).resolve()

    progress_value = data.get("progress_log")
    if progress_value:
        log_path = Path(progress_value)
        if not log_path.is_absolute():
            log_path = (root_path / log_path).resolve()
        else:
            log_path = log_path.resolve()
    else:
        log_path = docs_path / "PROGRESS_LOG.md"

    defaults_raw = data.get("defaults") or {}
    defaults = {k: v for k, v in defaults_raw.items() if v}

    return {
        "name": name,
        "root": str(root_path),
        "progress_log": str(log_path),
        "docs_dir": str(docs_path),
        "defaults": defaults,
    }


if __name__ == "__main__":
    main()
