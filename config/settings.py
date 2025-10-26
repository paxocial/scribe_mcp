"""Runtime configuration helpers for the Scribe MCP server."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _load_env_json(name: str) -> Dict[str, Any]:
    """Return JSON data from the environment when available."""
    raw = os.environ.get(name)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


@dataclass(frozen=True)
class Settings:
    """Resolved configuration for the MCP server."""

    project_root: Path
    default_state_path: Path
    db_url: Optional[str]
    storage_backend: str
    sqlite_path: Path
    allow_network: bool
    mcp_server_name: str
    extra_options: Dict[str, Any]
    recent_projects_limit: int
    log_rate_limit_count: int
    log_rate_limit_window: int
    log_max_bytes: int
    storage_timeout_seconds: float
    reminder_defaults: Dict[str, Any]
    reminder_idle_minutes: int
    reminder_warmup_minutes: int

    @classmethod
    def load(cls) -> "Settings":
        project_root = Path(os.environ.get("SCRIBE_ROOT", _default_root())).resolve()
        state_path = Path(
            os.environ.get("SCRIBE_STATE_PATH", "~/.scribe/state.json")
        ).expanduser()

        db_url = os.environ.get("SCRIBE_DB_URL")
        storage_backend = os.environ.get("SCRIBE_STORAGE_BACKEND")
        if storage_backend:
            storage_backend = storage_backend.lower()
        else:
            storage_backend = "postgres" if db_url else "sqlite"

        sqlite_path = Path(
            os.environ.get("SCRIBE_SQLITE_PATH", "~/.scribe/scribe.db")
        ).expanduser()

        allow_network = os.environ.get("SCRIBE_ALLOW_NETWORK", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        mcp_server_name = os.environ.get("SCRIBE_MCP_NAME", "scribe.mcp")

        extra_options = _load_env_json("SCRIBE_EXTRA_OPTIONS")
        recent_limit_raw = os.environ.get("SCRIBE_RECENT_PROJECT_LIMIT", "5")
        try:
            recent_limit = max(1, int(recent_limit_raw))
        except ValueError:
            recent_limit = 5

        log_rate_limit_count = max(0, _int_env("SCRIBE_LOG_RATE_LIMIT_COUNT", 60))
        log_rate_limit_window = max(0, _int_env("SCRIBE_LOG_RATE_LIMIT_WINDOW", 60))
        log_max_bytes = max(0, _int_env("SCRIBE_LOG_MAX_BYTES", 512 * 1024))
        storage_timeout_seconds = max(0.1, float(os.environ.get("SCRIBE_STORAGE_TIMEOUT_SECONDS", "5")))
        reminder_defaults = _load_env_json("SCRIBE_REMINDER_DEFAULTS")
        reminder_idle_minutes = max(1, _int_env("SCRIBE_REMINDER_IDLE_MINUTES", 45))
        reminder_warmup_minutes = max(0, _int_env("SCRIBE_REMINDER_WARMUP_MINUTES", 5))

        return cls(
            project_root=project_root,
            default_state_path=state_path,
            db_url=db_url,
            storage_backend=storage_backend,
            sqlite_path=sqlite_path,
            allow_network=allow_network,
            mcp_server_name=mcp_server_name,
            extra_options=extra_options,
            recent_projects_limit=recent_limit,
            log_rate_limit_count=log_rate_limit_count,
            log_rate_limit_window=log_rate_limit_window,
            log_max_bytes=log_max_bytes,
            storage_timeout_seconds=storage_timeout_seconds,
            reminder_defaults=reminder_defaults,
            reminder_idle_minutes=reminder_idle_minutes,
            reminder_warmup_minutes=reminder_warmup_minutes,
        )


def _default_root() -> str:
    """Infer the repository root from this file's location."""
    return str(Path(__file__).resolve().parents[1])


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


settings = Settings.load()
