"""Flexible log rotation tools leveraging shared logging utilities."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.config.log_config import load_log_config
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import (
    LoggingContext,
    ProjectResolutionError,
    resolve_log_definition as shared_resolve_log_definition,
    resolve_logging_context,
)
from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError
from scribe_mcp.templates import (
    TEMPLATE_FILENAMES,
    create_rotation_context,
    load_templates,
    substitution_context,
)
from scribe_mcp.tools.base.parameter_normalizer import normalize_dict_param
from scribe_mcp.utils.audit import get_audit_manager, store_rotation_metadata
from scribe_mcp.utils.files import rotate_file, verify_file_integrity, file_lock
from scribe_mcp.utils.integrity import (
    create_rotation_metadata,
    count_file_lines,
)
from scribe_mcp.utils.rotation_state import (
    get_next_sequence_number,
    get_state_manager,
    generate_rotation_id,
    update_project_state,
)
from scribe_mcp.utils.time import format_utc
from scribe_mcp import reminders

DEFAULT_AUTO_THRESHOLD_ENTRIES = 500
DEFAULT_BYTES_PER_LINE = 80.0
MIN_BYTES_PER_LINE = 16.0
MAX_BYTES_PER_LINE = 512.0
EMA_SMOOTHING_ALPHA = 0.2
ESTIMATION_BAND_RATIO = 0.1
ESTIMATION_BAND_MIN = 250
TAIL_SAMPLE_BYTES = 1024 * 1024
_SUFFIX_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")


class _RotateLogHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_ROTATE_HELPER = _RotateLogHelper()


class RotationTarget(NamedTuple):
    log_type: str
    path: Path
    definition: Dict[str, Any]


class EntryCountEstimate(NamedTuple):
    count: int
    approximate: bool
    method: str
    details: Dict[str, Any]


async def _write_rotated_log_header(path: Path, content: str) -> None:
    """Write rendered rotation template to the freshly rotated log."""

    def _write() -> None:
        with file_lock(path, 'w', timeout=30.0) as handle:
            handle.write(content)
            if not content.endswith("\n"):
                handle.write("\n")

    await asyncio.to_thread(_write)


@app.tool()
async def rotate_log(
    suffix: Optional[str] = None,
    custom_metadata: Optional[str] = None,
    confirm: Optional[bool] = False,
    dry_run: Optional[bool] = None,
    dry_run_mode: Optional[str] = None,
    log_type: Optional[str] = None,
    log_types: Optional[List[str]] = None,
    rotate_all: bool = False,
    auto_threshold: bool = False,
    threshold_entries: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Rotate one or more project log files with integrity guarantees.

    Args:
        suffix: Optional suffix for archive filenames.
        custom_metadata: Optional JSON metadata appended to rotation record.
        confirm: When True, perform actual rotation (required unless auto-threshold triggers).
        dry_run: If True, preview rotation without changing files. Defaults to safe preview when confirm=False.
        dry_run_mode: Controls dry-run accuracy. \"estimate\" (default) returns approximate counts; \"precise\" forces a full line count.
        log_type: Single log type to rotate (e.g., "progress", "doc_updates").
        log_types: List of log types to rotate.
        rotate_all: When True, rotate every configured log type for the project.
        auto_threshold: When True, only rotate logs whose entry count exceeds a threshold.
        threshold_entries: Optional override for entry threshold (defaults to definition or 500).
    """
    state_snapshot = await server_module.state_manager.record_tool("rotate_log")

    try:
        context = await _ROTATE_HELPER.prepare_context(
            tool_name="rotate_log",
            agent_id=None,
            require_project=True,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        payload = _ROTATE_HELPER.translate_project_error(exc)
        payload.setdefault("suggestion", "Invoke set_project before rotating logs")
        payload.setdefault("reminders", [])
        return payload

    project = context.project or {}

    parsed_metadata, metadata_error = _parse_custom_metadata(custom_metadata)
    if metadata_error:
        response = {
            "ok": False,
            "error": metadata_error,
            "suggestion": "Ensure custom_metadata is valid JSON string",
        }
        return _ROTATE_HELPER.apply_context_payload(response, context)

    try:
        targets = _determine_rotation_targets(
            project,
            log_type=log_type,
            log_types=log_types,
            rotate_all=rotate_all,
        )
    except ValueError as exc:
        return _ROTATE_HELPER.apply_context_payload({"ok": False, "error": str(exc)}, context)

    if not targets:
        return _ROTATE_HELPER.apply_context_payload(
            {"ok": False, "error": "No log types matched for rotation."},
            context,
        )

    state_manager = get_state_manager()
    audit_manager = get_audit_manager()

    results: List[Dict[str, Any]] = []
    overall_ok = True

    for target in targets:
        result = await _rotate_single_log(
            project=project,
            context=context,
            state_manager=state_manager,
            audit_manager=audit_manager,
            log_type=target.log_type,
            log_path=target.path,
            definition=target.definition,
            suffix=suffix,
            parsed_metadata=parsed_metadata,
            confirm=confirm,
            dry_run=dry_run,
            dry_run_mode=dry_run_mode,
            auto_threshold=auto_threshold,
            threshold_entries=threshold_entries,
        )
        if not result.get("ok", True):
            overall_ok = False
        results.append(result)

    reminders_payload = await reminders.get_reminders(
        project,
        tool_name="rotate_log",
        state=state_snapshot,
    )

    summary: Dict[str, Any] = {
        "ok": overall_ok,
        "rotations": results,
        "auto_threshold": auto_threshold,
        "rotate_all": rotate_all,
    }
    summary = _ROTATE_HELPER.apply_context_payload(summary, context)
    summary["reminders"] = reminders_payload

    if len(results) == 1:
        summary = _merge_single_rotation_response(summary, results[0])

    return summary


@app.tool()
async def verify_rotation_integrity(rotation_id: str) -> Dict[str, Any]:
    """
    Verify the integrity of a specific rotation archive.
    """
    state_snapshot = await server_module.state_manager.record_tool("verify_rotation_integrity")

    try:
        context = await _ROTATE_HELPER.prepare_context(
            tool_name="verify_rotation_integrity",
            agent_id=None,
            require_project=True,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        payload = _ROTATE_HELPER.translate_project_error(exc)
        payload.setdefault("suggestion", "Invoke set_project before verifying rotations")
        return payload

    project = context.project or {}

    try:
        audit_manager = get_audit_manager()
        is_valid, message = audit_manager.verify_rotation_integrity(
            project["name"], rotation_id
        )

        response = {
            "ok": True,
            "rotation_id": rotation_id,
            "project": project["name"],
            "integrity_valid": is_valid,
            "verification_message": message,
            "verified_at": format_utc(),
        }
        return _ROTATE_HELPER.apply_context_payload(response, context)

    except Exception as exc:  # pragma: no cover - defensive
        response = {
            "ok": False,
            "error": f"Integrity verification failed: {exc}",
            "rotation_id": rotation_id,
        }
        return _ROTATE_HELPER.apply_context_payload(response, context)


@app.tool()
async def get_rotation_history(limit: int = 10) -> Dict[str, Any]:
    """
    Return recent rotation history entries for the active project.
    """
    state_snapshot = await server_module.state_manager.record_tool("get_rotation_history")

    try:
        context = await _ROTATE_HELPER.prepare_context(
            tool_name="get_rotation_history",
            agent_id=None,
            require_project=True,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        payload = _ROTATE_HELPER.translate_project_error(exc)
        payload.setdefault("suggestion", "Invoke set_project before querying rotation history")
        return payload

    project = context.project or {}

    try:
        audit_manager = get_audit_manager()
        history = audit_manager.get_rotation_history(project["name"], limit=limit)

        response = {
            "ok": True,
            "project": project["name"],
            "rotation_count": len(history),
            "rotations": history,
            "queried_at": format_utc(),
        }
        return _ROTATE_HELPER.apply_context_payload(response, context)

    except Exception as exc:  # pragma: no cover - defensive
        response = {
            "ok": False,
            "error": f"Failed to get rotation history: {exc}",
        }
        return _ROTATE_HELPER.apply_context_payload(response, context)


def _parse_custom_metadata(custom_metadata: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not custom_metadata:
        return None, None

    try:
        normalized = normalize_dict_param(custom_metadata, "custom_metadata")
        if isinstance(normalized, dict):
            return normalized, None
    except ValueError:
        pass

    try:
        parsed = json.loads(custom_metadata)
        if isinstance(parsed, dict):
            return parsed, None
    except json.JSONDecodeError:
        pass

    return None, "Invalid JSON in custom_metadata parameter"


def _normalize_log_type_param(value: Optional[Sequence[str] | str]) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = value.split(",")
    else:
        candidates = value
    result: List[str] = []
    for candidate in candidates:
        text = str(candidate).strip().lower()
        if text:
            result.append(text)
    return result


def _determine_rotation_targets(
    project: Dict[str, Any],
    *,
    log_type: Optional[str],
    log_types: Optional[List[str]],
    rotate_all: bool,
) -> List[RotationTarget]:
    config = load_log_config()
    available = set(config.keys())

    requested: List[str]
    if rotate_all:
        requested = sorted(available)
    else:
        requested = _normalize_log_type_param(log_types) or _normalize_log_type_param(log_type)
        if not requested:
            requested = ["progress"]

    cache: Dict[str, Tuple[Path, Dict[str, Any]]] = {}
    targets: List[RotationTarget] = []

    for log_key in requested:
        if log_key not in available:
            project_name = project.get("name") or "unknown project"
            available_types = ", ".join(sorted(available))
            raise ValueError(
                f"Unknown log_type '{log_key}' for project '{project_name}'. "
                f"Available types: {available_types}"
            )
        path, definition = shared_resolve_log_definition(project, log_key, cache=cache)
        targets.append(RotationTarget(log_key, path, definition))

    return targets


def _rotation_threshold_for_definition(
    definition: Dict[str, Any],
    override: Optional[int],
) -> Optional[int]:
    if override is not None and override > 0:
        return override
    threshold = definition.get("rotation_threshold_entries")
    if isinstance(threshold, int) and threshold > 0:
        return threshold
    return None


def _sanitize_suffix(value: str) -> str:
    """
    Sanitize user-provided suffix to ensure archive filenames stay within safe characters.
    """
    sanitized = value.replace("/", "_").replace("\\", "_")
    sanitized = _SUFFIX_SANITIZER.sub("_", sanitized).strip("_")
    return sanitized[:64] or "log"


def _build_archive_suffix(suffix: Optional[str], log_type: str, rotation_id: str) -> str:
    safe_rotation_id = rotation_id.replace("-", "")[:8]
    base = _sanitize_suffix(suffix) if suffix else f"{log_type}_archive"
    return f"{base}_{safe_rotation_id}"


async def _build_template_content(
    log_type: str,
    project: Dict[str, Any],
    rotation_context: Dict[str, Any],
) -> str:
    if log_type != "progress":
        timestamp = rotation_context.get("rotation_timestamp_utc", "Unknown time")
        rotation_id = rotation_context.get("rotation_id", "unknown")
        project_name = project.get("name", "Unknown Project")
        return (
            f"# {log_type.replace('_', ' ').title()} Log\n\n"
            f"Log rotated on {timestamp} (rotation id {rotation_id}) for project {project_name}.\n\n"
        )

    template_context = substitution_context(
        project_name=project["name"],
        author=project.get("defaults", {}).get("agent", "Scribe"),
        rotation_context=rotation_context,
    )

    template_engine = None
    try:
        project_root = Path(project.get("root", "")) if project.get("root") else Path.cwd()
        template_engine = Jinja2TemplateEngine(
            project_root=project_root,
            project_name=project["name"],
            security_mode="sandbox",
        )
    except Exception as engine_error:  # pragma: no cover - defensive path
        print(f"Warning: Failed to initialize Jinja2 template engine for rotation: {engine_error}")

    template_name = f"documents/{TEMPLATE_FILENAMES['progress_log']}"
    if template_engine:
        try:
            rendered = template_engine.render_template(template_name, metadata=template_context)
            if rendered:
                return rendered
        except TemplateEngineError as render_error:
            print(f"Warning: Jinja2 rendering failed for {template_name}: {render_error}")

    from scribe_mcp.tools.generate_doc_templates import _render_template

    templates = await load_templates()
    template_body = templates.get("progress_log", "")
    try:
        rendered = _render_template(template_body, template_context)
        if rendered:
            return rendered
    except Exception as template_error:  # pragma: no cover - defensive
        print(f"Warning: Template generation failed: {template_error}")

    rotation_id = rotation_context.get("rotation_id", "unknown")
    timestamp = rotation_context.get("rotation_timestamp_utc", "Unknown")
    project_name = project.get("name", "Unknown Project")
    author = project.get("defaults", {}).get("agent", "Scribe")

    return (
        "# Progress Log\n\n"
        "## Rotation Notice\n"
        f"Previous log was archived with rotation ID: {rotation_id}\n\n"
        f"Created: {timestamp}\n"
        f"Project: {project_name}\n"
        f"Author: {author}\n\n"
        "---\n\n"
    )


async def _rotate_single_log(
    *,
    project: Dict[str, Any],
    context: LoggingContext,
    state_manager,
    audit_manager,
    log_type: str,
    log_path: Path,
    definition: Dict[str, Any],
    suffix: Optional[str],
    parsed_metadata: Optional[Dict[str, Any]],
    confirm: Optional[bool],
    dry_run: Optional[bool],
    dry_run_mode: Optional[str],
    auto_threshold: bool,
    threshold_entries: Optional[int],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"log_type": log_type}

    if not log_path.exists():
        result.update({
            "ok": False,
            "error": f"Log file not found: {log_path}",
            "suggestion": "Create initial log entries before rotating",
        })
        return result

    normalized_mode = (dry_run_mode or "estimate").lower()
    if normalized_mode not in {"estimate", "precise"}:
        result.update({
            "ok": False,
            "error": f"Invalid dry_run_mode '{dry_run_mode}'. Use 'estimate' or 'precise'.",
            "suggestion": "Set dry_run_mode to 'estimate' (default) or 'precise' for exact counts.",
        })
        return result

    try:
        snapshot = _snapshot_file_state(log_path)
    except OSError as snapshot_error:
        result.update({
            "ok": False,
            "error": f"Unable to inspect log file: {snapshot_error}",
            "suggestion": "Verify file permissions and that the log path is readable.",
        })
        return result

    cached_stats = state_manager.get_log_stats(project["name"], log_type)
    cached_ema = cached_stats.get("ema_bytes_per_line") if cached_stats else None
    cached_initialized = cached_stats.get("initialized") if cached_stats else False
    entry_estimate = _estimate_entry_count(snapshot, cached_stats)

    threshold_limit = _rotation_threshold_for_definition(definition, threshold_entries)
    if auto_threshold and threshold_limit is None:
        threshold_limit = DEFAULT_AUTO_THRESHOLD_ENTRIES

    estimation_band = _compute_estimation_band(threshold_limit)
    estimation_decision: Optional[str] = None

    if auto_threshold and threshold_limit:
        estimation_decision = _classify_estimate(entry_estimate.count, threshold_limit, estimation_band)
        if estimation_decision == "undecided":
            refined_estimate = _refine_entry_estimate(log_path, snapshot, entry_estimate)
            if refined_estimate:
                entry_estimate = refined_estimate
                if not refined_estimate.approximate:
                    observed_bpl = _compute_bytes_per_line(snapshot["size_bytes"], refined_estimate.count)
                    state_manager.update_log_stats(
                        project["name"],
                        log_type,
                        size_bytes=snapshot["size_bytes"],
                        line_count=refined_estimate.count,
                        ema_bytes_per_line=observed_bpl,
                        mtime_ns=snapshot.get("mtime_ns"),
                        inode=snapshot.get("inode"),
                        source="tail_sample",
                        initialized=True,
                    )
                estimation_decision = _classify_estimate(entry_estimate.count, threshold_limit, estimation_band)

        if estimation_decision == "undecided" and normalized_mode == "precise":
            precise_count = count_file_lines(str(log_path))
            observed_bpl = _compute_bytes_per_line(snapshot["size_bytes"], precise_count)
            state_manager.update_log_stats(
                project["name"],
                log_type,
                size_bytes=snapshot["size_bytes"],
                line_count=precise_count,
                ema_bytes_per_line=observed_bpl,
                mtime_ns=snapshot.get("mtime_ns"),
                inode=snapshot.get("inode"),
                source="precise_dry_run",
                initialized=True,
            )
            entry_estimate = EntryCountEstimate(
                count=precise_count,
                approximate=False,
                method="full_count",
                details={**snapshot, "bytes_per_line": observed_bpl},
            )
            estimation_decision = _classify_estimate(entry_estimate.count, threshold_limit, estimation_band)

    if auto_threshold and threshold_limit and estimation_decision == "below":
        result.update({
            "ok": True,
            "rotation_skipped": True,
            "reason": "threshold_not_reached",
            "entry_count": entry_estimate.count,
            "entry_count_approximate": entry_estimate.approximate,
            "entry_count_method": entry_estimate.method,
            "threshold_entries": threshold_limit,
            "estimation_band": estimation_band,
            "estimation_details": dict(entry_estimate.details),
            "current_log_path": str(log_path),
            "auto_threshold_triggered": False,
            "estimation_decision": "below",
        })
        return result

    auto_triggered = bool(auto_threshold and threshold_limit and estimation_decision == "above")
    confirm_requested = bool(confirm)
    should_rotate = confirm_requested or auto_triggered
    dry_run_flag = dry_run if dry_run is not None else not should_rotate

    if dry_run_flag and normalized_mode == "precise" and entry_estimate.approximate:
        precise_count = count_file_lines(str(log_path))
        observed_bpl = _compute_bytes_per_line(snapshot["size_bytes"], precise_count)
        state_manager.update_log_stats(
            project["name"],
            log_type,
            size_bytes=snapshot["size_bytes"],
            line_count=precise_count,
            ema_bytes_per_line=observed_bpl,
            mtime_ns=snapshot.get("mtime_ns"),
            inode=snapshot.get("inode"),
            source="precise_dry_run",
            initialized=True,
        )
        entry_estimate = EntryCountEstimate(
            count=precise_count,
            approximate=False,
            method="full_count",
            details={**snapshot, "bytes_per_line": observed_bpl},
        )

    sequence_number = get_next_sequence_number(project["name"])
    hash_chain_info = state_manager.get_hash_chain_info(project["name"])
    previous_hash = hash_chain_info.get("last_hash")
    rotation_id = generate_rotation_id(project["name"])
    rotation_timestamp = format_utc()

    if dry_run_flag:
        archive_suffix = _build_archive_suffix(suffix, log_type, rotation_id)
        potential_archive = await rotate_file(
            log_path,
            archive_suffix,
            confirm=should_rotate,
            dry_run=True,
        )
        current_size_mb = round(snapshot["size_bytes"] / (1024 * 1024), 3) if snapshot["size_bytes"] else 0.0
        estimation_decision_label = estimation_decision or ("rotate" if should_rotate else "manual")
        result.update({
            "ok": True,
            "dry_run": True,
            "rotation_id": rotation_id,
            "rotation_timestamp_utc": rotation_timestamp,
            "rotation_timestamp": rotation_timestamp,
            "project": project["name"],
            "log_type": log_type,
            "current_file_path": str(log_path),
            "current_log_path": str(log_path),
            "current_file_size_bytes": snapshot["size_bytes"],
            "current_file_size_mb": current_size_mb,
            "current_file_line_count": entry_estimate.count,
            "current_file_sha256": cached_stats.get("sha256") if cached_stats else None,
            "current_file_hash": cached_stats.get("sha256") if cached_stats else None,
            "file_hash": cached_stats.get("sha256") if cached_stats else None,
            "entry_count": entry_estimate.count,
            "entry_count_approximate": entry_estimate.approximate,
            "entry_count_method": entry_estimate.method,
            "estimation_band": estimation_band,
            "estimation_details": dict(entry_estimate.details),
            "estimation_decision": estimation_decision_label,
            "sequence_number": sequence_number,
            "hash_chain_previous": previous_hash,
            "hash_chain_root": hash_chain_info.get("root_hash"),
            "hash_chain_sequence": sequence_number,
            "archived_to": str(potential_archive),
            "requires_confirmation": not should_rotate,
            "auto_threshold_triggered": auto_triggered,
        })
        if threshold_limit:
            result["threshold_entries"] = threshold_limit

        return result

    if not should_rotate:
        result.update({
            "ok": False,
            "error": "Rotation requires explicit confirmation. Add confirm=true to proceed.",
            "suggestion": "Use confirm=true to perform rotation, or dry_run=true to preview changes",
        })
        return result

    rotation_start_time = datetime.utcnow()

    archive_suffix = _build_archive_suffix(suffix, log_type, rotation_id)

    archive_path = await rotate_file(
        log_path,
        archive_suffix,
        confirm=True,
        dry_run=False,
        template_content=None,
    )

    archive_info = verify_file_integrity(archive_path)
    archive_hash = archive_info.get("sha256")
    archive_size = archive_info.get("size_bytes")
    rotated_entries = archive_info.get("line_count")
    entry_count_method = "archive_scan"
    entry_count_approximate = False
    if rotated_entries is None:
        rotated_entries = entry_estimate.count
        entry_count_method = entry_estimate.method
        entry_count_approximate = entry_estimate.approximate

    rotation_context = create_rotation_context(
        rotation_id=rotation_id,
        rotation_timestamp=rotation_timestamp,
        previous_log_path=str(archive_path),
        previous_log_hash=archive_hash or "",
        previous_log_entries=str(rotated_entries),
        current_sequence=str(sequence_number),
        total_rotations=str(sequence_number),
        hash_chain_previous=previous_hash or "",
        hash_chain_sequence=str(sequence_number),
        hash_chain_root=hash_chain_info.get("root_hash") or "",
    )

    rendered_template = await _build_template_content(log_type, project, rotation_context)

    try:  # Best-effort WAL entry
        from scribe_mcp.utils.files import WriteAheadLog

        wal = WriteAheadLog(archive_path)
        rotation_journal_entry = {
            "op": "rotate",
            "from": str(log_path),
            "to": str(archive_path),
            "rotation_id": rotation_id,
            "timestamp": rotation_timestamp,
            "sequence": str(sequence_number),
            "entries_rotated": str(rotated_entries),
            "log_type": log_type,
        }
        wal.write_entry(rotation_journal_entry)
    except Exception as wal_error:  # pragma: no cover - defensive
        print(f"Warning: Failed to write rotation journal entry: {wal_error}")

    rotation_metadata = create_rotation_metadata(
        archived_file_path=str(archive_path),
        rotation_uuid=rotation_id,
        rotation_timestamp=rotation_timestamp,
        sequence_number=sequence_number,
        previous_hash=previous_hash,
        log_type=log_type,
    )
    if rotated_entries is not None:
        rotation_metadata["entry_count"] = rotated_entries

    if parsed_metadata:
        rotation_metadata.update(parsed_metadata)

    audit_success = store_rotation_metadata(project["name"], rotation_metadata)
    state_success = update_project_state(project["name"], rotation_metadata)

    rotation_duration = max(
        0.0, (datetime.utcnow() - rotation_start_time).total_seconds()
    )

    if rendered_template:
        await _write_rotated_log_header(log_path, rendered_template)

    observed_bpl = None if entry_count_approximate else _compute_bytes_per_line(archive_size, rotated_entries)
    try:
        new_snapshot = _snapshot_file_state(log_path)
    except OSError:
        new_snapshot = {"size_bytes": 0, "mtime_ns": None, "inode": None}

    new_log_line_count = rendered_template.count("\n") if rendered_template else 0
    ema_value = cached_ema
    ema_source = "post_rotation"
    initialized_flag = cached_initialized
    if not entry_count_approximate:
        observed_bpl = _compute_bytes_per_line(archive_size, rotated_entries)
        if observed_bpl:
            ema_value = _blend_ema(cached_ema, observed_bpl, EMA_SMOOTHING_ALPHA)
            ema_source = "post_rotation_precise"
            initialized_flag = True
    else:
        approx_bpl = _compute_bytes_per_line(archive_size, entry_estimate.count)
        if approx_bpl:
            ema_value = _blend_ema(cached_ema, approx_bpl, EMA_SMOOTHING_ALPHA / 2)
            ema_source = "post_rotation_estimate"

    state_manager.update_log_stats(
        project["name"],
        log_type,
        size_bytes=new_snapshot.get("size_bytes"),
        line_count=new_log_line_count,
        ema_bytes_per_line=ema_value,
        mtime_ns=new_snapshot.get("mtime_ns"),
        inode=new_snapshot.get("inode"),
        source=ema_source,
        initialized=initialized_flag,
    )

    result.update({
        "ok": True,
        "rotation_completed": True,
        "rotation_id": rotation_id,
        "rotation_timestamp_utc": rotation_timestamp,
        "rotation_timestamp": rotation_timestamp,
        "project": project["name"],
        "log_type": log_type,
        "sequence_number": sequence_number,
        "current_log_path": str(log_path),
        "archive_path": str(archive_path),
        "archived_to": str(archive_path),
        "archive_sha256": archive_hash,
        "archive_hash": archive_hash,
        "archive_size_bytes": archive_size,
        "archive_size_mb": archive_info.get("size_mb"),
        "rotated_entry_count": rotated_entries,
        "entry_count": rotated_entries,
        "entry_count_approximate": entry_count_approximate,
        "entry_count_method": entry_count_method,
        "estimated_entry_count": entry_estimate.count,
        "estimated_entry_count_method": entry_estimate.method,
        "estimated_entry_count_approximate": entry_estimate.approximate,
        "estimation_band": estimation_band,
        "estimation_details": dict(entry_estimate.details),
        "estimation_decision": estimation_decision or "rotate",
        "rotation_duration_seconds": rotation_duration,
        "hash_chain_previous": previous_hash,
        "hash_chain_root": hash_chain_info.get("root_hash"),
        "hash_chain_sequence": sequence_number,
        "audit_trail_stored": audit_success,
        "state_updated": state_success,
        "auto_threshold_triggered": auto_triggered,
        "template_generated": bool(rendered_template),
        "integrity_verified": archive_hash is not None,
    })
    if threshold_limit:
        result["threshold_entries"] = threshold_limit

    if parsed_metadata:
        result["custom_metadata_applied"] = True
        result["custom_metadata"] = parsed_metadata

    return result


def _merge_single_rotation_response(summary: Dict[str, Any], rotation_result: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(summary)
    for key, value in rotation_result.items():
        if key == "ok":
            merged["ok"] = merged["ok"] and bool(value)
        else:
            merged[key] = value
    merged.setdefault("rotations", summary.get("rotations", [rotation_result]))
    return merged


def _snapshot_file_state(path: Path) -> Dict[str, Any]:
    stat_result = path.stat()
    inode = getattr(stat_result, "st_ino", None)
    if not inode:
        inode = None

    return {
        "size_bytes": stat_result.st_size,
        "mtime_ns": getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1_000_000_000)),
        "inode": inode,
    }


def _clamp_bytes_per_line(value: float) -> float:
    return max(MIN_BYTES_PER_LINE, min(MAX_BYTES_PER_LINE, value))


def _estimate_entry_count(snapshot: Dict[str, Any], cached_stats: Optional[Dict[str, Any]]) -> EntryCountEstimate:
    size_bytes = snapshot.get("size_bytes", 0) or 0
    details: Dict[str, Any] = {"size_bytes": size_bytes}

    if cached_stats:
        cached_size = cached_stats.get("size_bytes")
        cached_mtime = cached_stats.get("mtime_ns")
        cached_line_count = cached_stats.get("line_count")
        details["cached_initialized"] = cached_stats.get("initialized")
        if (
            cached_size is not None
            and cached_mtime is not None
            and cached_line_count is not None
            and cached_size == size_bytes
            and cached_mtime == snapshot.get("mtime_ns")
        ):
            details.update({
                "source": cached_stats.get("source", "cache"),
                "cache_hit": True,
                "ema_bytes_per_line": cached_stats.get("ema_bytes_per_line"),
            })
            return EntryCountEstimate(int(cached_line_count), False, "cache", details)

        ema = cached_stats.get("ema_bytes_per_line")
        if ema:
            ema = _clamp_bytes_per_line(float(ema))
        else:
            ema = None
    else:
        ema = None

    if ema is None:
        ema = DEFAULT_BYTES_PER_LINE
        details["source"] = "initial_estimate"

    details["ema_bytes_per_line"] = ema

    if size_bytes <= 0:
        return EntryCountEstimate(0, False, "empty", details)

    estimated = max(1, int(round(size_bytes / ema)))
    details["approximation"] = "ema"
    return EntryCountEstimate(estimated, True, "ema", details)


def _refine_entry_estimate(log_path: Path, snapshot: Dict[str, Any], estimate: EntryCountEstimate) -> Optional[EntryCountEstimate]:
    if not estimate.approximate:
        return estimate

    size_bytes = snapshot.get("size_bytes", 0)
    if not size_bytes:
        return None

    sample_size = min(size_bytes, TAIL_SAMPLE_BYTES)
    if sample_size <= 0:
        return None

    try:
        with open(log_path, "rb") as handle:
            if size_bytes > sample_size:
                handle.seek(size_bytes - sample_size)
            data = handle.read(sample_size)
    except OSError:
        return None

    newline_count = data.count(b"\n")
    if newline_count <= 0:
        return None

    bytes_per_line = sample_size / newline_count
    bytes_per_line = _clamp_bytes_per_line(bytes_per_line)
    refined = max(1, int(round(size_bytes / bytes_per_line)))

    details = dict(estimate.details)
    details.update({
        "tail_sample_bytes": sample_size,
        "tail_newlines": newline_count,
        "refined_bytes_per_line": bytes_per_line,
    })

    approximate = sample_size != size_bytes
    if not approximate:
        method = "full_tail"
    else:
        method = "tail" if estimate.method == "empty" else f"{estimate.method}+tail"

    return EntryCountEstimate(refined, approximate, method, details)


def _compute_estimation_band(threshold: Optional[int]) -> Optional[int]:
    if not threshold:
        return None
    return max(int(threshold * ESTIMATION_BAND_RATIO), ESTIMATION_BAND_MIN)


def _classify_estimate(value: int, threshold: int, band: Optional[int]) -> str:
    margin = band or 0
    if value < threshold - margin:
        return "below"
    if value > threshold + margin:
        return "above"
    return "undecided"


def _compute_bytes_per_line(size_bytes: Optional[int], line_count: Optional[int]) -> Optional[float]:
    if not size_bytes or not line_count or line_count <= 0:
        return None
    return _clamp_bytes_per_line(float(size_bytes) / float(line_count))


def _blend_ema(current: Optional[float], observed: Optional[float], smoothing: float) -> Optional[float]:
    if observed is None:
        return current
    observed = _clamp_bytes_per_line(observed)
    smoothing = max(0.0, min(1.0, smoothing))
    if current is None:
        return observed
    current = _clamp_bytes_per_line(current)
    blended = (1.0 - smoothing) * current + smoothing * observed
    return _clamp_bytes_per_line(blended)
