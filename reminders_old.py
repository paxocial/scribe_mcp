"""Configurable reminder engine for Scribe MCP."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.state.manager import State
from scribe_mcp.utils.logs import parse_log_line, read_all_lines
from scribe_mcp.utils.time import parse_utc, utcnow

DEFAULT_SEVERITY = {"info": 3, "warning": 6, "urgent": 9}
DEFAULT_SUPPRESS_PHASE_TOOLS: Sequence[str] = ("append_entry", "generate_doc_templates")


@dataclass
class ReminderConfig:
    tone: str
    severity_weights: Dict[str, int]
    log_warning_minutes: int
    log_urgent_minutes: int
    doc_stale_days: int
    min_doc_length: int
    warmup_minutes: int
    idle_reset_minutes: int
    suppress_phase_on_tools: Sequence[str]


@dataclass
class Reminder:
    level: str
    score: int
    message: str
    emoji: str = "ℹ️"
    context: Optional[str] = None
    category: str = "general"


@dataclass
class ReminderContext:
    config: ReminderConfig
    project_name: str
    last_log_time: Optional[datetime]
    minutes_since_log: Optional[float]
    docs_status: Dict[str, str]
    doc_hashes: Dict[str, str]
    doc_changes: List[str]
    doc_paths: Dict[str, Path]
    current_phase: Optional[str]
    total_entries: int
    recent_actions: List[str]
    session_age_minutes: Optional[float]
    is_new_session: bool


async def get_reminders(
    project: Dict[str, Any],
    *,
    tool_name: str,
    state: Optional[State] = None,
) -> List[Dict[str, Any]]:
    """Generate reminder payloads for the given project and tool."""
    if not project:
        return []

    config = _build_config(project)
    ctx = await _build_context(project, state, config)

    reminders: List[Reminder] = []
    reminders.extend(_logging_reminders(ctx, tool_name))
    reminders.extend(_doc_status_reminders(ctx))
    reminders.extend(_doc_drift_reminders(ctx))
    reminders.extend(_phase_compliance_reminders(ctx, tool_name))
    reminders.extend(_stale_doc_reminders(ctx))
    reminders.append(_project_context_reminder(ctx))

    tone = config.tone
    output: List[Dict[str, Any]] = []
    for reminder in reminders:
        payload = {
            "level": reminder.level,
            "score": reminder.score,
            "emoji": reminder.emoji,
            "message": _apply_tone(tone, reminder.message, reminder.level),
            "category": reminder.category,
            "tone": tone,
        }
        if reminder.context:
            payload["context"] = reminder.context
        output.append(payload)
    return output


# ---------------------------------------------------------------------------
# Context builders


async def _build_context(
    project: Dict[str, Any],
    state: Optional[State],
    config: ReminderConfig,
) -> ReminderContext:
    log_path = Path(project["progress_log"])
    lines = await read_all_lines(log_path)

    last_log_time: Optional[datetime] = None
    total_entries = 0
    for line in lines:
        if line.strip():
            total_entries += 1
    for line in reversed(lines):
        parsed = parse_log_line(line)
        if not parsed:
            continue
        ts_str = parsed.get("ts")
        if ts_str:
            last_log_time = parse_utc(ts_str)
            break

    minutes_since = None
    if last_log_time:
        delta = utcnow() - last_log_time
        minutes_since = delta.total_seconds() / 60

    state_project = state.projects.get(project["name"]) if state else project
    docs_status, doc_hashes, changed_docs, doc_paths = await _docs_status(project, state_project, config)

    current_phase = await _detect_phase(project)
    recent_actions = _extract_recent_actions(state)
    session_age_minutes, is_new_session = _session_details(state, config)

    return ReminderContext(
        config=config,
        project_name=project["name"],
        last_log_time=last_log_time,
        minutes_since_log=minutes_since,
        docs_status=docs_status,
        doc_hashes=doc_hashes,
        doc_changes=changed_docs,
        doc_paths=doc_paths,
        current_phase=current_phase,
        total_entries=total_entries,
        recent_actions=recent_actions,
        session_age_minutes=session_age_minutes,
        is_new_session=is_new_session,
    )


def _build_config(project: Dict[str, Any]) -> ReminderConfig:
    global_defaults = settings.reminder_defaults or {}
    project_defaults = (project.get("defaults", {}) or {}).get("reminder", {})

    severity = dict(DEFAULT_SEVERITY)
    severity.update(global_defaults.get("severity_weights", {}))
    severity.update(project_defaults.get("severity_weights", {}))

    tone = project_defaults.get("tone") or global_defaults.get("tone") or "neutral"

    default_warning = global_defaults.get("log_warning_minutes", settings.reminder_warmup_minutes + 5)
    log_warning = int(project_defaults.get("log_warning_minutes", default_warning))
    default_urgent = global_defaults.get("log_urgent_minutes", log_warning + 10)
    log_urgent = int(project_defaults.get("log_urgent_minutes", default_urgent))
    doc_stale = int(project_defaults.get("doc_stale_days", global_defaults.get("doc_stale_days", 7)))
    min_length = int(project_defaults.get("min_doc_length", global_defaults.get("min_doc_length", 400)))
    warmup = int(project_defaults.get("warmup_minutes", global_defaults.get("warmup_minutes", settings.reminder_warmup_minutes)))
    idle = int(project_defaults.get("idle_reset_minutes", global_defaults.get("idle_reset_minutes", settings.reminder_idle_minutes)))

    suppress_tools = list(DEFAULT_SUPPRESS_PHASE_TOOLS)
    suppress_tools.extend(global_defaults.get("suppress_phase_on_tools", []))
    suppress_tools.extend(project_defaults.get("suppress_phase_on_tools", []))

    return ReminderConfig(
        tone=str(tone),
        severity_weights={k: int(v) for k, v in severity.items()},
        log_warning_minutes=log_warning,
        log_urgent_minutes=log_urgent,
        doc_stale_days=doc_stale,
        min_doc_length=min_length,
        warmup_minutes=warmup,
        idle_reset_minutes=idle,
        suppress_phase_on_tools=tuple(dict.fromkeys(t.strip() for t in suppress_tools if t)),
    )


def _extract_recent_actions(state: Optional[State]) -> List[str]:
    if not state:
        return []
    actions = []
    for entry in state.recent_tools:
        name = entry.get("name") if isinstance(entry, dict) else str(entry)
        if not name:
            continue
        actions.append(name)
    return actions


def _session_details(state: Optional[State], config: ReminderConfig) -> tuple[Optional[float], bool]:
    if not state or not state.session_started_at:
        return None, False
    start_dt = parse_utc(state.session_started_at)
    if not start_dt:
        return None, False
    age_minutes = (utcnow() - start_dt).total_seconds() / 60
    is_new = age_minutes <= config.warmup_minutes
    return age_minutes, is_new


# ---------------------------------------------------------------------------
# Reminder generators


def _logging_reminders(ctx: ReminderContext, tool_name: str) -> List[Reminder]:
    if tool_name == "append_entry":
        return []

    reminders: List[Reminder] = []
    level = None
    message = None
    context = None
    emoji = "⏰"

    threshold_warn = ctx.config.log_warning_minutes
    threshold_urgent = ctx.config.log_urgent_minutes

    if ctx.minutes_since_log is None:
        level = "info"
        emoji = "📝"
        message = "No progress logs yet. Use append_entry to start the audit trail."
    elif ctx.minutes_since_log >= threshold_urgent:
        level = "urgent"
        emoji = "🚨"
        message = f"Last log was {int(ctx.minutes_since_log)} minutes ago—scribe your progress immediately."
        context = "Keep logs flowing to retain full observability."
    elif ctx.minutes_since_log >= threshold_warn:
        level = "warning"
        message = f"It's been {int(ctx.minutes_since_log)} minutes since the last log entry."
        context = "Use append_entry to capture what changed."

    if not level or not message:
        return reminders

    reminders.append(_make_reminder(level, emoji, message, context, "logging", ctx))
    return reminders


def _doc_status_reminders(ctx: ReminderContext) -> List[Reminder]:
    reminders: List[Reminder] = []
    missing = [name for name, status in ctx.docs_status.items() if status == "missing"]
    incomplete = [name for name, status in ctx.docs_status.items() if status == "incomplete"]

    if missing:
        reminders.append(
            _make_reminder(
                "urgent",
                "📋",
                f"Missing documentation: {', '.join(sorted(missing))}.",
                "Run generate_doc_templates or create the docs before moving forward.",
                "docs",
                ctx,
            )
        )

    if "architecture" in incomplete:
        reminders.append(
            _make_reminder(
                "warning",
                "🏗️",
                "Architecture guide still reads like a template—fill it in before coding.",
                category="docs",
                ctx=ctx,
            )
        )

    if "phase_plan" in incomplete and "architecture" not in missing:
        reminders.append(
            _make_reminder(
                "warning",
                "🗓️",
                "Phase plan incomplete. Break the architecture into executable phases.",
                category="docs",
                ctx=ctx,
            )
        )

    if "checklist" in incomplete and "phase_plan" not in missing:
        reminders.append(
            _make_reminder(
                "info",
                "✅",
                "Checklist needs attention—turn the phase plan into actionable boxes.",
                category="docs",
                ctx=ctx,
            )
        )

    return reminders


def _doc_drift_reminders(ctx: ReminderContext) -> List[Reminder]:
    reminders: List[Reminder] = []
    if ctx.doc_changes:
        changed = ", ".join(sorted(ctx.doc_changes))
        reminders.append(
            _make_reminder(
                "info",
                "🧭",
                f"Docs changed since the last audit: {changed}.",
                "Review and cross-check implementation to keep docs aligned.",
                "docs",
                ctx,
            )
        )
    return reminders


def _phase_compliance_reminders(ctx: ReminderContext, tool_name: str) -> List[Reminder]:
    if tool_name in ctx.config.suppress_phase_on_tools:
        return []

    reminders: List[Reminder] = []

    if ctx.docs_status.get("architecture") == "incomplete" and ctx.total_entries > 5:
        reminders.append(
            _make_reminder(
                "urgent",
                "⛔",
                "Architecture guide incomplete but development is underway. Pause and document first.",
                category="workflow",
                ctx=ctx,
            )
        )

    if ctx.docs_status.get("architecture") == "complete" and ctx.docs_status.get("phase_plan") == "incomplete":
        reminders.append(
            _make_reminder(
                "warning",
                "📊",
                "Architecture is set—draft the phase plan next.",
                category="workflow",
                ctx=ctx,
            )
        )

    if ctx.docs_status.get("phase_plan") == "complete" and ctx.docs_status.get("checklist") == "incomplete":
        reminders.append(
            _make_reminder(
                "info",
                "🗒️",
                "Phase plan done—convert it into a checklist to track progress.",
                category="workflow",
                ctx=ctx,
            )
        )

    return reminders


def _stale_doc_reminders(ctx: ReminderContext) -> List[Reminder]:
    reminders: List[Reminder] = []
    stale_cutoff = utcnow() - timedelta(days=ctx.config.doc_stale_days)

    for label, path in ctx.doc_paths.items():
        if not path.exists():
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < stale_cutoff:
            reminders.append(
                _make_reminder(
                    "info",
                    "📆",
                    f"{path.name} hasn't been updated in {ctx.config.doc_stale_days}+ days.",
                    "Review the doc and confirm it still matches implementation.",
                    "docs",
                    ctx,
                )
            )
    return reminders


def _project_context_reminder(ctx: ReminderContext) -> Reminder:
    phase = f" | Phase: {ctx.current_phase}" if ctx.current_phase else ""
    last_log = (
        ctx.last_log_time.strftime("%Y-%m-%d %H:%M UTC") if ctx.last_log_time else "no logs yet"
    )
    message = f"Project: {ctx.project_name}{phase}"
    context = f"Entries: {ctx.total_entries} | Last log: {last_log}"
    if ctx.session_age_minutes is not None:
        context += f" | Session age: {ctx.session_age_minutes:.1f} min"
    return _make_reminder("info", "🎯", message, context, "context", ctx)


# ---------------------------------------------------------------------------
# Helper functions


def _make_reminder(
    level: str,
    emoji: str,
    message: str,
    context: Optional[str] = None,
    category: str = "general",
    ctx: ReminderContext | None = None,
) -> Reminder:
    assert ctx is not None, "Reminder context is required"
    severity = ctx.config.severity_weights.get(level, DEFAULT_SEVERITY.get(level, 3))
    adjusted_level = level

    if ctx.is_new_session and level in {"warning", "urgent"}:
        adjusted_level = "info"
        severity = max(1, ctx.config.severity_weights.get("info", 3))

    return Reminder(
        level=adjusted_level,
        score=severity,
        message=message,
        emoji=emoji,
        context=context,
        category=category,
    )


async def _docs_status(
    project: Dict[str, Any],
    state_project: Optional[Dict[str, Any]],
    config: ReminderConfig,
) -> tuple[Dict[str, str], Dict[str, str], List[str], Dict[str, Path]]:
    docs = project.get("docs", {}) or {}
    status: Dict[str, str] = {}
    hashes: Dict[str, str] = {}
    doc_paths: Dict[str, Path] = {}
    changed: List[str] = []
    previous_hashes = (state_project or {}).get("_doc_hashes", {})

    for key, path_str in docs.items():
        if key == "progress_log":
            continue
        path = Path(path_str)
        label = key.split("/")[-1] if "/" in key else key
        if not path.exists():
            status[label] = "missing"
            continue
        content = await asyncio.to_thread(path.read_text, encoding="utf-8")
        hash_value = hashlib.sha1(content.encode("utf-8")).hexdigest()
        hashes[label] = hash_value
        doc_paths[label] = path
        stripped = content.strip()
        if "{{" in content and "}}" in content:
            status[label] = "incomplete"
        elif len(stripped) < config.min_doc_length:
            status[label] = "incomplete"
        else:
            status[label] = "complete"
        if previous_hashes.get(label) and previous_hashes[label] != hash_value:
            changed.append(label)

    if project.get("name") and hashes != previous_hashes:
        await server_module.state_manager.update_project_metadata(
            project["name"], {"_doc_hashes": hashes}
        )

    return status, hashes, changed, doc_paths


async def _detect_phase(project: Dict[str, Any]) -> Optional[str]:
    phase_plan_path = project.get("docs", {}).get("phase_plan")
    if not phase_plan_path:
        return None
    path = Path(phase_plan_path)
    if not path.exists():
        return None
    content = await asyncio.to_thread(path.read_text, encoding="utf-8")

    match = re.search(r"##\s+Phase\s+(.+?)\s*\(In Progress\)", content)
    if match:
        return match.group(1).strip()

    phases = re.findall(r"##\s+Phase\s+(.+)", content)
    for phase in phases:
        section = re.search(
            rf"##\s+Phase\s+{re.escape(phase)}.*?(?=##\s+Phase|\Z)",
            content,
            re.DOTALL,
        )
        if section and "- [ ]" in section.group(0):
            return phase.strip()
    return None


def _apply_tone(tone: str, message: str, level: str) -> str:
    tone = tone.lower()
    if tone == "friendly":
        prefix = "Heads up: " if level != "urgent" else "Hey! "
        return prefix + message
    if tone == "direct":
        return message.upper() if level == "urgent" else message
    if tone == "formal":
        return f"Kind reminder: {message}" if level == "info" else message
    return message
