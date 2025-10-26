"""Tool for generating documentation scaffolds from templates."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from scribe_mcp import reminders, server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.tools.project_utils import slugify_project_name
from scribe_mcp.server import app
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


@app.tool()
async def generate_doc_templates(
    project_name: str,
    author: str | None = None,
    overwrite: bool = False,
    documents: Iterable[str] | None = None,
    base_dir: str | None = None,
    custom_context: Any = None,
) -> Dict[str, Any]:
    """Render the standard documentation templates for a project."""
    state_snapshot = await server_module.state_manager.record_tool("generate_doc_templates")
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

    output_dir = _target_directory(project_name, base_dir)
    await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)

    selected = _select_documents(documents)

    written: List[str] = []
    skipped: List[str] = []
    for key, filename in OUTPUT_FILENAMES:
        if key not in selected:
            continue
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
