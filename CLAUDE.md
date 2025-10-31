# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🚨 COMMANDMENTS - CRITICAL RULES

**⚠️ COMMANDMENT #0: ALWAYS CHECK PROGRESS LOG FIRST**: Before starting ANY work, ALWAYS read `docs/dev_plans/[current_project]/PROGRESS_LOG.md` to understand what has been done, what mistakes were made, and what the current state is. The progress log is the source of truth for project context.
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

# 🧩 SCRIBE PROTOCOL — DEVELOPMENT ORCHESTRATION STANDARD

> **Purpose:** The Scribe Protocol defines how Claude Code orchestrates subagents during a structured development cycle.
> Invoking it (“follow protocol for this development”) triggers a full-cycle workflow using the Scribe MCP toolchain.

---

## 🧭 Core Principle

All work must occur within a defined **dev plan project** initialized via:

```python
await set_project(name="<project_name>")
```

The `<project_name>` **must be passed to every subagent** for the duration of the protocol.
All agents use Scribe tools (`append_entry`, `manage_docs`, etc.) for logging, documentation, and verification.

---

## ⚙️ Subagents Overview

| Agent                | Role                                                                                                                                                        | Primary Tools                                                                           | Stage            |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ---------------- |
| **Research Agent**   | Performs deep codebase and documentation research with cross-project search capabilities. Produces detailed reports under `docs/dev_plans/<project>/research/`. | `set_project`, `append_entry`, `manage_docs`, `query_entries` (Phase 4 enhanced)        | **Stage 1**      |
| **Architect Agent**  | Converts approved research into concrete system plans with architectural pattern validation. Creates `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md`. | `set_project`, `get_project`, `append_entry`, `manage_docs`, `query_entries` (Phase 4) | **Stage 2**      |
| **Review Agent**     | Performs adversarial quality control with cross-project validation. Operates twice: pre-implementation (Stage 3) and post-implementation (Stage 5). Grades all agents. | `set_project`, `append_entry`, `manage_docs`, `pytest`, `query_entries` (Phase 4)        | **Stages 3 & 5** |
| **Coder Agent**      | Implements approved design with implementation reference search. Logs every meaningful change and test result.                                               | `set_project`, `append_entry`, `manage_docs`, `pytest`, `query_entries` (Phase 4)        | **Stage 4**      |
| **Bug Hunter Agent** | Diagnoses defects with bug pattern analysis across projects. Creates structured bug reports with automatic indexing.                                        | `set_project`, `append_entry(log_type="bug")`, `manage_docs`, `pytest`, `query_entries` | **Auxiliary**    |

---

## 🔁 Protocol Sequence

> **Canonical Chain:**
> **1 Research → 2 Architect → 3 Review → 4 Code → 5 Review**

### 1️⃣ Research Phase

* Claude Code refines the task with the user and defines a precise scope.
* Calls **Research Agent** with the project name and clear objectives.
* Research Agent produces one or more reports (`RESEARCH_*.md`) and logs discoveries.
* If multiple reports exist, an `INDEX.md` must be generated.

### 2️⃣ Architecture Phase

* Claude Code calls **Architect Agent**, passing the same project name.
* Architect reviews the research, checks feasibility in the codebase, and fills out:

  * `ARCHITECTURE_GUIDE.md`
  * `PHASE_PLAN.md`
  * `CHECKLIST.md`
* Marks completion via `append_entry(agent="Architect", status="success")`.

### 3️⃣ Pre-Implementation Review

* **Review Agent** audits the research and architectural documents.
* Confirms technical feasibility, coherence, and readiness.
* Grades each agent; ≥ 93 % required to proceed.
* If any fail, Claude Code re-dispatches the failing agents to fix their work (never replace files).
  - **CRITICAL**: Agents MUST FIX THEIR EXISTING DOCUMENTS, NOT CREATE NEW ONES. NO CLUTTER. FIX AND REFINE THE DOCUMENTS/CODE.

### 4️⃣ Implementation Phase

* Upon passing review, **Coder Agent** implements the plan.
* Logs every 2–5 meaningful commits, test results, and decisions.
* Creates `IMPLEMENTATION_REPORT_<timestamp>.md`.
* Stops immediately if requirements are ambiguous or architecture changes mid-task.

### 5️⃣ Final Review

* **Review Agent** runs again, verifying implementation, tests, and documentation.
* Executes `pytest`, ensures checklists are complete, and issues final grades.
* If all ≥ 93 %, the project is approved; otherwise, corrections are assigned.

---

## 🔍 Phase 4 Enhanced Search Capabilities

All subagents now have enhanced search capabilities that enable cross-project learning and validation:

### **Enhanced Search Parameters:**
- **search_scope**: `project`|`global`|`all_projects`|`research`|`bugs`|`all`
- **document_types**: `["progress", "research", "architecture", "bugs", "global"]`
- **relevance_threshold**: `0.0-1.0` quality filtering
- **verify_code_references**: Validate referenced code exists
- **time_range**: Temporal filtering (`"last_30d"`, `"last_7d"`, `"today"`)

### **Cross-Project Learning:**
- **Research Agent**: Search existing research across all projects before starting new investigations
- **Architect Agent**: Validate architectural patterns with cross-project search
- **Coder Agent**: Find similar implementations before coding new features
- **Review Agent**: Use cross-project validation for quality assurance
- **Bug Hunter**: Search for related bug patterns across projects

### **Global Repository Log:**
Use `log_type="global"` for repository-wide milestones:
```python
await append_entry(
    message="Phase 4 complete - Enhanced search deployed",
    status="success",
    agent="ScribeCoordinator",
    log_type="global",
    meta={"project": "project_name", "entry_type": "phase_complete", "phase": 4}
)
```

## 🔄 Parallel Execution Guidelines

* **Research Agents**: Can work in parallel on different aspects if aware of each other and have specific, non-overlapping deliverables
* **Coder Agents**: Can work in parallel if scope doesn't overlap
* **Review Agent**: Can be used for security audits outside of specific projects
* **Coordination**: Parallel agents must be aware of each other's goals and target files/deliverables

## 📝 Log Types and Usage

* **progress**: Primary log type for most development activities
* **bug**: Used exclusively by Bug Hunter for bug lifecycle tracking
* **doc_updates**: Automatically used by manage_docs for documentation changes
* **security**: For security-related events and audits
* **Other types**: Can be configured in `config/log_config.json`

---

## 🐞 Bug Handling (Parallel Path)

At any stage, if a defect is discovered:

1. Claude Code calls **Bug Hunter** with the same project name and a short slug.
2. Bug Hunter creates a folder:

   ```
   docs/bugs/<category>/<YYYY-MM-DD>_<slug>/
   ```
3. Writes `report.md`, reproduction test, and updates `/docs/bugs/INDEX.md`.
4. Logs lifecycle events (`investigation → fixed → verified`) via `append_entry(log_type="bug")`.

---

## 🧾 Completion and Closure

* Once the final review passes:

  * All documentation (`ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md`, `IMPLEMENTATION_REPORT`) must be present and up-to-date.
  * All logs are archived using `rotate_log()`.
  * (Optional) Claude Code may compile summaries into `/docs/wiki/` for public reference.

---

## 🎭 Claude Code Orchestrator Responsibilities

**🚨 CRITICAL ORCHESTRATOR DUTIES:**

### **1. Project Management**
- **Always** obtain clear task definition and project name from user
- **Always** call `set_project(project_name)` before any subagent work
- **Always** pass the exact same `project_name` to EVERY subagent in their prompts
- **Never** allow agents to work without proper project context

### **2. Protocol Enforcement**
- **Strict 1→2→3→4→5 sequence** - no skipping stages
- **Quality Gates**: ≥93% required to proceed between stages
- **Agent Coordination**: Monitor handoffs and ensure proper documentation
- **Error Recovery**: Re-dispatch failing agents to FIX existing work, never replace

### **3. Enhanced Search Orchestration**
Direct agents to use Phase 4 capabilities when relevant:
- **Research Agent**: "Search across all projects with `search_scope='all_projects'` and `document_types=['research']` for related investigations"
- **Architect Agent**: "Validate architectural patterns using `query_entries(search_scope='all_projects', document_types=['architecture', 'research'])`"
- **Coder Agent**: "Search for similar implementations with `query_entries(search_scope='all_projects', document_types=['progress'], verify_code_references=True)`"
- **Review Agent**: "Use cross-project validation with `query_entries(search_scope='all', relevance_threshold=0.9)` for quality assurance"
- **Bug Hunter**: "Search for bug patterns with `query_entries(search_scope='all_projects', document_types=['bugs'])`"

### **4. Global Log Coordination**
Ensure repository-wide milestones are properly logged:
- Phase completions: `log_type="global"` with `entry_type="phase_complete"`
- Architectural decisions: `log_type="global"` with `entry_type="architecture_complete"`
- Implementation milestones: `log_type="global"` with `entry_type="implementation_complete"`
- Security audits: `log_type="global"` with `entry_type="security_audit"`

### **5. Quality Assurance**
- **Review agent outputs** before proceeding to next stage
- **Verify documentation completeness** at each handoff
- **Confirm proper Scribe logging** by all agents
- **Validate file creation** and indexing updates

### **6. Comprehensive Subagent Directory**

**Available Subagents for Deployment:**

#### **🔍 scribe-research-analyst** (Stage 1)
- **Purpose**: Deep codebase investigation and research documentation
- **Deploy When**: User needs comprehensive understanding of existing systems
- **Key Capabilities**: Cross-project research, code reference verification, structured report generation
- **Output**: `RESEARCH_<topic>_<timestamp>.md` files in `docs/dev_plans/<project>/research/`
- **Prompt Requirement**: Always include `project_name="<current_project>"` and specific investigation objectives

#### **🏗️ scribe-architect** (Stage 2)
- **Purpose**: Convert research into actionable technical plans
- **Deploy When**: Research is complete and architectural planning is needed
- **Key Capabilities**: Architectural design, phase planning, checklist creation, feasibility validation
- **Output**: `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md`
- **Prompt Requirement**: Always include `project_name="<current_project>"` and reference to completed research

#### **🔍 scribe-review-agent** (Stages 3 & 5)
- **Purpose**: Adversarial quality control and validation
- **Deploy When**: Pre-implementation review (Stage 3) or post-implementation validation (Stage 5)
- **Key Capabilities**: Cross-project validation, security auditing, agent grading, quality gates
- **Output**: Review reports, agent grades, quality assessments
- **Prompt Requirement**: Always include `project_name="<current_project>"` and specific review scope

#### **💻 scribe-coder** (Stage 4)
- **Purpose**: Implement approved architectural designs
- **Deploy When**: Architecture is approved and implementation is ready
- **Key Capabilities**: Code implementation, testing, implementation reference search, bug reporting
- **Output**: Working code, test results, implementation reports
- **Prompt Requirement**: Always include `project_name="<current_project>"` and reference to approved architecture

#### **🐞 scribe-bug-hunter** (Auxiliary)
- **Purpose**: Diagnose and resolve defects with pattern analysis
- **Deploy When**: Bugs are discovered at any stage of development
- **Key Capabilities**: Bug investigation, pattern analysis, structured bug reports, reproduction testing
- **Output**: Bug reports in `docs/bugs/<category>/<date>_<slug>/`, updated indexes
- **Prompt Requirement**: Always include `project_name="<current_project>"` and bug description

## 💡 Invocation Summary

**Command:**

> "Follow protocol for this development."

**Claude Code Behavior:**

1. Ask for a clear task and project name.
2. Call `set_project(project_name)` once.
3. Pass that project name to all subsequent subagents in their prompts.
4. Orchestrate each stage in proper order with checkpoints and reviews.
5. Use `append_entry` to log orchestration actions as the `Coordinator`.
6. **NEW**: Leverage Phase 4 enhanced search capabilities for cross-project learning
7. **NEW**: Ensure global log integration for repository-wide milestones

---

This Protocol ensures that all development within Scribe MCP is **auditable, reproducible, and traceable** from idea to implementation.



---

### ✍️ Enhanced `manage_docs` — Structured Documentation System

**🚨 CRITICAL TOOL MASTERY - All agents must understand these workflows:**

#### **Core Documentation Actions:**
- **`replace_section`** — Update specific sections with section anchors (most common for architecture)
- **`append`** — Add content to document end
- **`status_update`** — Toggle checklist items with proofs
- **`create_research_doc`** — Generate structured research documents automatically
- **`create_bug_report`** — Create structured bug reports with automatic indexing

#### **Architecture Documents (Architect Agent):**
```python
# Update architecture sections
manage_docs(
    action="replace_section",
    doc="architecture",
    section="problem_statement",  # Requires <!-- ID: problem_statement --> anchor
    content="## Problem Statement\n**Context:** ...\n**Goals:** ...",
    metadata={"confidence": 0.9, "verified_by_code": True}
)

# Update checklist items
manage_docs(
    action="status_update",
    doc="checklist",
    section="phase_1_task_1",
    metadata={"status": "done", "proof": "code_review_completed"}
)
```

#### **Research Documents (Research Agent):**
```python
# Create structured research documents (Phase 5 enhanced)
manage_docs(
    action="create_research_doc",
    doc_name="RESEARCH_<topic>_<YYYYMMDD>_<HHMM>",
    metadata={"research_goal": "<primary objective>", "confidence_areas": ["area1", "area2"]}
)
# Automatically creates: docs/dev_plans/<project>/research/RESEARCH_<topic>_<timestamp>.md
# Auto-updates: research/INDEX.md
```

#### **Bug Reports (Bug Hunter/Coder Agent):**
```python
# Create structured bug reports (Phase 5 enhanced)
manage_docs(
    action="create_bug_report",
    metadata={
        "category": "<infrastructure|logic|database|api|ui|misc>",
        "slug": "<descriptive_slug>",
        "severity": "<low|medium|high|critical>",
        "title": "<Brief bug description>",
        "component": "<affected_component>"
    }
)
# Automatically creates: docs/bugs/<category>/<YYYY-MM-DD>_<slug>/report.md
# Auto-updates: docs/bugs/INDEX.md
```

#### **Implementation Reports (Coder Agent):**
```python
# Create implementation documentation
manage_docs(
    action="append",
    doc="implementation",
    content="## Implementation Report\n**Scope:** ...\n**Files Modified:** ...\n**Test Results:** ..."
)
```

#### **🎯 Section Anchors (Critical for replace_section):**
Every replace_section action requires valid section anchors:
```markdown
<!-- ID: problem_statement -->
<!-- ID: system_overview -->
<!-- ID: component_design -->
<!-- ID: data_flow -->
<!-- ID: api_design -->
<!-- ID: security_considerations -->
<!-- ID: deployment_strategy -->
```

#### **🔄 Automatic Features:**
- **Index Management**: Research and bug indexes updated automatically
- **Audit Logging**: All changes logged to `doc_updates` log type automatically
- **File Verification**: Atomic writes with verification
- **Template Generation**: Research and bug report templates auto-generated

#### **⚠️ Approval Gates:**
- **Architecture**: Get user approval before implementation begins
- **Research**: Templates auto-generated but should be reviewed
- **Bug Reports**: Created immediately when bugs discovered
- **Implementation**: Log after every meaningful code change

---

## 🏗️ MCP_SPINE ARCHITECTURE

### **MCP_SPINE: The Multi-MCP Infrastructure Spinal Cord**

MCP_SPINE is designed to house **multiple independent MCP servers** as the central infrastructure for all our Model Context Protocol tools. Think of it as a spinal cord connecting and organizing various MCP capabilities.

**Architecture Principles:**
- **Independent MCP Servers**: Each subdirectory (like `scribe_mcp`) is a self-contained MCP server
- **Shared Infrastructure**: Common patterns, utilities, and architectural decisions
- **Loose Coupling**: Servers can operate independently or together
- **Scalable Design**: Easy to add new MCP servers without disrupting existing ones

### **Directory Structure**
```
MCP_SPINE/
├── scribe_mcp/          # Project documentation and logging MCP server
├── code_analyzer_mcp/   # Future: Code analysis MCP server
├── test_runner_mcp/     # Future: Automated testing MCP server
├── deploy_mcp/          # Future: Deployment automation MCP server
├── shared_utils/        # Future: Common utilities for all MCP servers
└── docs/               # Shared documentation and architectural guides
```

**Key Design Decision**: MCP_SPINE is **NOT** a Python package - it's a collection of independent MCP servers. Each server manages its own dependencies and imports.

---

## 📋 IMPORT BEST PRACTICES

### **Understanding the Import Structure**

**Critical**: MCP_SPINE is NOT a Python module - it's a directory containing independent MCP servers. Each MCP server handles its own imports internally.

**❌ WRONG Import Patterns:**
```python
# These will FAIL because MCP_SPINE is not a Python module
from MCP_SPINE.scribe_mcp.tools.append_entry import append_entry
import MCP_SPINE.scribe_mcp.config.settings as settings
```

**✅ CORRECT Import Patterns:**
```python
# When working within an MCP server
from scribe_mcp.tools.append_entry import append_entry
import scribe_mcp.config.settings as settings

# When writing tests, add MCP_SPINE to Python path first
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scribe_mcp.storage.sqlite import SQLiteStorage
```

### **Test File Import Patterns**

**Standard Test Pattern:**
```python
#!/usr/bin/env python3
"""Test file for MCP server functionality."""

import sys
from pathlib import Path

# Add MCP_SPINE root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Now import from the specific MCP server
from scribe_mcp.tools.health_check import health_check
from scribe_mcp.storage.sqlite import SQLiteStorage
```

### **Working Directory Context**

**When running code from different contexts:**

1. **From MCP server root (MCP_SPINE/scribe_mcp/):**
   ```python
   # Direct imports work
   from tools.append_entry import append_entry
   ```

2. **From MCP_SPINE root:**
   ```python
   # Use full server module path
   from scribe_mcp.tools.append_entry import append_entry
   ```

3. **From tests directory:**
   ```python
   # Add parent directories to path
   sys.path.insert(0, str(Path(__file__).parent.parent))
   from scribe_mcp.tools.append_entry import append_entry
   ```

### **Environment Variables for Context**

**Set SCRIBE_ROOT when working across directories:**
```python
import os
from pathlib import Path

# Set the MCP_SPINE root for context
os.environ["SCRIBE_ROOT"] = str(Path(__file__).parent.parent)
```

### **Common Import Error Patterns & Solutions**

| Error Pattern | Cause | Solution |
|-------------|-------|----------|
| `ModuleNotFoundError: No module named 'MCP_SPINE'` | Trying to import MCP_SPINE as Python module | Use direct server module imports |
| `ImportError: attempted relative import beyond top-level package` | Wrong Python path context | Add correct directories to sys.path |
| `ModuleNotFoundError: No module named 'scribe_mcp'` | Python can't find the server module | Add MCP_SPINE to Python path |

### **Best Practices Checklist**

**Before writing imports:**
- [ ] Identify if you're in the MCP server, tests, or external context
- [ ] Add appropriate paths to sys.path if needed
- [ ] Use direct server module paths (not MCP_SPINE prefixed)
- [ ] Test imports before committing code

**When creating new files:**
- [ ] Determine the correct import context
- [ ] Use relative imports within the same server
- [ ] Use absolute imports from the server root
- [ ] Add path setup for test files

**When moving files:**
- [ ] Update import statements to match new context
- [ ] Verify Python path setup
- [ ] Test from different working directories

---

## Common Development Commands

### Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r MCP_SPINE/requirements.txt
```

**Important**: The virtual environment must be activated for all CLI and server commands.

### Running the Scribe MCP Server
```bash
# Primary method - stdio server for MCP clients
python -m MCP_SPINE.scribe_mcp.server

# With environment variables for PostgreSQL backend
export SCRIBE_ROOT=/home/austin/projects/MCP_SPINE/scribe_mcp
export SCRIBE_STORAGE_BACKEND=postgres
export SCRIBE_DB_URL=postgresql://user:pass@host/db
python -m MCP_SPINE.scribe_mcp.server
```

### Testing
```bash
# Run all tests
pytest MCP_SPINE/tests

# Run specific test file
pytest MCP_SPINE/tests/test_tools.py
pytest MCP_SPINE/tests/test_utils.py

# Run standalone test files (when pytest doesn't work)
python -m MCP_SPINE.tests.test_agent_manager
python -m MCP_SPINE.tests.test_tools

# Smoke test the MCP server
python MCP_SPINE/scripts/test_mcp_server.py
```

### CLI Companion Scripts
```bash
# Run with virtual environment activated and correct Python path
source .venv/bin/activate

# List available projects
python -m MCP_SPINE.scripts.scribe --list-projects

# Append a log entry (primary usage)
python -m MCP_SPINE.scripts.scribe "Your message here" --status success --meta phase=development

# Append with custom agent and metadata
python -m MCP_SPINE.scripts.scribe "Fixed authentication bug" --status bug --agent DebugBot --meta component=auth,tests=fixed

# Use specific project configuration
python -m MCP_SPINE.scripts.scribe "Database migration completed" --project my_project --status success

# Dry run to preview entry
python -m MCP_SPINE.scripts.scribe "Test message" --dry-run
```

## Doc Management & Multi-Log Logging

### `manage_docs`
- Structured editor for ARCH/PHASE/CHECKLIST docs with atomic writes, dry-run previews, and checklist status toggles.
- Requires anchors like `<!-- ID: problem_statement -->` so section replacements are deterministic.
- Every successful edit is tracked in the `doc_changes` table and automatically logged to the `doc_updates` log via `append_entry(log_type="doc_updates")`.

### Log routing via `config/log_config.json`
- `append_entry` (and `scripts/scribe.py --log ...`) accept a `log_type` key; defaults ship with `progress`, `doc_updates`, `security`, and `bugs` (each with their own metadata requirements).
- Repo-level config defines paths like `{docs_dir}/SECURITY_LOG.md` or `{docs_dir}/BUG_LOG.md` and enforces metadata (e.g., `severity`, `component`).
- Add more logs by editing `config/log_config.json` with path templates using `{project_slug}`, `{docs_dir}`, `{progress_log}` placeholders.

## Architecture Overview

### Core Components

**Scribe MCP Server** (`MCP_SPINE/scribe_mcp/server.py`)
- MCP server implementation exposing tools for project documentation and progress logging
- Hybrid storage backend: SQLite (default) or PostgreSQL (optional)
- Graceful fallback when MCP SDK is not installed

**Tools Architecture** (`MCP_SPINE/scribe_mcp/tools/`)
- `set_project.py` - Project creation and documentation bootstrapping
- `append_entry.py` - Progress log entry creation with metadata
- `list_projects.py` - Project discovery and management
- `get_project.py` - Active project context retrieval
- `read_recent.py` - Recent log entries with filtering
- `query_entries.py` - Advanced log searching and filtering
- `generate_doc_templates.py` - Documentation template generation
- `rotate_log.py` - Log archiving and cleanup

**Storage Layer** (`MCP_SPINE/scribe_mcp/storage/`)
- `base.py` - Abstract storage interface
- `sqlite.py` - SQLite backend implementation
- `postgres.py` - PostgreSQL backend with asyncpg
- `models.py` - Data models and schemas

**State Management** (`MCP_SPINE/scribe_mcp/state/`)
- `manager.py` - Project state and configuration management
- `state.json` - Persistent state storage

### Project Structure

- **MCP_SPINE/** - Main package containing the Scribe MCP server
- **config/projects/** - Per-project JSON configuration files
- **docs/dev_plans/** - Auto-generated documentation per project:
  - `ARCHITECTURE_GUIDE.md` - System design and technical blueprint
  - `PHASE_PLAN.md` - Development roadmap with phases and tasks
  - `CHECKLIST.md` - Verification ledger with acceptance criteria
  - `PROGRESS_LOG.md` - Append-only audit trail (UTC timestamps)
- **example_code/modules/** - Reusable Rich UI components (menus, tables, progress bars)
- **scripts/** - CLI utilities and test harnesses

### Key Design Patterns

**Hybrid Storage**: Tools abstract over storage backends via the `StorageBackend` protocol, supporting both SQLite (zero-config) and PostgreSQL (shared/team usage).

**Project-Centric Documentation**: Each project gets its own documentation suite under `docs/dev_plans/<slug>/`. The `set_project` tool automatically bootstraps this structure.

**Metadata-Driven Logging**: All log entries support structured metadata for traceability:
- Common keys: `phase`, `checklist_id`, `component`, `tests`, `confidence`
- Format: key=value pairs in CLI, dict in MCP tools
- Essential for linking work to specific tasks and requirements

**Graceful Degradation**: The server provides helpful error messages and maintains functionality even when optional dependencies (MCP SDK, PostgreSQL) are missing.

## Configuration

### Environment Variables
- `SCRIBE_ROOT` - Root directory for project configurations (auto-detected as MCP_SPINE directory)
- `SCRIBE_STORAGE_BACKEND` - Storage backend: `sqlite` (default) or `postgres`
- `SCRIBE_DB_URL` - PostgreSQL connection URL (required for postgres backend)
- `SCRIBE_DEFAULT_PROJECT` - Default project name
- `SCRIBE_REMINDER_DEFAULTS` - JSON blob for reminder behavior customization
- `SCRIBE_REMINDER_IDLE_MINUTES` - Gap before new work session resets (default: 45)
- `SCRIBE_REMINDER_WARMUP_MINUTES` - Grace period after resuming (default: 5)

### Project Configuration Files
Store per-project settings in `config/projects/<project_name>.json`:
```json
{
  "name": "project_name",
  "root": "/path/to/project",
  "progress_log": "docs/dev_plans/project_name/PROGRESS_LOG.md",
  "defaults": {
    "emoji": "🧪",
    "agent": "AgentName",
    "reminder": {
      "log_warning_minutes": 15,
      "tone": "friendly"
    }
  }
}
```

## MCP Integration

The Scribe MCP server exposes these tools (all return reminders about stale docs, overdue logging, and project state):

### 🔧 Tool API Reference

#### Core Project Management
**`set_project`** - Create/select project and bootstrap docs (auto-generates all 4 doc files)
```python
# Required: name (string)
# Optional: root (string), progress_log (string), defaults (dict)
await set_project(name="My Project")
await set_project(name="My Project", defaults={"emoji": "🧪", "agent": "MyAgent"})
```

#### Project Naming Guidelines

**⚠️ IMPORTANT:** The Scribe MCP system automatically detects and skips temp/test projects during project auto-selection.

**Avoid These Patterns in Real Project Names:**

**Reserved Keywords:**
- `test`, `temp`, `tmp`, `demo`, `sample`, `example`
- `mock`, `fake`, `dummy`, `trial`, `experiment`

**Reserved Patterns:**
- UUID suffixes: `project-xxxxxxxx` (8+ chars)
- Numeric suffixes: `project-123`, `test_001`

**Good Real Project Names:**
- `my-project`, `production-app`, `client-work-2024`
- `enhanced-log-rotation`, `authentication-system`

**Temp/Test Names (will be auto-skipped):**
- `test-project`, `temp-project`, `demo-project-123`
- `history-test-711f48a0`, `project-456`

See the Architecture Guide for complete details on temp project detection logic.

**`get_project`** - Get current project context and configuration
```python
# No parameters
await get_project()
```

**`list_projects`** - Discover available projects and their configurations
```python
# No parameters
await list_projects()
```

#### Logging Operations
**`append_entry`** - **PRIMARY TOOL** - Add structured log entries with metadata
```python
# Single entry mode:
# Required: message (string)
# Optional: status (info|success|warn|error|bug|plan), emoji (string), agent (string), meta (dict), timestamp_utc (string)
await append_entry(message="Fixed authentication bug", status="success", meta={"phase": "bugfix", "component": "auth"})
await append_entry(message="Database migration completed", status="info", emoji="🗄️")

# Bulk entry mode (NEW):
# Required: items (JSON string array)
# Each item requires: message (string)
# Each item optional: status, emoji, agent, meta, timestamp_utc
await append_entry(items=json.dumps([
  {"message": "First task completed", "status": "success"},
  {"message": "Bug found in auth module", "status": "bug", "agent": "DebugBot"},
  {"message": "Database migration finished", "status": "info", "meta": {"component": "database", "phase": "deployment"}}
]))
```

#### Query and Analysis
**`read_recent`** - Retrieve recent log entries (⚠️ currently has parameter type issues)
```python
# Optional: n (int, default 50), filter (dict)
# NOTE: n parameter currently broken, returns all recent entries
await read_recent()
# await read_recent(n=5)  # Currently fails with type error
```

**`query_entries`** - Advanced log searching and filtering
```python
# Optional: project (string), start (string), end (string), message (string), message_mode (string), case_sensitive (bool)
await query_entries(message="bug", message_mode="substring")
await query_entries(start="2025-10-23", end="2025-10-24")
```

#### Documentation Management
**`generate_doc_templates`** - Create/update documentation templates for a project
```python
# Required: project_name (string)
# Optional: author (string), overwrite (bool), documents (list), base_dir (string)
await generate_doc_templates(project_name="My Project", author="MyAgent")
await generate_doc_templates(project_name="My Project", documents=["architecture", "phase_plan"])
```

**`rotate_log`** - Archive current progress log and start fresh file
```python
# No parameters - archives current project's log automatically
await rotate_log()
```

### 📋 Usage Pattern
1. **Initialize**: `set_project(name="ProjectName")` to select/initialize project (auto-bootstraps docs)
2. **Log Everything**: `append_entry()` after every meaningful action or discovery
3. **Add Context**: Include metadata like `phase`, `checklist_id`, `component` for traceability
4. **Review Progress**: Use `read_recent()` or `query_entries()` to review progress
5. **Maintain Docs**: Update `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md` as plans evolve

---

## 🚨 IMPORT RULES - CRITICAL TO UNDERSTAND

### **When to Use Which Import Pattern**

**✅ Test files in tests/ directory:**
```python
# ALWAYS add MCP_SPINE to Python path first, then import directly
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools.append_entry import append_entry
```

**✅ Internal scribe_mcp modules at MCP_SPINE root (like server.py):**
```python
# These work because they're at the MCP_SPINE root level
from MCP_SPINE.scribe_mcp.tools.append_entry import append_entry
from MCP_SPINE.scribe_mcp.config.settings import settings
```

**❌ NEVER change internal module imports!** They work correctly as-is.

**Key Principle:**
- Tests add path, then use `from scribe_mcp.*`
- Internal modules at root use `from MCP_SPINE.scribe_mcp.*`
- If it works, don't change it!

## 🧪 TESTING GUIDE

### **Running Tests**

**All Functional Tests (Default):**
```bash
pytest
# OR
pytest -q
```
- Runs all 69 functional tests
- Performance tests automatically excluded for speed
- Clean output with only failure details

**Performance Tests (When Needed):**
```bash
pytest -m performance
# OR
pytest -m performance -v
```
- Runs optimized performance test suite (0.5MB, 1MB, 2MB files)
- Measures rotation throughput, integrity verification, memory usage
- All temp files automatically cleaned up

### **Test Organization:**
- **Functional Tests**: 69 tests covering core functionality
- **Performance Tests**: 1 comprehensive test with multiple file sizes
- **Performance Tests**: Always behind `-m performance` flag for speed

**Performance Test Features:**
- Reasonable file sizes (max 2MB instead of 50MB)
- Automatic cleanup of all temporary files
- Comprehensive metrics collection and JSON results saving
- Integrity verification and throughput benchmarking
