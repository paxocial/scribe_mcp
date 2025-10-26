# 🧠 AGENTS.md - Scribe MCP Server
**Author:** CortaLabs | **Role:** Project-agnostic logging + doc bootstrap | **Version:** v1.0 (condensed)

---

## 🚨 COMMANDMENTS - CRITICAL RULES


**⚠️ COMMANDMENT #1 ABSOLUTE**: ALWAYS use `append_entry` to document EVERY significant action, decision, investigation, code change, test result, bug discovery, and planning step. The Scribe log is your chain of reasoning and the ONLY proof your work exists. If it's not Scribed, it didn't fucking happen.

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

### ✍️ `manage_docs` — Non‑Negotiable Doc Management Workflow
- **When:** Run immediately after `set_project` (before writing any feature code). Populate `ARCHITECTURE_GUIDE`, `PHASE_PLAN`, and `CHECKLIST` with the proposed plan via `manage_docs`, get the human sign-off, then proceed with implementation.
- **Why:** Ensures every plan/change is captured through the Jinja-managed doc pipeline with atomic writes, verification, and automatic `doc_updates` logging.
- **Actions:** `replace_section` (needs valid `section` anchor), `append` (freeform/Jinja content), `status_update` (toggle checklist items + proofs).
- **Example payload:**
```jsonc
{
  "action": "status_update",
  "doc": "checklist",
  "section": "architecture_review",
  "content": "status toggle placeholder",
  "metadata": {
    "status": "done",
    "proof": "PROGRESS_LOG.md#2025-10-26-08-37-52"
  }
}
```
- **Customization:** All doc sections are editable; append fragments, drop in metadata-driven templates, or flip `[ ]` → `[x]` with proofs. If an anchor/token is wrong the tool fails safely—fix it and rerun.
- **Approval gate:** No coding until the manage_docs-authored plan is approved by the user. Re-run manage_docs whenever the plan shifts so docs stay authoritative.
---
**⚠️ COMMANDMENT #11 CRITICAL**: NEVER write replacement files. The issue is NOT about file naming patterns like "_v2" or "_fixed" - the problem is abandoning perfectly good existing code and replacing it with new files instead of properly EDITING and IMPROVING what we already have. This is lazy engineering that creates technical debt and confusion.

**ALWAYS work with existing files through proper edits. NEVER abandon current code for new files when improvements are needed.**
---
**⚠️ COMMANDMENT #12 CRITICAL**: Follow proper project structure and best practices. Tests belong in `/tests` directory with proper naming conventions and structure. Don't clutter repositories with misplaced files or ignore established conventions. Keep the codebase clean and organized.

Violations = INSTANT TERMINATION. Reviewers who miss commandment violations get 80% pay docked. Nexus coders who implement violations face $1000 fine.

---

Scribe is our non-negotiable audit trail. If you touch code, plan phases, or discover issues, you log it through Scribe. **Append entries every 2-3 meaningful actions or every 10 minutes - no exceptions.** Logs are append-only, UTC, single line, and must be created via the MCP tools or `scripts/scribe.py`.

## 🚀 Quick Tool Reference (Top Priority)

**`set_project(name, [defaults])`** - Initialize/select project (auto-bootstraps docs)
**`append_entry(message, [status, meta])`** - **PRIMARY TOOL** - Log work/progress (single & bulk mode)
**`manage_docs(action, doc, content/section)`** - Structured edits for ARCH/PHASE/CHECKLIST (auto-logs + SQL history)
**`get_project()`** - Get current project context
**`list_projects()`** - Discover available projects
**`read_recent()`** - Get recent log entries
**`query_entries([filters])`** - Search/filter logs
**`generate_doc_templates(project_name, [author])`** - Create doc scaffolding
**`rotate_log()`** - Archive current log

**NEW**: Bulk append with `append_entry(items=[{message, status, agent, meta}, ...])` - Multiple entries in one call!

---

## 🔌 MCP Tool Reference
All tools live under the `scribe.mcp` server. Payloads are minimal JSON; unspecified fields are omitted.

### 1. `set_project` - **Project Initialization**
**Purpose**: Select or create active project and auto-bootstrap docs tree
**Usage**: `set_project(name, [root, progress_log, defaults])`
```json
// Minimal request (recommended)
{
  "name": "My Project"
}

// Full request
{
  "name": "IMPLEMENTATION TESTING",
  "root": "/abs/path/to/repo",
  "progress_log": "docs/dev_plans/implementation_testing/PROGRESS_LOG.md",
  "defaults": { "emoji": "🧪", "agent": "MyAgent" }
}

// response
{
  "ok": true,
  "project": {
    "name": "My Project",
    "root": "/abs/path/to/repo",
    "progress_log": "/abs/.../PROGRESS_LOG.md",
    "docs_dir": "/abs/.../docs/dev_plans/my_project",
    "docs": {
      "architecture": ".../ARCHITECTURE_GUIDE.md",
      "phase_plan": ".../PHASE_PLAN.md",
      "checklist": ".../CHECKLIST.md",
      "progress_log": ".../PROGRESS_LOG.md"
    },
    "defaults": { "emoji": "🧪", "agent": "MyAgent" }
  },
  "generated": [".../ARCHITECTURE_GUIDE.md", ".../PHASE_PLAN.md", ".../CHECKLIST.md", ".../PROGRESS_LOG.md"]
}
```

### 2. `get_project`
Return the current context exactly as Scribe sees it.
```json
// request
{}

// response
{
  "ok": true,
  "project": {
    "name": "IMPLEMENTATION TESTING",
    "root": "/abs/path/to/repo",
    "progress_log": "/abs/.../PROGRESS_LOG.md",
    "docs_dir": "/abs/.../docs/dev_plans/implementation_testing",
    "defaults": { "emoji": "ℹ️", "agent": "Scribe" }
  }
}
```

### 3. `append_entry` - **PRIMARY LOGGING TOOL**
**Use this constantly. If it isn't Scribed, it didn't happen.**
**Usage**: `append_entry(message, [status, emoji, agent, meta, timestamp_utc, items])`

#### Single Entry Mode:
```json
// Basic request (recommended)
{
  "message": "Fixed authentication bug",
  "status": "success"
}

// Full request with metadata
{
  "message": "Completed database migration",
  "status": "success",              // info | success | warn | error | bug | plan
  "emoji": "🗄️",                   // optional override
  "agent": "MigrationBot",         // optional override
  "meta": {
    "phase": "deployment",
    "checklist_id": "DEPLOY-001",
    "component": "database",
    "tests": "passed"
  },
  "timestamp_utc": "2025-10-22 10:21:14 UTC"   // optional; auto if omitted
}

// response (single entry)
{
  "ok": true,
  "written_line": "[2025-10-22 10:21:14 UTC] [🗄️] [Agent: MigrationBot] [Project: My Project] Completed database migration | phase=deployment; checklist_id=DEPLOY-001; component=database; tests=passed",
  "path": "/abs/.../PROGRESS_LOG.md"
}
```

#### Bulk Entry Mode (NEW):
```json
// Bulk request - multiple entries with individual timestamps
{
  "items": [
    {
      "message": "First task completed",
      "status": "success"
    },
    {
      "message": "Bug found in auth module",
      "status": "bug",
      "agent": "DebugBot"
    },
    {
      "message": "Database migration finished",
      "status": "info",
      "agent": "MigrationBot",
      "meta": {
        "component": "database",
        "phase": "deployment",
        "records_affected": 1250
      },
      "timestamp_utc": "2025-10-22 15:30:00 UTC"
    }
  ]
}

// response (bulk entries)
{
  "ok": true,
  "written_count": 3,
  "failed_count": 0,
  "written_lines": [
    "[✅] [2025-10-24 10:45:00 UTC] [Agent: Scribe] [Project: My Project] First task completed",
    "[🐞] [2025-10-24 10:45:01 UTC] [Agent: DebugBot] [Project: My Project] Bug found in auth module",
    "[ℹ️] [2025-10-22 15:30:00 UTC] [Agent: MigrationBot] [Project: My Project] Database migration finished | component=database; phase=deployment; records_affected=1250"
  ],
  "failed_items": [],
  "path": "/abs/.../PROGRESS_LOG.md"
}
```

#### Multi-log routing (`log_type`)
- Pass `log_type="doc_updates"` (or any key from `config/log_config.json`) to route entries into custom logs like `DOC_LOG.md`.
- Each log can enforce metadata (e.g., `doc`, `section`, `action` for doc updates). Missing required fields will reject the entry.
- Default config ships with `progress`, `doc_updates`, `security`, and `bugs`. Add more under `config/log_config.json` with placeholders such as `{docs_dir}` or `{project_slug}` for path templates.
- CLI (`scripts/scribe.py`) also accepts `--log doc_updates` to stay consistent with MCP usage.

### 4. `manage_docs` – Structured doc updates
- **Purpose**: Safely edit `ARCHITECTURE_GUIDE`, `PHASE_PLAN`, `CHECKLIST`, etc., with audit metadata and automatic logging.
- **Args**:
  - `action`: `append`, `replace_section`, or `status_update`.
  - `doc`: `architecture`, `phase_plan`, `checklist`, or custom template key.
  - `section`: Required for section/status operations; matches anchors like `<!-- ID: problem_statement -->`.
  - `content` or `template`: Provide raw Markdown or reference a fragment under `docs/dev_plans/1_templates/fragments/`.
  - `metadata`: Optional context (e.g., `{"status": "done", "proof": "PROGRESS_LOG#..."}`).
  - `dry_run`: Preview diff without writing.
- **Behavior**:
  - Edits are persisted atomically, recorded in the new `doc_changes` table, and auto-logged via `append_entry(log_type="doc_updates")`.
  - Checklist status updates flip `[ ]` ↔ `[x]` and can attach proof links automatically.

### 5. `list_projects`
Discover configured or recently used projects.
```json
// request
{ "roots": ["/abs/path/to/repos"], "limit": 500 }

// response
{
  "ok": true,
  "projects": [
    {
      "name": "IMPLEMENTATION TESTING",
      "root": "/abs/path/to/repo",
      "progress_log": "/abs/.../PROGRESS_LOG.md",
      "docs": { "architecture": "...", "phase_plan": "...", "checklist": "...", "progress_log": "..." }
    }
  ]
}
```

### 6. `read_recent` - **Recent Log Entries**
**Purpose**: Tail the log via MCP instead of opening files by hand
**Usage**: `read_recent([n, filter])`
**⚠️ NOTE**: n parameter currently has type issues, returns all recent entries
```json
// Basic request (recommended)
{}

// With filtering (when n parameter fixed)
{
  "n": 50,
  "filter": { "status": "error", "agent": "Scribe" }
}

// response
{
  "ok": true,
  "entries": [
    {
      "id": "uuid",
      "ts": "2025-10-22 10:21:14 UTC",
      "emoji": "ℹ️",
      "agent": "Scribe",
      "message": "Describe the work or finding",
      "meta": { "phase": "bootstrap" },
      "raw_line": "[ℹ️] [2025-10-22 10:21:14 UTC] [Agent: Scribe] [Project: My Project] Describe the work or finding"
    }
  ]
}
```

### 7. `rotate_log`
Archive the current log and create a fresh file.
```json
// request
{ "suffix": "2025-10-22" }

// response
{ "ok": true, "archived_to": "/abs/.../PROGRESS_LOG.md.2025-10-22.md" }
```

### 8. `db.persist_entry` *(optional)*
Mirror a freshly written line into Postgres when configured.
```json
// request
{
  "line": "[2025-10-22 ...] ...",
  "project": "IMPLEMENTATION TESTING",
  "sha256": "abc123"
}

// response
{ "ok": true, "id": "uuid" }
```

### 9. `db.query` *(optional)*
Run predefined parameterized queries against the Scribe database.
```json
// request
{
  "query_name": "recent_failures",
  "params": { "project": "IMPLEMENTATION TESTING", "since_hours": 24 }
}

// response
{ "ok": true, "rows": [ { "ts": "2025-10-22 09:10:03 UTC", "agent": "Scribe", "message": "..." } ] }
```

### 10. `query_entries` - **Advanced Log Search**
**Purpose**: Advanced searching and filtering of progress log entries
**Usage**: `query_entries([project, start, end, message, message_mode, case_sensitive])`
```json
// Search by message content
{
  "message": "bug",
  "message_mode": "substring"
}

// Search by date range
{
  "start": "2025-10-23",
  "end": "2025-10-24"
}

// Search specific project
{
  "project": "My Project",
  "message": "migration",
  "case_sensitive": false
}

// response
{
  "ok": true,
  "entries": [
    {
      "id": "uuid",
      "ts": "2025-10-23 15:30:00 UTC",
      "emoji": "🗄️",
      "agent": "MigrationBot",
      "message": "Completed database migration",
      "meta": { "phase": "deployment", "component": "database" },
      "raw_line": "[🗄️] [...]"
    }
  ]
}
```

### 11. `generate_doc_templates` - **Documentation Scaffolding**
**Purpose**: Create/update documentation templates for a project
**Usage**: `generate_doc_templates(project_name, [author, overwrite, documents, base_dir])`
```json
// Basic request
{
  "project_name": "My New Project",
  "author": "MyAgent"
}

// Select specific documents
{
  "project_name": "My Project",
  "documents": ["architecture", "phase_plan"],
  "overwrite": true
}

// response
{
  "ok": true,
  "files": [
    "/abs/.../ARCHITECTURE_GUIDE.md",
    "/abs/.../PHASE_PLAN.md",
    "/abs/.../CHECKLIST.md",
    "/abs/.../PROGRESS_LOG.md"
  ],
  "skipped": [],
  "directory": "/abs/.../docs/dev_plans/my_new_project"
}
```

## 🛠️ CLI Companion (Optional)
`python scripts/scribe.py` mirrors the MCP tools for shell workflows:
- `--list-projects`
- `--project <name>` or `--config <path>`
- `append "Message" --status success --meta key=value`
- `read --n 20`
- `rotate --suffix YYYY-MM-DD`

Always prefer tool calls from agents; the CLI is for human operators.

---

## 🗂️ Dev Plan Document Suite
Each project under `docs/dev_plans/<slug>/` maintains four synchronized files. Scribe bootstraps them during `set_project`; agents keep them current.

- `ARCHITECTURE_GUIDE.md` - Canonical blueprint. Explain the problem, goals, constraints, system design, data flow, and current directory tree. Update immediately when structure or intent changes.
- `PHASE_PLAN.md` - Roadmap derived from the architecture. Enumerate phases with objectives, tasks, owners, acceptance criteria, and confidence. Keep it aligned with reality.
- `CHECKLIST.md` - Verification ledger mirroring the phase plan. Each box must link to proof (commit, PR, screenshot, or Scribe entry). Do not invent tasks here.
- `PROGRESS_LOG.md` - Append-only audit trail written **only** through `append_entry`. Include `meta` keys like `phase=`, `checklist_id=`, `tests=` for traceability. Rotate periodically (~200 entries) using `rotate_log`.

**Workflow Loop**
1. `set_project` -> confirm docs exist.
2. Fill `ARCHITECTURE_GUIDE.md`, then `PHASE_PLAN.md`, then `CHECKLIST.md`.
3. Work in small, logged increments. `append_entry` after every meaningful action or insight.
4. When plans shift, update the docs first, then log the change.
5. Treat missing or stale documentation as a blocker - fix before coding further.

---

## 🔒 Operating Principles
- Always append; never rewrite logs manually.
- Timestamps are UTC; emoji is mandatory.
- Scribe reminders about stale docs or missing logs are blocking alerts.
- Default storage is local SQLite; Postgres and GitHub bridges require explicit env configuration.
- No autonomous prose generation - Scribe stays deterministic and fast.

> **Repeat:** Append entries religiously. If there is no Scribe line, reviewers assume it never happened.

---

## 🏗️ MCP_SPINE ARCHITECTURE

### **MCP_SPINE: The Multi-MCP Infrastructure Spinal Cord**

You are working within **MCP_SPINE**, a multi-MCP infrastructure designed to house multiple independent MCP servers. This is the **spinal cord** of our Model Context Protocol tools ecosystem.

**Architecture Principles:**
- **Independent MCP Servers**: Each subdirectory (like `scribe_mcp`) is a self-contained MCP server
- **Shared Infrastructure**: Common patterns, utilities, and architectural decisions
- **Loose Coupling**: Servers can operate independently or together
- **Scalable Design**: Easy to add new MCP servers without disrupting existing ones

### **Directory Structure**
```
MCP_SPINE/
├── scribe_mcp/          # Project documentation and logging MCP server (THIS ONE)
├── code_analyzer_mcp/   # Future: Code analysis MCP server
├── test_runner_mcp/     # Future: Automated testing MCP server
├── deploy_mcp/          # Future: Deployment automation MCP server
├── shared_utils/        # Future: Common utilities for all MCP servers
├── tests/               # Cross-server tests
├── demo/                # Demonstrations and examples
└── docs/                # Shared documentation and architectural guides
```

**Key Design Decision**: MCP_SPINE is **NOT** a Python package - it's a collection of independent MCP servers. Each server manages its own dependencies and imports.

---

## 📋 CRITICAL: Import Best Practices for MCP_SPINE

**⚠️ MOST IMPORTANT RULE**: **NEVER** import from `MCP_SPINE` as if it were a Python module. It's NOT a module!

**❌ WRONG Import Patterns - WILL FAIL:**
```python
from MCP_SPINE.scribe_mcp.tools.append_entry import append_entry
import MCP_SPINE.scribe_mcp.config.settings as settings
```

**✅ CORRECT Import Patterns - WILL WORK:**
```python
# When working within scribe_mcp server
from scribe_mcp.tools.append_entry import append_entry
import scribe_mcp.config.settings as settings

# When writing tests, add MCP_SPINE to Python path first
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scribe_mcp.storage.sqlite import SQLiteStorage
```

### **Working Directory Context Awareness**

**Always be aware of where you're working from:**

1. **Inside scribe_mcp server** (`MCP_SPINE/scribe_mcp/`):
   ```python
   # Use relative imports within the server
   from tools.append_entry import append_entry
   from config.settings import settings
   ```

2. **From MCP_SPINE root**:
   ```python
   # Use full server module paths
   from scribe_mcp.tools.append_entry import append_entry
   ```

3. **From tests directory**:
   ```python
   # Add parent to path, then import
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).parent.parent))
   from scribe_mcp.tools.health_check import health_check
   ```

### **Test File Import Pattern**

**Standard Test Template:**
```python
#!/usr/bin/env python3
"""Test file for scribe_mcp functionality."""

import sys
from pathlib import Path

# Add MCP_SPINE root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment context if needed
import os
os.environ["SCRIBE_ROOT"] = str(Path(__file__).parent.parent)

# Now import from scribe_mcp
from scribe_mcp.tools.some_tool import some_function
from scribe_mcp.storage.sqlite import SQLiteStorage
```

### **Common Import Errors & Solutions**

| Error Pattern | Cause | Solution |
|-------------|-------|----------|
| `ModuleNotFoundError: No module named 'MCP_SPINE'` | Trying to import MCP_SPINE as Python module | Use direct server module imports |
| `ImportError: attempted relative import beyond top-level package` | Wrong Python path context | Add correct directories to sys.path |
| `ModuleNotFoundError: No module named 'scribe_mcp'` | Python can't find the server module | Add MCP_SPINE to Python path |

### **Agent Workflow Best Practices**

**When Starting Work:**
- [ ] Identify which MCP server you're working with (usually scribe_mcp)
- [ ] Check your current working directory
- [ ] Set up correct import paths if needed
- [ ] Test imports before proceeding

**When Creating New Files:**
- [ ] Determine file location relative to server root
- [ ] Use appropriate import patterns
- [ ] Add path setup for test files
- [ ] Verify imports work from different contexts

**When Writing Tests:**
- [ ] Always add MCP_SPINE to Python path first
- [ ] Set environment variables if needed
- [ ] Use correct server module imports
- [ ] Test imports work before writing test logic

---

> *See `scribe_mcp/docs/AGENTS_EXTENDED.md` for implementation rationale and schema notes.*
