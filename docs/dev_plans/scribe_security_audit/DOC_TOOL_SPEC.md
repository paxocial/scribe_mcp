# 📘 Scribe Doc Management Tool — Design Spec
**Project:** Scribe Security Audit  
**Owner:** Codex (via Scribe)  
**Status:** Draft for Phase 2 planning  
**Last Updated:** 2025-10-25 21:16 UTC

This spec describes a proposed Scribe MCP tool that manages project documentation (Architecture Guide, Phase Plan, Checklist, and future templates) with structured metadata, template selection, and optional SQL-backed history. It supplements `AUD-001`/`AUD-002` audit findings and will guide Phase 2 implementation.

---

## 1. Problem Statement
- Manual editing of `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, and `CHECKLIST.md` leaves no structured audit trail beyond raw git diffs.
- Templates exist but only during bootstrap; subsequent edits cannot leverage template snippets or validation.
- We lack a first-class way to track doc changes in SQLite/Postgres, trigger reminders when docs drift, or enforce Commandment #11 rules within doc updates.

## 2. Goals
1. Provide an MCP tool (`manage_docs` placeholder name) that can:
   - Create or update sections of the core dev-plan docs (and additional templates) via structured operations.
   - Record metadata (agent, timestamp, action, doc, section, reason) in both Markdown and storage backend.
   - Optionally render template fragments (e.g., new phase block, checklist item) before insertion.
2. Unlock SQL analytics for documentation health (who updated, when, section lengths, status).
3. Emit reminders/log entries automatically so `append_entry` reflects doc edits without manual copy/paste.
4. Support future custom documents sourced from `scribe_mcp/templates/` (unused template directory becomes active).

## 3. Non-Goals
- Replacing free-form Markdown editing entirely; direct file edits remain possible but discouraged.
- Handling arbitrary repo files; scope is limited to dev_plans (initially architecture/phase/checklist/progress log, plus registered templates).
- Implementing full doc diff visualization inside the tool (could be follow-up work).

## 4. High-Level Architecture
```
Client -> manage_docs tool (MCP) -> Doc Manager service
                                   -> Template registry (existing templates + new ones)
                                   -> Storage backend (doc_changes table)
                                   -> File writer (with sandbox enforcement)
                                   -> Reminders/logging (auto append_entry hook)
```

- **Doc Manager Service**: new module (`scribe_mcp/doc_management/manager.py`) responsible for validating operations, loading templates, and writing files atomically via existing `utils.files` helpers.
- **Template Registry**: reuses `scribe_mcp/templates` and allows repos to register extra templates (tie-in to plugin system once secured).
- **Storage**: extend storage models to add `doc_changes` table storing doc name, section id, change type, summary, metadata JSON, SHA, and optional diff hash. Include retention policy hooks (e.g., archive records older than N entries per project) to prevent unbounded growth.
- **Reminders + Logging**: tool should call `append_entry` (internal) or return payload so caller logs with `checklist_id` automatically.

## 5. API Sketch (MCP Tool)
`manage_docs(action, doc, section=None, template=None, content=None, metadata=None, dry_run=False)`

| Parameter | Description |
|-----------|-------------|
| `action` | enum: `create`, `update`, `append`, `replace_section`, `status_update`. |
| `doc` | Target doc identifier (`architecture`, `phase_plan`, `checklist`, `custom:<name>`). |
| `section` | Logical anchor (e.g., `problem_statement`, `phase:Audit & Alignment`). Required for section operations. |
| `template` | Optional template name; when provided, `content` fields fill template variables. |
| `content` | Dict or string with data to insert (validated per template or action). |
| `metadata` | Extra context (e.g., `checklist_id`, `reason`, `jira_id`). Stored alongside SQL row + appended to log. |
| `dry_run` | Returns preview diff + rendered content without writing. |

Responses include `ok`, `doc_path`, `section`, `preview_diff`, `written_content`, `storage_record_id`, and `reminders`.

## 6. Workflow Examples
1. **Add a Phase**: `action=append`, `doc=phase_plan`, `template=phase_block`, `content={...}`. Tool renders phase template, appends before “Milestone Tracking”, logs change, updates SQL.
2. **Update Checklist Item**: `action=status_update`, `doc=checklist`, `section=FIX-TESTS`, `content={"status":"done","proof":"PROGRESS_LOG#... "}`. Tool finds matching bullet, toggles `[ ]` -> `[x]`, and records update.
3. **Doc Summary Edit**: `action=replace_section`, `doc=architecture`, `section=problem_statement`, `content="New Markdown"`. Tool replaces the section between heading anchors, recalculates hash, logs.

## 7. Template Handling
- Templates stored under `scribe_mcp/templates/doc_fragments/<name>.md`.
- Each template declares required fields + optional default metadata (YAML front-matter or JSON manifest).
- Tool loads template, merges `content` dict, and renders with existing substitution utilities (extend `substitution_context`). Validate `content` using a schema (e.g., pydantic models) to guarantee required keys/types.
- Repos can add custom templates via plugin once plugin security (AUD-003) is addressed; until then, restrict to built-ins or allowlist.

## 8. Storage & Telemetry
- Add `doc_changes` table (SQLite/Postgres) with columns: `id`, `project_id`, `doc`, `section`, `action`, `agent`, `metadata_json`, `sha_before`, `sha_after`, `created_at`.
- Provide helper queries (`list_doc_changes`, `get_doc_history(doc, section)`).
- Use existing WAL/locking to ensure atomic writes; integrate with WriteAheadLog to recover partial doc edits.

## 9. Security & Permissions
- Enforce sandboxed paths (after fixing AUD-005) before any file write.
- Require stable section identifiers. Each managed section should include an explicit anchor (`<!-- ID: phase_audit_alignment -->` or `{#phase_audit_alignment}`) so replacements are deterministic even if headings change.
- Require explicit opt-in for templates referencing external resources.
- Hooks into reminder system to flag stale docs for projects not using the tool (comparing doc hash stored in SQL vs file hash).
- Integrate with revived permission checker to support repo policies (e.g., only certain agents can edit `phase_plan`). Until policy plugins are secure, provide a repo config flag listing allowed tools or docs per agent.

## 10. Integration with append_entry Enhancements
- `manage_docs` should optionally trigger specialized logs (e.g., `log_type="doc_update"`) once `append_entry` supports multi-log templates (AUD-002). Until then, tool can auto-call `append_entry` with `meta={"doc_action": ...}`.
- Provide config for “doc log” path if multi-log support ships (e.g., `docs/dev_plans/<project>/DOC_LOG.md`).

## 11. Implementation Phases
1. **Foundation (Phase 2)**:
   - Create Doc Manager module + MCP tool skeleton.
   - Implement section detection and template rendering for core docs.
   - Extend storage schema with `doc_changes`.
   - Hook into reminders/logging.
2. **Enhancements**:
   - Add dry-run diff previews (use `difflib`).
   - Support custom docs and template discovery.
   - Integrate with plugin system (post AUD-003 fix).
3. **Future**:
   - UI/CLI wrappers for human operators.
   - Automated verification that doc + plan + checklist stay in sync (e.g., cross-link tasks).

## 12. Testing Strategy
- Unit tests covering template rendering, section replacement, and validation failures.
- Integration tests that run `manage_docs` against temp projects and assert file+SQL outputs.
- Regression tests ensuring WriteAheadLog + atomic write behavior (simulate crash mid-edit).

## 13. Open Questions
| Topic | Notes |
|-------|-------|
| Section Anchors | Finalize anchor format and retrofit existing docs (one-time migration). |
| Custom Template Registry | Do we require repo-level config / allowlist before enabling? |
| Backfill SQL history | Should we parse existing git history to populate `doc_changes` for legacy projects? |
| Permissions | How do we allow certain agents to edit docs while blocking others (tie into permission checker once revived)? |
| Concurrency | Should we implement per-doc async locks or database advisory locks (Postgres) to serialize edits? |
| Retention | What is the default archive policy for `doc_changes`, and how do we expose pruning commands? |

---

## Appendix A — Draft Plan for Multi-Log `append_entry` (AUD-002)

To support bug/suggestion/etc. logs via templates, we will extend `append_entry` with log-routing capabilities.

### Goals
- Allow agents to write to multiple structured logs (e.g., `progress`, `doc_updates`, `bug_log`) without duplicating code paths.
- Each log can customize formatting, template, and file destination while respecting Commandment #1 (all entries recorded via Scribe).
- Configurable via JSON/YAML (per repo) so teams can define arbitrary log types.

### Proposed Design

1. **Config Schema**
   ```json
   {
     "logs": {
       "progress": {
         "path": "docs/dev_plans/<slug>/PROGRESS_LOG.md",
         "template": "default_progress",
         "metadata_requirements": ["checklist_id"]
       },
       "doc_updates": {
         "path": "docs/dev_plans/<slug>/DOC_LOG.md",
         "template": "doc_update",
         "metadata_requirements": ["doc", "section", "action"]
       },
       "bug_log": {
         "path": "docs/dev_plans/<slug>/BUG_LOG.md",
         "template": "bug_entry",
         "metadata_requirements": ["severity", "component"]
       }
     }
   }
   ```

2. **API Changes**
   - Extend `append_entry` parameters with `log_type: str = "progress"`.
   - `items/items_list` inherit the specified log type unless overridden per item.

3. **Template Rendering**
   - Add log-specific templates under `scribe_mcp/templates/logs/<name>.md`.
   - Template defines line format + metadata validation.

4. **File Routing**
   - Look up log definition by `log_type`, resolve file path using current project context, and ensure sandbox compliance.
   - Fallback to progress log if unknown log type (configurable).

5. **Reminders & Metrics**
   - Track per-log stats (entry counts, last update) in storage to power reminders (e.g., “Bug log silent for 7 days?”).

6. **Backward Compatibility**
   - Default config only contains `progress`, so existing behavior is unchanged.
   - CLI wrappers (`scripts/scribe.py`) can gain `--log doc_updates` option.

7. **Testing**
   - Add integration tests ensuring log routing writes to the right file and that templates enforce required metadata.
   - Negative tests for missing metadata or unauthorized log types.

This appendix serves as the initial spec for AUD-002; we can expand it during Phase 2 planning once doc tooling enters implementation.
---

**Next Action:** Review this spec during Phase 1 wrap-up, refine requirements, and schedule implementation tasks in Phase 2 alongside other high-priority fixes.
