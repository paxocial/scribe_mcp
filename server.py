"""Entrypoint for the Scribe MCP server."""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Awaitable, Callable, Dict, Protocol, cast

# Ensure the repository root (which contains the `scribe_mcp` package) is on sys.path.
# This allows running `python server.py` or `python -m server` from within the package directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:  # pragma: no cover - optional dependency
    from mcp.server import Server  # type: ignore
    from mcp.server import stdio as mcp_stdio  # type: ignore
    from mcp import types as mcp_types  # type: ignore
    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _MCP_AVAILABLE = False

    class _ServerStub:
        def __init__(self, name: str) -> None:
            self.name = name

        def tool(self, _name: str | None = None):
            def decorator(func):
                return func

            return decorator

        def on_startup(self, func):
            return func

        def on_shutdown(self, func):
            return func

        def create_initialization_options(self) -> dict[str, Any]:
            return {}

        async def run(self, *args, **kwargs) -> None:
            raise RuntimeError(
                "MCP Python SDK not installed. Install the 'mcp' package to run the server."
            )

        def run_stdio(self) -> None:
            raise RuntimeError(
                "MCP Python SDK not installed. Install the 'mcp' package to run the server."
            )

    class _MissingStdIOServer:
        async def __aenter__(self) -> tuple[Any, Any]:
            raise RuntimeError(
                "MCP Python SDK not installed. Install the 'mcp' package to run the stdio server."
            )

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    def _missing_stdio_server() -> AsyncIterator[tuple[Any, Any]]:
        return _MissingStdIOServer()

    Server = _ServerStub  # type: ignore
    mcp_stdio = type("_StubStdIO", (), {"stdio_server": _missing_stdio_server})()  # type: ignore
    mcp_types = None  # type: ignore

from scribe_mcp.config.settings import settings
from scribe_mcp.state import StateManager
from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.utils.sentinel_logs import log_scope_violation
from scribe_mcp.state.agent_manager import init_agent_context_manager
from scribe_mcp.state.agent_identity import init_agent_identity
from scribe_mcp.storage import create_storage_backend

if TYPE_CHECKING:
    class ToolDecorator(Protocol):
        def __call__(self, func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]: ...

    class ToolServer(Server):
        def tool(
            self,
            func: Callable[..., Awaitable[Any]] | None = None,
            **_: Any,
        ) -> ToolDecorator: ...

        def list_tools(self, *args: Any, **kwargs: Any) -> ToolDecorator: ...

        def call_tool(self, *args: Any, **kwargs: Any) -> ToolDecorator: ...

if TYPE_CHECKING:
    _server_instance: ToolServer = cast("ToolServer", Server(settings.mcp_server_name))
    app = _server_instance
else:
    app = Server(settings.mcp_server_name)
state_manager = StateManager()
storage_backend = create_storage_backend()
agent_context_manager = None  # Will be initialized in startup
agent_identity = None  # Will be initialized in startup
router_context_manager = RouterContextManager()
_startup_complete = False

if _MCP_AVAILABLE:
    from mcp import types as mcp_types

    if not hasattr(app, "tool"):
        if not hasattr(Server, "_scribe_tool_registry"):
            Server._scribe_tool_registry = {}
            Server._scribe_tool_defs = {}

        def _tool_decorator(
            func: Callable[..., Awaitable[Any]] | None = None,
            *,
            name: str | None = None,
            description: str | None = None,
            input_schema: Dict[str, Any] | None = None,
            output_schema: Dict[str, Any] | None = None,
        ):
            def register(target: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
                tool_name = name or target.__name__
                schema = input_schema or {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                }
                tool_description = description or (inspect.getdoc(target) or "")
                Server._scribe_tool_registry[tool_name] = target
                Server._scribe_tool_defs[tool_name] = mcp_types.Tool(
                    name=tool_name,
                    description=tool_description,
                    inputSchema=schema,
                    outputSchema=output_schema,
                )
                return target

            if func is not None:
                return register(func)
            return register

        setattr(app, "tool", _tool_decorator)

        @app.list_tools()
        async def _list_tools() -> list[mcp_types.Tool]:
            defs = getattr(Server, "_scribe_tool_defs", {})
            return list(defs.values())

        @app.call_tool()
        async def _call_tool(name: str, arguments: Dict[str, Any], **kwargs: Any) -> Any:
            registry = getattr(Server, "_scribe_tool_registry", {})
            func = registry.get(name)
            if not func:
                raise ValueError(f"Unknown tool '{name}'")

            sentinel_only = {"append_event", "open_bug", "open_security", "link_fix"}
            sentinel_allowed = sentinel_only | {"read_file", "query_entries"}

            context_payload = arguments.pop("context", None)
            if context_payload is None and "context" in kwargs:
                context_payload = kwargs.get("context")
            if not isinstance(context_payload, dict):
                context_payload = {}

            if not context_payload.get("repo_root"):
                repo_root = None
                try:
                    from scribe_mcp.tools.project_utils import load_active_project  # Lazy import.
                    active_project, _, _ = await load_active_project(state_manager)
                    if active_project:
                        repo_root = active_project.get("root")
                except Exception:
                    repo_root = None
                context_payload["repo_root"] = repo_root or str(settings.project_root)

            if context_payload.get("mode") not in {"sentinel", "project"}:
                context_payload["mode"] = "sentinel" if name in sentinel_only else "project"

            if not context_payload.get("intent"):
                context_payload["intent"] = f"tool:{name}"

            affected = context_payload.get("affected_dev_projects")
            if not isinstance(affected, list):
                affected = []
            if not affected and isinstance(arguments, dict):
                project_hint = arguments.get("project") or arguments.get("name")
                if project_hint:
                    affected = [str(project_hint)]
            context_payload["affected_dev_projects"] = affected

            exec_context = await router_context_manager.build_execution_context(context_payload)

            if exec_context.mode == "sentinel" and name not in sentinel_allowed:
                log_scope_violation(
                    exec_context,
                    reason="tool_not_allowed_in_sentinel_mode",
                    tool_name=name,
                )
                raise ValueError(f"Tool '{name}' not allowed in sentinel mode")
            if exec_context.mode == "project" and name in sentinel_only:
                raise ValueError(f"Tool '{name}' not allowed in project mode")

            token = router_context_manager.set_current(exec_context)
            try:
                result = func(**arguments)
            except TypeError:
                raise ValueError(f"Invalid arguments for tool '{name}'")

            if inspect.isawaitable(result):
                try:
                    return await result
                finally:
                    router_context_manager.reset(token)
            try:
                return result
            finally:
                router_context_manager.reset(token)


# Import tool modules to register them with the server instance.
from scribe_mcp import tools  # noqa: E402  # isort:skip


_HAS_LIFECYCLE_HOOKS = hasattr(app, "on_startup") and hasattr(app, "on_shutdown")


async def _startup() -> None:
    """Initialise shared resources before handling requests."""
    global agent_context_manager, agent_identity, _startup_complete
    if _startup_complete:
        return
    _startup_complete = True

    if storage_backend:
        await storage_backend.setup()

    # Initialize plugins for the current repository
    try:
        from scribe_mcp.config.repo_config import RepoConfig
        from scribe_mcp.plugins.registry import initialize_plugins

        # Create repository configuration using the resolved project root.
        # Avoid relying on cwd, which may be MCP_SPINE when launched from a wrapper.
        repo_root = settings.project_root or Path.cwd()
        repo_config = RepoConfig.from_directory(Path(repo_root))
        initialize_plugins(repo_config)
        print("🔌 Plugin system initialized")
    except Exception as e:
        print(f"⚠️  Plugin initialization failed: {e}")
        print("   💡 Continuing without plugins (vector search will not be available)")

    # Initialize AgentContextManager for agent-scoped project context
    if storage_backend and state_manager:
        agent_context_manager = init_agent_context_manager(storage_backend, state_manager)
        agent_identity = init_agent_identity(state_manager)
        print("🤖 AgentContextManager initialized for multi-agent support")
        print("🆔 AgentIdentity system initialized for automatic agent detection")

        # Migrate legacy global state to agent-scoped context
        from scribe_mcp.state.agent_manager import migrate_legacy_state
        try:
            await migrate_legacy_state(state_manager, storage_backend)
        except Exception as e:
            print(f"⚠️  Legacy state migration failed: {e}")
            print("   💡 Continuing with agent-scoped context (legacy state may be lost)")

        # Start background session cleanup task
        asyncio.create_task(_session_cleanup_task(agent_context_manager))
        print("🧹 Session cleanup task started")

    # Replay any uncommitted journal entries for crash recovery (all projects)
    from scribe_mcp.utils.files import WriteAheadLog
    from scribe_mcp.tools.project_utils import load_active_project
    from scribe_mcp.tools.list_projects import list_projects

    try:
        # Enhanced recovery: Scan all projects for orphaned journals
        total_replayed = 0
        recovered_projects = []

        # Method 1: Try to get list of all configured projects
        try:
            projects_result = await list_projects()
            available_projects = projects_result.get("projects", [])
            for project_info in available_projects:
                project_name = project_info.get("name")
                if project_name and project_info.get("progress_log"):
                    progress_log_path = Path(project_info["progress_log"])
                    if progress_log_path.exists():
                        wal = WriteAheadLog(progress_log_path)
                        replayed = wal.replay_uncommitted()
                        if replayed > 0:
                            total_replayed += replayed
                            recovered_projects.append(project_name)
        except Exception as list_error:
            print(f"⚠️  Project listing failed during recovery: {list_error}")

        # Method 2: Fallback - scan for orphaned journal files in project directories
        try:
            import glob

            # Look for .journal files in typical project locations
            journal_patterns = [
                str(settings.project_root / "config" / "projects" / "*" / "*.journal"),
                str(settings.project_root / ".scribe" / "docs" / "dev_plans" / "*" / "*.journal"),
                "**/PROGRESS_LOG.md.journal"  # Common pattern
            ]

            for pattern in journal_patterns:
                for journal_file in glob.glob(pattern, recursive=True):
                    journal_path = Path(journal_file)
                    if journal_path.exists():
                        # Find corresponding log file
                        log_path = journal_path.with_suffix('')
                        if log_path.exists():
                            wal = WriteAheadLog(log_path)
                            replayed = wal.replay_uncommitted()
                            if replayed > 0:
                                total_replayed += replayed
                                project_name = log_path.parent.name
                                if project_name not in recovered_projects:
                                    recovered_projects.append(project_name)
        except Exception as scan_error:
            print(f"⚠️  Journal scan failed during recovery: {scan_error}")

        # Report recovery results
        if total_replayed > 0:
            print(f"🛡️  CRASH RECOVERY: Replayed {total_replayed} uncommitted entries across {len(recovered_projects)} projects")
            for project_name in recovered_projects:
                print(f"   📋 Recovered entries for project: {project_name}")
            print("   ✅ Audit trail integrity maintained despite crash")

    except Exception as e:
        # Journal recovery should not prevent server startup
        print(f"⚠️  Journal recovery warning: {e}")
        print("   💡 Server will continue but some audit entries may be missing")


async def _shutdown() -> None:
    """Ensure resources are released when the server stops."""
    if storage_backend:
        try:
            async with asyncio.timeout(settings.storage_timeout_seconds):
                await asyncio.shield(storage_backend.close())
        except Exception:
            pass


if _HAS_LIFECYCLE_HOOKS:
    app.on_startup(_startup)
    app.on_shutdown(_shutdown)


def get_agent_context_manager():
    """Get the global AgentContextManager instance."""
    global agent_context_manager
    return agent_context_manager


def get_agent_identity():
    """Get the global AgentIdentity instance."""
    global agent_identity
    return agent_identity


def get_execution_context():
    """Return the active ExecutionContext for the current request."""
    return router_context_manager.get_current()


async def _session_cleanup_task(agent_manager):
    """Background task to clean up expired sessions."""
    import asyncio
    while True:
        try:
            await asyncio.sleep(300)  # Clean every 5 minutes
            cleaned = await agent_manager.cleanup_expired_sessions()
            if cleaned > 0:
                print(f"🧹 Cleaned up {cleaned} expired sessions")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"⚠️  Session cleanup error: {e}")
            # Continue cleaning despite errors


async def main() -> None:
    """Run the MCP server over stdio."""
    if not _MCP_AVAILABLE:
        raise RuntimeError(
            "MCP Python SDK not installed. Install the 'mcp' package to run the server."
        )
    await _startup()

    try:
        async with mcp_stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
    finally:
        if not _HAS_LIFECYCLE_HOOKS:
            await _shutdown()


if __name__ == "__main__":
    asyncio.run(main())
