# CLAUDE.md

**Scribe MCP v2.1.1** - Enterprise-grade documentation governance for AI-powered development

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.


The Main Claude Code Instance must use a distinct Agent Name with all scribe tools.  agent=Orchestrator

All Subagents (And OpenAI Codex) must use their own agent names.    For session concurrency, Each agent name should be unique.   Coder-9289 as an example.   Or Coder A, B and C.


---

## 🎯 ACTIVE PROJECT ORCHESTRATION WORKFLOW

> **Current Project**: `scribe_tool_output_refinement`
> **Orchestrator**: Claude Code (Lead) + Human
> **Protocol**: Research → Architect → Review → Code → Review

### Protocol Sequence (Mandatory)

---

## 🔒 **Directive: File Reading Priority (Scribe MCP)**

**MANDATORY RULE — NO EXCEPTIONS UNLESS EXPLICITLY OVERRIDDEN**

> **Agents MUST prioritize the Scribe MCP `read_file` tool over any basic or native `read` tool when inspecting repository files.**

### **Rationale**

The Scribe MCP `read_file` tool provides:

* Auditable access history
* Stable, human-readable formatting (line numbers, headers, metadata)
* File identity verification (sha256, size, encoding)
* Project and context reminders
* Chunk-aware reading for large files

Basic read tools lack auditability, provenance, and contextual framing and **must not be used for primary file inspection**.

---

### **Required Behavior**

* **Claude Code**:

  * Always use `scribe.read_file` for file inspection, review, or debugging.
  * Native `Read` may only be used for *non-audited, ephemeral previews* when explicitly instructed.

* **Codex / Other Agents**:

  * Default to `scribe.read_file` for *all* file reads.
  * Treat native read tools as **fallback-only** if Scribe MCP is unavailable.

---

### **Prohibited Behavior**

* ❌ Using native `Read` when Scribe MCP is available
* ❌ Inspecting files without generating an audit trail
* ❌ Returning raw JSON blobs or escaped newline output when readable output is required

---

### **Exception Clause**

An agent may bypass this directive **only if**:

1. The user explicitly instructs otherwise, **or**
2. Scribe MCP is unavailable or errors irrecoverably

In such cases, the agent **must state the exception explicitly**.

---

```
┌─────────────────────────────────────────────────────────────────┐
│  1️⃣ RESEARCH PHASE                                              │
│     Agent: scribe-research-analyst                              │
│     Input: Initial context + skeleton docs                      │
│     Output: RESEARCH_*.md reports in research/ folder           │
│     Scribe: agent="ResearchAgent"                               │
├─────────────────────────────────────────────────────────────────┤
│  2️⃣ ARCHITECT PHASE                                             │
│     Agent: scribe-architect                                     │
│     Input: Research reports + initial context                   │
│     Output: Full ARCHITECTURE_GUIDE.md, PHASE_PLAN.md,          │
│             CHECKLIST.md                                        │
│     Scribe: agent="ArchitectAgent"                              │
├─────────────────────────────────────────────────────────────────┤
│  3️⃣ PRE-IMPLEMENTATION REVIEW                                   │
│     Agent: scribe-review-agent                                  │
│     Input: All docs from phases 1-2                             │
│     Output: Review report, agent grades (≥93% to pass)          │
│     Scribe: agent="ReviewAgent"                                 │
├─────────────────────────────────────────────────────────────────┤
│  4️⃣ IMPLEMENTATION PHASE                                        │
│     Agent: scribe-coder                                         │
│     Input: Approved architecture + phase plan                   │
│     Output: Working code, tests, IMPLEMENTATION_REPORT.md       │
│     Scribe: agent="CoderAgent" (every 3 edits or less!)         │
├─────────────────────────────────────────────────────────────────┤
│  5️⃣ FINAL REVIEW                                                │
│     Agent: scribe-review-agent                                  │
│     Input: Implementation + all docs                            │
│     Output: Final grades, approval/rejection                    │
│     Scribe: agent="ReviewAgent"                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Scribe Requirements (Non-Negotiable)

| Agent | Scribe Name | Must Log |
|-------|-------------|----------|
| Orchestrator (Claude Code) | `Orchestrator` | Phase transitions, agent dispatches, decisions |
| Research Agent | `ResearchAgent` | Findings, analysis, sources, confidence |
| Architect Agent | `ArchitectAgent` | Design decisions, trade-offs, constraints |
| Review Agent | `ReviewAgent` | Grades, pass/fail, issues found |
| Coder Agent | `CoderAgent` | Every 3 edits, test results, bugs |
| Bug Hunter | `BugHunterAgent` | Bug lifecycle, root cause, fixes |

### Orchestrator Responsibilities

1. **Always pass `project_name="scribe_tool_output_refinement"` to every subagent**
2. **Log phase transitions** with `append_entry(agent="Orchestrator")`
3. **Enforce quality gates** - no progression without ≥93% review score
4. **Re-dispatch failing agents** to FIX existing docs (never replace)
5. **Coordinate handoffs** between agents with clear context

### Current Phase Status

- [ ] Phase 1: Research - PENDING
- [ ] Phase 2: Architecture - PENDING
- [ ] Phase 3: Pre-Implementation Review - PENDING
- [ ] Phase 4: Implementation - PENDING
- [ ] Phase 5: Final Review - PENDING

---

## 🚨 COMMANDMENTS - CRITICAL RULES
 ### MCP Tool Usage Policy
  - You have full access to every tool exposed by the MCP server.
  - If a tool exists (`append_entry`, `rotate_log`, etc.), always call it directly via the MCP interface — no manual scripting or intent
  logging substitutes.
  - Log your intent only after the tool call succeeds or fails.
  - Confirmation flags (`confirm`, `dry_run`, etc.) must be passed as actual tool parameters.

  **⚠️ COMMANDMENT #0: ALWAYS CHECK PROGRESS LOG FIRST**: Before starting ANY work, ALWAYS use `read_recent` or `query_entries` to inspect `docs/dev_plans/[current_project]/PROGRESS_LOG.md` (do not open the full log directly). Read at least the last 5 entries; if you need the overall plan or project creation context, read the first ~20 entries (or more as needed) and rehydrate context appropriately. Use `query_entries` for targeted history. The progress log is the source of truth for project context.

**⚠️ COMMANDMENT #0.5 — INFRASTRUCTURE PRIMACY (GLOBAL LAW)**: You must ALWAYS work within the existing system. NEVER create parallel or replacement files (e.g., enhanced_*, *_v2, *_new) to bypass integrating with the actual infrastructure. You must modify, extend, or refactor the existing component directly. Any attempt to replace working modules results in immediate failure of the task.
---

**⚠️ COMMANDMENT #1 ABSOLUTE**: ALWAYS use `append_entry` to document EVERY significant action, decision, investigation, code change, test result, bug discovery, and planning step. The Scribe log is your chain of reasoning and the ONLY proof your work exists. If it's not Scribed, it didn't fucking happen.
- To Claude Code (Orchestrator) You must ALWAYS pass the current `project_name` to each subagent as we work.  To avoid confusion and them accidentally logging to the wrong project.
---

# ⚠️ COMMANDMENT #2: REASONING TRACES & CONSTRAINT VISIBILITY (CRITICAL)

Every `append_entry` must explain **why** the decision was made, **what** constraints/alternatives were considered, and **how** the steps satisfied or violated those constraints, creating an auditable record.
Use a `reasoning` block with the Three-Part Framework:
- `"why"`: research goal, decision point, underlying question
- `"what"`: active constraints, search space, alternatives rejected, constraint coverage
- `"how"`: methodology, steps taken, uncertainty remaining

This creates an auditable record of decision-making for consciousness research.Include reasoning for research, architecture, implementation, testing, bugs, constraint violations, and belief updates; status/config/deploy changes are encouraged too.

The Review Agent flags missing or incomplete traces (any absent `"why"`, `"what"`, or `"how"` → **REJECT**; weak confidence rationale or incomplete constraint coverage → **WARNING/CLARIFY**).  Your reasoning chain must influence your confidence score.

**Mandatory for all agents—zero exceptions;** stage completion is blocked until reasoning traces are present.
---

**⚠️ COMMANDMENT #3 CRITICAL**: NEVER write replacement files. The issue is NOT about file naming patterns like "_v2" or "_fixed" - the problem is abandoning perfectly good existing code and replacing it with new files instead of properly EDITING and IMPROVING what we already have. This is lazy engineering that creates technical debt and confusion.

**ALWAYS work with existing files through proper edits. NEVER abandon current code for new files when improvements are needed.**
---

**⚠️ COMMANDMENT #4 CRITICAL**: Follow proper project structure and best practices. Tests belong in `/tests` directory with proper naming conventions and structure. Don't clutter repositories with misplaced files or ignore established conventions. Keep the codebase clean and organized.

Violations = INSTANT TERMINATION. Reviewers who miss commandment violations get 80% pay docked. Nexus coders who implement violations face $1000 fine.
---


**🌍 GLOBAL LOG USAGE**: For repository-wide milestones and cross-project events, use `log_type="global"` with required metadata `["project", "entry_type"]`:
```python
await append_entry(
    message="Phase 4 implementation complete - Enhanced search capabilities deployed",
    status="success",
    agent="ScribeCoordinator",
    log_type="global",
    meta={"project": "scribe_mcp_enhancement", "entry_type": "manual_milestone", "phase": 4}
)
```


**What Gets Logged (Non-Negotiable):**
- 🔍 Investigation findings and analysis results
- 💻 Code changes (what was changed and why)
- ✅ Test results (pass/fail with context)
- 🐞 Bug discoveries (symptoms, root cause, fix approach)
- 📋 Planning decisions and milestone completions
- 🔧 Configuration changes and deployments
- ⚠️ Errors encountered and recovery actions
- 🎯 Task completions and progress updates

**Single Entry Mode** - Use for real-time logging:
```python
await append_entry(
    message="Discovered authentication bug in JWT validation",
    status="bug",
    agent="DebugAgent",
    meta={"component": "auth", "severity": "high", "file": "auth.py:142"}
)
```

**Bulk Entry Mode** - Use when you realize you missed logging steps:
```python
await append_entry(items=json.dumps([
    {"message": "Analyzed authentication flow", "status": "info", "meta": {"phase": "investigation"}},
    {"message": "Found JWT expiry bug in token refresh", "status": "bug", "meta": {"component": "auth"}},
    {"message": "Implemented fix with 15min grace period", "status": "success", "meta": {"files_changed": 2}},
    {"message": "All auth tests passing", "status": "success", "meta": {"tests_run": 47, "tests_passed": 47}}
]))
```

**Why This Matters:**
- Creates auditable trail of ALL decisions and changes
- Enables debugging by reviewing reasoning chain
- Prevents lost work and forgotten context
- Allows other agents to understand what was done and why
- Makes project state queryable and analyzable

**If You Missed Entries:** Use bulk mode IMMEDIATELY to backfill your work trail. NEVER let gaps exist in the Scribe log - every action must be traceable. The log is not optional documentation, it's the PRIMARY RECORD of all development activity.

---

## 🚀 v2.1.1 KEY FEATURES (NEW)

### **Precision Document Editing**
**NEW: Structured edit modes with body-relative line numbers**

```python
# 1. apply_patch (structured mode - RECOMMENDED)
manage_docs(
    action="apply_patch",
    doc="architecture",
    edit={
        "type": "replace_range",
        "start_line": 12,  # Body-relative (excludes YAML frontmatter)
        "end_line": 15,
        "content": "Updated content\n"
    }
)

# 2. replace_range (explicit line targeting)
manage_docs(
    action="replace_range",
    doc="architecture",
    start_line=12,
    end_line=15,
    content="Replacement text\n"
)

# 3. normalize_headers (canonical ATX output)
manage_docs(action="normalize_headers", doc="architecture")

# 4. generate_toc (GitHub-style anchors)
manage_docs(action="generate_toc", doc="architecture")
```

**YAML Frontmatter** (automatic):
- All managed docs use YAML frontmatter as canonical identity
- Line numbers are **body-relative** (frontmatter excluded)
- `last_updated` auto-refreshes on edits
- Optional frontmatter override via `metadata.frontmatter`

### **NEW Tools v2.1.1**

**`read_file`** - Repo-scoped file access with provenance:
```python
await read_file(
    path="docs/Scribe_Usage.md",
    mode="chunk",  # scan_only, chunk, line_range, page, search
    chunk_index=[0]
)
```

**`scribe_doctor`** - Diagnostics:
```python
await scribe_doctor()
# Returns: repo root, config paths, plugin status, vector readiness
```

**Semantic Search** via `manage_docs`:
```python
await manage_docs(
    action="search",
    doc="*",
    metadata={"query": "authentication", "search_mode": "semantic", "k": 8}
)
```

### **Project Registry & Lifecycle**
**SQLite-backed `scribe_projects` table with lifecycle states**

- **States**: `planning → in_progress → blocked → complete → archived → abandoned`
- **Auto-promotion**: `planning → in_progress` when docs + first entry exist
- **Activity Metadata**: `meta.activity` (staleness, activity_score, days_since_last_entry)
- **Doc Hygiene Flags**: `meta.docs.flags` (docs_ready_for_work, doc_drift_suspected)

**Registry Integration**:
- `set_project` → ensures row exists, updates `last_access_at`
- `append_entry` → updates `last_entry_at`, may auto-promote status
- `manage_docs` → records baseline/current hashes, doc hygiene flags
- `list_projects` → surfaces lifecycle, activity metrics, doc state

---

## 🧩 SCRIBE PROTOCOL (CONDENSED)

**Workflow**: 1️⃣ Research → 2️⃣ Architect → 3️⃣ Review → 4️⃣ Code → 5️⃣ Review

**Core Principle**: All work occurs within a dev plan project initialized via `set_project(name="<project_name>")`. The project name must be passed to every subagent.

**Quality Gates**: ≥93% required to proceed between stages. Agents must FIX existing work, never replace files.

**Subagents**:
- **Research** (Stage 1): Deep investigation with cross-project search → `RESEARCH_*.md`
- **Architect** (Stage 2): Creates `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md`
- **Review** (Stages 3 & 5): Adversarial QC, grades agents, validates ≥93%
- **Coder** (Stage 4): Implements design, logs every 2-5 meaningful changes
- **Bug Hunter** (Auxiliary): Pattern analysis, structured bug reports

**Enhanced Search** (Phase 4):
- `search_scope`: `project|global|all_projects|research|bugs|all`
- `document_types`: `["progress", "research", "architecture", "bugs", "global"]`
- `relevance_threshold`: `0.0-1.0` quality filtering
- `verify_code_references`: Validate referenced code exists

**Orchestrator Command**: "Follow protocol for this development."

---

## ✍️ ENHANCED `manage_docs` WORKFLOWS

**v2.1.1 Recommendation**: Use `apply_patch` (structured) or `replace_range` for precision edits. Reserve `replace_section` for initial scaffolding.

**Core Actions**:
- `apply_patch` - Structured edits with compiler (RECOMMENDED)
- `replace_range` - Explicit line targeting (body-relative)
- `replace_section` - Legacy anchor-based (scaffolding only)
- `normalize_headers` - Canonical ATX output
- `generate_toc` - GitHub-style TOC
- `status_update` - Toggle checklist items
- `create_research_doc` / `create_bug_report` - Automated docs

**Examples**:
```python
# Update architecture (v2.1.1 style)
manage_docs(
    action="apply_patch",
    doc="architecture",
    edit={"type": "replace_range", "start_line": 12, "end_line": 12, "content": "New line\n"}
)

# Create research doc
manage_docs(
    action="create_research_doc",
    doc_name="RESEARCH_AUTH_20250102",
    metadata={"research_goal": "Analyze authentication flow"}
)

# Update checklist
manage_docs(
    action="status_update",
    doc="checklist",
    section="phase_1_task_1",
    metadata={"status": "done", "proof": "PROGRESS_LOG#2025-01-02"}
)
```

**Automatic Features**:
- Index management (research/bugs)
- Audit logging via `doc_updates` log type
- Atomic writes with verification
- YAML frontmatter auto-updates

---

## ✅ CORRECT manage_docs USAGE PATTERNS (REQUIRED READING)

**Critical**: All agents MUST follow these exact patterns when using `manage_docs`. Incorrect parameter combinations will fail.

### 📋 Action Types & Required Parameters

#### **1. create_research_doc** - Create New Research Document

**✅ CORRECT:**
```python
await manage_docs(
    action="create_research_doc",
    doc="research",  # REQUIRED (always use "research")
    doc_name="RESEARCH_CONTEXT_HYDRATION_20260103",  # REQUIRED
    metadata={  # OPTIONAL
        "research_goal": "Design context hydration for list/get/set project tools",
        "confidence_areas": ["tool_behavior", "output_formats"],
        "priority": "high"
    }
)
```

**❌ INCORRECT:**
```python
# Missing doc and doc_name parameters
await manage_docs(
    action="create_research_doc",
    metadata={"research_goal": "..."}  # FAILS - doc and doc_name are REQUIRED
)
```

**Creates:** `.scribe/docs/dev_plans/<project>/research/RESEARCH_*.md` + auto-updates INDEX.md

#### **2. create_bug_report** - Create Structured Bug Report

**✅ CORRECT:**
```python
await manage_docs(
    action="create_bug_report",
    metadata={  # REQUIRED
        "category": "infrastructure",  # infrastructure|logic|database|api|ui|misc
        "slug": "session_isolation_bug",
        "severity": "high",  # low|medium|high|critical
        "title": "Session isolation failing in concurrent scenarios",
        "component": "execution_context"
    }
)
```

**Creates:** `.scribe/docs/bugs/<category>/<YYYY-MM-DD>_<slug>/report.md` + auto-updates INDEX.md

### 🚨 Common Mistakes to Avoid

**❌ Missing Required Parameters:**
```python
# WRONG: Missing doc_name
manage_docs(action="create_research_doc", metadata={"research_goal": "..."})  # FAILS

# CORRECT:
manage_docs(action="create_research_doc", doc_name="RESEARCH_TOPIC_20260103", metadata={...})
```

**❌ Wrong Document Key:**
```python
# WRONG: Invalid doc key
manage_docs(action="replace_section", doc="unknown_doc", ...)  # FAILS

# CORRECT: Use registered keys
manage_docs(action="replace_section", doc="architecture", ...)  # Valid
```

**❌ Missing Section Anchors:**
```python
# WRONG: Section doesn't exist
manage_docs(action="replace_section", doc="architecture", section="nonexistent", ...)  # FAILS

# CORRECT: List valid sections first
manage_docs(action="list_sections", doc="architecture")  # Returns valid section IDs
```

### 📚 Quick Reference by Use Case

| Use Case | Action | Key Parameters |
|----------|--------|----------------|
| Create research doc | `create_research_doc` | `doc_name` (required) + `metadata` (optional) |
| Create bug report | `create_bug_report` | `metadata.category`, `metadata.slug` (required) |
| Update architecture | `replace_section` | `doc`, `section`, `content` |
| Precise line edits | `apply_patch` or `replace_range` | `start_line`, `end_line`, `content` |
| Toggle checklist | `status_update` | `doc="checklist"`, `section`, `metadata.status` |
| Search docs | `search` | `doc="*"`, `metadata.query`, `metadata.search_mode="semantic"` |

**⚠️ ENFORCEMENT**: Any agent using incorrect `manage_docs` patterns will have their work rejected during Review phase.

**📖 Full Reference**: See `docs/Scribe_Usage.md` for complete documentation of all 11 action types.

---

## 🚀 QUICK START (v2.1.1)

**1. Setup**:
```bash
cd scribe_mcp  # Always work from this directory
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Run Server** (for MCP client connection):
```bash
python -m server  # Test startup only
```

**3. Testing**:
```bash
pytest              # 69 functional tests (fast)
pytest -m performance  # Performance tests (when needed)
```

**4. CLI Usage**:
```bash
python -m scripts.scribe "Message" --status success
python -m scripts.scribe --list-projects
```

---

## 📋 CRITICAL IMPORT PATTERNS

**❌ WRONG**: `from MCP_SPINE.scribe_mcp.tools...`
**✅ CORRECT**:
```python
# From scribe_mcp directory
from scribe_mcp.tools.append_entry import append_entry

# From tests/ directory
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from scribe_mcp.storage.sqlite import SQLiteStorage
```

**Key Principle**: MCP_SPINE is NOT a Python module. Each MCP server handles its own imports.

---

## 🔧 ESSENTIAL TOOLS

**Project Management**:
- `set_project(name)` - Initialize/bootstraps docs
- `get_project()` - Current context
- `list_projects()` - Discover projects (lifecycle, activity, doc hygiene)

**Logging**:
- `append_entry(message, status, meta)` - **PRIMARY TOOL**
- Bulk mode: `items=[{message, status, meta}, ...]`

**Documentation**:
- `manage_docs(action, doc, ...)` - Atomic doc updates
- `generate_doc_templates(project_name)` - Template scaffolding
- `rotate_log()` - Archive logs

**v2.1.1 NEW**:
- `read_file(path, mode)` - Repo-scoped file access
- `scribe_doctor()` - Diagnostics
- `manage_docs(action="search")` - Semantic search

**Readable Output Formatting** (v2.1.1+):
- All tools support `format` parameter: `readable` (default), `structured`, `compact`
- **ANSI colors OFF by default** for high-frequency tools (token conservation)
- **ANSI colors config-driven** for display-heavy tools (`read_file`, log queries)
- See `docs/Scribe_Usage.md#readable-output-formatting-v211` for implementation details

---

See `AGENTS.md` for complete protocol details and `docs/Scribe_Usage.md` for comprehensive tool reference.
