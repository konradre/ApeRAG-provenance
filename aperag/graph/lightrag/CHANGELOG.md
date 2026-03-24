# LightRAG Improvement Log (ApeRAG Version)

---

## Overview

ApeRAG has deeply refactored LightRAG with the main goals of:
1. Supporting true concurrent processing
2. Adapting to distributed asynchronous task queues like Celery/Prefect
3. Eliminating global state dependencies
4. Enhancing system stability and maintainability

---

## Core Architecture Improvements

### 1. Data Isolation Mechanism - From `namespace_prefix` to `workspace`

**Original Version Issues**:
- Using string prefix concatenation for data isolation (e.g., `rag_test_entity_vdb`)
- Prone to naming conflicts
- Code filled with string concatenation logic

**Improved Solution**:
- Introduced the **`workspace`** concept; each collection uses an independent workspace
- All storage layers uniformly use the `workspace` field for data isolation
- **PostgreSQL**: Isolates data within tables via the `workspace` field
- **Neo44j, Qdrant**: Isolates data between databases via the `workspace` field
- Simplifies code and improves maintainability

### 2. Stateless Interface Design

**Original Version Issues**:
- The `ainsert` method coupled multiple processing stages
- Relied on global state for flow control
- Difficult to use in distributed environments

**Improved Solution**:
`ainsert` is split into several independent, stateless interfaces:

```python
# 1. Document Writing
async def ainsert_and_chunk_document(
    documents: List[str],
    doc_ids: List[str] | None = None,
    file_paths: List[str] | None = None,
) -> Dict[str, Any]

# 2. Graph Index Building
async def aprocess_graph_indexing(
    chunks: Dict[str, Any],
    collection_id: str | None = None,
) -> Dict[str, Any]

# 3. Document Deletion
async def adelete_by_doc_id(doc_id: str) -> None
```

Each interface is completely stateless and can be called independently.

### 3. Elimination of Global State Management

**Original Version's Global State**:
```python
# shared_storage.py - module-level global variables
_shared_dicts: Optional[Dict[str, Any]] = None
_pipeline_status_lock: Optional[LockType] = None
_storage_lock: Optional[LockType] = None
_graph_db_lock: Optional[LockType] = None
_is_multiprocess = None
_manager = None
_initialized = None
```

**Improved Solution**:
- **Deleted `_shared_dicts`**: No longer uses global shared dictionaries
- **Deleted `_pipeline_status_lock`**: Removed global pipeline mutex mechanism
- **Deleted `_storage_lock`**: File storage has been removed
- **Deleted multiprocess-related variables**: Unified to an asynchronous architecture
- **Retained `_graph_db_lock` but changed to instance-level lock**

### 4. Removal of `pipeline_status` Global Mutex System

**Original Version Mechanism**:
```python
# Global pipeline_status["busy"] ensures only one ainsert is executing
pipeline_status = await get_namespace_data("pipeline_status")
if not pipeline_status.get("busy", False):
    pipeline_status["busy"] = True  # Prevents other instances
else:
    pipeline_status["request_pending"] = True
    return  # Other calls are blocked
```

**Improved Solution**:
- Completely **deleted the `pipeline_status` system**
- Created the **`LightRAGLogger`** class to provide structured logging
- Supports true **concurrent processing**, allowing multiple collections to process documents simultaneously
- Tracks processing progress via **logs rather than global state**

### 5. General Concurrent Control System (`concurrent_control`)

**Original Version Lock Mechanism Issues**:
- The `UnifiedLock` abstract class, while attempting to unify interfaces, was unfriendly to multi-threading, coroutines, and multi-processing
- Global locks were tied to the event loop, causing conflicts when used across event loops
- Lacked timeout control and flexible lock management mechanisms

**New `concurrent_control` Module**:
- **`ThreadingLock`**: Based on `threading.Lock` + `asyncio.to_thread`
  - Supports multi-threading and multi-coroutine concurrency within a single process
  - Avoids blocking the event loop
  - Suitable for Celery `--pool=solo` and `--pool=threads`
- **Reserved `RedisLock` interface**: For future distributed locks
- **`LockManager`**: Unified lock manager, supporting named lock creation and reuse
- **`lock_context`**: Asynchronous context manager supporting timeouts
- **Completely independent**: Can be used in any Python project, not limited to LightRAG

### 6. Database Connection Management Optimization

#### 6.1 PostgreSQL Synchronous Connection Pool

**Reason for Creation**:
- Event loop conflicts in the Celery environment
- The original `ClientManager._lock = asyncio.Lock()` was created at module import, binding to the default event loop

**Solution**:
```python
# PostgreSQLSyncConnectionManager
- Uses psycopg2.pool.ThreadedConnectionPool
- Worker-level connection pool reuse
- Avoids event loop conflicts
- Maintains asynchronous interface compatibility via asyncio.to_thread
```

**Implemented Synchronous Storage Classes**:
- **`PGOpsSyncKVStorage`**: KV storage using `DatabaseOps`
- **`PGOpsSyncVectorStorage`**: Vector storage using `DatabaseOps`
- **`PGOpsSyncDocStatusStorage`**: Document status storage using `DatabaseOps`

#### 6.2 Neo4j Synchronous Driver Support

**Design Philosophy**:
- References practices from large projects like Reddit and Instagram
- Using synchronous drivers in a Celery environment is standard practice

**Implementation**:
```python
# Neo4jSyncConnectionManager
- Worker-level Driver instances
- Uses threading.Lock for thread safety
- Automatically manages lifecycle via Celery signals
- Neo4j driver has built-in connection pooling
```

### 7. Streamlined Storage Implementations, Focused on Best Practices

**Deleted Storage Implementations** (to reduce maintenance and testing burden):
- **File-based Storage**:
  - `networkx_impl.py`: NetworkX graph storage (only suitable for prototyping)
  - `nano_vector_db_impl`: NanoVectorDB vector storage (limited functionality)
  - `json_kv_impl.py`: JSON KV storage (poor performance)
  - `json_doc_status_impl.py`: JSON document status storage (no concurrency control)
- **Experimental Databases**:
  - `tidb_impl.py`: TiDB storage (infrequent use cases)
  - `age_impl.py`: Apache AGE graph storage (not mature enough)
  - Other experimental storage implementations

**Retained Production-Grade Storage**:
- **PostgreSQL**:
  - `postgres_impl.py`: Asynchronous implementation (suitable for FastAPI, etc.)
  - `postgres_sync_impl.py`: Synchronous implementation (suitable for Celery)
  - Supports KV, Vector, DocStatus storage
- **Neo4j**:
  - `neo4j_impl.py`: Asynchronous implementation
  - `neo4j_sync_impl.py`: Synchronous implementation
  - Professional graph database storage
- **Redis**:
  - `redis_impl.py`: KV storage (caching scenarios)
- **Qdrant**:
  - `qdrant_impl.py`: Professional vector storage

**Design Philosophy**: Only retain production-validated storage implementations with clear use cases.

### 8. Complete Deletion of `shared_storage.py`

**Original `shared_storage.py` Issues**:
- 300+ lines of complex global state management code
- Multi-layered locking mechanisms difficult to understand and maintain
- Global variables causing interference between instances
- Multiprocess Manager mechanism adding complexity

**Post-Deletion Effects**:
- **File completely removed**: No more `shared_storage.py`
- **Locks changed to instance-level**: Each LightRAG instance has its own `_graph_db_lock`
- **No global state**: Thoroughly eliminated global variable dependencies
- **Simplified initialization**: No longer requires `initialize_share_data()`
- **Better isolation**: Multiple instances run completely independently

### 9. Optimized LightRAG Lifecycle Management

**Original Version Issues**:
- Asynchronous initialization flaws: `_run_async_safely` returned an incompletely initialized object in an asynchronous environment
- Complex storage state management
- Difficult to properly destroy and clean up resources

**Improved Solution**:
- **Deleted caching mechanism in `lightrag_holder.py`**
- **Creates a brand new LightRAG instance each time** (truly stateless)
- **Simplified initialization and destruction** processes
- Provides a clear instance creation interface via **`lightrag_manager.py`**

### 10. Celery/Prefect and Other Asynchronous Task Queue Integration

**Supported Task Queue Systems**:
- **Celery**: Fully supported
- **Prefect**: Supported through stateless design and independent event loops
- **Other task queues**: Any Python asynchronous task queue can be integrated

**Core Design**:
```python
# Convenient functions provided by lightrag_manager.py
def process_document_for_celery(collection, content, doc_id, file_path)
def delete_document_for_celery(collection, doc_id)

# Internal implementation: independent event loop for each task
def _run_in_new_loop(coro: Awaitable) -> Any:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)
```

**Key Features**:
- Each task creates an independent event loop
- Completely avoids cross-task event loop conflicts
- Stateless design supports arbitrary concurrency
- Synchronous interfaces wrap asynchronous implementations

---

## Feature Improvements

### 1. Logging System Optimization

**`LightRAGLogger` Features**:
- Structured log format
- Supports workspace identification
- Dedicated progress recording methods
- Facilitates monitoring and debugging

### 2. Concurrent Performance Enhancement

**Original Version Limitations**:
- Only one `ainsert` operation could execute at a time
- `max_parallel_insert` only controlled concurrency within a single batch

**Improvements**:
- Supports true multi-instance concurrency
- Each collection processed independently
- No global lock limitations
- **3-5x performance improvement**

### 3. Enhanced Error Handling

- Custom **`LightRAGError`** exception class
- More detailed error messages
- Graceful degradation handling
- Full error tracing

### 4. Database Concurrent Operation Fixes

**Original Version Issues**:
- Used `asyncio.gather` to concurrently execute multiple database operations
- Concurrent operations on the same connection led to `InterfaceError`

**Fixes**:
- Changed critical database operations to **execute serially**
- Maintained concurrency for computation-intensive operations (e.g., embedding)
- Avoided database connection conflicts
- Improved system stability

---

## Removed Features

### 1. Removed LLM Caching

**Reason**:
- The original caching mechanism was too simplistic
- Planned to implement a global LLM Response History module
- Avoided cache consistency issues

### 2. Removed Complex LLM/Embedding Decorators

**Removed Features**:
- `priority_limit_async_func_call` decorator (280 lines)
- Complex priority control mechanisms
- Multi-layered nested asynchronous call management

**Effects**:
- **Zero decorator overhead**
- **Cleaner, clearer code**
- Avoids event loop conflicts

---

## Summary

The ApeRAG version of LightRAG, through deep refactoring, resolves fundamental issues of the original version related to concurrent processing, state management, and Celery/Prefect integration. The new architecture is simpler, more efficient, and easier to maintain, providing a solid foundation for large-scale production deployments.

**Key Achievements**:
- **True Concurrency Support**: From single-instance serial to multi-instance concurrent, supporting multi-coroutine, multi-thread, and multi-process concurrency
- **Production-Grade Stability**: Solved all known event loop and concurrency conflicts
- **Simplified Architecture**: Eliminated tens of thousands of lines of redundant code, improving maintainability
- **Flexible Integration**: Supports various asynchronous task queues and deployment modes
- **Focus on Core Value**: Retained best practices and removed experimental features