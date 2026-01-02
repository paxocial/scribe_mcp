"""Tests for manage_docs semantic limit resolution and doc skip rules."""

from pathlib import Path

from scribe_mcp.tools.manage_docs import _resolve_semantic_limits, _should_skip_doc_index


def test_semantic_limits_defaults() -> None:
    limits = _resolve_semantic_limits(search_meta={}, repo_root=None)
    assert limits["total_k"] == 8
    assert limits["doc_k"] == 5
    assert limits["log_k"] == 3


def test_semantic_limits_total_caps_logs() -> None:
    limits = _resolve_semantic_limits(search_meta={"k": 4}, repo_root=None)
    assert limits["total_k"] == 4
    assert limits["doc_k"] == 4
    assert limits["log_k"] == 0


def test_semantic_limits_overrides() -> None:
    limits = _resolve_semantic_limits(
        search_meta={"k": 10, "doc_k": 2, "log_k": 5},
        repo_root=None,
    )
    assert limits["total_k"] == 10
    assert limits["doc_k"] == 2
    assert limits["log_k"] == 5


def test_doc_index_skip_for_logs() -> None:
    assert _should_skip_doc_index("progress_log", Path("PROGRESS_LOG.md"))
    assert _should_skip_doc_index("doc_log", Path("DOC_LOG.md"))
    assert _should_skip_doc_index("architecture", Path("PROGRESS_LOG.md.2026-01-02.md"))
