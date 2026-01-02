"""Runtime plugin registry detection tests."""

from __future__ import annotations

import textwrap

import pytest

from scribe_mcp.config.repo_config import RepoConfig
from scribe_mcp.plugins.registry import get_plugin_registry, initialize_plugins
from scribe_mcp.plugins.vector_indexer import FAISS_AVAILABLE


@pytest.mark.skipif(not FAISS_AVAILABLE, reason="Vector dependencies not available")
def test_plugin_registry_loads_builtin_vector_indexer(tmp_path) -> None:
    """Ensure plugin registry loads built-in vector indexer when enabled in repo config."""
    config_dir = tmp_path / ".scribe" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_yaml = textwrap.dedent(
        """\
        repo_slug: test-repo
        plugins_dir: .scribe/plugins
        plugin_config:
          enabled: true
        vector_index_docs: true
        vector_index_logs: true
        """
    )
    (config_dir / "scribe.yaml").write_text(config_yaml, encoding="utf-8")

    repo_config = RepoConfig.from_directory(tmp_path)
    initialize_plugins(repo_config)

    registry = get_plugin_registry(tmp_path)
    assert "vector_indexer" in registry.plugins
    assert registry.plugins["vector_indexer"].initialized

    registry.cleanup()
