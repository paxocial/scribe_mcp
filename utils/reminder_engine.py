"""Advanced reminder engine with localization and intelligent selection.

This module provides a sophisticated reminder system that:
- Loads reminders from configurable JSON files
- Supports multiple languages with fallbacks
- Implements intelligent reminder selection and deduplication
- Provides progressive teaching with cooldown periods
- Uses variable substitution for dynamic content
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta

from scribe_mcp.config.settings import settings


@dataclass
class ReminderInstance:
    """A single reminder instance with metadata."""
    key: str
    level: str
    emoji: str
    message: str
    context: Optional[str] = None
    category: str = "general"
    score: int = 3
    variables: Dict[str, Any] = field(default_factory=dict)
    tools_suppressed: List[str] = field(default_factory=list)
    cooldown_minutes: int = 0
    last_shown: Optional[datetime] = None


@dataclass
class ReminderContext:
    """Context for reminder generation."""
    tool_name: str
    project_name: Optional[str]
    total_entries: int
    minutes_since_log: Optional[float]
    last_log_time: Optional[datetime]
    docs_status: Dict[str, str]
    docs_changed: List[str]
    current_phase: Optional[str]
    session_age_minutes: Optional[float]
    variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReminderHistory:
    """Tracks recently shown reminders for deduplication."""
    reminder_hashes: Dict[str, datetime] = field(default_factory=dict)
    teaching_sessions: Dict[str, int] = field(default_factory=dict)
    last_cleanup: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ReminderEngine:
    """Advanced reminder engine with localization and intelligent selection."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/reminder_config.json"
        self.reminders_path: Optional[str] = None
        self.rules_path: Optional[str] = None

        self.config: Dict[str, Any] = {}
        self.reminders: Dict[str, Any] = {}
        self.rules: Dict[str, Any] = {}
        self.variables: Dict[str, Any] = {}
        self.formatting: Dict[str, Any] = {}

        self.language = "en-US"
        self.fallback_language = "en-US"

        self.history = ReminderHistory()

        self._load_configuration()

    def _load_configuration(self) -> None:
        """Load all configuration files."""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                self.config = json.loads(config_file.read_text(encoding="utf-8"))
                self.language = self.config.get("language", "en-US")
                self.fallback_language = self.config.get("fallback_language", "en-US")

                base_path = config_file.parent
                self.reminders_path = base_path / self.config.get("reminder_paths", {}).get("templates", "reminders")
                self.rules_path = base_path / self.config.get("reminder_paths", {}).get("rules", "reminder_rules.json")

            self._load_reminders()
            self._load_rules()

        except Exception as e:
            print(f"Warning: Failed to load reminder configuration: {e}")
            self._load_fallback_reminders()

    def _load_reminders(self) -> None:
        """Load reminder templates for current language."""
        if not self.reminders_path:
            return

        # Try to load preferred language
        lang_file = self.reminders_path / f"{self.language}.json"
        if lang_file.exists():
            self.reminders = json.loads(lang_file.read_text(encoding="utf-8"))
            self.variables = self.reminders.get("variables", {})
            self.formatting = self.reminders.get("formatting", {})
            return

        # Fallback to default language
        fallback_file = self.reminders_path / f"{self.fallback_language}.json"
        if fallback_file.exists():
            self.reminders = json.loads(fallback_file.read_text(encoding="utf-8"))
            self.variables = self.reminders.get("variables", {})
            self.formatting = self.reminders.get("formatting", {})

    def _load_rules(self) -> None:
        """Load reminder selection rules."""
        if not self.rules_path or not self.rules_path.exists():
            return

        self.rules = json.loads(self.rules_path.read_text(encoding="utf-8"))

    def _load_fallback_reminders(self) -> None:
        """Load minimal fallback reminders."""
        self.reminders = {
            "reminders": {
                "logging": {
                    "no_logs_yet": {
                        "level": "info",
                        "emoji": "📝",
                        "template": "No progress logs yet. Use append_entry to start the audit trail.",
                        "category": "logging"
                    }
                },
                "context": {
                    "project_context": {
                        "level": "info",
                        "emoji": "🎯",
                        "template": "Project: {project_name}",
                        "category": "context"
                    }
                }
            }
        }
        self.config = {
            "behavior": {"max_reminders_per_call": 2},
            "selection": {"priority_order": ["urgent", "warning", "info"]}
        }

    def _cleanup_history(self) -> None:
        """Clean up old reminder history."""
        now = datetime.now(timezone.utc)
        cleanup_after_hours = self.config.get("tracking", {}).get("cleanup_after_hours", 24)
        cutoff = now - timedelta(hours=cleanup_after_hours)

        # Remove old reminder hashes
        self.history.reminder_hashes = {
            h: t for h, t in self.history.reminder_hashes.items()
            if t > cutoff
        }

        # Remove old teaching sessions
        self.history.teaching_sessions = {
            k: v for k, v in self.history.teaching_sessions.items()
            if v > 0  # Sessions reset when count reaches 0
        }

        self.history.last_cleanup = now

    def _get_reminder_hash(self, reminder_key: str, variables: Dict[str, Any]) -> str:
        """Generate hash for reminder deduplication."""
        content = f"{reminder_key}:{json.dumps(variables, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _should_show_reminder(self, reminder: ReminderInstance, context: ReminderContext) -> bool:
        """Check if reminder should be shown based on rules."""

        # Tool suppression
        if context.tool_name in reminder.tools_suppressed:
            return False

        # Cooldown check
        if reminder.cooldown_minutes > 0:
            reminder_hash = self._get_reminder_hash(reminder.key, reminder.variables)
            last_shown = self.history.reminder_hashes.get(reminder_hash)
            if last_shown:
                cooldown_cutoff = datetime.now(timezone.utc) - timedelta(minutes=reminder.cooldown_minutes)
                if last_shown > cooldown_cutoff:
                    return False

        # Teaching session limits
        if reminder.category == "teaching":
            session_key = f"{context.tool_name}:{reminder.key}"
            sessions_used = self.history.teaching_sessions.get(session_key, 0)
            max_sessions = self.config.get("behavior", {}).get("max_teaching_reminders_per_session", 3)
            if sessions_used >= max_sessions:
                return False

        return True

    def _format_reminder(self, reminder: ReminderInstance, use_short: bool = True) -> ReminderInstance:
        """Apply variable substitution and formatting to reminder."""
        # Choose template
        template_key = "short_template" if use_short and "short_template" in reminder.variables else "template"
        template = reminder.variables.get(template_key, reminder.message)

        # Variable substitution
        try:
            formatted_message = template.format(**reminder.variables)
            if reminder.context:
                formatted_context = reminder.context.format(**reminder.variables)
                reminder.context = formatted_context
        except KeyError as e:
            # Fallback to original template if variable missing
            formatted_message = reminder.message

        reminder.message = formatted_message
        return reminder

    def _evaluate_condition(self, condition: str, context: ReminderContext) -> bool:
        """Evaluate a condition string against context."""
        # Simple condition evaluation (can be extended)
        if condition == "no_log_entries":
            return context.total_entries == 0
        elif condition.startswith("minutes_since_log > "):
            threshold = int(condition.split()[-1])
            return (context.minutes_since_log or 0) > threshold
        elif condition == "docs_missing":
            return any(status == "missing" for status in context.docs_status.values())
        elif condition.startswith("tool="):
            return context.tool_name == condition.split("=")[1]
        elif condition == "always":
            return True

        return False

    def _build_variables(self, context: ReminderContext) -> Dict[str, Any]:
        """Build variable dictionary for template substitution."""
        variables = {
            "project_name": context.project_name or "No project",
            "total_entries": context.total_entries,
            "minutes": int(context.minutes_since_log or 0),
            "hours": int((context.minutes_since_log or 0) / 60),
            "days": int((context.minutes_since_log or 0) / 1440),
        }

        # Time formatting
        if context.last_log_time:
            variables["last_log"] = context.last_log_time.strftime(
                self.formatting.get("date_format", "%Y-%m-%d %H:%M UTC")
            )
        else:
            variables["last_log"] = "no logs yet"

        # Session info
        if context.session_age_minutes is not None:
            variables["session_age"] = f"{context.session_age_minutes:.1f} min"
        else:
            variables["session_age"] = ""

        # Phase info
        if context.current_phase:
            variables["current_phase"] = context.current_phase
            variables["phase_info"] = f" | Phase: {context.current_phase}"
            variables["phase_suffix"] = f" (Phase: {context.current_phase})"
        else:
            variables["phase_info"] = ""
            variables["phase_suffix"] = ""

        # Documentation info
        missing_docs = [name for name, status in context.docs_status.items() if status == "missing"]
        if missing_docs:
            variables["missing_docs"] = ", ".join(missing_docs[:3])
            if len(missing_docs) > 3:
                variables["missing_docs"] += f" (+{len(missing_docs) - 3} more)"

        if context.docs_changed:
            variables["changed_docs"] = ", ".join(context.docs_changed[:3])

        # Merge with context variables
        variables.update(context.variables)

        return variables

    async def generate_reminders(self, context: ReminderContext) -> List[ReminderInstance]:
        """Generate relevant reminders for the given context."""
        self._cleanup_history()

        candidates = []

        # Evaluate conditions and generate reminder candidates
        if "conditions" in self.rules:
            for rule_name, rule_data in self.rules["conditions"].items():
                if self._evaluate_rule_conditions(rule_data.get("triggers", []), context):
                    reminder = self._create_reminder_from_rule(rule_name, rule_data, context)
                    if reminder:
                        candidates.append(reminder)

        # Add teaching reminders
        teaching_reminders = self._generate_teaching_reminders(context)
        candidates.extend(teaching_reminders)

        # Filter and select best reminders
        selected = self._select_reminders(candidates, context)

        # Track shown reminders
        for reminder in selected:
            reminder_hash = self._get_reminder_hash(reminder.key, reminder.variables)
            self.history.reminder_hashes[reminder_hash] = datetime.now(timezone.utc)

            if reminder.category == "teaching":
                session_key = f"{context.tool_name}:{reminder.key}"
                self.history.teaching_sessions[session_key] = self.history.teaching_sessions.get(session_key, 0) + 1

        # Apply formatting
        use_short = self.config.get("formatting", {}).get("use_short_templates", True)
        selected = [self._format_reminder(r, use_short) for r in selected]

        return selected

    def _evaluate_rule_conditions(self, triggers: List[str], context: ReminderContext) -> bool:
        """Evaluate if all trigger conditions are met."""
        for trigger in triggers:
            if not self._evaluate_condition(trigger, context):
                return False
        return True

    def _create_reminder_from_rule(self, rule_name: str, rule_data: Dict[str, Any], context: ReminderContext) -> Optional[ReminderInstance]:
        """Create a reminder instance from rule data."""
        reminder_key = rule_data.get("reminder_key")
        if not reminder_key:
            return None

        # Navigate reminder structure
        category, name = reminder_key.split(".", 1) if "." in reminder_key else ("general", reminder_key)
        reminder_templates = self.reminders.get("reminders", {}).get(category, {}).get(name)

        if not reminder_templates:
            return None

        variables = self._build_variables(context)
        variable_mapping = rule_data.get("variable_mapping", {})
        for key, source in variable_mapping.items():
            variables[key] = variables.get(source, "")

        return ReminderInstance(
            key=reminder_key,
            level=reminder_templates.get("level", "info"),
            emoji=reminder_templates.get("emoji", "ℹ️"),
            message=reminder_templates.get("template", ""),
            context=reminder_templates.get("context"),
            category=reminder_templates.get("category", "general"),
            variables=variables,
            tools_suppressed=reminder_templates.get("tools_suppressed", []),
            cooldown_minutes=rule_data.get("cooldown_minutes", 0)
        )

    def _generate_teaching_reminders(self, context: ReminderContext) -> List[ReminderInstance]:
        """Generate teaching reminders based on context."""
        teaching = []

        if not self.config.get("behavior", {}).get("teaching_enabled", True):
            return teaching

        teaching_rules = self.rules.get("teaching_rules", {})
        for rule_name, rule_data in teaching_rules.items():
            if self._evaluate_rule_conditions(rule_data.get("triggers", []), context):
                reminder = self._create_reminder_from_rule(rule_name, rule_data, context)
                if reminder and self._should_show_reminder(reminder, context):
                    teaching.append(reminder)

        return teaching

    def _select_reminders(self, candidates: List[ReminderInstance], context: ReminderContext) -> List[ReminderInstance]:
        """Select the best reminders based on priority and rules."""
        if not candidates:
            return []

        # Filter out suppressed reminders
        filtered = [r for r in candidates if self._should_show_reminder(r, context)]

        # Sort by priority
        priority_order = self.config.get("selection", {}).get("priority_order", [])
        category_weights = self.config.get("selection", {}).get("category_weights", {})

        def get_priority(reminder: ReminderInstance) -> int:
            # Try priority order first
            if reminder.key in priority_order:
                return priority_order.index(reminder.key)
            # Fall back to category weight
            return category_weights.get(reminder.level, 999)

        filtered.sort(key=get_priority)

        # Apply tool-specific limits
        tool_limits = self.config.get("selection", {}).get("tool_specific_limits", {})
        tool_config = tool_limits.get(context.tool_name, {})
        max_total = tool_config.get("max_total", self.config.get("behavior", {}).get("max_reminders_per_call", 2))
        allowed_categories = tool_config.get("categories", ["all"])

        if allowed_categories != ["all"]:
            filtered = [r for r in filtered if r.category in allowed_categories]

        return filtered[:max_total]

    def to_dict_list(self, reminders: List[ReminderInstance]) -> List[Dict[str, Any]]:
        """Convert reminder instances to dictionary format for API response."""
        return [
            {
                "level": r.level,
                "score": r.score,
                "emoji": r.emoji,
                "message": r.message,
                "category": r.category,
                "tone": "neutral",  # Can be made configurable
            } | ({"context": r.context} if r.context else {})
            for r in reminders
        ]