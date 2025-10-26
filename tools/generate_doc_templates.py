"""Tool for generating documentation scaffolds from templates."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple

from scribe_mcp import reminders, server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.tools.project_utils import slugify_project_name
from scribe_mcp.server import app
from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError
from scribe_mcp.templates import TEMPLATE_FILENAMES, load_templates, substitution_context


OUTPUT_FILENAMES: List[Tuple[str, str]] = [
    ("architecture", "ARCHITECTURE_GUIDE.md"),
    ("phase_plan", "PHASE_PLAN.md"),
    ("checklist", "CHECKLIST.md"),
    ("progress_log", "PROGRESS_LOG.md"),
    ("doc_log", "DOC_LOG.md"),
    ("security_log", "SECURITY_LOG.md"),
    ("bug_log", "BUG_LOG.md"),
]

logger = logging.getLogger(__name__)


@app.tool()
async def generate_doc_templates(
    project_name: str,
    author: str | None = None,
    overwrite: bool = False,
    documents: Iterable[str] | None = None,
    base_dir: str | None = None,
    custom_context: Any = None,
    legacy_fallback: bool = False,
) -> Dict[str, Any]:
    """Render the standard documentation templates for a project."""
    state_snapshot = await server_module.state_manager.record_tool("generate_doc_templates")
    templates: Dict[str, str] = {}
    if legacy_fallback:
        templates = await load_templates()

    # INTELLIGENT PARAMETER HANDLING: Support custom context with bulletproof error recovery
    try:
        if custom_context is not None:
            # If custom_context is provided, use it for enhanced template rendering
            if isinstance(custom_context, dict):
                # Merge with base context
                base_context = substitution_context(project_name, author)
                base_context.update(custom_context)
                context = base_context
            else:
                # Try to convert to dict if it's not already
                context = substitution_context(project_name, author)
                print(f"Warning: custom_context should be a dict, got {type(custom_context).__name__}")
        else:
            context = substitution_context(project_name, author)
    except Exception as e:
        # Graceful fallback if context handling fails
        context = substitution_context(project_name, author)
        print(f"Warning: Error handling custom_context: {e}. Using base context.")

    engine_error: Exception | None = None
    try:
        engine = Jinja2TemplateEngine(
            project_root=settings.project_root,
            project_name=project_name,
            security_mode="sandbox",
        )
    except Exception as exc:  # pragma: no cover - initialization rarely fails
        engine = None
        engine_error = exc
        logger.error("Failed to initialize Jinja2 template engine: %s", exc)

    if engine is None and not legacy_fallback:
        return {
            "ok": False,
            "error": f"Failed to initialize Jinja2 template engine: {engine_error}",
        }

    output_dir = _target_directory(project_name, base_dir)
    await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)

    selected = _select_documents(documents)

    written: List[str] = []
    skipped: List[str] = []
    for key, filename in OUTPUT_FILENAMES:
        if key not in selected:
            continue
        template_name = f"documents/{TEMPLATE_FILENAMES[key]}"
        rendered = None
        metadata_payload = _metadata_for(key, project_name, context)

        if engine:
            try:
                rendered = engine.render_template(template_name, metadata=metadata_payload)
            except TemplateEngineError as template_error:
                logger.warning("Jinja2 rendering failed for %s: %s", template_name, template_error)
                if not legacy_fallback:
                    return {
                        "ok": False,
                        "error": f"Jinja2 rendering failed for {template_name}: {template_error}",
                        "template": template_name,
                    }

        if rendered is None:
            if not legacy_fallback:
                return {
                    "ok": False,
                    "error": f"No rendered output generated for {template_name}",
                    "template": template_name,
                }
            template_body = templates.get(key)
            if not template_body:
                source_name = TEMPLATE_FILENAMES[key]
                return {"ok": False, "error": f"Template missing: {source_name}"}
            rendered = _render_template(template_body, context)
        path = output_dir / filename
        if overwrite or not path.exists():
            await asyncio.to_thread(_write_template, path, rendered, overwrite)
            written.append(str(path))
        else:
            skipped.append(str(path))

    project_stub = {
        "name": project_name,
        "progress_log": str(output_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(output_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(output_dir / "PHASE_PLAN.md"),
            "checklist": str(output_dir / "CHECKLIST.md"),
            "progress_log": str(output_dir / "PROGRESS_LOG.md"),
            "doc_log": str(output_dir / "DOC_LOG.md"),
            "security_log": str(output_dir / "SECURITY_LOG.md"),
            "bug_log": str(output_dir / "BUG_LOG.md"),
        },
    }
    reminders_payload = await reminders.get_reminders(
        project_stub,
        tool_name="generate_doc_templates",
        state=state_snapshot,
    )
    return {
        "ok": True,
        "files": written,
        "skipped": skipped,
        "directory": str(output_dir),
        "reminders": reminders_payload,
    }


def _target_directory(project_name: str, base_dir: str | None) -> Path:
    slug = slugify_project_name(project_name)
    if base_dir:
        return Path(base_dir).resolve() / "docs" / "dev_plans" / slug
    return settings.project_root / "docs" / "dev_plans" / slug


def _render_template(template: str, context: Dict[str, str]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    rendered = re.sub(r"\{\{[^{}]+\}\}", "TBD", rendered)
    return rendered


def _write_template(path: Path, content: str, overwrite: bool) -> None:
    if overwrite and path.exists():
        backup_path = path.with_suffix(path.suffix + ".bak")
        path.replace(backup_path)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(content)


def _select_documents(documents: Iterable[str] | None) -> List[str]:
    if not documents:
        return [key for key, _ in OUTPUT_FILENAMES]
    normalized = {doc.lower() for doc in documents}
    valid = [key for key, _ in OUTPUT_FILENAMES if key in normalized]
    return valid


MetadataBuilder = Callable[[str, Dict[str, str]], Dict[str, Any]]


def _metadata_for(doc_key: str, project_name: str, context: Dict[str, str]) -> Dict[str, Any]:
    builder = METADATA_BUILDERS.get(doc_key)
    if builder:
        return builder(project_name, context)
    return {}


def _architecture_metadata(project_name: str, context: Dict[str, str]) -> Dict[str, Any]:
    project_root = context.get("project_root", "project")
    return {
        "summary": f"Architecture guide for {project_name}.",
        "version": "Draft v0.1",
        "status": "Draft",
        "problem_statement": {
            "context": f"{project_name} needs a reliable documentation system.",
            "goals": [
                "Eliminate silent failures",
                "Improve template flexibility",
            ],
            "non_goals": ["Define UI/UX beyond documentation"],
            "success_metrics": [
                "All manage_docs operations verified",
                "Templates easy to customize",
            ],
        },
        "requirements": {
            "functional": [
                "Atomic document updates",
                "Jinja2 templates with inheritance",
            ],
            "non_functional": [
                "Backwards-compatible file layout",
                "Sandboxed template rendering",
            ],
            "assumptions": [
                "Filesystem read/write access",
                "Python runtime available",
            ],
            "risks": [
                "User edits outside manage_docs",
                "Template misuse causing errors",
            ],
        },
        "architecture_overview": {
            "summary": "Document manager orchestrates template rendering and writes.",
            "components": [
                {
                    "name": "Doc Manager",
                    "description": "Validates sections and applies atomic writes.",
                    "interfaces": "manage_docs tool",
                    "notes": "Provides verification and logging.",
                },
                {
                    "name": "Template Engine",
                    "description": "Renders templates via Jinja2 with sandboxing.",
                    "interfaces": "Jinja2 environment",
                    "notes": "Supports project/local overrides.",
                },
            ],
            "data_flow": "User -> manage_docs -> template engine -> filesystem/database.",
            "external_integrations": "SQLite mirror, git history.",
        },
        "subsystems": [
            {
                "name": "Doc Change Pipeline",
                "purpose": "Coordinate apply/verify steps.",
                "interfaces": "Atomic writer, storage backend",
                "notes": "Async aware",
                "error_handling": "Rollback on verification failure",
            }
        ],
        "directory_structure": f"{project_root}/docs/dev_plans/{slugify_project_name(project_name)}",
        "data_storage": {
            "datastores": ["Filesystem markdown", "SQLite mirror"],
            "indexing": "FTS for sections",
            "migrations": "Sequential migrations tracked in storage layer",
        },
        "testing_strategy": {
            "unit": "Template rendering + doc ops",
            "integration": "manage_docs tool exercises real files",
            "manual": "Project review after each release",
            "observability": "Structured logging via doc_updates log",
        },
        "deployment": {
            "environments": "Local development",
            "release": "Git commits drive deployment",
            "config": "Project-specific .scribe settings",
            "ownership": "Doc management team",
        },
        "open_questions": [
            {
                "item": "Should templates support conditionals per phase?",
                "owner": "Docs Lead",
                "status": "TODO",
                "notes": "Evaluate after initial rollout.",
            }
        ],
        "references": ["PROGRESS_LOG.md", "ARCHITECTURE_GUIDE.md"],
        "appendix": "Generated via generate_doc_templates.",
    }


def _phase_plan_metadata(project_name: str, context: Dict[str, str]) -> Dict[str, Any]:
    return {
        "summary": f"Execution roadmap for {project_name}.",
        "phases": [
            {
                "name": "Phase 0 — Foundation",
                "anchor": "phase_0",
                "goal": "Stabilize document writes and storage.",
                "deliverables": ["Async atomic write", "SQLite mirror"],
                "confidence": 0.9,
                "tasks": ["Fix async bug", "Add verification"],
                "acceptance": [
                    {"label": "No silent failures", "proof": "tests"},
                ],
                "dependencies": "Existing storage layer",
                "notes": "Must complete before template overhaul.",
            },
            {
                "name": "Phase 1 — Templates",
                "anchor": "phase_1",
                "goal": "Introduce advanced Jinja2 template system.",
                "deliverables": ["Base templates", "Custom template discovery"],
                "confidence": 0.8,
                "tasks": ["Add inheritance", "Add sandboxing"],
                "acceptance": [
                    {"label": "All built-in templates render", "proof": "pytest"},
                ],
                "dependencies": "Phase 0",
                "notes": "Focus on template authoring UX.",
            },
        ],
        "milestones": [
            {
                "name": "Foundation Complete",
                "target": "2025-10-29",
                "owner": "DevTeam",
                "status": "🚧 In Progress",
                "evidence": "PROGRESS_LOG.md",
            },
            {
                "name": "Template Engine Ship",
                "target": "2025-11-02",
                "owner": "DevTeam",
                "status": "⏳ Planned",
                "evidence": "Phase 1 tasks",
            },
        ],
    }


def _checklist_metadata(project_name: str, context: Dict[str, str]) -> Dict[str, Any]:
    return {
        "summary": f"Acceptance checklist for {project_name}.",
        "sections": [
            {
                "title": "Documentation Hygiene",
                "anchor": "documentation_hygiene",
                "items": [
                    {"label": "Architecture guide updated", "proof": "ARCHITECTURE_GUIDE.md"},
                    {"label": "Phase plan current", "proof": "PHASE_PLAN.md"},
                ],
            },
            {
                "title": "Phase 0",
                "anchor": "phase_0",
                "items": [
                    {"label": "Async write fix merged", "proof": "commit"},
                    {"label": "Verification enabled", "proof": "tests"},
                ],
            },
        ],
    }


def _log_metadata(label: str) -> MetadataBuilder:
    def builder(project_name: str, _: Dict[str, str]) -> Dict[str, Any]:
        return {
            "summary": f"{label} for {project_name}.",
            "is_rotation": False,
        }

    return builder


METADATA_BUILDERS: Dict[str, MetadataBuilder] = {
    "architecture": _architecture_metadata,
    "phase_plan": _phase_plan_metadata,
    "checklist": _checklist_metadata,
    "progress_log": _log_metadata("Progress log"),
    "doc_log": _log_metadata("Documentation updates"),
    "security_log": _log_metadata("Security log"),
    "bug_log": _log_metadata("Bug log"),
}
