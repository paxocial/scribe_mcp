"""Unit tests for shared.logging_utils helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

from scribe_mcp.shared.logging_utils import (
    LoggingContext,
    ProjectResolutionError,
    clean_list,
    compose_log_line,
    default_status_emoji,
    normalize_metadata,
    normalize_meta_filters,
    resolve_log_definition,
    resolve_logging_context,
)


def test_normalize_metadata_with_dict() -> None:
    meta = {"Phase": "Alpha", "count": 10, "details": {"nested": True}}
    normalised = normalize_metadata(meta)

    assert ("Phase", "Alpha") in normalised
    assert ("count", "10") in normalised
    # Nested objects should become sorted JSON, stripped of problematic characters.
    assert any(pair[0] == "details" and pair[1] == '{"nested": true}' for pair in normalised)


def test_normalize_metadata_with_cli_string_pairs() -> None:
    meta = "phase=beta owner=codex"
    normalised = normalize_metadata(meta)

    assert normalised == (("phase", "beta"), ("owner", "codex"))


def test_normalize_metadata_invalid_input() -> None:
    normalised = normalize_metadata(12345)
    assert normalised == (("parse_error", "Expected dict or JSON string, got int"),)


def test_normalize_meta_filters_success() -> None:
    filters, error = normalize_meta_filters({"foo": "bar", "phase": 3})
    assert error is None
    assert filters == {"foo": "bar", "phase": "3"}


def test_normalize_meta_filters_invalid_key() -> None:
    filters, error = normalize_meta_filters({"bad key": "value"})
    assert filters == {}
    assert error == "Meta filter key 'bad key' contains unsupported characters."


def test_clean_list_handles_strings_and_duplicates() -> None:
    result = clean_list(["Alpha", "alpha", "  Beta  "])
    assert result == ["alpha", "beta"]

    result_from_string = clean_list('["Gamma", "Delta"]')
    assert result_from_string == ["gamma", "delta"]


def test_compose_log_line_includes_metadata() -> None:
    line = compose_log_line(
        emoji="✅",
        timestamp="2025-10-31 17:00:00 UTC",
        agent="Scribe",
        project_name="demo",
        message="Task complete",
        meta_pairs=(("phase", "alpha"),),
        entry_id="abc123",
    )
    assert line == "[✅] [2025-10-31 17:00:00 UTC] [Agent: Scribe] [Project: demo] [ID: abc123] Task complete | phase=alpha"


def test_default_status_emoji_prefers_explicit() -> None:
    project = {"defaults": {"emoji": "🛠️"}}
    assert default_status_emoji(explicit="🎯", status=None, project=project) == "🎯"
    assert default_status_emoji(explicit=None, status="success", project=project) == "✅"
    assert default_status_emoji(explicit=None, status=None, project=project) == "🛠️"


def test_resolve_log_definition_uses_cache(tmp_path) -> None:
    project = {
        "name": "demo_project",
        "root": str(tmp_path),
        "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
    }
    cache: Dict[str, Tuple[Path, Dict[str, Any]]] = {}

    path, definition = resolve_log_definition(project, "progress", cache=cache)
    assert path == tmp_path / "PROGRESS_LOG.md"
    assert "path" in definition
    # Second call should hit cache and return same path.
    cached_path, _ = resolve_log_definition(project, "progress", cache=cache)
    assert cached_path == path


@pytest.mark.asyncio
async def test_resolve_logging_context_with_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that agent-scoped project resolution surfaces reminders and recents."""

    recorded_tools: List[str] = []

    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            recorded_tools.append(tool_name)
            return {"tool": tool_name}

        async def load(self) -> Any:
            return SimpleNamespace(current_project=None, recent_projects=[])

    class DummyServerModule:
        state_manager = DummyStateManager()

    async def fake_get_agent_project_data(agent_id: str) -> Tuple[Dict[str, Any], List[str]]:
        assert agent_id == "agent-1"
        project = {
            "name": "demo",
            "progress_log": "/tmp/demo.log",
            "defaults": {"emoji": "ℹ️"},
        }
        return project, ["demo"]

    async def fake_get_reminders(project: Dict[str, Any], tool_name: str, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [{"message": "hi", "tool": tool_name}]

    agent_module = types.ModuleType("scribe_mcp.tools.agent_project_utils")
    agent_module.get_agent_project_data = fake_get_agent_project_data  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.agent_project_utils", agent_module)

    project_module = types.ModuleType("scribe_mcp.tools.project_utils")

    async def fake_load_active_project(state_manager):
        return (None, None, ())

    def fake_load_project_config(name):
        return None

    project_module.load_active_project = fake_load_active_project  # type: ignore[attr-defined]
    project_module.load_project_config = fake_load_project_config  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.project_utils", project_module)

    monkeypatch.setattr("scribe_mcp.shared.logging_utils.reminders.get_reminders", fake_get_reminders)

    context = await resolve_logging_context(
        tool_name="append_entry",
        server_module=DummyServerModule(),
        agent_id="agent-1",
    )

    assert isinstance(context, LoggingContext)
    assert context.project and context.project["name"] == "demo"
    assert context.reminders == [{"message": "hi", "tool": "append_entry"}]
    assert recorded_tools == ["append_entry"]


@pytest.mark.asyncio
async def test_resolve_logging_context_requires_project(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

    class DummyServerModule:
        state_manager = DummyStateManager()

    async def no_project(*args, **kwargs):
        return (None, None, ())


    agent_module = types.ModuleType("scribe_mcp.tools.agent_project_utils")
    agent_module.get_agent_project_data = lambda agent_id: asyncio.sleep(0.0, result=(None, []))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.agent_project_utils", agent_module)

    project_module = types.ModuleType("scribe_mcp.tools.project_utils")
    project_module.load_active_project = no_project  # type: ignore[attr-defined]
    project_module.load_project_config = lambda name: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.project_utils", project_module)

    monkeypatch.setattr("scribe_mcp.shared.logging_utils.reminders.get_reminders", lambda *args, **kwargs: asyncio.sleep(0.0, result=[]))

    with pytest.raises(ProjectResolutionError):
        await resolve_logging_context(
            tool_name="query_entries",
            server_module=DummyServerModule(),
            agent_id=None,
            explicit_project=None,
        )
