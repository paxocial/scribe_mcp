---
id: scribe_mcp_audit-custom_doc
title: Longform Proof Document
doc_type: custom_doc
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-01'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
<!-- TOC:start -->
- [1 Longform Proof Document](#1-longform-proof-document)
  - [1.1 Overview](#11-overview)
  - [1.2 Architecture Narrative](#12-architecture-narrative)
  - [1.3 Workflow Walkthrough](#13-workflow-walkthrough)
  - [1.4 Risk Register](#14-risk-register)
  - [1.5 Implementation Notes](#15-implementation-notes)
  - [1.6 Validation Checklist](#16-validation-checklist)
  - [1.7 Appendix](#17-appendix)
<!-- TOC:end -->

# 1 Longform Proof Document

## 1.1 Overview
This document exists to stress the editing pipeline with a long, structured body that spans multiple sections and formats. It is intentionally verbose, but still clear and technical. The goal is to create enough surface area for structured edits, range edits, and TOC regeneration without relying on fragile anchors.

The text is written in a neutral, engineering-focused tone. It includes narrative paragraphs, bullet lists, tables, and code fences so that the parser must respect fences and headings. All content is ASCII to avoid encoding issues.

## 1.2 Architecture Narrative
The system is a document mutation protocol with a small, explicit surface area. Requests arrive through a tool boundary that performs parameter healing and validation. That boundary must not silently redirect write operations to the wrong document. Instead, strict actions should fail hard when the provided doc key is not registered.

The mutation flow can be described in stages:
- Read: load the target file and parse frontmatter if present.
- Isolate: operate on body-only text so frontmatter does not shift line math.
- Mutate: apply structured edit operations deterministically.
- Reattach: rejoin frontmatter and body and write atomically.
- Verify: compute hashes, record verification, and emit diagnostics.

A central rule is idempotency. If a tool is run twice, the second run should not introduce changes. This prevents feedback loops in automation and makes diffs predictable for human review.

## 1.3 Workflow Walkthrough
A normal workflow begins with a structured edit request. The edit describes intent, not diffs. The server compiles a safe diff and applies it in a single mutation engine. If the edit is ambiguous or the context does not match, the operation fails with diagnostics and no file change.

The workflow also supports a normalize step that re-numbers headings and converts Setext to ATX. Once normalized, a table of contents can be generated deterministically using the same anchor algorithm as header extraction. This ensures that anchors are consistent across operations.

Example pseudo-process:
```
request -> validate -> parse frontmatter -> mutate body -> reattach -> write -> verify
```

## 1.4 Risk Register
This section was revised to simulate a complicated edit. It now includes a longer explanation plus an embedded table.

- Risk: ambiguous anchor matches cause incorrect edits
  - Mitigation: error on multiple matches and report line numbers
- Risk: doc key mismatch routes edits to the wrong file
  - Mitigation: registry-based doc validation; fail hard on missing keys
- Risk: TOC generation diverges from anchor extraction
  - Mitigation: use a single anchor algorithm for both

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Anchor ambiguity | High | Hard fail + diagnostics |
| Wrong-file mutation | High | Registry validation |
| Anchor drift | Medium | Shared anchor builder |

- Risk: silent doc healing changes the wrong file
  - Mitigation: strict doc validation against project registry
- Risk: anchor matching inside fenced code blocks
  - Mitigation: skip fenced blocks in match logic
- Risk: idempotency breaks on second run
  - Mitigation: add idempotency tests for normalize_headers and generate_toc
- Risk: metadata sanitization strips newlines
  - Mitigation: preserve newlines in content fields
## 1.5 Implementation Notes
This section mixes long paragraphs with short lists to create varied structures. The intent is to ensure that replace_block and replace_range can operate safely even when the paragraph structure is uneven.

Key design notes:
1. Actions that write to disk must never auto-correct the doc target.
2. Doc keys must be validated against the project registry before write.
3. A single mutation engine must apply all edits for consistent diagnostics.
4. Frontmatter must be preserved unless explicitly updated.
5. All structured edits must report diagnostics on failure.

Short paragraph to increase density and length without changing meaning. This helps simulate the longer documents used in audit and release workflows.

## 1.6 Validation Checklist
The following checklist is intentionally verbose to support complicated edits, including replacing and reordering items.

- [ ] Confirm that create_doc preserves newlines in metadata body fields.
- [ ] Confirm normalize_headers handles ATX without space and Setext styles.
- [ ] Confirm generate_toc uses GitHub-style anchors with unicode folding.
- [ ] Confirm structured edits fail on ambiguous anchors with line lists.
- [ ] Confirm structural actions do not mutate the wrong document.
- [ ] Confirm doc registry updates surface warnings on failure.

## 1.7 Appendix
Table of example metrics:

| Metric | Target | Notes |
| --- | --- | --- |
| Idempotency | 100% | Second run produces no diff |
| Anchor parity | 100% | Matches GitHub anchor generation |
| Mutation safety | 100% | No wrong-file writes |

Closing note: this document is a controlled stress case. It is meant to be edited, normalized, and re-toc'd as part of a sanity pass.
