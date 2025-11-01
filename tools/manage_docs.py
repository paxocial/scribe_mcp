"""Tool for managing project documentation with structured updates."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Callable, Awaitable

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.doc_management.manager import apply_doc_change, DocumentOperationError
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.shared.logging_utils import (
    LoggingContext,
    ProjectResolutionError,
)
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin


class _ManageDocsHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_MANAGE_DOCS_HELPER = _ManageDocsHelper()


def _normalize_metadata(metadata: Optional[Dict[str, Any] | str]) -> Dict[str, Any]:
    """Normalize metadata parameter to handle both dict and JSON string inputs from MCP framework."""
    if metadata is None:
        return {}
    elif isinstance(metadata, str):
        try:
            import json
            return json.loads(metadata)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
    elif isinstance(metadata, dict):
        return metadata.copy() if metadata else {}
    else:
        # Handle any other unexpected types
        try:
            import json
            return json.loads(str(metadata))
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}


def _hash_text(content: str) -> str:
    """Return a deterministic hash for stored document content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _current_timestamp() -> str:
    """Return the current UTC timestamp for metadata usage."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _write_file_atomically(file_path: Path, content: str) -> bool:
    """Write file atomically using temp file and move operation."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temporary file first, then move atomically
        temp_path = file_path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Verify the temp file was written correctly
        if temp_path.exists() and temp_path.stat().st_size > 0:
            temp_path.replace(file_path)
            return True
        else:
            print(f"⚠️ Failed to write {file_path.name}: temporary file not created properly")
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink()
            return False

    except (OSError, IOError) as exc:
        print(f"⚠️ Failed to write {file_path.name}: {exc}")
        return False
    except Exception as exc:
        print(f"❌ Unexpected error writing {file_path.name}: {exc}")
        return False


def _validate_and_repair_index(index_path: Path, doc_dir: Path) -> bool:
    """Validate index file and repair if it's broken or out of sync."""
    try:
        # Check if index exists and is readable
        if not index_path.exists():
            print(f"🔧 Index file {index_path.name} missing, will create new one")
            return False

        # Try to read the index
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (UnicodeDecodeError, IOError) as exc:
            print(f"🔧 Index file {index_path.name} corrupted ({exc}), will repair")
            # Backup corrupted file
            backup_path = index_path.with_suffix('.corrupted.backup')
            if index_path.exists():
                index_path.rename(backup_path)
            return False

        # Basic validation - check if it looks like a proper index
        if not content.strip().startswith('#'):
            print(f"🔧 Index file {index_path.name} doesn't look like valid index, will repair")
            backup_path = index_path.with_suffix('.invalid.backup')
            index_path.rename(backup_path)
            return False

        # Count actual documents vs indexed documents
        if doc_dir.exists():
            actual_docs = list(doc_dir.glob("*.md"))
            actual_docs = [d for d in actual_docs if d.name != "INDEX.md" and not d.name.startswith("_")]

            # Simple heuristic: if index says 0 docs but we have actual docs, it's stale
            if "Total Documents:** 0" in content and actual_docs:
                print(f"🔧 Index file {index_path.name} stale (shows 0 docs but {len(actual_docs)} found), will repair")
                return False

        return True

    except Exception as exc:
        print(f"🔧 Error validating index {index_path.name}: {exc}, will repair")
        return False


async def _get_or_create_storage_project(backend: Any, project: Dict[str, Any]) -> Any:
    """Fetch or create the backing storage record for a project."""
    timeout = server_module.settings.storage_timeout_seconds
    async with asyncio.timeout(timeout):
        storage_record = await backend.fetch_project(project["name"])
    if not storage_record:
        async with asyncio.timeout(timeout):
            storage_record = await backend.upsert_project(
                name=project["name"],
                repo_root=project["root"],
                progress_log_path=project["progress_log"],
            )
    return storage_record


def _build_special_metadata(
    project: Dict[str, Any],
    metadata: Dict[str, Any],
    agent_id: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Prepare metadata payload for template rendering and storage."""
    prepared = metadata.copy()
    prepared.setdefault("project_name", project.get("name"))
    prepared.setdefault("project_root", project.get("root"))
    prepared.setdefault("agent_id", agent_id)
    prepared.setdefault("agent_name", prepared.get("agent_name", agent_id))
    prepared.setdefault("timestamp", prepared.get("timestamp", _current_timestamp()))
    if extra:
        for key, value in extra.items():
            prepared.setdefault(key, value)
    return prepared


async def _render_special_template(
    project: Dict[str, Any],
    agent_id: str,
    template_name: str,
    metadata: Dict[str, Any],
    extra_metadata: Optional[Dict[str, Any]] = None,
    prepared_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Render a special document template using the shared Jinja2 engine."""
    try:
        from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

        engine = Jinja2TemplateEngine(
            project_root=Path(project.get("root", "")),
            project_name=project.get("name", ""),
            security_mode="sandbox",
        )
        if prepared_metadata is None:
            prepared_metadata = _build_special_metadata(
                project,
                metadata,
                agent_id,
                extra=extra_metadata,
            )
        return engine.render_template(
            template_name=f"documents/{template_name}",
            metadata=prepared_metadata,
        )
    except (ImportError, TemplateEngineError) as exc:
        raise DocumentOperationError(f"Failed to render template '{template_name}': {exc}") from exc


async def _record_special_doc_change(
    backend: Any,
    project: Dict[str, Any],
    agent_id: str,
    doc_label: str,
    target_path: Path,
    metadata: Dict[str, Any],
    before_hash: str,
    after_hash: str,
) -> None:
    """Persist document change information for special documents."""
    if not backend:
        return
    try:
        storage_record = await _get_or_create_storage_project(backend, project)
    except Exception as exc:  # pragma: no cover - defensive logging mirror behaviour above
        print(f"⚠️  Failed to prepare storage record for {doc_label}: {exc}")
        return

    action = "create" if not before_hash else "update"
    try:
        await backend.record_doc_change(
            storage_record,
            doc=doc_label,
            section=None,
            action=action,
            agent=agent_id,
            metadata=metadata,
            sha_before=before_hash,
            sha_after=after_hash,
        )
    except Exception as exc:
        print(f"⚠️  Failed to record special doc change for {doc_label}: {exc}")


def _parse_numeric_grade(value: Any) -> Optional[float]:
    """Convert percentage-like values to float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip()
        if text.endswith("%"):
            text = text[:-1]
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


async def _record_agent_report_card_metadata(
    backend: Any,
    project: Dict[str, Any],
    agent_id: str,
    target_path: Path,
    metadata: Dict[str, Any],
) -> None:
    """Persist structured agent report card metadata when supported."""
    if not backend:
        return
    try:
        storage_record = await _get_or_create_storage_project(backend, project)
    except Exception as exc:
        print(f"⚠️  Failed to prepare storage project for agent card: {exc}")
        return

    try:
        await backend.record_agent_report_card(
            storage_record,
            file_path=str(target_path),
            agent_name=metadata.get("agent_name", agent_id),
            stage=metadata.get("stage"),
            overall_grade=_parse_numeric_grade(metadata.get("overall_grade")),
            performance_level=metadata.get("performance_level"),
            metadata=metadata,
        )
    except Exception as exc:
        print(f"⚠️  Failed to record agent report card metadata: {exc}")


@app.tool()
async def manage_docs(
    action: str,
    doc: str,
    section: Optional[str] = None,
    content: Optional[str] = None,
    template: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    doc_name: Optional[str] = None,
    target_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply structured updates to architecture/phase/checklist documents and create research/bug documents."""
    state_snapshot = await server_module.state_manager.record_tool("manage_docs")
    try:
        context = await _MANAGE_DOCS_HELPER.prepare_context(
            tool_name="manage_docs",
            agent_id=None,
            require_project=True,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        payload = _MANAGE_DOCS_HELPER.translate_project_error(exc)
        payload.setdefault("suggestion", "Invoke set_project before managing docs.")
        payload.setdefault("reminders", [])
        return payload

    project = context.project or {}

    agent_identity = server_module.get_agent_identity()
    agent_id = "Scribe"
    if agent_identity:
        agent_id = await agent_identity.get_or_create_agent_id()

    backend = server_module.storage_backend

    # Handle research, bug, review, and agent report card creation
    if action in ["create_research_doc", "create_bug_report", "create_review_report", "create_agent_report_card"]:
        return await _handle_special_document_creation(
            project,
            action=action,
            doc_name=doc_name,
            target_dir=target_dir,
            content=content,
            metadata=metadata,
            dry_run=dry_run,
            agent_id=agent_id,
            storage_backend=backend,
            helper=_MANAGE_DOCS_HELPER,
            context=context,
        )

    try:
        change = await apply_doc_change(
            project,
            doc=doc,
            action=action,
            section=section,
            content=content,
            template=template,
            metadata=metadata,
            dry_run=dry_run,
        )
    except Exception as exc:
        response = {
            "ok": False,
            "error": str(exc),
        }
        return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

    storage_record = None
    if backend and not dry_run:
        try:
            storage_record = await _get_or_create_storage_project(backend, project)
            await backend.record_doc_change(
                storage_record,
                doc=doc,
                section=section,
                action=action,
                agent=agent_id,
                metadata=metadata,
                sha_before=change.before_hash,
                sha_after=change.after_hash,
            )
        except Exception as exc:
            print(f"⚠️  Failed to record doc change in storage: {exc}")

    log_error = None
    if not dry_run:
        # Use bulletproof metadata normalization
        log_meta = _normalize_metadata(metadata)
        log_meta.update(
            {
                "doc": doc,
                "section": section or "",
                "action": action,
                "sha_after": change.after_hash,
            }
        )
        try:
            await append_entry(
                message=f"Doc update [{doc}] {section or 'full'} via {action}",
                status="info",
                meta=log_meta,
                agent=agent_id,
                log_type="doc_updates",
            )
        except Exception as exc:
            log_error = str(exc)

    response: Dict[str, Any] = {
        "ok": change.success,
        "doc": doc,
        "section": section,
        "action": action,
        "path": str(change.path) if change.success else "",
        "dry_run": dry_run,
        "diff": change.diff_preview,
    }

    # Add error information if operation failed
    if not change.success and change.error_message:
        response["error"] = change.error_message

    # Add verification information
    if not dry_run:
        response["verification_passed"] = change.verification_passed
        response["file_size_before"] = change.file_size_before
        response["file_size_after"] = change.file_size_after

    if log_error:
        response["log_warning"] = log_error
    if dry_run:
        response["preview"] = change.content_written

    return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)


def manage_docs_main():
    """CLI entry point for manage_docs functionality."""
    import argparse
    import asyncio
    import sys
    from pathlib import Path

    async def _run_manage_docs(args):
        """Run manage_docs with provided CLI arguments."""
        try:
            result = await manage_docs(
                action=args.action,
                doc=args.doc,
                section=args.section,
                content=args.content,
                template=args.template,
                metadata=args.metadata,
                dry_run=args.dry_run,
            )

            if result.get("ok"):
                if "error_message" in result and result["error_message"]:
                    print(f"⚠️  Operation completed with warnings: {result['error_message']}")
                else:
                    print(f"✅ {result.get('message', 'Documentation updated successfully')}")

                if args.dry_run:
                    print("🔍 Dry run - no changes made")
                    if "preview" in result:
                        print("\nPreview:")
                        print(result["preview"])

                # Show verification status
                if "verification_passed" in result:
                    if result["verification_passed"]:
                        print("✅ File write verification passed")
                    else:
                        print("❌ File write verification failed")

                return 0
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}")
                return 1

        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return 1

    parser = argparse.ArgumentParser(
        description="Manage project documentation with structured updates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Replace a section in architecture guide
  manage_docs replace_section architecture directory_structure --template directory_structure

  # Update checklist status
  manage_docs status_update checklist phase_0 --metadata status=done proof=commit_123

  # Append content to document
  manage_docs append phase_plan --content "New phase details here"
        """
    )

    parser.add_argument(
        "action",
        choices=["replace_section", "append", "status_update"],
        help="Action to perform on the document"
    )

    parser.add_argument(
        "doc",
        choices=["architecture", "phase_plan", "checklist", "progress_log", "doc_log", "security_log", "bug_log"],
        help="Document to modify"
    )

    parser.add_argument(
        "--section",
        help="Section ID (required for replace_section and status_update)"
    )

    parser.add_argument(
        "--content",
        help="Content to add/replace"
    )

    parser.add_argument(
        "--template",
        help="Template fragment to use (from templates/fragments/)"
    )

    parser.add_argument(
        "--metadata",
        type=str,
        help="Metadata as JSON string (e.g., '{\"status\": \"done\", \"proof\": \"commit_123\"}')"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.action in ["replace_section", "status_update"] and not args.section:
        print("❌ Error: --section is required for replace_section and status_update actions")
        return 1

    if not args.content and not args.template:
        print("❌ Error: Either --content or --template must be provided")
        return 1

    # Parse metadata if provided
    metadata = None
    if args.metadata:
        try:
            import json
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print(f"❌ Error: Invalid JSON in metadata: {args.metadata}")
            return 1

    # Run the operation
    return asyncio.run(_run_manage_docs(args))



async def _handle_special_document_creation(
    project: Dict[str, Any],
    action: str,
    doc_name: Optional[str],
    target_dir: Optional[str],
    content: Optional[str],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    agent_id: str,
    storage_backend: Any,
    helper: LoggingToolMixin,
    context: LoggingContext,
) -> Dict[str, Any]:
    """Handle creation of research, bug, review, and agent report card documents."""
    metadata = _normalize_metadata(metadata)

    project_root = Path(project.get("root", ""))
    docs_dir = project_root / "docs" / "dev_plans" / project.get("name", "")
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    template_name = ""
    doc_label = ""
    target_path: Optional[Path] = None
    index_updater: Optional[Callable[[], Awaitable[None]]] = None
    extra_metadata: Dict[str, Any] = {}

    if action == "create_research_doc":
        if not doc_name:
            return helper.apply_context_payload(
                helper.error_response(
                    "doc_name is required for research document creation",
                ),
                context,
            )
        # Sanitize the doc_name for filesystem safety
        import re
        # Replace spaces and special chars with underscores, keep alphanumeric and basic symbols
        safe_name = re.sub(r'[^\w\-_\.]', '_', doc_name)
        # Remove multiple consecutive underscores
        safe_name = re.sub(r'_+', '_', safe_name)
        # Remove leading/trailing underscores
        safe_name = safe_name.strip('_')
        # Ensure it's not empty after sanitization
        if not safe_name:
            safe_name = f"research_{int(datetime.now().timestamp())}"

        research_dir = docs_dir / "research"
        target_path = research_dir / f"{safe_name}.md"
        template_name = "RESEARCH_REPORT_TEMPLATE.md"
        doc_label = "research_report"
        extra_metadata = {
            "title": doc_name.replace("_", " ").title(),
            "doc_name": safe_name,
            "researcher": metadata.get("researcher", agent_id),
        }
        index_updater = lambda: _update_research_index(research_dir, agent_id)
    elif action == "create_bug_report":
        category = metadata.get("category")
        if not category or not category.strip():
            return helper.apply_context_payload(
                helper.error_response(
                    "metadata with non-empty 'category' is required for bug report creation",
                ),
                context,
            )

        # Sanitize category
        import re
        category = re.sub(r'[^\w\-_\.]', '_', category.strip())

        slug = metadata.get("slug")
        if slug:
            # Sanitize slug as well
            slug = re.sub(r'[^\w\-_\.]', '_', str(slug).strip())
        if not slug:
            slug = f"bug_{int(now.timestamp())}"
        bug_dir = project_root / "docs" / "bugs" / category / f"{now.strftime('%Y-%m-%d')}_{slug}"
        target_path = bug_dir / "report.md"
        template_name = "BUG_REPORT_TEMPLATE.md"
        doc_label = "bug_report"
        extra_metadata = {
            "slug": slug,
            "category": category,
            "reported_at": metadata.get("reported_at", timestamp_str),
        }
        index_updater = lambda: _update_bug_index(project_root / "docs" / "bugs", agent_id)
    elif action == "create_review_report":
        stage = metadata.get("stage", "unknown")
        target_path = docs_dir / f"REVIEW_REPORT_{stage}_{now.strftime('%Y-%m-%d')}_{now.strftime('%H%M')}.md"
        template_name = "REVIEW_REPORT_TEMPLATE.md"
        doc_label = "review_report"
        extra_metadata = {"stage": stage}
        index_updater = lambda: _update_review_index(docs_dir, agent_id)
    elif action == "create_agent_report_card":
        card_agent = metadata.get("agent_name", agent_id)
        stage = metadata.get("stage", "unknown")
        target_path = docs_dir / f"AGENT_REPORT_CARD_{card_agent}_{stage}_{now.strftime('%Y%m%d_%H%M')}.md"
        template_name = "AGENT_REPORT_CARD_TEMPLATE.md"
        doc_label = "agent_report_card"
        extra_metadata = {
            "agent_name": card_agent,
            "stage": stage,
        }
        index_updater = lambda: _update_agent_card_index(docs_dir, agent_id)
    else:
        return helper.apply_context_payload(
            helper.error_response(f"Unsupported special document action: {action}"),
            context,
        )

    prepared_metadata = _build_special_metadata(project, metadata, agent_id, extra_metadata)

    rendered_content = content
    if not rendered_content:
        try:
            if action == "create_review_report":
                rendered_content = await _render_review_report_template(
                    project,
                    agent_id,
                    prepared_metadata,
                )
            elif action == "create_agent_report_card":
                rendered_content = await _render_agent_report_card_template(
                    project,
                    agent_id,
                    prepared_metadata,
                )
            else:
                rendered_content = await _render_special_template(
                    project,
                    agent_id,
                    template_name,
                    metadata,
                    extra_metadata=extra_metadata,
                    prepared_metadata=prepared_metadata,
                )
        except DocumentOperationError as exc:
            return helper.apply_context_payload(
                helper.error_response(str(exc)),
                context,
            )

    if rendered_content is None:
        return helper.apply_context_payload(
            helper.error_response("Failed to render document content."),
            context,
        )

    try:
        target_path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return helper.apply_context_payload(
            helper.error_response(
                f"Generated document path {target_path} is outside project root",
            ),
            context,
        )

    if dry_run:
        return helper.apply_context_payload(
            {
                "ok": True,
                "dry_run": True,
                "path": str(target_path),
                "content": rendered_content,
            },
            context,
        )

    before_hash = ""
    if target_path.exists():
        try:
            before_hash = _hash_text(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            before_hash = ""

    log_warning: Optional[str] = None

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(rendered_content, encoding="utf-8")

        after_hash = _hash_text(rendered_content)

        await _record_special_doc_change(
            storage_backend,
            project,
            agent_id,
            doc_label,
            target_path,
            prepared_metadata,
            before_hash,
            after_hash,
        )
        if doc_label == "agent_report_card":
            await _record_agent_report_card_metadata(
                storage_backend,
                project,
                agent_id,
                target_path,
                prepared_metadata,
            )

        log_meta = _normalize_metadata(prepared_metadata)
        log_meta.update(
            {
                "doc": doc_label,
                "section": "",
                "action": "create",
                "document_type": doc_label,
                "file_path": str(target_path),
                "file_size": target_path.stat().st_size,
            }
        )
        for key, value in list(log_meta.items()):
            if isinstance(value, (dict, list)):
                try:
                    log_meta[key] = json.dumps(value, sort_keys=True)
                except (TypeError, ValueError):
                    log_meta[key] = str(value)

        try:
            await append_entry(
                message=f"Created {doc_label.replace('_', ' ')}: {target_path.name}",
                status="success",
                meta=log_meta,
                agent=agent_id,
                log_type="doc_updates",
            )
        except Exception as exc:
            log_warning = str(exc)

        if index_updater:
            try:
                await index_updater()
            except Exception as exc:
                print(f"⚠️ Failed to update index for {doc_label}: {exc}")
                # Don't fail the whole operation if index update fails
                # The document was created successfully, just the index is stale

        success_payload: Dict[str, Any] = {
            "ok": True,
            "path": str(target_path),
            "document_type": doc_label,
            "file_size": target_path.stat().st_size,
        }
        if log_warning:
            success_payload["log_warning"] = log_warning

        return helper.apply_context_payload(success_payload, context)

    except Exception as exc:
        return helper.apply_context_payload(
            helper.error_response(f"Failed to create document: {exc}"),
            context,
        )


async def _update_research_index(research_dir: Path, agent_id: str) -> None:
    """Update the research INDEX.md file."""
    from datetime import datetime
    index_path = research_dir / "INDEX.md"

    # Self-healing: validate and repair index if needed
    if not _validate_and_repair_index(index_path, research_dir):
        print(f"🔧 Auto-repairing research index for {research_dir.name}")

    # Get all research documents
    research_docs = []
    if research_dir.exists():
        # Look for all .md files except INDEX.md and any template files
        for doc_path in research_dir.glob("*.md"):
            if doc_path.name != "INDEX.md" and not doc_path.name.startswith("_"):
                stat = doc_path.stat()
                research_docs.append({
                    "name": doc_path.stem,
                    "path": doc_path.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })

    # Generate INDEX content
    content = f"""# Research Documents Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains research documents generated during the development process.

## Available Research Documents

"""

    if research_docs:
        # Sort by modification time (newest first)
        research_docs.sort(key=lambda x: x["modified"], reverse=True)

        for doc in research_docs:
            modified_time = datetime.fromtimestamp(doc["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{doc['name']}]({doc['path']})** - {modified_time} ({doc['size']} bytes)\n"
    else:
        content += "*No research documents found.*\n"

    content += f"""

## Index Information

- **Total Documents:** {len(research_docs)}
- **Index Location:** `{index_path.relative_to(research_dir.parent.parent)}`

---

*This index is automatically updated when research documents are created or modified.*"""

    # Write the index atomically
    if not _write_file_atomically(index_path, content):
        print(f"⚠️ Failed to update research index at {index_path}")


async def _update_bug_index(bugs_dir: Path, agent_id: str) -> None:
    """Update the main bugs INDEX.md file."""
    from datetime import datetime
    index_path = bugs_dir / "INDEX.md"

    # Get all bug reports
    bug_reports = []
    if bugs_dir.exists():
        for category_dir in bugs_dir.iterdir():
            if category_dir.is_dir() and category_dir.name != "archived":
                for bug_dir in category_dir.iterdir():
                    if bug_dir.is_dir():
                        report_path = bug_dir / "report.md"
                        if report_path.exists():
                            stat = report_path.stat()
                            bug_reports.append({
                                "category": category_dir.name,
                                "slug": bug_dir.name,
                                "path": str(report_path.relative_to(bugs_dir)),
                                "size": stat.st_size,
                                "modified": stat.st_mtime,
                            })

    # Generate INDEX content
    content = f"""# Bug Reports Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains bug reports generated during development and testing.

## Bug Statistics

- **Total Reports:** {len(bug_reports)}
- **Categories:** {len(set(report['category'] for report in bug_reports))}

## Recent Bug Reports

"""

    if bug_reports:
        # Sort by modification time (newest first)
        bug_reports.sort(key=lambda x: x["modified"], reverse=True)

        for bug in bug_reports[:20]:  # Show last 20
            modified_time = datetime.fromtimestamp(bug["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{bug['category']}/{bug['slug']}]({bug['path']})** - {modified_time}\n"

        if len(bug_reports) > 20:
            content += f"\n*... and {len(bug_reports) - 20} older reports*\n"
    else:
        content += "*No bug reports found.*\n"

    content += f"""

## Browse by Category

"""

    # Group by category
    categories = {}
    for bug in bug_reports:
        if bug["category"] not in categories:
            categories[bug["category"]] = []
        categories[bug["category"]].append(bug)

    for category, bugs in sorted(categories.items()):
        content += f"### {category.title()} ({len(bugs)} reports)\n"
        for bug in bugs[:5]:  # Show first 5 per category
            content += f"- [{bug['slug']}]({bug['path']})\n"
        if len(bugs) > 5:
            content += f"- ... and {len(bugs) - 5} more\n"
        content += "\n"

    content += f"""
---

## Index Information

- **Index Location:** `{index_path}`
- **Total Categories:** {len(categories)}
- **Last Scan:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}

---

*This index is automatically updated when bug reports are created or modified.*"""

    # Write the index
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)


async def _update_review_index(docs_dir: Path, agent_id: str) -> None:
    """Update the review reports INDEX.md file."""
    from datetime import datetime
    index_path = docs_dir / "REVIEW_INDEX.md"

    # Get all review reports
    review_reports = []
    for review_file in docs_dir.glob("REVIEW_REPORT_*.md"):
        if review_file.name != "REVIEW_INDEX.md":
            stat = review_file.stat()
            # Extract stage from filename
            try:
                # Format: REVIEW_REPORT_Stage3_2025-10-31_1203.md
                parts = review_file.stem.split('_')
                stage = parts[2] if len(parts) > 2 else "unknown"
                review_reports.append({
                    "name": review_file.stem,
                    "path": review_file.name,
                    "stage": stage,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
            except:
                continue

    # Generate INDEX content
    content = f"""# Review Reports Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains review reports generated during the development quality assurance process.

## Review Statistics

- **Total Reports:** {len(review_reports)}
- **Stages Reviewed:** {len(set(report['stage'] for report in review_reports))}

## Recent Review Reports

"""

    if review_reports:
        # Sort by modification time (newest first)
        review_reports.sort(key=lambda x: x["modified"], reverse=True)

        for report in review_reports[:20]:  # Show last 20
            modified_time = datetime.fromtimestamp(report["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{report['name']}]({report['path']})** - {report['stage']} - {modified_time}\n"

        if len(review_reports) > 20:
            content += f"\n*... and {len(review_reports) - 20} older reports*\n"
    else:
        content += "*No review reports found.*\n"

    content += f"""

## Browse by Stage

"""

    # Group by stage
    stages = {}
    for report in review_reports:
        if report["stage"] not in stages:
            stages[report["stage"]] = []
        stages[report["stage"]].append(report)

    for stage, reports in sorted(stages.items()):
        content += f"### {stage.title()} ({len(reports)} reports)\n"
        for report in reports[:5]:  # Show first 5 per stage
            content += f"- [{report['name']}]({report['path']})\n"
        if len(reports) > 5:
            content += f"- ... and {len(reports) - 5} more\n"
        content += "\n"

    content += f"""

## Index Information

- **Index Location:** `{index_path}`
- **Total Stages:** {len(stages)}
- **Last Scan:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}

---

*This index is automatically updated when review reports are created or modified.*"""

    # Write the index
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)


async def _update_agent_card_index(docs_dir: Path, agent_id: str) -> None:
    """Update the agent report cards INDEX.md file."""
    from datetime import datetime
    index_path = docs_dir / "AGENT_CARDS_INDEX.md"

    # Get all agent report cards
    agent_cards = []
    for card_file in docs_dir.glob("AGENT_REPORT_CARD_*.md"):
        if card_file.name != "AGENT_CARDS_INDEX.md":
            stat = card_file.stat()
            # Extract agent name from filename
            try:
                # Format: AGENT_REPORT_CARD_ResearchAnalyst_Stage3_20251031_1203.md
                parts = card_file.stem.split('_')
                agent_name = parts[3] if len(parts) > 3 else "unknown"
                stage = parts[4] if len(parts) > 4 else "unknown"
                agent_cards.append({
                    "name": card_file.stem,
                    "path": card_file.name,
                    "agent": agent_name,
                    "stage": stage,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
            except:
                continue

    # Generate INDEX content
    content = f"""# Agent Report Cards Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains agent performance evaluation reports generated during the development process.

## Agent Statistics

- **Total Reports:** {len(agent_cards)}
- **Agents Evaluated:** {len(set(report['agent'] for report in agent_cards))}
- **Stages Covered:** {len(set(report['stage'] for report in agent_cards))}

## Recent Agent Evaluations

"""

    if agent_cards:
        # Sort by modification time (newest first)
        agent_cards.sort(key=lambda x: x["modified"], reverse=True)

        for card in agent_cards[:20]:  # Show last 20
            modified_time = datetime.fromtimestamp(card["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{card['name']}]({card['path']})** - {card['agent']} - {card['stage']} - {modified_time}\n"

        if len(agent_cards) > 20:
            content += f"\n*... and {len(agent_cards) - 20} older evaluations*\n"
    else:
        content += "*No agent report cards found.*\n"

    content += f"""

## Browse by Agent

"""

    # Group by agent
    agents = {}
    for card in agent_cards:
        if card["agent"] not in agents:
            agents[card["agent"]] = []
        agents[card["agent"]].append(card)

    for agent, cards in sorted(agents.items()):
        content += f"### {agent} ({len(cards)} evaluations)\n"
        for card in cards[:5]:  # Show first 5 per agent
            content += f"- [{card['name']}]({card['path']})\n"
        if len(cards) > 5:
            content += f"- ... and {len(cards) - 5} more\n"
        content += "\n"

    content += f"""

## Index Information

- **Index Location:** `{index_path}`
- **Total Agents:** {len(agents)}
- **Last Scan:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}

---

*This index is automatically updated when agent report cards are created or modified.*"""

    # Write the index
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)


async def _render_review_report_template(
    project: Dict[str, Any],
    agent_id: str,
    prepared_metadata: Dict[str, Any],
) -> str:
    """Render review report using Jinja2 template."""
    try:
        from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

        # Initialize template engine
        engine = Jinja2TemplateEngine(
            project_root=Path(project.get("root", "")),
            project_name=project.get("name", ""),
            security_mode="sandbox"
        )

        # Prepare template context
        template_context = prepared_metadata.copy()
        template_context.setdefault("project_name", project.get("name", ""))
        template_context.setdefault("agent_id", agent_id)
        template_context.setdefault("timestamp", _current_timestamp())
        template_context.setdefault("stage", prepared_metadata.get("stage", "unknown"))

        # Render template
        rendered = engine.render_template(
            template_name="REVIEW_REPORT_TEMPLATE.md",
            metadata=template_context
        )

        return rendered

    except (TemplateEngineError, ImportError) as e:
        print(f"⚠️ Template engine error for review report: {e}")
        # Fallback to basic content if template engine fails
        stage = prepared_metadata.get("stage", "unknown")
        overall_decision = prepared_metadata.get("overall_decision", "[PENDING]")
        final_decision = prepared_metadata.get("final_decision", overall_decision)
        return f"""# Review Report: {stage.replace('_', ' ').title()} Stage

**Review Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Reviewer:** {agent_id}
**Project:** {project.get('name')}
**Stage:** {stage}

---

<!-- ID: executive_summary -->
## Executive Summary

**Overall Decision:** {overall_decision}

---

<!-- ID: final_decision -->
## Final Decision

**{final_decision}**

*This review report is part of the quality assurance process for {project.get('name')}.*
"""
    except Exception as e:
        print(f"❌ Unexpected error rendering review report template: {e}")
        raise DocumentOperationError(f"Failed to render review report template: {e}")


async def _render_agent_report_card_template(
    project: Dict[str, Any],
    agent_id: str,
    prepared_metadata: Dict[str, Any],
) -> str:
    """Render agent report card using Jinja2 template."""
    try:
        from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

        # Initialize template engine
        engine = Jinja2TemplateEngine(
            project_root=Path(project.get("root", "")),
            project_name=project.get("name", ""),
            security_mode="sandbox"
        )

        # Prepare template context
        template_context = prepared_metadata.copy()
        template_context.setdefault("project_name", project.get("name", ""))
        template_context.setdefault("agent_id", agent_id)
        template_context.setdefault("timestamp", _current_timestamp())
        template_context.setdefault("agent_name", prepared_metadata.get("agent_name", agent_id))
        template_context.setdefault("stage", prepared_metadata.get("stage", "unknown"))

        # Render template
        rendered = engine.render_template(
            template_name="AGENT_REPORT_CARD_TEMPLATE.md",
            metadata=template_context
        )

        return rendered

    except (TemplateEngineError, ImportError) as e:
        print(f"⚠️ Template engine error for agent report card: {e}")
        # Fallback to basic content if template engine fails
        agent_name = prepared_metadata.get("agent_name", agent_id)
        stage = prepared_metadata.get("stage", "unknown")
        overall_grade = prepared_metadata.get("overall_grade", "[PENDING]")
        final_recommendation = prepared_metadata.get("final_recommendation", "[PENDING]")
        return f"""# Agent Performance Report Card

**Agent:** {agent_name}
**Review Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Reviewer:** {agent_id}
**Project:** {project.get('name')}
**Stage:** {stage}

---

<!-- ID: executive_summary -->
## Executive Summary

**Overall Grade:** {overall_grade}

---

<!-- ID: final_assessment -->
## Final Assessment

**Overall Recommendation:** {final_recommendation}

*This agent report card is part of the performance management system for {project.get('name')}.*
"""
    except Exception as e:
        print(f"❌ Unexpected error rendering agent report card template: {e}")
        raise DocumentOperationError(f"Failed to render agent report card template: {e}")


if __name__ == "__main__":
    sys.exit(manage_docs_main())
