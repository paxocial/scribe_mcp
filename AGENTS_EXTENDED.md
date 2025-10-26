# 🧠 AGENTS_EXTENDED.md — Scribe MCP Server (Internal)

**Author:** CortaLabs
**Maintainer:** UAP / Sanctum Division
**Version:** v1.0 Extended
**Last Updated:** 2025-10-22

---

## 🧭 Purpose & Doctrine

Scribe exists to **enforce total traceability** across every project, subproject, and agentic action under the CortaLabs ecosystem.

It is the **central audit trail** of Sanctum — a living record of all progress, discoveries, failures, and design changes.
If something meaningful happens and isn’t Scribed, it’s assumed to have *never occurred*.

> “If it wasn’t Scribed, it didn’t happen.”

### Guiding Principles

* **Append-only.** Nothing is ever rewritten or deleted. History is immutable.
* **Deterministic.** Every log line is machine-readable and timestamped in UTC.
* **Agent-centric.** Human and AI operators use the same interface and follow the same rules.
* **Observable.** All work is auditable via plain text, SQL, or dashboard views.
* **Portable.** Scribe integrates with any repo through the MCP protocol.

---

## 🧩 Architectural Overview

### Core Design

Scribe runs as a **Modular MCP Server**, exposing simple tools that handle:

* project discovery and selection,
* document bootstrapping,
* structured log appends,
* optional persistence into SQLite or Postgres,
* and eventual external sync (e.g. GitHub, dashboards).

All logs and metadata live under each repo’s `docs/dev_plans/<slug>/` directory, ensuring locality and version control alignment.

### System Flow

```mermaid
flowchart TD
  Agent["Agent / MCP Tool"] -->|JSON payload| Scribe["Scribe MCP Server"]
  Scribe -->|append_entry| LogFile["PROGRESS_LOG.md"]
  Scribe -->|optional mirror| SQLite[(SQLite DB)]
  SQLite --> Postgres[(Postgres Mirror - optional)]
  Scribe -->|generate| Docs["ARCHITECTURE_GUIDE / PHASE_PLAN / CHECKLIST"]
  Docs --> Human["Developers & Reviewers"]
```

This ensures **bidirectional traceability** between design (architecture), planning (phase), verification (checklist), and execution (log).

---

## 🧱 Storage Architecture

Scribe supports two persistence layers:

### 1. Local Filesystem (Default)

* Every project folder contains markdown logs and docs.
* Ideal for single-developer or local-first workflows.
* Immutable append via MCP ensures safety from accidental edits.

### 2. Optional Postgres Mirror

When `SCRIBE_DB_URL` is set:

* Entries are mirrored to a per-repo `scribe_entries` table.
* Integrity hashes (`sha256`) guarantee replay safety.
* Indexed by `(project_id, ts DESC)` for query speed.

#### Example Schema

```sql
CREATE TABLE scribe_projects (
  id uuid PRIMARY KEY,
  name text,
  repo_root text,
  progress_log_path text,
  created_at timestamptz default now()
);

CREATE TABLE scribe_entries (
  id uuid PRIMARY KEY,
  project_id uuid references scribe_projects(id),
  ts timestamptz,
  emoji text,
  agent text,
  message text,
  meta jsonb,
  raw_line text,
  sha256 text,
  created_at timestamptz default now()
);

CREATE INDEX idx_entries_project_ts ON scribe_entries(project_id, ts DESC);
CREATE INDEX idx_entries_meta_gin ON scribe_entries USING GIN (meta);
```

---

## 🧮 Canonical Log Format

```
[2025-10-22 10:21:14 UTC] [✅] [Agent: SnapshotAgent] [Project: IMPLEMENTATION TESTING] Message body | key=value; key2=value
```

| Field     | Description                                                              |
| --------- | ------------------------------------------------------------------------ |
| Timestamp | Always UTC                                                               |
| Emoji     | Visual status marker (`info`, `success`, `warn`, `error`, `bug`, `plan`) |
| Agent     | Origin of the action                                                     |
| Project   | Context of the operation                                                 |
| Message   | One-line summary                                                         |
| Meta      | Key-value pairs; sorted alphabetically                                   |

---

## 🔩 Integration Surfaces

### 1. MCP Protocol

* Primary interface for both AI and automation agents.
* Lightweight JSON input/output.
* Stateless, modular, and CLI-compatible.

### 2. CLI Utility (`scripts/scribe.py`)

* Mirrors all MCP tools for human use.
* Acts as a fallback in case the MCP server is not running.

### 3. External Bridges (Optional)

* **GitHub Sync:** Post rendered summaries to issues or discussions.
* **Analytics Dashboards:** Use Postgres mirror for BI tooling or Grafana panels.
* **AI Assistants:** Provide Scribe logs as structured memory sources for reasoning.

---

## 🧱 Scribe Tool Philosophy

| Tool               | Intent                                | Agent Obligation                                   |
| ------------------ | ------------------------------------- | -------------------------------------------------- |
| `set_project`      | Initialize or switch current project. | Always set this first; generates docs if missing.  |
| `append_entry`     | Append structured log line.           | Use after every meaningful action or discovery.    |
| `read_recent`      | Tail last N entries.                  | Review context before continuing work.             |
| `rotate_log`       | Archive large logs.                   | Rotate when file exceeds ~200 entries.             |
| `db.persist_entry` | Mirror entry to DB.                   | Optional, triggered automatically when configured. |
| `db.query`         | Perform quick analytics.              | Use for dashboards or summaries.                   |
| `gh.post`          | Sync status to GitHub.                | Off by default; manual activation required.        |

---

## 🧭 Roadmap

| Version  | Feature                               | Status         |
| -------- | ------------------------------------- | -------------- |
| **v1.1** | Database mirror + query filters       | ✅ Planned      |
| **v1.2** | Multi-root project scanning           | 🔜 In progress |
| **v1.3** | Integrity attestations (rolling hash) | ⏳ Planned      |
| **v2.0** | Optional LLM enrichment summaries     | ⚙️ Deferred    |

---

## 🔐 Security & Policy

* **Default mode:** local, no network calls.
* **LLMs:** disabled on the hot path for determinism.
* **DB/GitHub:** opt-in via env vars.
* **Tamper resistance:** all logs are append-only with optional file locking.
* **Auth:** none for local stdio mode; token required for remote.

---

## 🧠 Cultural Doctrine

Scribe enforces a cultural norm of **radical transparency**.

Every agent, human or synthetic, must maintain:

1. **An unbroken audit trail** of its operations.
2. **Synchronized design documentation** (architecture ↔ plan ↔ checklist ↔ log).
3. **Immediate accountability** for stale or missing entries.

> The Scribe mindset:
> Log everything.
> Keep documentation living.
> Never assume memory — make it written truth.

---

## 🪶 Appendix — Environment Variables

```
SCRIBE_ROOT=/abs/path/to/scribe
SCRIBE_DB_URL=postgresql://user:pass@localhost:5432/scribe
SCRIBE_ALLOW_NETWORK=false
SCRIBE_DEFAULT_PROJECT=scribe_mcp
```

---

