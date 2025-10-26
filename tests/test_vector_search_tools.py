"""Tests for vector search MCP tools."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Try to import vector dependencies - if not available, tests will be skipped
try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    VECTOR_DEPS_AVAILABLE = True
except ImportError:
    VECTOR_DEPS_AVAILABLE = False
    faiss = None
    np = None
    SentenceTransformer = None

from scribe_mcp.tools.vector_search import (
    vector_search,
    retrieve_by_uuid,
    vector_index_status,
    register_vector_tools,
    _get_vector_indexer
)


@pytest.mark.skipif(not VECTOR_DEPS_AVAILABLE, reason="Vector dependencies not available")
class TestVectorSearchTools:
    """Test vector search MCP tools functionality."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            (repo_path / ".scribe_vectors").mkdir(exist_ok=True)
            yield repo_path

    @pytest.fixture
    def mock_vector_indexer(self, temp_repo):
        """Create a mock VectorIndexer with test data."""
        indexer = MagicMock()
        indexer.initialized = True
        indexer.repo_root = temp_repo
        indexer.repo_slug = "tmp"

        # Mock search results
        def mock_search_similar(query, k=10, filters=None):
            if "test" in query.lower():
                return [
                    {
                        'entry_id': 'test1234567890abcdef1234567890ab',
                        'project_slug': 'test-project',
                        'text_content': 'This is a test message about testing',
                        'agent_name': 'TestAgent',
                        'timestamp_utc': '2025-10-26 12:00:00 UTC',
                        'metadata_json': '{"phase": "test"}',
                        'similarity_score': 0.95,
                        'vector_rowid': 0
                    },
                    {
                        'entry_id': 'test2abcdef1234567890abcdef123456',
                        'project_slug': 'test-project',
                        'text_content': 'Another test message for verification',
                        'agent_name': 'TestAgent',
                        'timestamp_utc': '2025-10-26 12:01:00 UTC',
                        'metadata_json': '{"phase": "test"}',
                        'similarity_score': 0.87,
                        'vector_rowid': 1
                    }
                ]
            return []

        indexer.search_similar = mock_search_similar

        # Mock UUID retrieval
        def mock_retrieve_by_uuid(entry_id):
            if entry_id == 'test1234567890abcdef1234567890ab':
                return {
                    'entry_id': 'test1234567890abcdef1234567890ab',
                    'project_slug': 'test-project',
                    'text_content': 'This is a test message about testing',
                    'agent_name': 'TestAgent',
                    'timestamp_utc': '2025-10-26 12:00:00 UTC',
                    'metadata_json': '{"phase": "test"}',
                    'vector_rowid': 0
                }
            return None

        indexer.retrieve_by_uuid = mock_retrieve_by_uuid

        # Mock status
        def mock_get_index_status():
            return {
                'initialized': True,
                'enabled': True,
                'repo_slug': 'tmp',
                'model': 'all-MiniLM-L6-v2',
                'dimension': 384,
                'total_entries': 2,
                'last_updated': '2025-10-26T12:01:00',
                'queue_depth': 0,
                'queue_max': 1024,
                'gpu_enabled': False,
                'faiss_available': True
            }

        indexer.get_index_status = mock_get_index_status

        return indexer

    @pytest.mark.asyncio
    async def test_vector_search_success(self, mock_vector_indexer):
        """Test successful vector search."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=mock_vector_indexer), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            result = await vector_search(
                query="test query",
                k=5,
                project_slug="test-project"
            )

            assert result['ok'] is True
            assert result['query'] == "test query"
            assert result['results_count'] == 2
            assert len(result['results']) == 2

            # Check first result
            first_result = result['results'][0]
            assert first_result['entry_id'] == 'test1234567890abcdef1234567890ab'
            assert first_result['text_content'] == 'This is a test message about testing'
            assert first_result['similarity_score'] == 0.95

            # Check filters were applied
            assert result['filters_applied'] == {'project_slug': 'test-project'}

    @pytest.mark.asyncio
    async def test_vector_search_no_results(self, mock_vector_indexer):
        """Test vector search with no results."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=mock_vector_indexer), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            result = await vector_search(
                query="query with no matches",
                k=10
            )

            assert result['ok'] is True
            assert result['results_count'] == 0
            assert result['results'] == []

    @pytest.mark.asyncio
    async def test_vector_search_plugin_not_available(self):
        """Test vector search when plugin is not available."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=None), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            result = await vector_search(query="test query")

            assert result['ok'] is False
            assert "not available" in result['error']
            assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_vector_search_plugin_not_initialized(self, mock_vector_indexer):
        """Test vector search when plugin is not initialized."""
        mock_vector_indexer.initialized = False

        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=mock_vector_indexer), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            result = await vector_search(query="test query")

            assert result['ok'] is False
            assert "not initialized" in result['error']

    @pytest.mark.asyncio
    async def test_vector_search_with_filters(self, mock_vector_indexer):
        """Test vector search with various filters."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=mock_vector_indexer), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            # Test with multiple filters
            result = await vector_search(
                query="test query",
                k=10,
                project_slug="test-project",
                agent_name="TestAgent",
                time_start="2025-10-25T12:00:00",
                time_end="2025-10-27T12:00:00",
                min_similarity=0.9
            )

            assert result['ok'] is True

            filters = result['filters_applied']
            assert filters['project_slug'] == 'test-project'
            assert filters['agent_name'] == 'TestAgent'
            assert 'time_range' in filters
            assert filters['time_range']['start'] == '2025-10-25T12:00:00'
            assert filters['time_range']['end'] == '2025-10-27T12:00:00'

    @pytest.mark.asyncio
    async def test_vector_search_similarity_threshold(self, mock_vector_indexer):
        """Test vector search with similarity threshold."""
        # Mock search results with different scores
        def mock_search_with_scores(query, k=10, filters=None):
            return [
                {
                    'entry_id': 'high_score',
                    'text_content': 'High similarity result',
                    'similarity_score': 0.95,
                },
                {
                    'entry_id': 'low_score',
                    'text_content': 'Low similarity result',
                    'similarity_score': 0.75,
                }
            ]

        mock_vector_indexer.search_similar = mock_search_with_scores

        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=mock_vector_indexer), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            # Test with high threshold
            result = await vector_search(
                query="test query",
                min_similarity=0.9
            )

            assert result['ok'] is True
            assert result['results_count'] == 1
            assert result['results'][0]['entry_id'] == 'high_score'

    @pytest.mark.asyncio
    async def test_retrieve_by_uuid_success(self, mock_vector_indexer):
        """Test successful UUID retrieval."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=mock_vector_indexer), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            result = await retrieve_by_uuid(
                entry_id='test1234567890abcdef1234567890ab'
            )

            assert result['ok'] is True
            assert 'entry' in result

            entry = result['entry']
            assert entry['entry_id'] == 'test1234567890abcdef1234567890ab'
            assert entry['text_content'] == 'This is a test message about testing'
            assert entry['agent_name'] == 'TestAgent'

    @pytest.mark.asyncio
    async def test_retrieve_by_uuid_not_found(self, mock_vector_indexer):
        """Test UUID retrieval when entry is not found."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=mock_vector_indexer), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            result = await retrieve_by_uuid(
                entry_id='nonexistent1234567890abcdef12345678'
            )

            assert result['ok'] is False
            assert "not found" in result['error']
            assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_retrieve_by_uuid_plugin_not_available(self):
        """Test UUID retrieval when plugin is not available."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=None), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            result = await retrieve_by_uuid(
                entry_id='test1234567890abcdef1234567890ab'
            )

            assert result['ok'] is False
            assert "not available" in result['error']

    @pytest.mark.asyncio
    async def test_vector_index_status_success(self, mock_vector_indexer):
        """Test successful index status retrieval."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=mock_vector_indexer), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            result = await vector_index_status()

            assert result['ok'] is True
            assert 'status' in result

            status = result['status']
            assert status['initialized'] is True
            assert status['enabled'] is True
            assert status['repo_slug'] == 'tmp'
            assert status['model'] == 'all-MiniLM-L6-v2'
            assert status['dimension'] == 384
            assert status['total_entries'] == 2
            assert status['queue_depth'] == 0
            assert status['queue_max'] == 1024

    @pytest.mark.asyncio
    async def test_vector_index_status_plugin_not_available(self):
        """Test index status when plugin is not available."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=None), \
             patch('scribe_mcp.tools.vector_search.server') as mock_server:

            mock_server.state_manager.record_tool.return_value = {}

            result = await vector_index_status()

            assert result['ok'] is False
            assert "not available" in result['error']


@pytest.mark.skipif(not VECTOR_DEPS_AVAILABLE, reason="Vector dependencies not available")
class TestVectorToolRegistration:
    """Test vector tool registration functionality."""

    def test_register_vector_tools_success(self):
        """Test successful tool registration when plugin is available."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer') as mock_get_indexer, \
             patch('scribe_mcp.tools.vector_search.app') as mock_app:

            # Mock available and initialized plugin
            mock_indexer = MagicMock()
            mock_indexer.initialized = True
            mock_get_indexer.return_value = mock_indexer

            result = register_vector_tools()

            assert result is True
            # Should have registered 3 tools
            assert mock_app.tool.call_count == 3

    def test_register_vector_tools_no_plugin(self):
        """Test tool registration when no plugin is available."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer', return_value=None), \
             patch('scribe_mcp.tools.vector_search.app') as mock_app, \
             patch('scribe_mcp.tools.vector_search.logging') as mock_logging:

            result = register_vector_tools()

            assert result is False
            # Should not have registered any tools
            assert mock_app.tool.call_count == 0
            mock_logging.debug.assert_called()

    def test_register_vector_tools_plugin_not_initialized(self):
        """Test tool registration when plugin is not initialized."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer') as mock_get_indexer, \
             patch('scribe_mcp.tools.vector_search.app') as mock_app, \
             patch('scribe_mcp.tools.vector_search.logging') as mock_logging:

            # Mock available but not initialized plugin
            mock_indexer = MagicMock()
            mock_indexer.initialized = False
            mock_get_indexer.return_value = mock_indexer

            result = register_vector_tools()

            assert result is False
            # Should not have registered any tools
            assert mock_app.tool.call_count == 0

    def test_register_vector_tools_with_exception(self):
        """Test tool registration handling of exceptions."""
        with patch('scribe_mcp.tools.vector_search._get_vector_indexer') as mock_get_indexer, \
             patch('scribe_mcp.tools.vector_search.app') as mock_app, \
             patch('scribe_mcp.tools.vector_search.logging') as mock_logging:

            # Mock plugin that raises exception during tool registration
            mock_indexer = MagicMock()
            mock_indexer.initialized = True
            mock_get_indexer.return_value = mock_indexer

            # Make app.tool() raise an exception
            mock_app.tool.side_effect = Exception("Registration failed")

            result = register_vector_tools()

            assert result is False
            mock_logging.warning.assert_called()

    def test_get_vector_indexer_not_initialized(self):
        """Test getting vector indexer when plugin is not initialized."""
        with patch('scribe_mcp.plugins.registry.get_plugin_registry') as mock_get_registry:
            mock_registry = MagicMock()
            mock_plugin = MagicMock()
            mock_plugin.name = "vector_indexer"
            mock_plugin.initialized = False  # Not initialized
            mock_registry.plugins.values.return_value = [mock_plugin]
            mock_get_registry.return_value = mock_registry

            result = _get_vector_indexer()

            assert result is None

    def test_get_vector_indexer_success(self):
        """Test successful vector indexer retrieval."""
        with patch('scribe_mcp.plugins.registry.get_plugin_registry') as mock_get_registry:
            mock_registry = MagicMock()
            mock_plugin = MagicMock()
            mock_plugin.name = "vector_indexer"
            mock_plugin.initialized = True  # Initialized
            mock_registry.plugins.values.return_value = [mock_plugin]
            mock_get_registry.return_value = mock_registry

            result = _get_vector_indexer()

            assert result is not None
            assert result.initialized is True


@pytest.mark.skipif(VECTOR_DEPS_AVAILABLE, reason="Test requires missing dependencies")
class TestVectorToolsWithoutDependencies:
    """Test vector tools behavior when dependencies are missing."""

    @pytest.mark.asyncio
    async def test_vector_search_no_dependencies(self):
        """Test vector search when dependencies are missing."""
        # Should not be able to register tools without dependencies
        result = register_vector_tools()
        assert result is False

    def test_get_vector_indexer_without_dependencies(self):
        """Test getting vector indexer when dependencies are missing."""
        result = _get_vector_indexer()
        assert result is None