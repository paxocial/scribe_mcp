"""Router-owned execution context and session identity management."""

from __future__ import annotations

import asyncio
import contextvars
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


_CURRENT_CONTEXT: contextvars.ContextVar["ExecutionContext | None"] = contextvars.ContextVar(
    "scribe_execution_context",
    default=None,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AgentIdentity:
    agent_kind: str
    model: Optional[str]
    instance_id: str
    sub_id: Optional[str]
    display_name: Optional[str]


@dataclass(frozen=True)
class ExecutionContext:
    repo_root: str
    mode: str
    session_id: str
    execution_id: str
    agent_identity: AgentIdentity
    intent: str
    timestamp_utc: str
    affected_dev_projects: list[str]
    sentinel_day: Optional[str] = None
    transport_session_id: Optional[str] = None
    bug_id: Optional[str] = None
    security_id: Optional[str] = None
    parent_execution_id: Optional[str] = None
    toolchain: Optional[str] = None


class RouterContextManager:
    """Owns router-generated session/execution identity and current context."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._transport_sessions: Dict[str, str] = {}
        self._process_session_id = str(uuid.uuid4())
        self._process_instance_id = str(uuid.uuid4())

    async def get_or_create_session_id(self, transport_session_id: Optional[str]) -> str:
        if not transport_session_id:
            return self._process_session_id
        async with self._lock:
            existing = self._transport_sessions.get(transport_session_id)
            if existing:
                return existing
            session_id = str(uuid.uuid4())
            self._transport_sessions[transport_session_id] = session_id
            return session_id

    def _build_agent_identity(self, payload: Dict[str, Any]) -> AgentIdentity:
        agent_kind = os.environ.get("SCRIBE_AGENT_KIND", "other")
        model = os.environ.get("SCRIBE_AGENT_MODEL") or os.environ.get("CODEX_MODEL")
        sub_id = None
        display_name = None
        raw_identity = payload.get("agent_identity")
        if isinstance(raw_identity, dict):
            sub_id = raw_identity.get("sub_id") or raw_identity.get("sub_id".lower())
            display_name = raw_identity.get("display_name")
        return AgentIdentity(
            agent_kind=agent_kind,
            model=model,
            instance_id=self._process_instance_id,
            sub_id=sub_id,
            display_name=display_name,
        )

    async def build_execution_context(self, payload: Dict[str, Any]) -> ExecutionContext:
        repo_root = payload.get("repo_root")
        mode = payload.get("mode")
        intent = payload.get("intent") or ""
        affected = payload.get("affected_dev_projects") or []

        if not repo_root or not isinstance(repo_root, str):
            raise ValueError("ExecutionContext missing required field: repo_root")
        if not Path(repo_root).is_absolute():
            raise ValueError("ExecutionContext repo_root must be an absolute path")
        if mode not in {"sentinel", "project"}:
            raise ValueError("ExecutionContext mode must be 'sentinel' or 'project'")
        if not intent:
            raise ValueError("ExecutionContext missing required field: intent")
        if not isinstance(affected, list):
            raise ValueError("ExecutionContext affected_dev_projects must be a list")

        transport_session_id = payload.get("transport_session_id")
        session_id = await self.get_or_create_session_id(transport_session_id)
        execution_id = str(uuid.uuid4())
        timestamp_utc = _utc_now_iso()

        sentinel_day = None
        if mode == "sentinel":
            sentinel_day = timestamp_utc.split("T", 1)[0]

        agent_identity = self._build_agent_identity(payload)

        return ExecutionContext(
            repo_root=repo_root,
            mode=mode,
            session_id=session_id,
            execution_id=execution_id,
            agent_identity=agent_identity,
            intent=intent,
            timestamp_utc=timestamp_utc,
            affected_dev_projects=[str(item) for item in affected],
            sentinel_day=sentinel_day,
            transport_session_id=transport_session_id,
            bug_id=payload.get("bug_id"),
            security_id=payload.get("security_id"),
            parent_execution_id=payload.get("parent_execution_id"),
            toolchain=payload.get("toolchain"),
        )

    def set_current(self, context: ExecutionContext) -> contextvars.Token:
        return _CURRENT_CONTEXT.set(context)

    def reset(self, token: contextvars.Token) -> None:
        _CURRENT_CONTEXT.reset(token)

    def get_current(self) -> Optional[ExecutionContext]:
        return _CURRENT_CONTEXT.get()
