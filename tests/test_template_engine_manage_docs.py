"""End-to-end tests for Jinja2 template engine and manage_docs integration."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Dict
from uuid import uuid4

import pytest

from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp import server as server_module
from scribe_mcp.state import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.template_engine import Jinja2TemplateEngine
from scribe_mcp.tools.manage_docs import manage_docs


def test_template_engine_renders_builtin_and_custom_templates(tmp_path: Path) -> None:
    """Ensure every built-in document template renders and custom overrides work."""
    repo_root = Path(__file__).resolve().parents[1]
    engine = Jinja2TemplateEngine(project_root=repo_root, project_name="Template QA")

    documents_dir = repo_root / "templates" / "documents"
    templates_rendered = 0
    metadata = {
        "author": "QA Bot",
        "summary": "Automated coverage",
        "problem_statement": {
            "context": "Test harness",
            "goals": ["Exercise templates"],
            "non_goals": [],
            "success_metrics": ["All templates render"],
        },
        "requirements": {
            "functional": ["Render templates"],
            "non_functional": [],
            "assumptions": [],
            "risks": [],
        },
        "architecture_overview": {
            "summary": "Test overview",
            "components": [
                {
                    "name": "engine",
                    "description": "Rendering pipeline",
                    "interfaces": "Inputs/Outputs",
                    "notes": "Core logic",
                }
            ],
            "data_flow": "n/a",
            "external_integrations": "n/a",
        },
        "subsystems": [
            {
                "name": "engine",
                "purpose": "Test",
                "interfaces": "n/a",
                "notes": "n/a",
                "error_handling": "n/a",
            }
        ],
        "directory_structure": "/tmp/project\n├── docs/\n└── src/",
        "data_storage": {},
        "testing_strategy": {},
        "deployment": {},
        "open_questions": [],
        "references": ["Design doc", "ADR-001"],
        "appendix": "Extended data",
        "phases": [
            {
                "name": "Foundation",
                "goal": "Stabilize writer",
                "deliverables": ["Async write", "DB schema"],
                "confidence": 0.95,
                "anchor": "phase_foundation",
                "tasks": ["Add async_atomic_write", "Add verification"],
                "acceptance": [
                    {"label": "No silent failures", "proof": "tests"},
                    {"label": "DB stays in sync", "proof": "fts"},
                ],
                "dependencies": "SQLite",
                "notes": "Baseline reliability",
            },
            {
                "name": "Templates",
                "goal": "Ship Jinja2 engine",
                "deliverables": ["Base templates", "CLI"],
                "confidence": 0.85,
                "anchor": "phase_templates",
                "tasks": ["Add base_document", "Add base_log"],
                "acceptance": [
                    {"label": "All templates render", "proof": "pytest"},
                ],
                "dependencies": "Phase 0",
                "notes": "Introduce inheritance",
            },
        ],
        "milestones": [
            {
                "name": "Phase 0 Complete",
                "target": "2025-10-29",
                "owner": "DevTeam",
                "status": "✅ Complete",
                "evidence": "PROGRESS_LOG#123",
            }
        ],
        "sections": [
            {
                "title": "Documentation Hygiene",
                "anchor": "documentation_hygiene",
                "items": [
                    {"label": "Architecture guide updated", "proof": "log#1"},
                    {"label": "Phase plan current", "proof": "log#2"},
                ],
            },
            {
                "title": "Phase 0",
                "anchor": "phase_0",
                "items": [
                    {"label": "Async bug fixed", "proof": "commit123"},
                ],
            },
        ],
    }

    for template_path in documents_dir.glob("*.md"):
        template_name = f"documents/{template_path.name}"
        rendered = engine.render_template(template_name, metadata=metadata)
        assert "Template QA" in rendered
        assert rendered.strip(), f"{template_name} should not render empty content"
        templates_rendered += 1

    assert templates_rendered > 0, "Expected to render at least one built-in template"

    # Custom project overrides (.scribe/templates) should take precedence
    project_root = tmp_path / "custom_repo"
    (project_root / ".scribe" / "templates").mkdir(parents=True, exist_ok=True)
    custom_template = project_root / ".scribe" / "templates" / "welcome.md"
    custom_template.write_text("# Welcome {{ project_name }} :: {{ metadata.note }}", encoding="utf-8")

    custom_engine = Jinja2TemplateEngine(project_root=project_root, project_name="Custom Project")
    custom_rendered = custom_engine.render_template("welcome.md", metadata={"note": "Rendered"})

    assert "Custom Project :: Rendered" in custom_rendered


@pytest.mark.asyncio
async def test_manage_docs_renders_jinja_content_and_custom_templates(tmp_path: Path) -> None:
    """Verify manage_docs updates sections via inline Jinja content and custom templates."""
    repo_root = Path(__file__).resolve().parents[1]
    test_root = repo_root / "tmp_tests" / f"manage_docs_{uuid4().hex}"
    project_root = test_root
    docs_dir = project_root / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text(
        "# Architecture\n"
        "<!-- ID: problem_statement -->\n"
        "Old problem statement\n\n"
        "<!-- ID: requirements_constraints -->\n"
        "Old requirements section\n",
        encoding="utf-8",
    )

    # Create placeholder files for other doc references
    for name in ("PHASE_PLAN", "CHECKLIST", "PROGRESS_LOG"):
        (docs_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

    project: Dict[str, object] = {
        "name": "Test Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(architecture_path),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
        "defaults": {"agent": "QA Bot"},
    }

    # Replace the problem_statement section using inline Jinja content
    metadata = {"note": "Upgraded via test"}
    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_section",
        section="problem_statement",
        content="**Project:** {{ project_name }} | Note: {{ metadata.note }}",
        template=None,
        metadata=metadata,
        dry_run=False,
    )

    assert change.success
    assert change.verification_passed
    updated_text = architecture_path.read_text(encoding="utf-8")
    assert "**Project:** Test Project | Note: Upgraded via test" in updated_text

    # Append additional content via a custom template stored under .scribe/templates
    custom_templates_dir = project_root / ".scribe" / "templates"
    custom_templates_dir.mkdir(parents=True, exist_ok=True)
    (custom_templates_dir / "summary_block.md").write_text(
        "### Auto Summary\nContext: {{ metadata.context }}\n", encoding="utf-8"
    )

    metadata_append = {"context": "manage_docs+jinja"}
    append_change = await apply_doc_change(
        project,
        doc="architecture",
        action="append",
        section=None,
        content=None,
        template="summary_block",
        metadata=metadata_append,
        dry_run=False,
    )

    assert append_change.success
    updated_text = architecture_path.read_text(encoding="utf-8")
    assert "### Auto Summary" in updated_text
    assert "Context: manage_docs+jinja" in updated_text

    shutil.rmtree(test_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_special_document_templates_and_agent_card_storage(tmp_path: Path) -> None:
    """Ensure special document creation uses Jinja templates and stores agent metrics."""
    project_name = "TestProject"
    project_root = tmp_path / "project"
    docs_dir = project_root / "docs" / "dev_plans" / project_name
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Seed required doc files
    for name in ("ARCHITECTURE_GUIDE", "PHASE_PLAN", "CHECKLIST", "PROGRESS_LOG"):
        (docs_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

    original_state_manager = server_module.state_manager
    original_storage_backend = server_module.storage_backend

    state_manager = StateManager(path=tmp_path / "state.json")
    storage = SQLiteStorage(tmp_path / "scribe.db")
    await storage.setup()

    server_module.state_manager = state_manager
    server_module.storage_backend = storage

    try:
        project_config = {
            "name": project_name,
            "root": str(project_root),
            "docs_dir": str(docs_dir),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
            "docs": {
                "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
                "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
                "checklist": str(docs_dir / "CHECKLIST.md"),
                "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
            },
            "defaults": {"agent": "QA Bot"},
        }

        await state_manager.set_current_project(project_name, project_config)

        # Dry-run research doc to confirm templated content
        research_result = await manage_docs(
            action="create_research_doc",
            doc="architecture",
            doc_name="architecture_findings",
            metadata={"objective": "Assess coverage"},
            dry_run=True,
        )
        assert research_result["ok"]
        assert "## Executive Summary" in research_result["content"]
        assert "## Research Scope" in research_result["content"]

        # Dry-run bug report to confirm templated content
        bug_result = await manage_docs(
            action="create_bug_report",
            doc="architecture",
            metadata={"category": "backend", "severity": "high"},
            dry_run=True,
        )
        assert bug_result["ok"]
        assert "## Bug Overview" in bug_result["content"]
        assert "## Resolution Plan" in bug_result["content"]

        # Create an agent report card and ensure storage captures metrics
        agent_metadata = {
            "agent_name": "Ai-Dev",
            "stage": "review",
            "overall_grade": "92%",
            "performance_level": "EXCELLENT",
        }
        agent_result = await manage_docs(
            action="create_agent_report_card",
            doc="architecture",
            metadata=agent_metadata,
            dry_run=False,
        )
        assert agent_result["ok"]
        card_path = Path(agent_result["path"])
        assert card_path.exists()
        assert agent_result["document_type"] == "agent_report_card"

        conn = sqlite3.connect(storage._path)
        try:
            card_rows = conn.execute(
                "SELECT agent_name, stage, overall_grade, performance_level, metadata FROM agent_report_cards"
            ).fetchall()
            assert len(card_rows) == 1
            agent_name, stage, overall_grade, performance_level, metadata_json = card_rows[0]
            assert agent_name == "Ai-Dev"
            assert stage == "review"
            assert pytest.approx(overall_grade, rel=1e-6) == 92.0
            assert performance_level == "EXCELLENT"
            assert "Ai-Dev" in metadata_json

            doc_changes = conn.execute(
                "SELECT doc_name FROM doc_changes WHERE doc_name = 'agent_report_card'"
            ).fetchall()
            assert doc_changes, "Expected doc_changes entry for agent report card"

            section_columns = {row[1] for row in conn.execute("PRAGMA table_info(document_sections)").fetchall()}
            assert {"project_root", "file_path", "relative_path"}.issubset(section_columns)

            sync_columns = {row[1] for row in conn.execute("PRAGMA table_info(sync_status)").fetchall()}
            assert "project_root" in sync_columns

            changes_columns = {row[1] for row in conn.execute("PRAGMA table_info(document_changes)").fetchall()}
            assert "project_root" in changes_columns
        finally:
            conn.close()
    finally:
        await storage.close()
        server_module.state_manager = original_state_manager
        server_module.storage_backend = original_storage_backend
