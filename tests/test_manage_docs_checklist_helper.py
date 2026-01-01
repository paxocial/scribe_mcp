from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "checklist_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    checklist_path = docs_dir / "CHECKLIST.md"
    checklist_path.write_text(
        "\n".join(
            [
                "# Checklist",
                "- [ ] Item A",
                "- [x] Item B",
                "- [ ] Item C",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Arch\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    return {
        "name": "Checklist Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(checklist_path),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
        "defaults": {"agent": "QA Bot"},
    }


@pytest.mark.asyncio
async def test_list_checklist_items_filters_exact_match(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    original_state_manager = server_module.state_manager
    original_storage_backend = server_module.storage_backend
    server_module.state_manager = state_manager
    server_module.storage_backend = None

    try:
        result = await manage_docs(
            action="list_checklist_items",
            doc="checklist",
            metadata={"text": "Item B"},
            dry_run=True,
        )
        assert result.get("ok")
        matches = result.get("matches", [])
        assert len(matches) == 1
        assert matches[0]["text"] == "Item B"
        assert matches[0]["status"] == "checked"
        assert matches[0]["start_line"] == matches[0]["end_line"]
    finally:
        server_module.state_manager = original_state_manager
        server_module.storage_backend = original_storage_backend


@pytest.mark.asyncio
async def test_list_checklist_items_case_insensitive(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    original_state_manager = server_module.state_manager
    original_storage_backend = server_module.storage_backend
    server_module.state_manager = state_manager
    server_module.storage_backend = None

    try:
        result = await manage_docs(
            action="list_checklist_items",
            doc="checklist",
            metadata={"text": "item c", "case_sensitive": False},
            dry_run=True,
        )
        assert result.get("ok")
        matches = result.get("matches", [])
        assert len(matches) == 1
        assert matches[0]["text"] == "Item C"
    finally:
        server_module.state_manager = original_state_manager
        server_module.storage_backend = original_storage_backend


@pytest.mark.asyncio
async def test_list_checklist_items_requires_match(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    original_state_manager = server_module.state_manager
    original_storage_backend = server_module.storage_backend
    server_module.state_manager = state_manager
    server_module.storage_backend = None

    try:
        result = await manage_docs(
            action="list_checklist_items",
            doc="checklist",
            metadata={"text": "Missing", "require_match": True},
            dry_run=True,
        )
        assert not result.get("ok")
        assert "No checklist items matched" in result.get("error", "")
    finally:
        server_module.state_manager = original_state_manager
        server_module.storage_backend = original_storage_backend


@pytest.mark.asyncio
async def test_list_checklist_items_body_line_offset(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    checklist_path = Path(project["docs"]["checklist"])
    checklist_path.write_text(
        "\n".join(
            [
                "---",
                "id: checklist-frontmatter",
                "title: \"Checklist\"",
                "doc_type: checklist",
                "---",
                "# Checklist",
                "- [ ] Item A",
                "- [ ] Item B",
                "",
            ]
        ),
        encoding="utf-8",
    )

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    original_state_manager = server_module.state_manager
    original_storage_backend = server_module.storage_backend
    server_module.state_manager = state_manager
    server_module.storage_backend = None

    try:
        result = await manage_docs(
            action="list_checklist_items",
            doc="checklist",
            metadata={"text": "Item A"},
            dry_run=True,
        )
        assert result.get("ok")
        assert result.get("body_line_offset") == 5
        matches = result.get("matches", [])
        assert matches[0]["line"] == 2
        assert matches[0]["file_line"] == 7
    finally:
        server_module.state_manager = original_state_manager
        server_module.storage_backend = original_storage_backend
