"""Helpers for working with progress log files."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG_LINE_PATTERN = re.compile(
    r"^\[(?P<emoji>.+?)\]\s+\[(?P<timestamp>.+?)\]\s+\[Agent: (?P<agent>.+?)\]\s+\[Project: (?P<project>.+?)\]\s+(?P<message>.*?)(?:\s+\|\s+(?P<meta>.+))?$"
)


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a canonical Scribe log line into structured fields."""
    match = LOG_LINE_PATTERN.match(line.strip())
    if not match:
        return None
    meta_text = match.group("meta")
    meta: Dict[str, str] = {}
    if meta_text:
        for chunk in meta_text.split(";"):
            key, value = _split_meta_chunk(chunk)
            if key:
                meta[key] = value
    return {
        "ts": match.group("timestamp"),
        "emoji": match.group("emoji"),
        "agent": match.group("agent"),
        "project": match.group("project"),
        "message": match.group("message"),
        "meta": meta,
        "raw_line": line.strip(),
    }


def _split_meta_chunk(chunk: str) -> tuple[str, str]:
    piece = chunk.strip()
    if not piece:
        return "", ""
    if "=" not in piece:
        return piece, ""
    key, value = piece.split("=", 1)
    return key.strip(), value.strip()


async def read_all_lines(path: Path) -> List[str]:
    """Read the entire file (or empty list on missing) without blocking the loop."""
    return await asyncio.to_thread(_read_lines, path)


def _read_lines(path: Path) -> List[str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return [line.rstrip("\n") for line in handle]
    except FileNotFoundError:
        return []
