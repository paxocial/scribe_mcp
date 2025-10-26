# Scribe MCP Server

Scribe is a Model Context Protocol (MCP) server that keeps project documentation and progress logs consistent across agents. This repo ships a lightweight stdio server, filesystem/DB storage backends, and tooling to keep docs in sync with day-to-day development.

## Prerequisites
- Python 3.11+
- `pip` (or your preferred package manager)
- (Optional) PostgreSQL if you want shared storage instead of the default SQLite backend

Install Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick Start
1. **Install dependencies** (see above).
2. **Choose a storage backend** via environment variables:
   - SQLite (default): no action required.
   - PostgreSQL: set `SCRIBE_STORAGE_BACKEND=postgres` and `SCRIBE_DB_URL=postgresql://...`.
3. **Launch the server**:
   ```bash
   python server.py
   ```

### Claude / MCP Configuration
Copy `config/mcp_config.json` into your Claude Desktop/Code MCP configuration and adjust the `SCRIBE_ROOT` path to point to this repository:

```json
{
  "mcpServers": {
    "scribe": {
      "command": "python",
        "args": ["/absolute/path/to/scribe_mcp/server.py"],
        "env": {
        "SCRIBE_ROOT": "/absolute/path/to/scribe_mcp",
        "SCRIBE_STORAGE_BACKEND": "sqlite"
        }
    }
  }
}
```

### Smoke Test
Verify the MCP server responds before wiring it into an IDE:

```bash
python scripts/test_mcp_server.py
```

This script runs a short-lived stdio session and checks that the server advertises tools.

### Reminder Metadata
Every MCP tool responds with a `reminders` array containing context like stale docs, overdue logs, and the active project. Use these cues to keep architecture, phase plan, and checklist in lockstep with the work you’re doing.

#### Customising reminders
- Set `defaults.reminder` inside a project config (or `SCRIBE_REMINDER_DEFAULTS` env JSON) to tweak behaviour. Example:

```json
{
  "name": "scribe_mcp",
  "defaults": {
    "reminder": {
      "tone": "friendly",
      "log_warning_minutes": 15,
      "log_urgent_minutes": 30,
      "severity_weights": {"warning": 7, "urgent": 10}
    }
  }
}
```

- Environment variables:
  - `SCRIBE_REMINDER_IDLE_MINUTES` — gap (minutes) before a new work session resets and warm-up kicks in (default: 45).
  - `SCRIBE_REMINDER_WARMUP_MINUTES` — grace period after resuming before warnings escalate (default: 5).
  - `SCRIBE_REMINDER_DEFAULTS` — JSON blob applied to every project when specific overrides aren’t set.

## Project Structure
- `MCP_SPINE/` – container package for MCP servers.
  - `scribe_mcp/` – Scribe server entrypoint, tools, storage backends, utilities.
  - `config/projects/` – per-project Scribe configs.
  - `config/mcp_config.json` – sample MCP configuration for Claude.
  - `docs/dev_plans/` – architecture, phase plan, checklist, and progress log.
  - `scripts/test_mcp_server.py` – smoke test for the MCP server.
  - `tests/` – unit tests (run with `pytest MCP_SPINE/tests`).

## Development Workflow
1. Select a project with `set_project` (either via MCP tool or `scripts/scribe.py`).
2. Use `append_entry` to log every meaningful change—Scribe tracks both the markdown log and (optionally) a database mirror.
3. Keep docs aligned with implementation; reminder tooling surfaces when architecture/phase plan/checklist drift.

## Troubleshooting
- **Missing MCP SDK**: install `pip install mcp` if the server exits with “MCP Python SDK not installed.”
- **No tools returned**: ensure `scribe_mcp/tools/__init__.py` imports all modules and that your virtual environment is active.
- **SQLite permissions**: confirm `SCRIBE_ROOT` is writable; the server stores SQLite databases under the repo by default.

## Contributing
1. Run `pytest MCP_SPINE/tests`.
2. Execute `python MCP_SPINE/scripts/test_mcp_server.py`.
3. Update docs (`MCP_SPINE/docs/dev_plans/scribe_mcp/…`) and log your changes with `MCP_SPINE/scripts/scribe.py`.


Alright, here’s the no‑BS rundown for wiring your custom Scribe MCP server into Codex CLI on WSL.  Follow the steps; swear at me later if it still doesn’t work.

### 1. Set up Scribe in your WSL project

1. **Clone / extract the repo and install dependencies.**
   From `~/projects/Scribe`, create a venv and install Python deps:

   ```bash
   cd ~/projects/Scribe
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   Scribe needs Python 3.11+; you already knew that.

2. **Decide on a storage backend.**

   * SQLite (default): do nothing – Scribe will drop a `.sqlite` file in your project directory.
   * PostgreSQL: set `SCRIBE_STORAGE_BACKEND=postgres` and `SCRIBE_DB_URL=postgresql://user:pass@host/db` before launching the server.

3. **Pick a root for your docs/logs.**
   Scribe uses `SCRIBE_ROOT` to find your project configs, dev plans and logs.  Point this at the `MCP_SPINE` directory of your Scribe repo (e.g. `/home/austin/projects/MCP_SPINE/scribe_mcp`).  This is where the per‑project configs live under `config/projects/` – you can drop new YAML/JSON files there for each subproject.

### 2. Smoke‑test the server locally

Before hooking it to Codex, make sure the damn thing responds.

```bash
export SCRIBE_ROOT=/home/austin/projects/MCP_SPINE/scribe_mcp
export SCRIBE_STORAGE_BACKEND=sqlite   # or postgres with DB_URL
python -m MCP_SPINE.scribe_mcp.server
```

In another terminal you can run the provided smoke test:

```bash
python MCP_SPINE/scripts/test_mcp_server.py
```

The test fires up a short STDIO session, calls `tools/list` and checks that the server advertises tools.  Fix any errors here before blaming Codex.

### 3. Tell Codex about your server

Codex CLI supports connecting to custom MCP servers via `codex mcp add <name> ...` or by editing the `~/.codex/config.toml` file.  The official docs confirm both methods.

#### Option A – use the CLI

Run this once to register Scribe as an MCP server (adjust paths/envs accordingly):

```bash
codex mcp add scribe \
  --env SCRIBE_ROOT=/home/austin/projects/MCP_SPINE/scribe_mcp \
  --env SCRIBE_STORAGE_BACKEND=sqlite \
  -- python -m MCP_SPINE.scribe_mcp.server
```

* The `--env` flags set environment variables for the server.  You can repeat `--env` for `SCRIBE_DB_URL` if using Postgres.
* Everything after `--` is the actual command used to launch the STDIO server.
* Codex stores this in `~/.codex/config.toml` for you.

You can verify it worked with `codex mcp ls` or by launching `codex`, entering its TUI, and typing `/mcp`.  Healthy servers will show up there.

#### Option B – edit the config file

If you prefer hand‑editing, open `~/.codex/config.toml` and append the following:

```toml
[mcp_servers.scribe]
command = "python"
args = ["-m", "MCP_SPINE.scribe_mcp.server"]

[mcp_servers.scribe.env]
SCRIBE_ROOT = "/home/austin/projects/MCP_SPINE/scribe_mcp"
SCRIBE_STORAGE_BACKEND = "sqlite"
# SCRIBE_DB_URL = "postgresql://…"  # uncomment for postgres
```

Codex reads this file on startup; the docs note that each MCP server lives under its own `[mcp_servers.<name>]` table with `command`, `args` and `env` entries.  Save it and relaunch `codex`.

### 4. Kick the tires

1. Launch Codex:

   ```bash
   codex
   ```
2. Once inside the TUI, list MCP servers with `/mcp`.  You should see `scribe` listed as healthy.
3. Ask Codex to call a tool, e.g. `/mcp call scribe tools/list` to see what Scribe advertises.  If that works, you’re good.

### 5. Dealing with multiple projects

* Each project/subproject should have its own config file under `MCP_SPINE/config/projects/`.  Name the file after the project (e.g. `myapp.json` or `myapp.yaml`) and define settings like `defaults.reminder` there.
* Use Scribe’s `set_project` tool to switch between them at runtime; the server uses `SCRIBE_ROOT` to locate these configs.
* Scribe logs docs/changes under `docs/dev_plans/` per project, so keep your directory structure tidy.

### 6. Run it under Windows

Codex CLI’s Windows support is experimental; OpenAI recommends WSL—you’re already using it.  The commands above should work unchanged in your WSL shell.  If you need to call it from a Windows terminal, use the `\\wsl$\Ubuntu\home\austin\projects\Scribe` style paths.

That’s it.  Set the environment variables, smoke‑test the server, register it with Codex via `codex mcp add` or `config.toml`, and verify with `/mcp` in the Codex TUI.  Once it’s hooked up, you can start logging and updating docs across your codebases.  Go forth and build your Frankenstein of subprojects—Scribe will keep the mess slightly less messy.
