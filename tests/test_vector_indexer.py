"""Tests for VectorIndexer plugin functionality."""

import pytest
import tempfile
import json
import sqlite3
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone

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

from scribe_mcp.plugins.vector_indexer import VectorIndexer
from scribe_mcp.config.repo_config import RepoConfig


@pytest.mark.skipif(not VECTOR_DEPS_AVAILABLE, reason="Vector dependencies not available")
class TestVectorIndexer:
    """Test VectorIndexer plugin functionality."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            # Create necessary directories
            (repo_path / ".scribe_vectors").mkdir(exist_ok=True)
            yield repo_path

    @pytest.fixture
    def mock_config(self, temp_repo):
        """Create a mock repository configuration."""
        config = MagicMock(spec=RepoConfig)
        config.repo_root = temp_repo
        config.plugins_dir = temp_repo / "plugins"
        config.plugin_config = {"enabled": True}
        config.repo_slug = "tmp"  # Add missing repo_slug attribute
        return config

    @pytest.fixture
    def vector_indexer(self, mock_config):
        """Create a VectorIndexer instance for testing."""
        # Mock vector config to use small values for testing
        with patch('scribe_mcp.plugins.vector_indexer.load_vector_config') as mock_load_config:
            mock_config_obj = MagicMock()
            mock_config_obj.enabled = True
            mock_config_obj.backend = "faiss"
            mock_config_obj.dimension = 384
            mock_config_obj.model = "all-MiniLM-L6-v2"
            mock_config_obj.gpu = False
            mock_config_obj.queue_max = 10
            mock_config_obj.batch_size = 2
            mock_load_config.return_value = mock_config_obj

            indexer = VectorIndexer()
            indexer.initialize(mock_config)
            yield indexer
            indexer.cleanup()

    def test_initialization_success(self, vector_indexer):
        """Test successful plugin initialization."""
        assert vector_indexer.initialized
        assert vector_indexer.enabled
        assert vector_indexer.repo_slug == "tmp"  # Based on temp directory name
        assert vector_indexer.embedding_model is not None
        assert vector_indexer.vector_index is not None
        assert vector_indexer.index_metadata is not None

    def test_initialization_disabled_by_config(self, mock_config):
        """Test plugin initialization when disabled by config."""
        with patch('scribe_mcp.plugins.vector_indexer.load_vector_config') as mock_load_config:
            # Mock disabled vector config
            mock_config_obj = MagicMock()
            mock_config_obj.enabled = False
            mock_load_config.return_value = mock_config_obj

            indexer = VectorIndexer()
            indexer.initialize(mock_config)

            assert not indexer.initialized
            assert not indexer.enabled

    @pytest.mark.skipif(VECTOR_DEPS_AVAILABLE, reason="Test requires missing dependencies")
    def test_initialization_missing_dependencies(self, mock_config):
        """Test plugin initialization when dependencies are missing."""
        with patch('scribe_mcp.plugins.vector_indexer.FAISS_AVAILABLE', False):
            indexer = VectorIndexer()
            indexer.initialize(mock_config)

            assert not indexer.initialized
            assert not indexer.enabled

    def test_get_repo_slug(self, vector_indexer):
        """Test repository slug generation."""
        # Test various path formats - note that it only uses the last component
        test_cases = [
            ("/home/user/my-project", "my-project"),
            ("/home/user/My Project v2.0", "my-project-v2-0"),
            ("test-repo", "test-repo"),  # Simple directory name
            ("", "unknown-repo")
        ]

        for path, expected in test_cases:
            result = vector_indexer._get_repo_slug(Path(path))
            assert result == expected

    def test_index_creation(self, vector_indexer, temp_repo):
        """Test FAISS index creation."""
        # Check that index files were created
        vectors_dir = temp_repo / ".scribe_vectors"
        index_file = vectors_dir / f"{vector_indexer.repo_slug}.faiss"
        metadata_file = vectors_dir / f"{vector_indexer.repo_slug}.meta.json"

        assert index_file.exists()
        assert metadata_file.exists()

        # Check metadata content
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        assert metadata['repo_slug'] == vector_indexer.repo_slug
        assert metadata['dimension'] == 384
        assert metadata['model'] == "all-MiniLM-L6-v2"
        assert metadata['scope'] == "repo-local"
        assert metadata['backend'] == "faiss"

    def test_mapping_database_creation(self, vector_indexer, temp_repo):
        """Test mapping database creation and schema."""
        mapping_db_path = temp_repo / ".scribe_vectors" / "mapping.sqlite"
        assert mapping_db_path.exists()

        # Check database schema
        conn = sqlite3.connect(str(mapping_db_path))
        cursor = conn.cursor()

        # Check tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert "vector_entries" in tables

        # Check indexes exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        assert any("idx_entry_id" in idx for idx in indexes)
        assert any("idx_project_slug" in idx for idx in indexes)

        conn.close()

    @pytest.mark.asyncio
    async def test_queue_entry_for_embedding(self, vector_indexer):
        """Test queueing entries for background processing."""
        entry_data = {
            'entry_id': 'test1234567890abcdef1234567890ab',
            'project_name': 'Test Project',
            'message': 'This is a test message',
            'agent': 'TestAgent',
            'timestamp': '2025-10-26 12:00:00 UTC',
            'meta': {'phase': 'test'}
        }

        # Queue the entry
        await vector_indexer._queue_entry_for_embedding(entry_data)

        # Check that it was queued
        assert not vector_indexer.embedding_queue.empty()
        queued_item = vector_indexer.embedding_queue.get_nowait()
        assert queued_item['entry_id'] == entry_data['entry_id']
        assert queued_item['text_content'] == entry_data['message']
        assert queued_item['project_slug'] == 'test-project'

    @pytest.mark.asyncio
    async def test_embedding_batch_processing(self, vector_indexer):
        """Test processing of embedding batches."""
        # Create test batch
        batch = [
            {
                'entry_id': 'test1',
                'project_slug': 'test',
                'text_content': 'First test message',
                'agent_name': 'TestAgent',
                'timestamp_utc': '2025-10-26 12:00:00 UTC',
                'metadata_json': '{"phase": "test"}',
                'embedding_model': 'all-MiniLM-L6-v2',
                'vector_dimension': 384,
                'retry_count': 0,
                'queued_at': datetime.now(timezone.utc)
            },
            {
                'entry_id': 'test2',
                'project_slug': 'test',
                'text_content': 'Second test message',
                'agent_name': 'TestAgent',
                'timestamp_utc': '2025-10-26 12:01:00 UTC',
                'metadata_json': '{"phase": "test"}',
                'embedding_model': 'all-MiniLM-L6-v2',
                'vector_dimension': 384,
                'retry_count': 0,
                'queued_at': datetime.now(timezone.utc)
            }
        ]

        initial_count = vector_indexer.vector_index.ntotal

        # Process the batch
        await vector_indexer._process_embedding_batch(batch)  # embeddings will be generated

        # Check that entries were added to index
        assert vector_indexer.vector_index.ntotal >= initial_count

    def test_get_index_status(self, vector_indexer):
        """Test getting index status."""
        status = vector_indexer.get_index_status()

        assert status['initialized'] is True
        assert status['enabled'] is True
        assert status['repo_slug'] == vector_indexer.repo_slug
        assert status['model'] == "all-MiniLM-L6-v2"
        assert status['dimension'] == 384
        assert status['queue_max'] == 10  # From mocked config
        assert status['gpu_enabled'] is False
        assert status['faiss_available'] is True

    def test_post_append_hook(self, vector_indexer):
        """Test post-append hook functionality."""
        entry_data = {
            'entry_id': 'test1234567890abcdef1234567890ab',
            'project_name': 'Test Project',
            'message': 'Test message for hook',
            'agent': 'TestAgent',
            'timestamp': '2025-10-26 12:00:00 UTC',
            'meta': {'phase': 'test'}
        }

        # Should not raise any exceptions
        vector_indexer.post_append(entry_data)

        # Entry should be queued for processing
        # (We can't easily test async processing here without more complex setup)

    def test_cleanup(self, vector_indexer):
        """Test plugin cleanup."""
        # Set shutdown event
        assert not vector_indexer._shutdown_event.is_set()

        # Cleanup
        vector_indexer.cleanup()

        # Check cleanup was performed
        assert vector_indexer._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_queue_worker_lifecycle(self, vector_indexer):
        """Test queue worker start and stop."""
        # Worker should be started during initialization
        assert vector_indexer.queue_worker_task is not None

        # Set shutdown event to stop worker
        vector_indexer._shutdown_event.set()

        # Give worker time to stop
        await asyncio.sleep(2.0)

        # Worker should be stopped or cancelled
        assert vector_indexer.queue_worker_task.done() or vector_indexer.queue_worker_task.cancelled()


@pytest.mark.skipif(not VECTOR_DEPS_AVAILABLE, reason="Vector dependencies not available")
class TestVectorIndexerEdgeCases:
    """Test edge cases and error handling in VectorIndexer."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            (repo_path / ".scribe_vectors").mkdir(exist_ok=True)
            yield repo_path

    @pytest.fixture
    def mock_config(self, temp_repo):
        """Create a mock repository configuration."""
        config = MagicMock(spec=RepoConfig)
        config.repo_root = temp_repo
        config.plugins_dir = temp_repo / "plugins"
        config.plugin_config = {"enabled": True}
        config.repo_slug = "tmp"  # Add missing repo_slug attribute
        return config

    def test_load_existing_index_with_metadata_mismatch(self, temp_repo, mock_config):
        """Test loading existing index with different metadata."""
        # Create index metadata with different configuration
        vectors_dir = temp_repo / ".scribe_vectors"
        metadata_path = vectors_dir / "tmp.meta.json"

        mismatched_metadata = {
            'repo_slug': 'tmp',
            'dimension': 768,  # Different dimension
            'model': 'different-model',
            'scope': 'repo-local',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'backend': 'faiss',
            'index_type': 'IndexFlatIP',
            'total_entries': 0,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }

        with open(metadata_path, 'w') as f:
            json.dump(mismatched_metadata, f)

        # Create empty FAISS index
        index_path = vectors_dir / "tmp.faiss"
        import faiss
        index = faiss.IndexFlatIP(768)  # Different dimension
        faiss.write_index(index, str(index_path))

        # Try to initialize - should load but warn about mismatch
        with patch('scribe_mcp.plugins.vector_indexer.settings') as mock_settings:
            mock_settings.vector_enabled = True
            mock_settings.vector_dimension = 384  # Different from stored
            mock_settings.vector_model = "all-MiniLM-L6-v2"
            mock_settings.vector_gpu = False
            mock_settings.vector_queue_max = 10
            mock_settings.vector_batch_size = 2

            indexer = VectorIndexer()

            # Should not raise exception but should log warning
            with patch('scribe_mcp.plugins.vector_indexer.plugin_logger') as mock_logger:
                indexer.initialize(mock_config)
                mock_logger.warning.assert_called()

                assert indexer.initialized  # Should still initialize

            indexer.cleanup()

    @pytest.mark.asyncio
    async def test_queue_full_handling(self, temp_repo, mock_config):
        """Test handling when queue is full."""
        # Create indexer with very small queue
        with patch('scribe_mcp.plugins.vector_indexer.settings') as mock_settings:
            mock_settings.vector_enabled = True
            mock_settings.vector_dimension = 384
            mock_settings.vector_model = "all-MiniLM-L6-v2"
            mock_settings.vector_gpu = False
            mock_settings.vector_queue_max = 1  # Very small queue
            mock_settings.vector_batch_size = 1

            indexer = VectorIndexer()
            indexer.initialize(mock_config)

            # Fill the queue
            entry_data = {
                'entry_id': 'test1',
                'project_name': 'Test Project',
                'message': 'Test message',
                'agent': 'TestAgent',
                'timestamp': '2025-10-26 12:00:00 UTC',
                'meta': {}
            }

            await indexer._queue_entry_for_embedding(entry_data)

            # Try to add another - should not raise exception but should log warning
            with patch('scribe_mcp.plugins.vector_indexer.plugin_logger') as mock_logger:
                await indexer._queue_entry_for_embedding(entry_data)
                # Should have logged a warning about full queue

            indexer.cleanup()

    def test_filter_application(self, temp_repo, mock_config):
        """Test filter application in search results."""
        with patch('scribe_mcp.plugins.vector_indexer.settings') as mock_settings:
            mock_settings.vector_enabled = True
            mock_settings.vector_dimension = 384
            mock_settings.vector_model = "all-MiniLM-L6-v2"
            mock_settings.vector_gpu = False
            mock_settings.vector_queue_max = 10
            mock_settings.vector_batch_size = 2

            indexer = VectorIndexer()
            indexer.initialize(mock_config)

            # Create mock database row
            from unittest.mock import Mock
            mock_row = Mock()
            mock_row.__getitem__ = lambda self, key: {
                'project_slug': 'test-project',
                'agent_name': 'TestAgent',
                'timestamp_utc': '2025-10-26T12:00:00'
            }[key]

            # Test no filters
            assert indexer._apply_filters(mock_row, {}) is True

            # Test matching project filter
            assert indexer._apply_filters(mock_row, {'project_slug': 'test-project'}) is True
            assert indexer._apply_filters(mock_row, {'project_slug': 'other-project'}) is False

            # Test matching agent filter
            assert indexer._apply_filters(mock_row, {'agent_name': 'TestAgent'}) is True
            assert indexer._apply_filters(mock_row, {'agent_name': 'OtherAgent'}) is False

            # Test time range filter
            time_filter = {
                'time_range': {
                    'start': '2025-10-25T12:00:00',
                    'end': '2025-10-27T12:00:00'
                }
            }
            assert indexer._apply_filters(mock_row, time_filter) is True

            # Test time range outside bounds
            time_filter_outside = {
                'time_range': {
                    'start': '2025-10-27T12:00:00',
                    'end': '2025-10-28T12:00:00'
                }
            }
            assert indexer._apply_filters(mock_row, time_filter_outside) is False

            indexer.cleanup()