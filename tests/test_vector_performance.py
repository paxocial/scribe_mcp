"""Performance tests for vector indexing functionality."""

import pytest
import tempfile
import time
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

# Try to import vector dependencies - if not available, tests will be skipped
try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    import psutil
    VECTOR_DEPS_AVAILABLE = True
except ImportError:
    VECTOR_DEPS_AVAILABLE = False
    faiss = None
    np = None
    SentenceTransformer = None
    psutil = None

from scribe_mcp.plugins.vector_indexer import VectorIndexer
from scribe_mcp.config.repo_config import RepoConfig


@pytest.mark.skipif(not VECTOR_DEPS_AVAILABLE, reason="Vector dependencies not available")
@pytest.mark.performance
class TestVectorPerformance:
    """Performance tests for vector indexing system."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            (repo_path / ".scribe_vectors").mkdir(exist_ok=True)
            yield repo_path

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings optimized for testing."""
        settings = MagicMock()
        settings.vector_enabled = True
        settings.vector_backend = "faiss"
        settings.vector_dimension = 384
        settings.vector_model = "all-MiniLM-L6-v2"
        settings.vector_gpu = False
        settings.vector_queue_max = 1000
        settings.vector_batch_size = 32
        return settings

    def test_embedding_generation_performance(self, temp_repo, mock_settings):
        """Test embedding generation performance."""
        with patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings):
            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo
            config.plugins_dir = temp_repo / "plugins"
            config.plugin_config = {"enabled": True}

            indexer = VectorIndexer()
            indexer.initialize(config)

            # Test batch embedding generation
            test_texts = [
                "This is a test message about software development",
                "Database optimization and performance tuning strategies",
                "User interface design principles and best practices",
                "Machine learning algorithms and model training",
                "Cloud infrastructure deployment and management",
                "Security considerations and threat mitigation",
                "API design and RESTful service architecture",
                "Frontend development with modern frameworks",
                "Backend services and microservices patterns",
                "DevOps practices and continuous integration"
            ] * 10  # 100 texts total

            start_time = time.time()

            # Generate embeddings
            embeddings = indexer.embedding_model.encode(
                test_texts,
                batch_size=32,
                convert_to_numpy=True
            )

            end_time = time.time()
            generation_time = end_time - start_time

            # Performance assertions
            assert generation_time < 30.0  # Should complete within 30 seconds
            assert len(embeddings) == len(test_texts)
            assert embeddings.shape[1] == 384  # Correct dimension

            print(f"Generated {len(embeddings)} embeddings in {generation_time:.2f}s")
            print(f"Rate: {len(embeddings)/generation_time:.2f} embeddings/second")

            indexer.cleanup()

    def test_index_creation_and_search_performance(self, temp_repo, mock_settings):
        """Test index creation and search performance."""
        with patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings):
            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo
            config.plugins_dir = temp_repo / "plugins"
            config.plugin_config = {"enabled": True}

            indexer = VectorIndexer()
            indexer.initialize(config)

            # Create test embeddings
            num_entries = 1000
            test_texts = [
                f"Test entry {i} with unique content for performance testing"
                for i in range(num_entries)
            ]

            # Generate embeddings
            embeddings = indexer.embedding_model.encode(
                test_texts,
                batch_size=64,
                convert_to_numpy=True
            )

            # Normalize embeddings
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

            # Measure index creation time
            start_time = time.time()
            indexer.vector_index.add(embeddings)
            creation_time = time.time() - start_time

            print(f"Added {num_entries} entries to index in {creation_time:.2f}s")
            print(f"Rate: {num_entries/creation_time:.2f} entries/second")

            # Measure search performance
            queries = [
                "software development and programming",
                "database performance optimization",
                "user interface design",
                "machine learning models",
                "cloud infrastructure management"
            ]

            search_times = []
            for query in queries:
                start_time = time.time()
                query_embedding = indexer.embedding_model.encode([query])
                query_embedding = query_embedding / np.linalg.norm(query_embedding, axis=1, keepdims=True)

                distances, rowids = indexer.vector_index.search(query_embedding, k=10)
                search_time = time.time() - start_time
                search_times.append(search_time)

            avg_search_time = sum(search_times) / len(search_times)
            max_search_time = max(search_times)

            print(f"Average search time: {avg_search_time*1000:.2f}ms")
            print(f"Max search time: {max_search_time*1000:.2f}ms")

            # Performance assertions
            assert creation_time < 60.0  # Index creation within 60 seconds
            assert avg_search_time < 0.1  # Average search under 100ms
            assert max_search_time < 0.5  # Max search under 500ms

            indexer.cleanup()

    @pytest.mark.asyncio
    async def test_background_queue_performance(self, temp_repo, mock_settings):
        """Test background queue processing performance."""
        with patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings):
            # Optimize settings for performance testing
            mock_settings.vector_batch_size = 64
            mock_settings.vector_queue_max = 2000

            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo
            config.plugins_dir = temp_repo / "plugins"
            config.plugin_config = {"enabled": True}

            indexer = VectorIndexer()
            indexer.initialize(config)

            # Create many entries for queue testing
            num_entries = 500
            entries = []

            for i in range(num_entries):
                entry = {
                    'entry_id': f'perf{i:04d}' + 'a' * 24,
                    'project_name': 'Performance Test',
                    'message': f'Performance test entry {i} with comprehensive content for embedding',
                    'agent_name': 'PerfAgent',
                    'timestamp_utc': f'2025-10-26 12:{i%60:02d}:00 UTC',
                    'metadata_json': f'{{"index": {i}, "batch": {i//100}}}',
                    'embedding_model': 'all-MiniLM-L6-v2',
                    'vector_dimension': 384,
                    'retry_count': 0,
                    'queued_at': None
                }
                entries.append(entry)

            # Measure queueing performance
            start_time = time.time()
            for entry in entries:
                await indexer._queue_entry_for_embedding(entry)
            queue_time = time.time() - start_time

            print(f"Queued {num_entries} entries in {queue_time:.2f}s")
            print(f"Queue rate: {num_entries/queue_time:.2f} entries/second")

            # Wait for processing
            initial_queue_depth = indexer.embedding_queue.qsize()
            print(f"Initial queue depth: {initial_queue_depth}")

            max_wait = 120  # 2 minutes max
            wait_time = 0
            while (indexer.embedding_queue and
                   not indexer.embedding_queue.empty() and
                   wait_time < max_wait):
                await asyncio.sleep(1)
                wait_time += 1

            final_status = indexer.get_index_status()
            print(f"Processing completed in {wait_time}s")
            print(f"Final queue depth: {final_status['queue_depth']}")
            print(f"Total entries processed: {final_status['total_entries']}")

            # Performance assertions
            assert queue_time < 10.0  # Queueing should be fast
            assert wait_time < 120.0  # Processing should complete in reasonable time

            indexer.cleanup()

    def test_memory_usage_performance(self, temp_repo, mock_settings):
        """Test memory usage during vector operations."""
        if not psutil:
            pytest.skip("psutil not available for memory testing")

        with patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings):
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB

            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo
            config.plugins_dir = temp_repo / "plugins"
            config.plugin_config = {"enabled": True}

            indexer = VectorIndexer()
            indexer.initialize(config)

            after_init_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Create a large number of entries
            num_entries = 2000
            test_texts = [
                f"Comprehensive test entry {i} with substantial content for memory testing"
                for i in range(num_entries)
            ]

            # Generate embeddings
            embeddings = indexer.embedding_model.encode(
                test_texts,
                batch_size=128,
                convert_to_numpy=True
            )

            after_embeddings_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Add to index
            indexer.vector_index.add(embeddings)

            after_index_memory = process.memory_info().rss / 1024 / 1024  # MB

            print(f"Memory usage:")
            print(f"  Initial: {initial_memory:.2f} MB")
            print(f"  After init: {after_init_memory:.2f} MB (+{after_init_memory-initial_memory:.2f} MB)")
            print(f"  After embeddings: {after_embeddings_memory:.2f} MB (+{after_embeddings_memory-after_init_memory:.2f} MB)")
            print(f"  After index: {after_index_memory:.2f} MB (+{after_index_memory-after_embeddings_memory:.2f} MB)")
            print(f"  Total increase: {after_index_memory-initial_memory:.2f} MB")
            print(f"  Memory per entry: {(after_index_memory-initial_memory)/num_entries:.4f} MB")

            # Memory usage assertions
            memory_per_entry = (after_index_memory - initial_memory) / num_entries
            assert memory_per_entry < 0.01  # Less than 10KB per entry
            assert after_index_memory < initial_memory + 500  # Total increase less than 500MB

            indexer.cleanup()

    def test_concurrent_search_performance(self, temp_repo, mock_settings):
        """Test concurrent search performance."""
        with patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings):
            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo
            config.plugins_dir = temp_repo / "plugins"
            config.plugin_config = {"enabled": True}

            indexer = VectorIndexer()
            indexer.initialize(config)

            # Add test data
            num_entries = 500
            test_texts = [
                f"Test entry {i} for concurrent search performance testing"
                for i in range(num_entries)
            ]

            embeddings = indexer.embedding_model.encode(
                test_texts,
                batch_size=64,
                convert_to_numpy=True
            )
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
            indexer.vector_index.add(embeddings)

            # Test concurrent searches
            import threading
            import concurrent.futures

            def perform_search(search_id):
                query = f"concurrent test query {search_id}"
                query_embedding = indexer.embedding_model.encode([query])
                query_embedding = query_embedding / np.linalg.norm(query_embedding, axis=1, keepdims=True)

                start_time = time.time()
                distances, rowids = indexer.vector_index.search(query_embedding, k=5)
                end_time = time.time()

                return end_time - start_time, len(rowids[0])

            # Run concurrent searches
            num_searches = 50
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(perform_search, i) for i in range(num_searches)]
                results = [future.result() for future in concurrent.futures.as_completed(futures)]

            search_times = [result[0] for result in results]
            result_counts = [result[1] for result in results]

            avg_search_time = sum(search_times) / len(search_times)
            max_search_time = max(search_times)
            min_search_time = min(search_times)

            print(f"Concurrent search performance ({num_searches} searches):")
            print(f"  Average time: {avg_search_time*1000:.2f}ms")
            print(f"  Max time: {max_search_time*1000:.2f}ms")
            print(f"  Min time: {min_search_time*1000:.2f}ms")
            print(f"  Total throughput: {num_searches/sum(search_times):.2f} searches/second")

            # Performance assertions
            assert avg_search_time < 0.1  # Average under 100ms
            assert max_search_time < 0.5  # Max under 500ms
            assert all(count == 5 for count in result_counts)  # All searches returned results

            indexer.cleanup()

    def test_index_size_performance(self, temp_repo, mock_settings):
        """Test index file size and I/O performance."""
        with patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings):
            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo
            config.plugins_dir = temp_repo / "plugins"
            config.plugin_config = {"enabled": True}

            indexer = VectorIndexer()
            indexer.initialize(config)

            vectors_dir = temp_repo / ".scribe_vectors"
            initial_index_size = (vectors_dir / f"{indexer.repo_slug}.faiss").stat().st_size

            # Add entries
            num_entries = 1000
            test_texts = [
                f"Index size test entry {i} with content for size analysis"
                for i in range(num_entries)
            ]

            embeddings = indexer.embedding_model.encode(
                test_texts,
                batch_size=128,
                convert_to_numpy=True
            )
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

            # Measure add time
            start_time = time.time()
            indexer.vector_index.add(embeddings)
            add_time = time.time() - start_time

            # Measure save time
            start_time = time.time()
            index_path = vectors_dir / f"{indexer.repo_slug}.faiss"
            faiss.write_index(indexer.vector_index, str(index_path))
            save_time = time.time() - start_time

            # Measure load time
            start_time = time.time()
            loaded_index = faiss.read_index(str(index_path))
            load_time = time.time() - start_time

            final_index_size = index_path.stat().st_size
            size_per_entry = (final_index_size - initial_index_size) / num_entries

            print(f"Index size performance ({num_entries} entries):")
            print(f"  Initial size: {initial_index_size:,} bytes")
            print(f"  Final size: {final_index_size:,} bytes")
            print(f"  Size increase: {final_index_size - initial_index_size:,} bytes")
            print(f"  Size per entry: {size_per_entry:.2f} bytes")
            print(f"  Add time: {add_time:.3f}s ({num_entries/add_time:.0f} entries/s)")
            print(f"  Save time: {save_time:.3f}s")
            print(f"  Load time: {load_time:.3f}s")

            # Performance assertions
            assert size_per_entry < 2000  # Less than 2KB per entry
            assert add_time < 30.0  # Add within 30 seconds
            assert save_time < 5.0  # Save within 5 seconds
            assert load_time < 5.0  # Load within 5 seconds

            indexer.cleanup()


@pytest.mark.skipif(not VECTOR_DEPS_AVAILABLE, reason="Vector dependencies not available")
class TestVectorScalability:
    """Scalability tests for vector indexing system."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            (repo_path / ".scribe_vectors").mkdir(exist_ok=True)
            yield repo_path

    def test_large_index_scalability(self, temp_repo):
        """Test scalability with large index sizes."""
        with patch('scribe_mcp.plugins.vector_indexer.settings') as mock_settings:
            mock_settings.vector_enabled = True
            mock_settings.vector_dimension = 384
            mock_settings.vector_model = "all-MiniLM-L6-v2"
            mock_settings.vector_gpu = False
            mock_settings.vector_queue_max = 10000
            mock_settings.vector_batch_size = 128

            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo
            config.plugins_dir = temp_repo / "plugins"
            config.plugin_config = {"enabled": True}

            indexer = VectorIndexer()
            indexer.initialize(config)

            # Test with progressively larger indexes
            test_sizes = [100, 500, 1000, 2000]

            for size in test_sizes:
                print(f"\nTesting with {size} entries:")

                # Generate test data
                test_texts = [
                    f"Scalability test entry {i} with comprehensive content"
                    for i in range(size)
                ]

                # Measure embedding generation
                start_time = time.time()
                embeddings = indexer.embedding_model.encode(
                    test_texts,
                    batch_size=128,
                    convert_to_numpy=True
                )
                embedding_time = time.time() - start_time

                # Measure index addition
                start_time = time.time()
                indexer.vector_index.add(embeddings)
                add_time = time.time() - start_time

                # Measure search performance
                start_time = time.time()
                query_embedding = indexer.embedding_model.encode(["scalability test"])
                query_embedding = query_embedding / np.linalg.norm(query_embedding, axis=1, keepdims=True)
                distances, rowids = indexer.vector_index.search(query_embedding, k=10)
                search_time = time.time() - start_time

                print(f"  Embedding generation: {embedding_time:.2f}s ({size/embedding_time:.0f} entries/s)")
                print(f"  Index addition: {add_time:.2f}s ({size/add_time:.0f} entries/s)")
                print(f"  Search time: {search_time*1000:.2f}ms")
                print(f"  Total entries: {indexer.vector_index.ntotal}")

                # Scalability assertions
                assert embedding_time < size * 0.01  # Less than 10ms per entry
                assert search_time < 0.1  # Search should remain fast regardless of size

            indexer.cleanup()