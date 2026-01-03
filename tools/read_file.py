"""Read file tool with scan + chunk + stream semantics and provenance logging."""

from __future__ import annotations

import asyncio
import os
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import yaml
import difflib

from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.server import app
from scribe_mcp.shared.execution_context import ExecutionContext
from scribe_mcp.shared.logging_utils import compose_log_line, default_status_emoji, resolve_logging_context
from scribe_mcp.utils.files import append_line
from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.utils.sentinel_logs import append_sentinel_event
from scribe_mcp.utils.response import default_formatter


_DEFAULT_DENYLIST = [
    ".env",
    ".git/",
    ".scribe/registry/",
    "~/.ssh",
    "/etc",
    "/proc",
    "/sys",
]

_CHUNK_LINES = 200
_CHUNK_MAX_BYTES = 131072
_GLOB_CHARS = {"*", "?", "["}
_DEFAULT_MAX_MATCHES = 200


def _load_sentinel_config(repo_root: Path) -> Dict[str, Any]:
    config_path = repo_root / ".scribe" / "sentinel" / "sentinel_config.yaml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_patterns(values: Any) -> List[str]:
    if not values:
        return []
    if isinstance(values, list):
        normalized: List[str] = []
        for item in values:
            if not item:
                continue
            value = os.path.expanduser(str(item))
            normalized.append(value)
        return normalized
    return [os.path.expanduser(str(values))]


def _normalize_path(path_str: str) -> str:
    return path_str.replace("\\", "/")


def _pattern_is_glob(pattern: str) -> bool:
    return any(char in pattern for char in _GLOB_CHARS)


def _matches_any(path_str: str, patterns: Iterable[str]) -> bool:
    path_posix = _normalize_path(path_str)
    parts = [part for part in path_posix.split("/") if part]
    for pattern in patterns:
        if not pattern:
            continue
        normalized = _normalize_path(str(pattern))
        if _pattern_is_glob(normalized):
            if fnmatch(path_posix, normalized) or fnmatch(f"/{path_posix}", normalized):
                return True
            continue
        if "/" in normalized:
            if normalized in path_posix:
                return True
            continue
        if normalized in parts:
            return True
    return False


def _enforce_path_policy(path: Path, repo_root: Path) -> Optional[str]:
    config = _load_sentinel_config(repo_root)
    allowlist = _normalize_patterns(config.get("allowlist"))
    denylist = _normalize_patterns(config.get("denylist")) or list(_DEFAULT_DENYLIST)

    abs_path = str(path)
    try:
        rel_path = str(path.relative_to(repo_root))
    except ValueError:
        rel_path = None

    if _matches_any(abs_path, denylist) or (rel_path and _matches_any(rel_path, denylist)):
        return "denylist_match"

    if rel_path is None and not _matches_any(abs_path, allowlist):
        return "absolute_path_not_allowlisted"

    if rel_path is not None:
        return None

    return None


def _scan_file(path: Path) -> Dict[str, Any]:
    size = 0
    line_count = 0
    has_crlf = False
    has_lf = False
    last_byte = None
    sha = None
    sample = b""

    import hashlib
    sha = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            size += len(chunk)
            sha.update(chunk)
            if len(sample) < 4096:
                remaining = 4096 - len(sample)
                sample += chunk[:remaining]
            if b"\r\n" in chunk:
                has_crlf = True
            if b"\n" in chunk and b"\r\n" not in chunk:
                has_lf = True
            line_count += chunk.count(b"\n")
            last_byte = chunk[-1]

    if size > 0 and line_count == 0:
        line_count = 1
    elif size > 0 and last_byte is not None and last_byte != ord("\n"):
        line_count = line_count + 1

    newline_type = "unknown"
    if has_crlf and has_lf:
        newline_type = "mixed"
    elif has_crlf:
        newline_type = "CRLF"
    elif has_lf:
        newline_type = "LF"

    encoding = "utf-8"
    try:
        sample.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        encoding = "latin-1"

    estimated_chunk_count = max(1, (line_count + _CHUNK_LINES - 1) // _CHUNK_LINES) if line_count else 0

    return {
        "byte_size": size,
        "line_count": line_count,
        "sha256": sha.hexdigest(),
        "newline_type": newline_type,
        "encoding": encoding,
        "estimated_chunk_count": estimated_chunk_count,
    }


def _read_frontmatter_header(path: Path, encoding: str) -> Dict[str, Any]:
    try:
        with path.open("rb") as handle:
            first = handle.readline()
            if not first:
                return {
                    "has_frontmatter": False,
                    "frontmatter_raw": "",
                    "frontmatter": {},
                    "frontmatter_line_count": 0,
                    "frontmatter_byte_count": 0,
                }
            if first.strip() != b"---":
                return {
                    "has_frontmatter": False,
                    "frontmatter_raw": "",
                    "frontmatter": {},
                    "frontmatter_line_count": 0,
                    "frontmatter_byte_count": 0,
                }

            lines = [first]
            while True:
                line = handle.readline()
                if not line:
                    return {
                        "has_frontmatter": True,
                        "frontmatter_raw": b"".join(lines).decode(encoding, errors="replace"),
                        "frontmatter": {},
                        "frontmatter_line_count": len(lines),
                        "frontmatter_byte_count": sum(len(item) for item in lines),
                        "frontmatter_error": "FRONTMATTER_PARSE_ERROR: missing closing '---' delimiter",
                    }
                lines.append(line)
                if line.strip() == b"---":
                    break

            raw_bytes = b"".join(lines)
            raw_text = raw_bytes.decode(encoding, errors="replace")
            try:
                parsed = parse_frontmatter(raw_text)
                data = parsed.frontmatter_data
                error = None
            except ValueError as exc:
                data = {}
                error = str(exc)

            return {
                "has_frontmatter": True,
                "frontmatter_raw": raw_text,
                "frontmatter": data,
                "frontmatter_line_count": len(lines),
                "frontmatter_byte_count": len(raw_bytes),
                "frontmatter_error": error,
            }
    except Exception as exc:
        return {
            "has_frontmatter": False,
            "frontmatter_raw": "",
            "frontmatter": {},
            "frontmatter_line_count": 0,
            "frontmatter_byte_count": 0,
            "frontmatter_error": f"FRONTMATTER_PARSE_ERROR: {exc}",
        }


def _iter_chunks(path: Path, encoding: str) -> Iterable[Dict[str, Any]]:
    chunk_index = 0
    current_line = 1
    chunk_line_start = None
    chunk_line_end = None
    chunk_bytes = 0
    segments: List[bytes] = []
    chunk_byte_start = 0
    chunk_byte_end = 0

    def flush_chunk() -> Optional[Dict[str, Any]]:
        nonlocal chunk_index, segments, chunk_bytes, chunk_line_start, chunk_line_end, chunk_byte_start, chunk_byte_end
        if not segments:
            return None
        text = b"".join(segments).decode(encoding, errors="replace")
        payload = {
            "chunk_index": chunk_index,
            "line_start": chunk_line_start or 1,
            "line_end": chunk_line_end or (chunk_line_start or 1),
            "byte_start": chunk_byte_start,
            "byte_end": chunk_byte_end,
            "content": text,
        }
        chunk_index += 1
        segments = []
        chunk_bytes = 0
        chunk_line_start = None
        chunk_line_end = None
        chunk_byte_start = 0
        chunk_byte_end = 0
        return payload

    with path.open("rb") as handle:
        while True:
            segment = handle.readline(_CHUNK_MAX_BYTES)
            if not segment:
                break

            segment_start = handle.tell() - len(segment)
            segment_end = handle.tell()
            if chunk_line_start is None:
                chunk_line_start = current_line
                chunk_byte_start = segment_start

            # Flush current chunk if adding the segment would exceed memory bound.
            if segments and (chunk_bytes + len(segment) > _CHUNK_MAX_BYTES):
                payload = flush_chunk()
                if payload:
                    yield payload
                chunk_line_start = current_line
                chunk_byte_start = segment_start

            segments.append(segment)
            chunk_bytes += len(segment)
            chunk_line_end = current_line
            chunk_byte_end = segment_end

            if segment.endswith(b"\n"):
                current_line += 1

            # Flush if we've hit line or byte thresholds.
            if chunk_line_start is not None:
                line_count = (chunk_line_end - chunk_line_start) + 1
                if line_count >= _CHUNK_LINES or chunk_bytes >= _CHUNK_MAX_BYTES:
                    payload = flush_chunk()
                    if payload:
                        yield payload

        payload = flush_chunk()
        if payload:
            yield payload


def _extract_line_range(path: Path, encoding: str, start_line: int, end_line: int) -> Dict[str, Any]:
    current_line = 0
    matched: List[bytes] = []
    byte_start = None
    byte_end = None

    with path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                break
            current_line += 1
            if current_line < start_line:
                continue
            if byte_start is None:
                byte_start = handle.tell() - len(line)
            if current_line <= end_line:
                matched.append(line)
                byte_end = handle.tell()
            if current_line >= end_line:
                break

    return {
        "line_start": start_line,
        "line_end": end_line,
        "byte_start": byte_start or 0,
        "byte_end": byte_end or (byte_start or 0),
        "content": b"".join(matched).decode(encoding, errors="replace"),
    }


_REGEX_META_CHARS = set(".^$*+?{}[]\\|()")


def _infer_search_mode(pattern: str) -> str:
    if any(char in _REGEX_META_CHARS for char in pattern):
        return "regex"
    return "literal"


def _search_file(
    path: Path,
    encoding: str,
    pattern: str,
    regex: bool,
    context_lines: int,
    max_matches: Optional[int],
    case_insensitive: bool,
    fuzzy_threshold: float,
) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    matcher = None
    if regex:
        try:
            flags = re.IGNORECASE if case_insensitive else 0
            matcher = re.compile(pattern, flags)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
    buffer: List[str] = []
    buffer_start = 1
    current_line = 0
    pattern_value = pattern.lower() if case_insensitive else pattern

    with path.open("rb") as handle:
        for raw_line in handle:
            current_line += 1
            line = raw_line.decode(encoding, errors="replace")
            buffer.append(line)
            if len(buffer) > context_lines * 2 + 1:
                buffer.pop(0)
                buffer_start += 1

            is_match = False
            score = None
            candidate = line.lower() if case_insensitive else line
            if regex:
                if matcher and matcher.search(line):
                    is_match = True
            elif fuzzy_threshold > 0:
                base = line.strip()
                candidate_text = base.lower() if case_insensitive else base
                score = difflib.SequenceMatcher(None, pattern_value, candidate_text).ratio()
                if score >= fuzzy_threshold:
                    is_match = True
            else:
                if pattern_value in candidate:
                    is_match = True

            if is_match:
                context_start = max(1, current_line - context_lines)
                context_end = current_line + context_lines
                snippet = buffer[-(context_lines * 2 + 1):]
                match_payload = {
                    "line_number": current_line,
                    "line": line,
                    "context_start": context_start,
                    "context_end": context_end,
                    "context": snippet,
                }
                if score is not None:
                    match_payload["match_score"] = score
                matches.append(match_payload)
                if max_matches is not None and len(matches) >= max_matches:
                    break

    return matches


async def _log_project_read(context: ExecutionContext, message: str, meta: Dict[str, Any]) -> None:
    log_context = await resolve_logging_context(
        tool_name="read_file",
        server_module=server_module,
        agent_id=None,
        require_project=True,
    )
    project = log_context.project or {}
    log_path = Path(project.get("progress_log", ""))
    if not log_path:
        return

    emoji = default_status_emoji(explicit=None, status="info", project=project)
    line = compose_log_line(
        emoji=emoji,
        timestamp=context.timestamp_utc,
        agent=context.agent_identity.instance_id,
        project_name=project.get("name", "unknown"),
        message=message,
        meta_pairs=tuple((str(k), str(v)) for k, v in meta.items()),
    )
    await append_line(
        log_path,
        line,
        repo_root=Path(context.repo_root),
        context={"component": "logs", "project_name": project.get("name")},
    )


@app.tool()
async def read_file(
    path: str,
    mode: str = "scan_only",
    chunk_index: Optional[List[int]] = None,
    start_chunk: Optional[int] = None,
    max_chunks: Optional[int] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    page_number: Optional[int] = None,
    page_size: Optional[int] = None,
    search: Optional[str] = None,
    search_mode: str = "literal",
    case_insensitive: Optional[bool] = None,
    context_lines: int = 0,
    max_matches: Optional[int] = None,
    fuzzy_threshold: Optional[float] = None,
    format: str = "readable",  # NEW: default is readable for agent-friendly output
) -> Union[Dict[str, Any], str]:
    exec_context = server_module.get_execution_context()
    if exec_context is None:
        return {"ok": False, "error": "ExecutionContext missing"}

    repo_root = Path(exec_context.repo_root)
    requested_mode = mode.lower()
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = (repo_root / target).resolve()
    else:
        target = target.resolve()
    try:
        rel_path = str(target.relative_to(repo_root))
    except ValueError:
        rel_path = None

    audit_meta = {
        "execution_id": exec_context.execution_id,
        "session_id": exec_context.session_id,
        "intent": exec_context.intent,
        "agent_kind": exec_context.agent_identity.agent_kind,
        "agent_instance_id": exec_context.agent_identity.instance_id,
        "agent_sub_id": exec_context.agent_identity.sub_id,
        "agent_display_name": exec_context.agent_identity.display_name,
        "agent_model": exec_context.agent_identity.model,
    }

    async def get_reminders(read_mode: str) -> List[Dict[str, Any]]:
        try:
            context = await resolve_logging_context(
                tool_name="read_file",
                server_module=server_module,
                agent_id=exec_context.agent_identity.instance_id,
                require_project=False,
                reminder_variables={"read_mode": read_mode},
            )
            return list(context.reminders or [])
        except Exception:
            return []

    async def finalize_response(payload: Dict[str, Any], read_mode: str) -> Union[Dict[str, Any], str]:
        payload.setdefault("mode", read_mode)
        payload["reminders"] = await get_reminders(read_mode)

        # NEW: Route through formatter for readable/structured/compact modes
        return await default_formatter.finalize_tool_response(
            data=payload,
            format=format,
            tool_name="read_file"
        )

    async def log_read(event_type: str, data: Dict[str, Any], *, include_md: bool = True) -> None:
        payload = {**audit_meta, **data}
        if exec_context.mode == "sentinel":
            append_sentinel_event(
                exec_context,
                event_type=event_type,
                data=payload,
                log_type="sentinel",
                include_md=include_md,
            )
        else:
            await _log_project_read(
                exec_context,
                message=event_type,
                meta=payload,
            )

    policy_error = _enforce_path_policy(target, repo_root)
    if policy_error:
        await log_read(
            "scope_violation",
            {"reason": policy_error, "path": str(target)},
            include_md=True,
        )
        return await finalize_response({
            "ok": False,
            "error": "read_file denied",
            "reason": policy_error,
            "absolute_path": str(target),
            "repo_relative_path": rel_path,
        }, requested_mode)

    if not target.exists() or not target.is_file():
        await log_read(
            "read_file_error",
            {"reason": "file_not_found", "path": str(target)},
            include_md=True,
        )
        return await finalize_response({
            "ok": False,
            "error": "file not found",
            "absolute_path": str(target),
            "repo_relative_path": rel_path,
        }, requested_mode)

    scan = _scan_file(target)
    scan_payload = {
        "absolute_path": str(target),
        "repo_relative_path": rel_path,
        **scan,
    }

    encoding = scan["encoding"]
    frontmatter_info = _read_frontmatter_header(target, encoding)
    response: Dict[str, Any] = {
        "ok": True,
        "scan": scan_payload,
        "mode": mode,
        "frontmatter": frontmatter_info.get("frontmatter", {}),
        "frontmatter_raw": frontmatter_info.get("frontmatter_raw", ""),
        "frontmatter_line_count": frontmatter_info.get("frontmatter_line_count", 0),
        "frontmatter_byte_count": frontmatter_info.get("frontmatter_byte_count", 0),
        "has_frontmatter": frontmatter_info.get("has_frontmatter", False),
    }
    if frontmatter_info.get("frontmatter_error"):
        response["frontmatter_error"] = frontmatter_info.get("frontmatter_error")
    mode = mode.lower()
    if chunk_index is None and mode == "chunk":
        chunk_index = [0]
    elif isinstance(chunk_index, (int, str)):
        chunk_index = [int(chunk_index)]

    if mode == "scan_only":
        await log_read("read_file", {"read_mode": "scan_only", **scan_payload}, include_md=True)
        return await finalize_response(response, "scan_only")

    if mode == "chunk":
        if not chunk_index:
            return await finalize_response({
                "ok": False,
                "error": "chunk_index required for chunk mode",
                "absolute_path": str(target),
                "repo_relative_path": rel_path,
            }, "chunk")
        try:
            wanted = {int(x) for x in chunk_index}
        except (TypeError, ValueError):
            return await finalize_response({
                "ok": False,
                "error": "chunk_index must be integers",
                "absolute_path": str(target),
                "repo_relative_path": rel_path,
            }, "chunk")
        max_wanted = max(wanted) if wanted else -1
        remaining = set(wanted)
        chunks: List[Dict[str, Any]] = []
        for chunk in _iter_chunks(target, encoding):
            index = chunk["chunk_index"]
            if index in remaining:
                chunks.append(chunk)
                remaining.remove(index)
            if not remaining and index >= max_wanted:
                break
        response["chunks"] = chunks
        if frontmatter_info.get("has_frontmatter") and chunks:
            line_offset = frontmatter_info.get("frontmatter_line_count", 0)
            byte_offset = frontmatter_info.get("frontmatter_byte_count", 0)
            first_chunk = chunks[0]
            raw_frontmatter = frontmatter_info.get("frontmatter_raw", "")
            if raw_frontmatter and first_chunk.get("content", "").startswith(raw_frontmatter):
                first_chunk["frontmatter_stripped"] = True
                first_chunk["original_line_start"] = first_chunk.get("line_start")
                first_chunk["original_line_end"] = first_chunk.get("line_end")
                first_chunk["original_byte_start"] = first_chunk.get("byte_start")
                first_chunk["original_byte_end"] = first_chunk.get("byte_end")
                first_chunk["content"] = first_chunk.get("content", "")[len(raw_frontmatter):]
                if isinstance(first_chunk.get("line_start"), int):
                    first_chunk["line_start"] = max(1, first_chunk["line_start"] - line_offset)
                if isinstance(first_chunk.get("line_end"), int):
                    first_chunk["line_end"] = max(0, first_chunk["line_end"] - line_offset)
                if isinstance(first_chunk.get("byte_start"), int):
                    first_chunk["byte_start"] = max(0, first_chunk["byte_start"] - byte_offset)
                if isinstance(first_chunk.get("byte_end"), int):
                    first_chunk["byte_end"] = max(0, first_chunk["byte_end"] - byte_offset)
        await log_read(
            "read_file",
            {"read_mode": "chunk", "chunk_index": sorted(wanted), **scan_payload},
            include_md=True,
        )
        return await finalize_response(response, "chunk")

    if mode == "line_range":
        if start_line is None or end_line is None:
            return await finalize_response({"ok": False, "error": "start_line and end_line required for line_range"}, "line_range")
        if start_line < 1 or end_line < start_line:
            return await finalize_response({"ok": False, "error": "invalid line range"}, "line_range")
        chunk = _extract_line_range(target, encoding, int(start_line), int(end_line))
        response["chunk"] = chunk
        await log_read(
            "read_file",
            {"read_mode": "line_range", "line_start": start_line, "line_end": end_line, **scan_payload},
            include_md=True,
        )
        return await finalize_response(response, "line_range")

    if mode == "page":
        if page_number is None:
            return await finalize_response({"ok": False, "error": "page_number required for page mode"}, "page")
        size = int(page_size or settings.default_page_size)
        start = (int(page_number) - 1) * size + 1
        end = start + size - 1
        chunk = _extract_line_range(target, encoding, start, end)
        response["chunk"] = chunk
        response["page_number"] = page_number
        response["page_size"] = size
        await log_read(
            "read_file",
            {"read_mode": "page", "page_number": page_number, "page_size": size, **scan_payload},
            include_md=True,
        )
        return await finalize_response(response, "page")

    if mode == "full_stream":
        if start_chunk is not None and start_chunk < 0:
            return await finalize_response({"ok": False, "error": "start_chunk must be >= 0"}, "full_stream")
        if max_chunks is not None and max_chunks <= 0:
            return await finalize_response({"ok": False, "error": "max_chunks must be >= 1"}, "full_stream")
        start_index = int(start_chunk if start_chunk is not None else (chunk_index[0] if chunk_index else 0))
        max_chunk_count = int(max_chunks if max_chunks is not None else (page_size or 1))
        chunks: List[Dict[str, Any]] = []
        for chunk in _iter_chunks(target, encoding):
            if chunk["chunk_index"] < start_index:
                continue
            if len(chunks) >= max_chunk_count:
                break
            chunks.append(chunk)
        next_index = None
        if chunks:
            next_index = chunks[-1]["chunk_index"] + 1
            if next_index >= scan["estimated_chunk_count"]:
                next_index = None
        response["chunks"] = chunks
        response["next_chunk_index"] = next_index
        await log_read(
            "read_file",
            {"read_mode": "full_stream", "start_chunk": start_index, "max_chunks": max_chunk_count, **scan_payload},
            include_md=True,
        )
        return await finalize_response(response, "full_stream")

    if mode == "search":
        if not search:
            return await finalize_response({"ok": False, "error": "search pattern required for search mode"}, "search")
        if max_matches is None:
            max_matches = _DEFAULT_MAX_MATCHES
        if max_matches <= 0:
            return await finalize_response({"ok": False, "error": "max_matches must be >= 1"}, "search")
        resolved_mode = search_mode.lower()
        if resolved_mode == "smart":
            resolved_mode = _infer_search_mode(search)
        if resolved_mode not in {"literal", "regex", "fuzzy"}:
            return await finalize_response({"ok": False, "error": f"Unsupported search_mode '{search_mode}'"}, "search")
        if case_insensitive is None:
            case_insensitive = resolved_mode in {"smart", "fuzzy"}
        if fuzzy_threshold is None:
            fuzzy_threshold = 0.7 if resolved_mode == "fuzzy" else 0.0
        if resolved_mode != "fuzzy":
            fuzzy_threshold = 0.0
        regex = resolved_mode == "regex"
        try:
            matches = _search_file(
                target,
                encoding,
                search,
                regex,
                int(context_lines),
                max_matches,
                case_insensitive,
                fuzzy_threshold,
            )
        except ValueError as exc:
            await log_read(
                "read_file_error",
                {
                    "read_mode": "search",
                    "reason": "invalid_regex",
                    "search": search,
                    "search_mode": search_mode,
                    "error": str(exc),
                    **scan_payload,
                },
                include_md=True,
            )
            return await finalize_response({
                "ok": False,
                "error": "invalid regex",
                "details": str(exc),
                "absolute_path": str(target),
                "repo_relative_path": rel_path,
            }, "search")
        response["matches"] = matches
        response["max_matches"] = max_matches
        await log_read(
            "read_file",
            {
                "read_mode": "search",
                "search": search,
                "search_mode": search_mode,
                "search_mode_resolved": resolved_mode,
                "case_insensitive": case_insensitive,
                "fuzzy_threshold": fuzzy_threshold if resolved_mode == "fuzzy" else None,
                "context_lines": context_lines,
                "max_matches": max_matches,
                **scan_payload,
            },
            include_md=True,
        )
        return await finalize_response(response, "search")

    return await finalize_response({"ok": False, "error": f"Unsupported read mode '{mode}'"}, mode)
