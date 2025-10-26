
# 🏗️ Architecture Guide — SCRIBE VECTOR INDEX (FAISS INTEGRATION)
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2025-10-26 12:03:59 UTC

> Architecture guide for SCRIBE VECTOR INDEX (FAISS INTEGRATION).

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## Problem Statement

The Scribe MCP system currently provides excellent chronological logging and metadata-driven documentation, but lacks semantic search capabilities. As repositories accumulate hundreds or thousands of log entries across multiple projects, finding relevant entries becomes challenging:

- **Linear Search Limitations**: Users can only search by time ranges or simple text matching, missing semantic relationships
- **Context Discovery**: No way to find entries about similar concepts using different terminology  
- **Cross-Project Insights**: Difficult to identify patterns across different dev_plans within the same repository
- **Knowledge Retrieval**: No efficient way to find related decisions, bugs, or solutions based on meaning rather than keywords

## Solution Overview

Implement **repo-scoped vector indexing** for Scribe entries using FAISS (Facebook AI Similarity Search) with the following key characteristics:

- **Semantic Search**: Enable meaning-based search across all log entries
- **UUID-Addressable Entries**: Each entry gets a stable, deterministic ID for direct retrieval
- **Repository Isolation**: Each repository maintains its own vector shard, ensuring no cross-repo leakage
- **Background Processing**: Non-blocking embedding generation with async queue management
- **Plugin Architecture**: Modular design that can be extended or disabled independently

**Key Innovation**: Transform the chronological PROGRESS_LOG.md from a simple timeline into a semantically searchable knowledge base while maintaining all existing functionality.

## Architecture Integration

The implementation leverages Scribe's existing sophisticated **HookPlugin system** for seamless integration:

- **Post-Append Hook**: Automatically indexes new log entries without blocking append operations
- **Plugin Registry**: Secure loading with hash verification and sandbox enforcement
- **Storage Abstraction**: Works with both SQLite and PostgreSQL backends
- **Configuration System**: Integrates with existing environment variable patterns
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
- Atomic document updates- Jinja2 templates with inheritance
- **Non-Functional Requirements:**
- Backwards-compatible file layout- Sandboxed template rendering
- **Assumptions:**
- Filesystem read/write access- Python runtime available
- **Risks & Mitigations:**
- User edits outside manage_docs- Template misuse causing errors


---
## 3. Architecture Overview
<!-- ID: architecture_overview -->
## Architecture Overview

### Vector Index Plugin Architecture

The vector indexing system is implemented as a **HookPlugin** that integrates seamlessly with Scribe's existing plugin architecture:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   append_entry  │───▶│  VectorIndexer   │───▶│  Background     │
│   (existing)    │    │  HookPlugin      │    │  Queue Worker   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │                        │
                              ▼                        ▼
                       ┌──────────────┐         ┌──────────────┐
                       │ Entry UUID   │         │ FAISS Index  │
                       │ Generation   │         │ + Embeddings │
                       └──────────────┘         └──────────────┘
```

### Core Components

**Solution Summary:** Add semantic search capabilities to Scribe through a non-blocking vector indexing plugin that maintains repository isolation and provides UUID-addressable entries.

**Component Breakdown:**
- **VectorIndexer HookPlugin:** 
  - Interfaces: HookPlugin base class, MCP tool registry
  - Purpose: Automatic post-append indexing and semantic search
  - Notes: Background processing with asyncio queue, per-repo FAISS shards

- **Storage Extensions:**
  - Interfaces: SQLite backend, FAISS index files
  - Purpose: Vector metadata storage and similarity search
  - Notes: Sidecar mapping DB for UUID ↔ vector rowid relationships

- **MCP Tools:**
  - Interfaces: @app.tool() decorator pattern
  - Purpose: vector_search, retrieve_by_uuid, index_status, rebuild_index
  - Notes: Follow existing tool patterns with proper error handling

**Data Flow:** 
1. User creates log entry via append_entry
2. HookPlugin.post_append() queues entry for background processing  
3. Background worker generates embeddings and updates FAISS index
4. Vector search tools provide semantic query capabilities

**External Integrations:** 
- sentence-transformers for embeddings
- FAISS for vector similarity search
- NumPy for vector operations
<!-- ID: detailed_design -->
## Detailed Design

### 1. Vector Index Pipeline

**Purpose:** Coordinate non-blocking embedding generation and index updates.

**Implementation Details:**
- **AsyncIO Queue:** Bounded queue (configurable maxsize, default 1024) for embedding tasks
- **Background Worker:** Single worker per repository with FAISS write locking
- **Batch Processing:** Configurable batch sizes (default 32) for embedding efficiency
- **Error Recovery:** Failed entries queued for retry with exponential backoff

**Error Handling:** 
- Graceful degradation when vector dependencies unavailable
- Retry queue for temporary failures (model loading, disk space)
- Fallback to traditional search when index unavailable

### 2. FAISS Storage System

**Purpose:** Manage per-repository vector indexes with atomic operations.

**Implementation Details:**
- **Repository Isolation:** Each repo gets separate FAISS shard in `.scribe_vectors/`
- **Index Type:** `IndexFlatIP` with L2-normalized vectors (cosine similarity)
- **Metadata Storage:** JSON file with dimension, model, creation timestamp
- **Atomic Updates:** Write to temp file, fsync, then rename for consistency

**File Structure:**
```
.scribe_vectors/
├── <repo_slug>.faiss        # Main FAISS index
├── <repo_slug>.meta.json    # Index metadata (dim, model, created_at)
└── mapping.sqlite           # UUID ↔ rowid/text/metadata mapping
```

### 3. Deterministic Entry ID System

**Purpose:** Generate stable, reproducible UUIDs for each log entry.

**Algorithm:** `sha256(repo_slug|project_slug|timestamp|agent|message|meta_sha)[:32]`

**Integration Points:**
- Added to markdown log line for visibility
- Stored in database entry record
- Used as primary key in vector mapping database
- Remains constant across index rebuilds

### 4. MCP Tool Interfaces

**Purpose:** Provide semantic search and retrieval capabilities.

**Tool Specifications:**
- **vector_search(query, k=10, filters):** Semantic similarity with optional filters
- **retrieve_by_uuid(entry_id):** Direct entry lookup by UUID
- **vector_index_status():** Index health, queue depth, configuration info
- **rebuild_vector_index(dimension, model):** Complete index rebuilding

**Interface Patterns:** Follow existing Scribe tool patterns with proper error handling, structured responses, and integration with reminder system.
<!-- ID: directory_structure -->
```
/home/austin/projects/MCP_SPINE/scribe_mcp/docs/dev_plans/scribe_vector_index__faiss_integration
```
> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.


---
## 6. Data & Storage
<!-- ID: data_storage -->
## Data & Storage

### Datastores

**Primary Storage:**
- **Filesystem Markdown:** Existing PROGRESS_LOG.md files (unchanged)
- **SQLite Mirror:** Existing Scribe database with entry records (extended)
- **Vector Index Files:** New FAISS indexes stored per repository
- **Mapping Database:** Sidecar SQLite for UUID ↔ vector relationships

### Vector Index Storage Schema

**Mapping SQLite Database (.scribe_vectors/mapping.sqlite):**
```sql
CREATE TABLE vector_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT UNIQUE NOT NULL,           -- Deterministic UUID
    project_slug TEXT NOT NULL,              -- Project identifier
    repo_slug TEXT NOT NULL,                  -- Repository identifier
    vector_rowid INTEGER NOT NULL,           -- Row in FAISS index
    text_content TEXT NOT NULL,               -- Original message text
    agent_name TEXT,                          -- Entry author
    timestamp_utc TEXT NOT NULL,              -- Entry timestamp
    metadata_json TEXT,                       -- Entry metadata
    embedding_model TEXT,                     -- Model used for embedding
    vector_dimension INTEGER,                 -- Vector dimension
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_entry_id ON vector_entries(entry_id);
CREATE INDEX idx_project_slug ON vector_entries(project_slug);
CREATE INDEX idx_timestamp ON vector_entries(timestamp_utc);
```

### Indexes & Performance

**FAISS Configuration:**
- **Index Type:** IndexFlatIP (flat search with inner product)
- **Vector Type:** float32, L2-normalized for cosine similarity
- **Dimensions:** Configurable (default 384 for all-MiniLM-L6-v2)
- **Storage:** Disk-backed with memory caching for frequently accessed vectors

**Performance Optimizations:**
- **Batch Embedding:** Process multiple entries together (configurable batch size)
- **Async Operations:** All vector processing in background, never blocks UI
- **Memory Management:** LRU cache for embeddings, periodic cleanup
- **Atomic Updates:** Index updates use write-temp-rename pattern

### Configuration Schema

**Index Metadata (.scribe_vectors/<repo_slug>.meta.json):**
```json
{
  "dimension": 384,
  "model": "all-MiniLM-L6-v2",
  "scope": "repo-local",
  "created_at": "2025-10-26T12:00:00Z",
  "backend": "faiss",
  "index_type": "IndexFlatIP",
  "total_entries": 1250,
  "last_updated": "2025-10-26T12:15:00Z",
  "embedding_model_version": "2.2.0"
}
```
<!-- ID: testing_strategy -->
## Testing & Validation Strategy

### Unit Tests

**Vector Index Plugin Tests:**
- HookPlugin initialization and configuration
- Deterministic UUID generation algorithm
- Background queue processing and error handling
- FAISS index creation, loading, and updates
- Embedding generation with various models

**Storage Layer Tests:**
- Vector mapping database operations
- FAISS file I/O and atomic updates
- Metadata file creation and validation
- Repository isolation verification

**MCP Tool Tests:**
- vector_search with various queries and filters
- retrieve_by_uuid for valid/invalid UUIDs
- vector_index_status reporting accuracy
- rebuild_vector_index with different dimensions/models

### Integration Tests

**End-to-End Workflow:**
1. append_entry → background indexing → vector search → result retrieval
2. Bulk entry processing with queue depth management
3. Index rebuilding with model/dimension changes
4. Cross-project search isolation verification

**Performance Tests:**
- Large index handling (10K+ entries)
- Memory usage under sustained load
- Search latency across different index sizes
- Concurrent append and search operations

**Error Scenarios:**
- Missing dependencies (FAISS, sentence-transformers)
- Corrupted index files and recovery
- Disk space exhaustion during indexing
- Model loading failures and fallback behavior

### Manual QA

**Feature Validation:**
- Semantic search quality assessment
- UUID consistency across index rebuilds
- Background processing non-interference testing
- Configuration option validation

**Multi-Repository Testing:**
- Verify no cross-repo vector leakage
- Confirm repository-specific index isolation
- Test with multiple projects per repository

### Observability

**Structured Logging:**
- All vector operations logged via existing Scribe logging
- Index performance metrics collection
- Error tracking and recovery monitoring
- Background queue depth and processing rates

**Health Monitoring:**
- Index integrity verification
- Model loading status tracking
- Storage usage monitoring
- Performance benchmarking capabilities
<!-- ID: deployment_operations -->
- **Environments:** Local development
- **Release Process:** Git commits drive deployment
- **Configuration Management:** Project-specific .scribe settings
- **Maintenance & Ownership:** Doc management team


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should templates support conditionals per phase? | Docs Lead | TODO | Evaluate after initial rollout. |
Close each question once answered and reference the relevant section above.


---
## 10. References & Appendix
<!-- ID: references_appendix -->
- PROGRESS_LOG.md- ARCHITECTURE_GUIDE.md
Generated via generate_doc_templates.


---