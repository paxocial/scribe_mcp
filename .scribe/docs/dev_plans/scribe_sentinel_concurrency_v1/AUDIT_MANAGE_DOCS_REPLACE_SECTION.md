---
id: scribe_sentinel_concurrency_v1-audit_replace_section
title: 'Audit: manage_docs replace_section & apply_patch'
doc_type: audit_replace_section
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-02'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Audit: manage_docs replace_section & apply_patch

## Scope
- Verify replace_section replacement semantics (no duplication, correct bounds, anchor validation).
- Verify apply_patch correctness (context matching, stale detection, diagnostics).
- Identify concurrency or repeated-call risks in doc updates.

## Current observations
- replace_section replaces the first matching anchor and stops at the next <!-- ID: --> marker.
- If the anchor is missing, replace_section auto-appends a new block instead of failing.
- apply_patch requires strict unified diff context; errors are explicit (PATCH_CONTEXT_MISMATCH, PATCH_DELETE_MISMATCH).

## Issues encountered during audit
- list_sections returns duplicate anchors without warning; no guardrails for ambiguity.
- list_checklist_items does not surface section context, so duplicates are harder to diagnose.
- manage_docs create_doc/apply_patch require doc registration; failures are not auto-healed.
- create_doc requires overwrite flag when file exists, which adds friction for iterative edits.
- FRONTMATTER_PARSE_ERROR occurs when frontmatter contains YAML '...' end marker, blocking any manage_docs updates.
- Invalid action auto-corrections (replace_section/append) can cause unintended edits instead of failing fast.
- Documentation still references legacy .scribe/scribe.yaml path instead of .scribe/config/scribe.yaml.

## Open questions
- Should replace_section fail fast on missing anchor for non-scaffold edits?
- Should duplicate anchors be detected and blocked before replace_section/apply_patch executes?
- Should apply_patch require patch_source_hash by default for checklist/docs to prevent replays?

## Output readability requests
- Reorder tool call payloads so context appears last (input readability).
- Reorder tool responses so user-facing fields appear first and context/reminders appear last.
- Evaluate token-guarding strategies to avoid repeating static context every call.

## Next steps
- Audit manage_docs wrapper healing paths for silent corrections.
- Review list_sections/list_checklist_items behavior with duplicate anchors.
- Propose hardening changes + tests for approval.
