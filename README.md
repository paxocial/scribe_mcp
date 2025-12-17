# 📝 Scribe MCP Server

<div align="center">

**[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](tests/)**
**[![Version](https://img.shields.io/badge/version-2.1-blue)](docs/whitepapers/)**
**[![License](https://img.shields.io/badge/license-Community+Small%20Business-orange)](LICENSE)**

*Enterprise-grade documentation governance for AI-powered development — by Corta Labs*

**Drop-in ready** • **13+ specialized templates** • **Zero-config SQLite** • **Production-tested**

</div>

---

## 🚀 Why Scribe MCP?

Scribe transforms how AI agents and developers maintain project documentation. Instead of scattered notes and outdated docs, Scribe provides **bulletproof audit trails**, **automated template generation**, and **cross-project intelligence** that keeps your entire development ecosystem in sync.

**Perfect for:**
- 🤖 **AI Agent Teams** - Structured workflows and quality grading
- 🏢 **Enterprise Teams** - Audit trails and compliance documentation
- 👨‍💻 **Solo Developers** - Automatic documentation that actually works
- 📚 **Research Projects** - Structured logs and reproducible reports

**Immediate Value:**
- ✅ **30-second setup** - Drop into any repository and start logging
- 🎯 **18+ specialized templates** - From architecture guides to bug reports
- 🔍 **Cross-project search** - Find patterns across your entire codebase
- 📊 **Agent report cards** - Performance grading for AI workflows
- 🛡️ **Bulletproof storage** - Atomic operations with crash recovery

## ⚡ Quick Start

**Get Scribe running in under 60 seconds (MCP-first, CLI optional):**

### 1️⃣ Install Dependencies
```bash
# Clone and navigate to Scribe
git clone <your-repo-url>
cd scribe_mcp

# Set up Python environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install 16 production-ready dependencies
pip install -r requirements.txt
```

### 2️⃣ Launch MCP Server (Primary Integration Path)
```bash
# Start the MCP server for Claude/Claude Code integration
python -m scribe_mcp.server
```

Once connected from Claude / Codex MCP:

- Use **`set_project`** to register/select a project and bootstrap dev_plan docs (pass `root=/abs/path/to/repo` to work in any repo).
- Use **`append_entry`** for all logging (single/bulk).
- Use **`manage_docs`** for architecture/phase/checklist updates.
- Use **`read_recent` / `list_projects`** to resume context after compaction.

### 3️⃣ (Optional) Manual CLI Logging

For shell workflows or quick one-off logs, you can call the MCP-aligned CLI:

```bash
# From the scribe_mcp directory or MCP_SPINE root
python -m scribe_mcp.scripts.scribe "🚀 My project is ready!" --status success --emoji 🎉
```

Under the hood this uses `set_project` + `append_entry`, so manual usage stays in sync with the registry, SQLite mirror, and reminder system.

---

## 🎯 Try These Examples

**Project Management:**
```bash
# Log project milestones
python -m scribe_mcp.scripts.scribe "Completed authentication module" --status success --meta component=auth,tests=47

# Track bugs and issues
python -m scribe_mcp.scripts.scribe "Fixed JWT token expiry bug" --status bug --meta severity=high,component=security
```

**Automatic log routing (BUG / SECURITY)**
- `status=bug` (or a bug emoji) will also write to `BUG_LOG.md` when required meta is present (`severity`, `component`, `status`).
- Security events can also tee to `SECURITY_LOG.md` (example: use a security emoji, or `--meta security_event=true,impact=...,status=...`).
- If required meta is missing, Scribe returns a teaching reminder instead of inventing data.

**Research Workflows:**
```bash
# Document research findings
python -m scribe_mcp.scripts.scribe "Discovered performance bottleneck in database queries" --status info --meta research=true,impact=high
```

**Team Collaboration:**
```bash
# List all projects
python -m scribe_mcp.scripts.scribe --list-projects

# Switch between projects
python -m scribe_mcp.scripts.scribe "Starting new feature work" --project frontend --status plan
```

---

## 🛠️ Installation Options

### Prerequisites
- **Python 3.11+** - Modern Python with async support
- **pip** - Standard Python package manager
- **Optional:** PostgreSQL for team deployments (SQLite works out of the box)

### Storage Backends

**🗄️ SQLite (Default - Zero Config)**
- Perfect for solo developers and small teams
- No setup required - just run and go
- Automatic database creation and management

**🐘 PostgreSQL (Enterprise)**
- Ideal for large teams and production deployments
- Set environment variables before starting:
  ```bash
  export SCRIBE_STORAGE_BACKEND=postgres
  export SCRIBE_DB_URL=postgresql://user:pass@host:port/database
  ```

### MCP Integration

In all examples below, **`REPO_ROOT`** means the directory that contains the
`scribe_mcp` package (i.e., where `scribe_mcp/server.py` lives). In your
personal setup this might be `.../MCP_SPINE`, but in the public repo it will
typically just be the cloned `scribe_mcp` directory.

**For Claude Desktop (JSON config):**
```jsonc
{
  "mcpServers": {
    "scribe": {
      // Run from REPO_ROOT so `scribe_mcp` imports resolve
      "command": "bash",
      "args": [
        "-lc",
        "cd /absolute/path/to/REPO_ROOT && exec python -m scribe_mcp.server"
      ],
      "env": {
        // Optional: override storage backend; SQLite is default
        "SCRIBE_STORAGE_BACKEND": "sqlite"
      }
    }
  }
}
```

**For Codex / Claude Code CLI:**
```bash
# From anywhere; codex will remember this configuration
codex mcp add scribe \
  --env SCRIBE_STORAGE_BACKEND=sqlite \
  -- bash -lc 'cd /absolute/path/to/REPO_ROOT && exec python -m scribe_mcp.server'
```

Notes:
- We intentionally **do not** bake a per-repo root into the MCP config. Scribe is multi-repo: switch repos by calling `set_project(name=..., root=/abs/path/to/repo)` (no MCP re-register needed).
- The same `bash -lc "cd REPO_ROOT && python -m scribe_mcp.server"` pattern works for any MCP client that expects a stdio server command.

---

## 🌐 Using Scribe Outside This Repo

You can run Scribe from any codebase (not just `MCP_SPINE`) by pointing it at that project’s root:

1. Start the MCP server from the Scribe codebase (once), then use `set_project(..., root=/abs/path/to/your/repo)` to target any repository.
2. Optional env vars:
   - `SCRIBE_STATE_PATH=/abs/path/to/state.json` (per-user; must be writable)
   - `SCRIBE_STORAGE_BACKEND=postgres` and `SCRIBE_DB_URL=postgresql://...` if you want Postgres.
3. Ensure `PYTHONPATH` includes the parent of `scribe_mcp` so imports work when launched from elsewhere.

---

## 🧠 Project Registry & Lifecycle (High-Level)

Scribe includes a **SQLite-backed Project Registry** that tracks every project’s lifecycle and documentation state:

- **Lifecycle states**: `planning`, `in_progress`, `blocked`, `complete`, `archived`, `abandoned`.
- **Core hooks**:
  - `set_project` – bootstraps docs (`ARCHITECTURE_GUIDE`, `PHASE_PLAN`, `CHECKLIST`, `PROGRESS_LOG`) and ensures a registry row exists.
  - `append_entry` – writes progress logs, updates activity metrics, and can auto‑promote `planning` → `in_progress` once docs + first entry exist.
  - `manage_docs` – applies atomic doc updates and records baseline/current hashes and doc‑hygiene flags in the registry.
  - `list_projects` – surfaces registry data (status, timestamps, counts, tags, `meta.activity`, `meta.docs.flags`) with filters like `status`, `tags`, and `order_by`.

At a glance, you can:
- See which projects are fresh, stale, or long inactive.
- Detect when architecture/phase/checklist docs are still at template state.
- Spot drift between implementation logs and documentation.

For full technical details, see `docs/whitepapers/scribe_mcp_whitepaper.md`.

---

## 📜 License & Commercial Use

Scribe MCP is **source-available** and free to use for:

- Individual developers
- Open-source contributors
- Researchers and educational use
- Small teams and small businesses that:
  - Have **fewer than 25 employees**, and
  - Generate **less than $1,000,000 USD in annual revenue**, and
  - Are **not** selling, hosting, or packaging Scribe MCP (or derivatives) as part of a paid product or service.

You **may not** use Scribe MCP under the community license if:

- Your organization exceeds the employee or revenue limits above, or
- You embed Scribe MCP into a paid SaaS, internal platform, or commercial agent/orchestration product.

For enterprise or large-scale commercial use, contact **licensing@cortalabs.com** to obtain a commercial license.

Details:

- Current code is licensed under the **Scribe MCP License (Community + Small Business License)** in `LICENSE`.
- Earlier snapshots were MIT-licensed; see `LICENSE_HISTORY.md` for historical licensing context.

Notes:
- `.env` is auto-loaded on startup when present (via python-dotenv); shell exports/direnv still work the same.
- Overlap checks only block true path collisions (same progress_log/docs_dir). Sharing one repo root with many dev_plan folders is supported.

---

## 🎨 Template System Showcase

**Scribe includes 13+ specialized templates** that auto-generate professional documentation:

### 📋 Document Templates
- **📐 Architecture Guides** - System design and technical blueprints
- **📅 Phase Plans** - Development roadmaps with milestones
- **✅ Checklists** - Verification ledgers with acceptance criteria
- **🔬 Research Reports** - Structured investigation documentation
- **🐛 Bug Reports** - Automated issue tracking with indexing
- **📊 Agent Report Cards** - Performance grading and quality metrics
- **📝 Progress Logs** - Append-only audit trails with UTC timestamps
- **🔒 Security Logs** - Compliance and security event tracking

### 🚀 Template Features
- **🔒 Security Sandboxing** - Jinja2 templates run in restricted environments
- **📝 Template Inheritance** - Create custom template families
- **🎯 Smart Discovery** - Project → Repository → Built-in template hierarchy (precedence: `.scribe/templates` → repo custom → project templates → packs → built-ins)
- **⚡ Atomic Generation** - Bulletproof template creation with integrity verification

For a deeper dive into available variables and expected metadata per template, see `docs/TEMPLATE_VARIABLES.md`.

### Example: Generate Architecture Guide
```bash
# Auto-generate a complete architecture document
python -m scribe_mcp.scripts.scribe "Generated architecture guide for new project" --status success --meta template=architecture,auto_generated=true
```

---

## 💻 CLI Power Tools

**Scribe's command-line interface (386 lines of pure functionality)** gives you complete control:

### 🎯 Core Commands
```bash
# List all available projects
python -m scribe_mcp.scripts.scribe --list-projects

# Log with rich metadata
python -m scribe_mcp.scripts.scribe "Fixed critical bug" \
  --status success \
  --emoji 🔧 \
  --meta component=auth,tests=12,severity=high

# Dry run to preview entries
python -m scribe_mcp.scripts.scribe "Test message" --dry-run

# Switch between projects
python -m scribe_mcp.scripts.scribe "Starting frontend work" \
  --project mobile_app \
  --status plan
```

### 🎨 Rich Features
- **🎭 Emoji Support** - Built-in emoji mapping for all status types
- **📊 Metadata Tracking** - Rich key=value metadata for organization
- **🔍 Multiple Log Types** - Progress, bugs, security, and custom logs
- **📅 Timestamp Control** - Override timestamps for bulk imports
- **🎯 Project Discovery** - Automatic project configuration detection

### Status Types & Emojis
- `info` ℹ️ - General information and updates
- `success` ✅ - Completed tasks and achievements
- `warn` ⚠️ - Warning messages and cautions
- `error` ❌ - Errors and failures
- `bug` 🐞 - Bug reports and issues
- `plan` 📋 - Planning and roadmap entries

---

## 🔍 Enterprise Features

### 📊 Agent Report Cards
**Performance grading infrastructure** for AI workflows:
- Quality metrics tracking and trend analysis
- Performance levels with UPSERT operations
- Automated agent evaluation and reporting

### 🔒 Security & Compliance
- **🛡️ Security Sandboxing** - Restricted Jinja2 environments with 22+ built-in controls
- **📋 Audit Trails** - Complete change tracking with metadata
- **🔐 Access Control** - Path validation and input sanitization
- **📊 Compliance Reporting** - Structured logs for regulatory requirements

### ⚡ Advanced Search
**Phase 4 Enhanced Search** capabilities:
- 🔍 **Cross-Project Validation** - Find patterns across your entire codebase
- 📊 **Relevance Scoring** - 0.0-1.0 quality filtering
- 🎯 **Code Reference Verification** - Validate referenced code exists
- 📅 **Temporal Filtering** - Search by time ranges ("last_30d", "last_7d")

### 💾 Bulletproof Storage
- **🗄️ Multi-Backend Support** - SQLite (zero-config) + PostgreSQL (enterprise)
- **⚡ Atomic Operations** - Temp-file-then-rename with fsync guarantees
- **🔄 Write-Ahead Logging** - Bulletproof crash recovery with journaling
- **✅ Integrity Verification** - Automatic corruption detection and recovery

---

## 🧠 Intelligent Reminders

**Scribe keeps your documentation in sync** with intelligent context awareness:

### 📋 Smart Reminders
Every MCP tool response includes contextual reminders about:
- 📅 **Stale Documentation** - When architecture docs need updates
- ⏰ **Overdue Logs** - Gentle nudges to maintain progress tracking
- 🎯 **Project Context** - Active project status and recent activity
- 🔄 **Drift Detection** - When implementation deviates from plans

Reminders are throttled with a short cooldown per `(repo_root, agent_id)` so you see what matters without constant repetition. If an agent gets confused, you can clear cooldowns with `set_project(reset_reminders=true)`.

If you call a project-bound tool without selecting a project, Scribe returns a “last known project” hint (including last access time) to help you recover quickly.

### ⚙️ Customization
```json
{
  "name": "my_project",
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

### 🌍 Environment Variables
- `SCRIBE_REMINDER_IDLE_MINUTES` - Work session reset timeout (default: 45)
- `SCRIBE_REMINDER_WARMUP_MINUTES` - Grace period after resuming (default: 5)
- `SCRIBE_REMINDER_DEFAULTS` - JSON configuration for all projects
- `SCRIBE_REMINDER_CACHE_PATH` - Optional path for reminder cooldown cache (default: `data/reminder_cooldowns.json`)

---

## 🏗️ Project Structure

```
scribe_mcp/                     # 🏛️ Main Scribe MCP server
├── 📁 config/
│   ├── 📁 projects/           # Per-project configurations
│   └── 📄 mcp_config.json     # Sample MCP configuration
├── 📁 docs/                   # 📖 Server docs (whitepapers, guides)
├── 📁 templates/              # 🎨 Jinja2 template system
│   ├── 📁 documents/          # 13+ specialized templates
│   ├── 📁 fragments/          # Reusable template pieces
│   └── 📁 custom/             # Your custom templates
├── 📁 tools/                  # 🔧 MCP tool implementations
├── 📁 storage/                # 💾 Multi-backend storage layer
├── 📁 scripts/                # 💻 CLI utilities
├── 📁 tests/                  # 🧪 Comprehensive test suite
└── 📄 server.py               # 🚀 MCP server entrypoint
```

**Per-repo output location (dev plans + logs)**
- Default: `<repo>/.scribe/docs/dev_plans/<project_slug>/...`
- Back-compat: if `<repo>/docs/dev_plans/<project_slug>` exists, Scribe keeps using it.
- Override: set `SCRIBE_DEV_PLANS_BASE` (example: `docs/dev_plans`) to force a different base.

---

## 🧪 Testing & Quality

**Comprehensive testing infrastructure** with 79+ test files:

### 🧪 Run Tests
```bash
# Run all functional tests (69 tests)
pytest

# Run performance tests with file size benchmarks
pytest -m performance

# Run specific test categories
pytest tests/test_tools.py
pytest tests/test_storage.py
```

### ✅ Quality Assurance
- **🔬 Functional Testing** - 69 comprehensive tests covering all core functionality
- **⚡ Performance Testing** - Optimized benchmarks for file operations
- **🛡️ Security Testing** - Template sandboxing and access control validation
- **🔄 Integration Testing** - MCP server protocol compliance verification

### 🚀 Smoke Test
```bash
# Quick MCP server validation
python scripts/test_mcp_server.py
```

---

## 💡 Real-World Use Cases

### 🤖 AI Agent Teams
**Structured workflows for AI development:**
```bash
# Research phase
python -m scribe_mcp.scripts.scribe "Research completed: authentication patterns" --status info --meta phase=research,confidence=0.9

# Architecture phase
python -m scribe_mcp.scripts.scribe "Architecture guide updated with auth design" --status success --meta phase=architecture,sections=5

# Implementation phase
python -m scribe_mcp.scripts.scribe "JWT authentication implemented" --status success --meta phase=implementation,tests=47,coverage=95%
```

### 🏢 Enterprise Documentation
**Compliance and audit trails:**
```bash
# Security events
python -m scribe_mcp.scripts.scribe "Security audit completed - all controls verified" --log security --status success --meta auditor=external,findings=0

# Change management
python -m scribe_mcp.scripts.scribe "Production deployment completed" --status success --meta version=v2.1.0,rollback_available=true
```

### 📚 Research Projects
**Structured research documentation:**
```bash
# Research findings
python -m scribe_mcp.scripts.scribe "Performance bottleneck identified in database queries" --status info --meta research=true,impact=high,evidence=query_analysis

# Experiment results
python -m scribe_mcp.scripts.scribe "A/B test results: new algorithm 23% faster" --status success --meta experiment=performance_optimization,improvement=23%
```

---

## 🔧 Troubleshooting

### Common Issues & Solutions

**🚨 MCP SDK Missing**
```bash
# Install the MCP Python SDK
pip install mcp
```

**🔧 No Tools Returned**
```bash
# Ensure all modules are properly imported
# Check that your virtual environment is active
source .venv/bin/activate

# Verify tool imports
python -c "from scribe_mcp.tools import *; print('All tools loaded')"
```

**🗄️ SQLite Permission Issues**
```bash
# Check your state/db paths are writable
echo $SCRIBE_STATE_PATH
ls -la $(dirname "$SCRIBE_STATE_PATH")

# Check the target repo is writable (Scribe writes under <repo>/.scribe/ by default)
ls -la /abs/path/to/your/repo
ls -la /abs/path/to/your/repo/.scribe || true
```

**🐍 Python Path Issues**
```bash
# Ensure you're running from the correct directory
# Run from MCP_SPINE parent directory, not inside scribe_mcp/
pwd  # Should show .../MCP_SPINE/

# Test import path
python -c "import sys; sys.path.insert(0, '.'); from scribe_mcp.config.settings import settings; print('✅ Imports working')"
```

**⚡ Server Not Starting**
```bash
# Check required dependencies
pip install -r requirements.txt

# Verify server startup with timeout
timeout 5 python -m scribe_mcp.server || echo "✅ Server starts correctly"
```

### Getting Help

- **📖 Documentation**: Check `docs/whitepapers/scribe_mcp_whitepaper.md` for comprehensive technical details
- **🧪 Test Suite**: Run `pytest` to verify system functionality
- **📋 Project Templates**: Use `--list-projects` to see available configurations
- **🔍 Smoke Test**: Run `python scripts/test_mcp_server.py` for MCP validation

---

## 🤝 Contributing

**We welcome contributions!** Here's how to get started:

### 🧪 Development Workflow
```bash
# 1. Run the test suite
pytest

# 2. Verify MCP server functionality
python scripts/test_mcp_server.py

# 3. Test your changes
python -m scribe_mcp.scripts.scribe "Testing new feature" --dry-run

# 4. Log your contribution
python -m scribe_mcp.scripts.scribe "Added new feature: description" --status success --meta contribution=true,feature_type=enhancement
```

### 📋 Development Guidelines
- **✅ Test Coverage**: All new features must include tests
- **📝 Documentation**: Update relevant documentation sections
- **🔧 Integration**: Ensure MCP server compatibility
- **🛡️ Security**: Follow security best practices for templates and inputs

### 🚀 Quality Standards
- **🧪 69+ functional tests** must pass
- **⚡ Performance benchmarks** for file operations
- **🔒 Security validation** for template sandboxing
- **📋 MCP protocol compliance** verification

---

## 📚 Further Reading

### 📖 Technical Documentation
- **[📄 Whitepaper v2.1](docs/whitepapers/scribe_mcp_whitepaper.md)** - Comprehensive technical architecture
- **[🔧 API Reference](docs/api/)** - Complete MCP tool documentation
- **[🎨 Template Guide](docs/templates/)** - Custom template development
- **[🏗️ Architecture Patterns](docs/architecture/)** - System design and integration

### 🌟 Advanced Features
- **🤖 Claude Code Integration** - Structured workflows and subagent coordination
- **📊 Agent Report Cards** - Performance grading and quality metrics
- **🔍 Vector Search** - FAISS integration for semantic search
- **🔐 Security Framework** - Comprehensive access control and audit trails

### 🚀 Production Deployment
- **🐘 PostgreSQL Setup** - Enterprise-scale deployment guide
- **📈 Monitoring** - Performance tracking and alerting
- **🔄 Backup & Recovery** - Data protection strategies
- **🌐 Multi-tenant** - Organizational deployment patterns

---

## 🙏 Acknowledgments

Built with passion for better documentation and AI-human collaboration. Special thanks to:
- The **MCP protocol** team for the standardized AI tool interface
- **Jinja2** for the powerful and secure templating system
- Our **early adopters** for invaluable feedback and feature suggestions

---

<div align="center">

**🚀 Ready to transform your documentation?**

[Start Logging](#-quick-start) • [Explore Templates](#-template-system-showcase) • [Read Whitepaper](docs/whitepapers/scribe_mcp_whitepaper.md)

*Join thousands of developers and AI teams using Scribe for bulletproof documentation governance*

</div>
