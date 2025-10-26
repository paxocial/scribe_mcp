"""Tool for managing project documentation with structured updates."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from scribe_mcp import server as server_module, reminders
from scribe_mcp.server import app
from scribe_mcp.tools.project_utils import load_active_project
from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.tools.append_entry import append_entry


@app.tool()
async def manage_docs(
    action: str,
    doc: str,
    section: Optional[str] = None,
    content: Optional[str] = None,
    template: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply structured updates to architecture/phase/checklist documents."""
    state_snapshot = await server_module.state_manager.record_tool("manage_docs")
    project, _, recent = await load_active_project(server_module.state_manager)
    reminders_payload: list[Dict[str, Any]] = []

    if not project:
        return {
            "ok": False,
            "error": "No project configured.",
            "suggestion": "Invoke set_project before managing docs.",
            "recent_projects": list(recent),
            "reminders": reminders_payload,
        }

    agent_identity = server_module.get_agent_identity()
    agent_id = "Scribe"
    if agent_identity:
        agent_id = await agent_identity.get_or_create_agent_id()

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
        return {
            "ok": False,
            "error": str(exc),
            "recent_projects": list(recent),
        }

    backend = server_module.storage_backend
    storage_record = None
    if backend and not dry_run:
        try:
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
        log_meta = metadata.copy() if metadata else {}
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

    reminders_payload = await reminders.get_reminders(
        project,
        tool_name="manage_docs",
        state=state_snapshot,
    )

    response: Dict[str, Any] = {
        "ok": change.success,
        "doc": doc,
        "section": section,
        "action": action,
        "path": str(change.path) if change.success else "",
        "dry_run": dry_run,
        "diff": change.diff_preview,
        "recent_projects": list(recent),
        "reminders": reminders_payload,
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

    return response


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


if __name__ == "__main__":
    sys.exit(manage_docs_main())
