# 🧠 AGENTS.md — Scribe (MCP Server)

**Author:** CortaLabs
**Role:** Project-agnostic progress logging & doc bootstrap
**Version:** Draft v1.0
**Last Updated:** 2025-10-20 00:00 UTC

---

## 🧾 Logging with Scribe

Scribe centralizes progress logging for this and future projects. SCRIBE OFTEN.  EVERY FEW CHANGES. NO EXCUSES. WE REQUIRE FULL AUDITABILITY AND OBSERVABILITY OF ALL AGENTIC OPERATIONS.

*Configuration:* one JSON file per project under `config/projects/*.json`

```json
{
  "name": "scribe_mcp",
  "root": ".",
  "progress_log": "docs/dev_plans/scribe_mcp/PROGRESS_LOG.md",
  "docs_dir": "docs/dev_plans/scribe_mcp",
  "defaults": {
    "emoji": "ℹ️",
    "agent": "Scribe"
  }
}
```
- Use `python scripts/scribe.py --list-projects` to see available configs.
- Select a project with `--project <name>` (or set `SCRIBE_DEFAULT_PROJECT` in `.env`).
- **Workflow rules:** The coding agent MUST log with Scribe after every couple of meaningful steps, favour the status presets when they fit, include `--meta` for tickets or durations, use `--dry-run` to preview entries, and never edit the progress log by hand.  Use Scribe to document the starting of new phases/goals.  Scribe everything you do for full observability!

*CLI Usage (development workflow utility):*

```bash
python scripts/scribe.py --list-projects
python scripts/scribe.py "Fetched snapshot for Austin_HCIM" --project scribe_mcp --status success --meta duration_ms=842
python scripts/scribe.py "New progress" --config config/projects/custom.json --agent SnapshotAgent
```

Entry format: `[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: scribe_mcp] message | key=value`

Set `--dry-run` to preview without writing.

**Status presets:**

| Status   | Emoji | Use case                     |
| -------- | ----- | ---------------------------- |
| `info`   | ℹ️     | Neutral update or note        |
| `success`| ✅     | Completed task                |
| `warn`   | ⚠️     | Minor issues or follow-ups    |
| `error`  | ❌     | Blocking failure              |
| `bug`    | 🐞     | Defect discovered             |
| `plan`   | 🧭     | Planning or roadmap updates   |

Pass `--emoji` for ad-hoc reactions. An emoji is always required; if none is provided, the `default_emoji` in the config is used.

---

## 🗂️ Project Docs
- **Phase Plan:** `docs/dev_plans/scribe_mcp/PHASE_PLAN.md`
- **Architecture Guide:** `docs/dev_plans/scribe_mcp/ARCHITECTURE_GUIDE.md`
- **Checklist:** `docs/dev_plans/scribe_mcp/CHECKLIST.md`
- **Operational Log:** `docs/dev_plans/scribe_mcp/PROGRESS_LOG.md` (central log for this repo; roll with `scripts/scribe.py`)

The phase plan tracks roadmap status (bootstrap done, storage abstraction in progress). Update it whenever phases shift or scope changes. The architecture guide outlines the current MCP stack and the hybrid storage approach (SQLite default, Postgres optional).

---

## 📚 Documentation Workflow
- **Architecture Guide:** Canonical source of truth. Capture the full problem statement, goals, constraints, design rationale, implementation plan, and an up-to-date directory tree. Whenever the code layout changes, the tree and relevant sections must be refreshed.
- **Phase Plan:** Translate the architecture into phased execution. Every milestone and subtask needed to ship the project belongs here. Keep it in sync with architectural changes.
- **Checklist:** Derived from the phase plan. Every phase task should map to a checkbox with space for proof or links. Update the checklist as phases evolve and mark items complete only when evidence is captured.
- **Progress Log:** Append-only event history. All entries come through Scribe (`scripts/scribe.py` or the MCP `append_entry` tool). Each log entry should reference related tasks (phase plan/checklist) so reviewers can trace work back to the docs.

**Agent Duties**
1. At project start, generate all four docs from templates (Scribe does the bootstrap; agents fill in details).
2. Before coding, review architecture + phase plan; ask clarifying questions if sections are blank.
3. After meaningful work, update architecture/phase plan/checklist as needed *then* log the activity.
4. If documentation diverges from implementation, pause and reconcile before continuing.

Scribe tools will remind you when documents appear stale. Treat those warnings as blocking issues.

---

## 🧭 Purpose

Scribe is a **minimal, fast-as-hell** documentation system you can drop into any dev repo. It exposes an **MCP server** with tools to:

* choose the “current project” context,
* append structured progress log entries (your classic Scribe format),
* manage logs at scale (hundreds+ of dev_plans),
* optionally persist entries into Postgres (per-repo DB) for queries/dashboards,
* optionally persist entries into SQLite (local-first default) or Postgres (team dashboards),
* optionally sync to GitHub issues/discussions.

LLM features are **explicitly deferred**—programmatic first, then enhancements later.

## 🔩 Scope

* **In:** MCP tools, project discovery, log append/rotate, DB persistence, basic queries.
* **Optional:** GitHub bridge, export/ingest, markdown report renderers.
* **Out (for now):** vectorization, embeddings, autonomous agents writing prose.

## 🧱 Mental Model

* A **project** = name + config entry (`config/projects/<name>.json`) describing where docs/logs live.
* A **log entry** = deterministic line:
  `[YYYY-MM-DD HH:MM:SS UTC] [EMOJI] [Agent: <name>] [Project: <name>] Message | k=v; k2=v2`
* Scribe serves tools to set/get project, write/read logs, and mirror entries to Postgres.
* Storage backends are pluggable—SQLite ships as the default, Postgres enables shared analytics when `SCRIBE_DB_URL` is set.

---

## 🛰️ MCP Server Overview

### Server Identity

* **Name:** `scribe.mcp`
* **Transport:** stdio (default), HTTP (optional)
* **Auth:** none by default (local), token for remote/server mode

### Capabilities

* Tool invocation only. No background jobs unless a scheduler is configured.

---

## 🧰 Tools (MCP)

> Keep tool I/O dead simple. Names are verbs, params are minimal, outputs are terse.

### 1) `set_project`

Short: Select or define the current project.

**Input**

```json
{
  "name": "scribe_mcp",
  "root": "/abs/path/to/repo",
  "progress_log": "docs/dev_plans/.../PROGRESS_LOG.md",
  "defaults": { "emoji": "ℹ️", "agent": "Scribe" }
}
```

**Output**

```json
{ "ok": true, "project": "scribe_mcp" }
```

### 2) `get_project`

Short: Return the current project context (or last used).

**Output**

```json
{
  "name": "scribe_mcp",
  "root": "/abs/path/to/repo",
  "progress_log": "/abs/path/to/PROGRESS_LOG.md",
  "defaults": { "emoji": "ℹ️", "agent": "Scribe" }
}
```

### 3) `append_entry`

Short: Append one Scribe line to the project log.

**Input**

```json
{
  "message": "Snapshot stored",
  "status": "success",       // enum: info|success|warn|error|bug|plan
  "emoji": "✅",             // optional; overrides status
  "agent": "SnapshotAgent",  // optional
  "meta": { "player": "ArchonBorn", "latency_ms": "603.21" },
  "timestamp_utc": "2025-10-20 04:43:26 UTC"   // optional; auto if omitted
}
```

**Output**

```json
{
  "ok": true,
  "written_line": "[2025-10-20 04:43:26 UTC] [✅] [Agent: SnapshotAgent] [Project: scribe_mcp] Snapshot stored | player=ArchonBorn; latency_ms=603.21",
  "path": "/abs/path/to/PROGRESS_LOG.md"
}
```

### 4) `list_projects`

Short: Discover projects by scanning known roots (monorepo/multi-repo).

**Input**

```json
{ "roots": ["/work/dev_plans", "/work/projects"], "limit": 500 }
```

**Output**

```json
{
  "projects": [
    { "name": "scribe_mcp", "root": "/work/projects/osrs", "progress_log": "docs/.../PROGRESS_LOG.md" }
  ]
}
```

### 5) `rotate_log`

Short: Roll current PROGRESS_LOG to timestamped archive; start fresh file.

**Input**

```json
{ "suffix": "2025-10-20" }
```

**Output**

```json
{ "ok": true, "archived_to": "PROGRESS_LOG.2025-10-20.md" }
```

### 6) `read_recent`

Short: Return the last N entries for UI display.

**Input**

```json
{ "n": 50, "filter": { "agent": "SnapshotAgent", "status": "warn" } }
```

**Output**

```json
{ "lines": ["[...]", "..."] }
```

### 7) `db.persist_entry` (optional)

Short: Mirror a single appended entry to Postgres.

**Input**

```json
{
  "line": "[2025-10-20 ...] ...",
  "project": "scribe_mcp",
  "sha256": "abc123..."
}
```

**Output**

```json
{ "ok": true, "id": "d0b6c5a7-..." }
```

### 8) `db.query` (optional)

Short: Minimal SELECT against Scribe tables with parameterized templates.

**Input**

```json
{
  "query_name": "recent_failures",
  "params": { "project": "scribe_mcp", "since_hours": 24 }
}
```

**Output**

```json
{ "rows": [ { "ts": "...", "agent": "SnapshotAgent", "message": "..." } ] }
```

### 9) `gh.post` (optional)

Short: Post a rendered entry or summary to GitHub issues/discussions.

---

## 🧪 Log Format (Canonical)

* Timestamp: **UTC** always.
* Deterministic, append-only, no inline wrapping by Scribe.
* Meta keys: `k=v; k2=v2` (sorted optional).
* Example:

```
[2025-10-20 05:11:45 UTC] [✅] [Agent: SnapshotAgent] [Project: scribe_mcp] Report generated | player=ArchonBorn; mode=hardcore; path=reports/...; snapshot_id=...
```

---

## 🗂️ Project Discovery

Scribe chooses a project by:

1. explicit `set_project`, or
2. last project (recent-use cache), or
3. walking up from `cwd` for `config/projects/*.json` or `docs/dev_plans/**/PROGRESS_LOG.md`.

Heuristics can be configured, but keep default rules simple and predictable.

---

## 🗄️ Storage (Optional Postgres, Per-Repo)

### Tables

* `scribe_projects(id, name, repo_root, progress_log_path, created_at)`
* `scribe_entries(id uuid, project_id, ts timestamptz, emoji text, agent text, message text, meta jsonb, raw_line text, sha256 text, created_at timestamptz)`

**Indexes**

* `idx_entries_project_ts (project_id, ts desc)`
* GIN on `meta` for key queries.

### Insert Path

1. `append_entry` writes to file.
2. If DB configured, mirror into `scribe_entries`.
3. Hash (`sha256`) for integrity/replays.

---

## 🔐 Security & Safety

* Default: local filesystem only.
* Network integrations (DB/GitHub) are **off by default**.
* MCP server runs with least privilege; explicit flags to enable DB/GitHub.
* No LLM calls on the hot path.

---

## 🧰 Dev Setup

### Env

```
SCRIBE_ROOT=/abs/path/to/scribe
SCRIBE_DB_URL=postgresql://user:pass@localhost:5432/scribe
SCRIBE_ALLOW_NETWORK=false
```

### Run (stdio)

```
python -m MCP_SPINE.scribe_mcp.server
```

---

## 🪶 CLI Parity (Optional)

You may ship a tiny CLI wrapper (for non-MCP contexts):

```
scribe append "Snapshot stored" --status success --meta player=Karma --meta mode=main
scribe set-project --name scribe_mcp --root . --log docs/.../PROGRESS_LOG.md
scribe read --n 50 --agent SnapshotAgent
scribe rotate --suffix 2025-10-20
```

---

## 🧭 Roadmap (Short)

* v1.1: DB mirror + `read_recent` filters; GitHub bridge (issues/discussions).
* v1.2: Project cache + multi-root scanning UX.
* v1.3: Integrity attestations (rolling file hash).
* v2.0: Optional LLM summary/enrichment (off by default).

---

## 🔁 Operating Rules (Scribe Doctrine)

* **Always append**—never rewrite logs.
* **UTC or bust.**
* Keep entries **one line** and **self-contained**.
* Log **phases/milestones** explicitly.
* If it wasn’t Scribed, it didn’t happen.


Perfect — here’s your cleaned-up, professional-grade rewrite of that “verbal vomit,” structured as **guidance instructions** for the purpose and workflow of each subproject document.
You can paste this block at the top of each dev-plan folder (`docs/dev_plans/<PROJECT_NAME>/README.md` or similar) so agents know *exactly* what each file is for and how they fit together.

---

# 🧭 Subproject Documentation Guidance

Each subproject within `docs/dev_plans/` represents an individual coding or research effort inside the larger repository.
Every subproject contains **four required documents** that together form its lifecycle:

`ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md`, and `PROGRESS_LOG.md`.

Scribe automatically generates these templates, but **agents are responsible for keeping them filled, current, and synchronized**.
If no updates appear in the `PROGRESS_LOG` after ~10 minutes of detected activity, Scribe will issue a gentle reminder to append an entry.

---

## 📘 1. ARCHITECTURE_GUIDE.md — The Blueprint

*(see template )*

**Purpose:** Define the *entire scope* of the subproject before a single line of code is written.
This file is the canonical source of truth for design intent.

**Agent Instructions**

* Write this first, immediately after bootstrapping the subproject.
* Describe **why** the project exists, **what** it must achieve, and **how** it will be structured.
* Include diagrams, data-flow, directory tree, and external dependencies.
* Update it *whenever* architecture or repo layout changes.
* The Phase Plan and Checklist are derived from this document — keep them aligned.

---

## ⚙️ 2. PHASE_PLAN.md — The Roadmap

*(see template )*

**Purpose:** Translate the architecture into a sequence of actionable phases with measurable deliverables.

**Agent Instructions**

* Create this immediately after finishing the Architecture Guide.
* Each phase must list:

  * **Objective** – what this phase accomplishes.
  * **Tasks & Deliverables** – everything needed for review.
  * **Acceptance Criteria** – clear, testable completion signals.
* Assign confidence levels and owners; revise them as progress clarifies.
* The Phase Plan drives both the Checklist and the Progress Log tags (`phase=...` meta).

---

## ✅ 3. CHECKLIST.md — The Verification Map

*(see template )*

**Purpose:** Turn the Phase Plan into a concrete, traceable list of boxes to tick.
Every item must link to proof of completion (commit, screenshot, or `PROGRESS_LOG` entry).

**Agent Instructions**

* Mirror tasks from the Phase Plan exactly; do not invent new ones here.
* Check items only when verifiable evidence exists.
* Include `meta checklist_id=` references in your Scribe entries to maintain traceability.
* Review the checklist weekly; stale or mismatched tasks are blocking issues.

---

## 🗒️ 4. PROGRESS_LOG.md — The Living History

*(see template )*

**Purpose:** Provide an append-only, timestamped audit trail of every meaningful action or discovery.

**Agent Instructions**

* **Use the Scribe MCP tool** (`append_entry`) or `scripts/scribe.py` to add entries—never edit by hand.
* Log after every 2-3 meaningful actions or at least every 10 minutes of active work.
* Include relevant meta (`phase=`, `checklist_id=`, `confidence=`).
* Note failures, design changes, and insights—not just successes.
* Scribe reminders trigger if this file goes quiet too long.
* Rotate logs after ~200 entries to maintain readability.

---

## 🧠 Reminder & Review Logic

Scribe monitors agent activity per tool:

* If **no new `append_entry`** occurs for 10 minutes, it pings the agent to document progress.
* If the **Architecture Guide or Phase Plan** haven’t changed in a long window, Scribe will flag them as *potentially stale*.
* Agents should respond by reviewing and updating relevant docs before continuing development.

---

## 🔁 Standard Workflow Summary

1. **Bootstrap** new subproject with Scribe (`set_project` → auto-generate docs).
2. **Complete `ARCHITECTURE_GUIDE.md`** in full.
3. **Derive `PHASE_PLAN.md`** from architecture.
4. **Generate `CHECKLIST.md`** directly from phase tasks.
5. **Begin active work**, logging frequently via `append_entry`.
6. **Keep all four docs synchronized**; reconcile divergences before major commits.
7. **Treat missing or outdated documentation as a blocking defect.**

---

## 🧩 Philosophy

> “If it wasn’t Scribed, it didn’t happen.”

Every agent operation, design decision, or failure must leave a trace.
The subproject docs together form a *closed loop of accountability*—design, plan, verify, and record.
Follow them religiously, and every project will remain transparent, auditable, and reproducible.

---
