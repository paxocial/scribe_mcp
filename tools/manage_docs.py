"""Tool for managing project documentation with structured updates."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from scribe_mcp import server as server_module, reminders
from scribe_mcp.server import app
from scribe_mcp.tools.project_utils import load_active_project
from scribe_mcp.doc_management.manager import apply_doc_change, DocumentOperationError
from scribe_mcp.tools.append_entry import append_entry


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

    # Handle research, bug, and review document creation
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
            recent_projects=list(recent),
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


async def _handle_special_document_creation(
    project: Dict[str, Any],
    action: str,
    doc_name: Optional[str],
    target_dir: Optional[str],
    content: Optional[str],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    agent_id: str,
    recent_projects: list,
) -> Dict[str, Any]:
    """Handle creation of research documents and bug reports."""
    from pathlib import Path
    from datetime import datetime
    import json

    # Ensure metadata is a dict using bulletproof normalization
    metadata = _normalize_metadata(metadata)

    # Validate required parameters
    if action == "create_research_doc" and not doc_name:
        return {
            "ok": False,
            "error": "doc_name is required for research document creation",
            "recent_projects": recent_projects,
        }

    if action == "create_bug_report":
        if not metadata or not metadata.get("category"):
            return {
                "ok": False,
                "error": "metadata with 'category' is required for bug report creation",
                "recent_projects": recent_projects,
            }

    # Generate document path
    project_root = Path(project.get("root", ""))
    docs_dir = project_root / "docs" / "dev_plans" / project.get("name", "")

    if action == "create_research_doc":
        # Create research directory
        research_dir = docs_dir / "research"
        target_path = research_dir / f"{doc_name}.md"

        # Generate default content if not provided
        if not content:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            content = f"""# {doc_name.replace('_', ' ').title()}

**Research Date:** {datetime.now().strftime("%Y-%m-%d")}
**Researcher:** {agent_id}
**Project:** {project.get('name')}
**Document Version:** 1.0

---

## Executive Summary

<!-- Executive summary of research findings -->

---

## Research Scope

**Research Goal:** [Describe the primary research objective]

**Investigation Areas:**
- [ ] Area 1
- [ ] Area 2
- [ ] Area 3

---

## Findings

### Finding 1
**Details:** [Describe the finding]

**Evidence:** [Provide evidence/code references]

**Confidence:** High/Medium/Low

---

## Technical Analysis

### Code Patterns Identified
- Pattern 1: [Description]
- Pattern 2: [Description]

### Dependencies
- External: [List]
- Internal: [List]

---

## Risks and Considerations

### Technical Risks
- **Risk:** [Description]
- **Mitigation:** [Strategy]

### Implementation Considerations
- **Complexity:** [Assessment]
- **Timeline:** [Estimate]

---

## Recommendations

1. **Recommendation 1:** [Details]
2. **Recommendation 2:** [Details]

---

## Next Steps

- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

---

*This research document is part of the development audit trail for {project.get('name')}.*
"""

    elif action == "create_review_report":
        # Create review report in project docs directory
        timestamp = datetime.now().strftime("%Y-%m-%d")
        stage = metadata.get("stage", "unknown")
        target_path = docs_dir / f"REVIEW_REPORT_{stage}_{timestamp}_{datetime.now().strftime('%H%M')}.md"

        # Generate default content using Jinja2 template if not provided
        if not content:
            content = await _render_review_report_template(project, agent_id, stage, metadata)

    elif action == "create_agent_report_card":
        # Create agent report card in project docs directory
        agent_name = metadata.get("agent_name", "unknown_agent")
        stage = metadata.get("stage", "unknown")
        target_path = docs_dir / f"AGENT_REPORT_CARD_{agent_name}_{stage}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"

        # Generate default content using Jinja2 template if not provided
        if not content:
            content = await _render_agent_report_card_template(project, agent_id, agent_name, stage, metadata)

    elif action == "create_bug_report":
        # Create bug report directory structure
        from scribe_mcp.utils.time import format_utc
        timestamp = datetime.now().strftime("%Y-%m-%d")
        category = metadata.get("category", "general")
        slug = metadata.get("slug", f"bug_{int(datetime.now().timestamp())}")

        bug_dir = project_root / "docs" / "bugs" / category / f"{timestamp}_{slug}"
        target_path = bug_dir / "report.md"

        # Generate default bug report content
        if not content:
            content = f"""# Bug Report: {metadata.get('title', 'Untitled Bug')}

**Bug ID:** {slug}
**Category:** {category}
**Severity:** {metadata.get('severity', 'medium')}
**Status:** INVESTIGATING
**Report Date:** {format_utc()}
**Reporter:** {agent_id}
**Project:** {project.get('name')}

---

## Bug Description

### Summary
[Brief description of the bug]

### Expected Behavior
[What should happen]

### Actual Behavior
[What actually happens]

### Steps to Reproduce
1. [Step 1]
2. [Step 2]
3. [Step 3]

### Environment
- **Component:** {metadata.get('component', 'unknown')}
- **Version:** [Version if applicable]

---

## Investigation Details

### Root Cause Analysis
[Analysis of what's causing the bug]

### Affected Areas
- **Files:** [List of affected files]
- **Components:** [List of affected components]

---

## Resolution Plan

### Immediate Actions
- [ ] [Action 1]
- [ ] [Action 2]

### Long-term Fixes
- [ ] [Fix 1]
- [ ] [Fix 2]

---

## Testing Strategy

### Reproduction Test
- [ ] Create minimal reproduction case
- [ ] Verify bug can be consistently reproduced

### Fix Verification
- [ ] Test fix against reproduction case
- [ ] Verify no regression in other areas

---

## Timeline

- **Investigation:** [Time estimate]
- **Fix Development:** [Time estimate]
- **Testing:** [Time estimate]
- **Deployment:** [Time estimate]

---

## Related Issues

- **Links:** [Related issues or discussions]
- **Dependencies:** [Any dependencies affecting this bug]

---

*This bug report is tracked in the project audit trail for {project.get('name')}.*
"""

    # Safety check
    try:
        target_path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return {
            "ok": False,
            "error": f"Generated document path {target_path} is outside project root",
            "recent_projects": recent_projects,
        }

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "path": str(target_path),
            "content": content,
            "recent_projects": recent_projects,
        }

    # Create directories and write file
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the document
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Log the creation
        # Use bulletproof metadata normalization
        log_meta = _normalize_metadata(metadata)
        log_meta.update({
            "document_type": action,
            "file_path": str(target_path),
            "file_size": target_path.stat().st_size,
        })

        await append_entry(
            message=f"Created {action.replace('_', ' ')}: {target_path.name}",
            status="success",
            meta=log_meta,
            agent=agent_id,
            log_type="doc_updates",
        )

        # Update INDEX files if needed
        if action == "create_research_doc":
            await _update_research_index(docs_dir / "research", agent_id)
        elif action == "create_bug_report":
            await _update_bug_index(project_root / "docs" / "bugs", agent_id)
        elif action == "create_review_report":
            await _update_review_index(docs_dir, agent_id)
        elif action == "create_agent_report_card":
            await _update_agent_card_index(docs_dir, agent_id)

        return {
            "ok": True,
            "path": str(target_path),
            "document_type": action,
            "file_size": target_path.stat().st_size,
            "recent_projects": recent_projects,
        }

    except Exception as exc:
        return {
            "ok": False,
            "error": f"Failed to create document: {str(exc)}",
            "recent_projects": recent_projects,
        }


async def _update_research_index(research_dir: Path, agent_id: str) -> None:
    """Update the research INDEX.md file."""
    from datetime import datetime
    index_path = research_dir / "INDEX.md"

    # Get all research documents
    research_docs = []
    if research_dir.exists():
        for doc_path in research_dir.glob("RESEARCH_*.md"):
            if doc_path.name != "INDEX.md":
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

    # Write the index
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)


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
    stage: str,
    metadata: Dict[str, Any]
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
        template_context = {
            "project_name": project.get("name", ""),
            "agent_id": agent_id,
            "stage": stage,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            **metadata
        }

        # Render template
        rendered = engine.render_template(
            template_name="REVIEW_REPORT_TEMPLATE.md",
            metadata=template_context
        )

        return rendered

    except (TemplateEngineError, ImportError) as e:
        print(f"⚠️ Template engine error for review report: {e}")
        # Fallback to basic content if template engine fails
        return f"""# Review Report: {stage.replace('_', ' ').title()} Stage

**Review Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Reviewer:** {agent_id}
**Project:** {project.get('name')}
**Stage:** {stage}

---

<!-- ID: executive_summary -->
## Executive Summary

**Overall Decision:** {{ overall_decision | default('[APPROVED/REJECTED/REQUIRES_REVISION]') }}

---

<!-- ID: final_decision -->
## Final Decision

**{{ final_decision | default('[APPROVED/REJECTED/REQUIRES_REVISION]') }}**

*This review report is part of the quality assurance process for {project.get('name')}.*
"""
    except Exception as e:
        print(f"❌ Unexpected error rendering review report template: {e}")
        raise DocumentOperationError(f"Failed to render review report template: {e}")


async def _render_agent_report_card_template(
    project: Dict[str, Any],
    agent_id: str,
    agent_name: str,
    stage: str,
    metadata: Dict[str, Any]
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
        template_context = {
            "project_name": project.get("name", ""),
            "agent_id": agent_id,
            "agent_name": agent_name,
            "stage": stage,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            **metadata
        }

        # Render template
        rendered = engine.render_template(
            template_name="AGENT_REPORT_CARD_TEMPLATE.md",
            metadata=template_context
        )

        return rendered

    except (TemplateEngineError, ImportError) as e:
        print(f"⚠️ Template engine error for agent report card: {e}")
        # Fallback to basic content if template engine fails
        return f"""# Agent Performance Report Card

**Agent:** {agent_name}
**Review Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Reviewer:** {agent_id}
**Project:** {project.get('name')}
**Stage:** {stage}

---

<!-- ID: executive_summary -->
## Executive Summary

**Overall Grade:** {{ overall_grade | default('[Score]%') }}

---

<!-- ID: final_assessment -->
## Final Assessment

**Overall Recommendation:** {{ final_recommendation | default('[RECOMMENDATION]') }}

*This agent report card is part of the performance management system for {project.get('name')}.*
"""
    except Exception as e:
        print(f"❌ Unexpected error rendering agent report card template: {e}")
        raise DocumentOperationError(f"Failed to render agent report card template: {e}")


if __name__ == "__main__":
    sys.exit(manage_docs_main())
