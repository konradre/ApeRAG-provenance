# ApeRAG Provenance Integration

Cross-index lineage tracking for all derived artifacts in ApeRAG's 5 index types (vector, fulltext, graph, summary, vision). Traces any search result back through its full derivation chain to the original uploaded document.

## Origin

Ported from [OCR Provenance MCP Server](https://www.npmjs.com/package/ocr-provenance-mcp) by ChrisRoyse. The original uses a strict 4-level tree (DOCUMENT → OCR_RESULT → CHUNK → EMBEDDING) with SQLite. This integration adapts the concept to a document-scoped DAG with PostgreSQL, supporting ApeRAG's multi-index fan-out and LightRAG's many-to-many entity merging.

Key architectural correction (validated by GPT 5.4 High): ApeRAG needs a DAG model, not a strict tree, because LightRAG entities accumulate `source_id` values from multiple chunks across multiple documents.

## Schema (3 tables)

### `provenance_node`

Core lineage DAG. Every derived artifact gets a row.

| Column | Type | Description |
|--------|------|-------------|
| `id` | String(24) | PK, `pn_` + random_id() |
| `document_id` | String(24) | FK → document.id |
| `collection_id` | String(24) | Collection scope |
| `run_id` | String(36) | UUID4, scopes one processing run |
| `artifact_type` | String | DOCUMENT_VERSION, PARSE_RESULT, TEXT_CHUNK, IMAGE_ASSET, SUMMARY_TEXT, EMBEDDING, GRAPH_CHUNK, ENTITY, RELATION, VLM_DESCRIPTION |
| `artifact_key` | String(255) | Deterministic natural key for idempotent upserts |
| `primary_parent_id` | String(24) | Self-FK, tree-like fast traversal |
| `depth` | Integer | Distance from root (0 = document) |
| `ancestor_ids` | ARRAY(String) | Materialized ancestor chain for fast queries |
| `path_types` | ARRAY(String) | Artifact types along the chain |
| `content_hash` | String(64) | SHA-256 of artifact content |
| `input_hash` | String(64) | Hash of inputs that produced this artifact |
| `lineage_hash` | String(64) | hash(content_hash + sorted parent lineage hashes) — tamper-evident |
| `processor` | String(128) | What produced this (upload, document_parser, rechunker, etc.) |
| `processor_version` | String(64) | Version for reproducibility |
| `processing_params` | JSONB | Frozen config (chunk_size, parser type, etc.) |
| `location` | JSONB | Where the artifact lives (object_path, etc.) |
| `quality_score` | Numeric | Optional quality metric |
| `duration_ms` | Integer | Processing time |
| `metadata` | JSONB | Arbitrary extra data |
| `gmt_created` | DateTime(tz) | Creation timestamp |

**Unique constraint:** `(document_id, artifact_type, artifact_key)` — Celery retries produce upserts, not duplicates.

### `provenance_input`

Junction table for DAG ancestry (multi-parent cases like graph entities).

| Column | Type | Description |
|--------|------|-------------|
| `node_id` | String(24) | FK → provenance_node.id (PK) |
| `input_node_id` | String(24) | FK → provenance_node.id (PK) |
| `input_role` | String | primary, secondary, merged_source, image_source |
| `input_order` | Integer | Ordering within role |

### `provenance_materialization`

Maps provenance nodes to external store references (Qdrant, Elasticsearch, LightRAG, object store).

| Column | Type | Description |
|--------|------|-------------|
| `id` | String(24) | PK, `pm_` + random_id() |
| `node_id` | String(24) | FK → provenance_node.id |
| `index_type` | String(32) | VECTOR, FULLTEXT, GRAPH, SUMMARY, VISION |
| `backend` | String(32) | qdrant, elasticsearch, lightrag_pg, neo4j, object_store |
| `external_id` | String(255) | ID in the external system |
| `locator` | JSONB | Collection name, index name, etc. |
| `metadata` | JSONB | Arbitrary extra data |
| `gmt_created` | DateTime(tz) | Creation timestamp |

**Unique constraint:** `(backend, external_id)`

## Lineage Chains

### Vector/Fulltext Path
```
DOCUMENT_VERSION (upload, content_hash of original file)
  └─ PARSE_RESULT (parser output, frozen parser config)
       └─ TEXT_CHUNK (rechunked content, chunk_size/overlap in params)
            ├─ Materialization: qdrant/{vector_id}    [VECTOR]
            └─ Materialization: elasticsearch/{index}/{chunk_id}  [FULLTEXT]
```

Vector and fulltext share the same `TEXT_CHUNK` provenance nodes via natural-key upsert. The first path to create the chunk wins; the second attaches its materialization to the existing node.

### Summary Path
```
DOCUMENT_VERSION
  └─ PARSE_RESULT
       └─ SUMMARY_TEXT (LLM-generated summary)
            └─ TEXT_CHUNK (if summary is rechunked)
                 └─ Materialization: qdrant/{vector_id}  [SUMMARY]
```

### Vision Path (Direct Multimodal)
```
DOCUMENT_VERSION
  └─ PARSE_RESULT
       └─ IMAGE_ASSET (extracted image, content_hash of image data)
            └─ Materialization: qdrant/{vector_id}  [VISION]
```

### Vision Path (Vision-to-Text)
```
DOCUMENT_VERSION
  └─ PARSE_RESULT
       └─ IMAGE_ASSET
            └─ VLM_DESCRIPTION (LLM-generated description of image)
                 └─ Materialization: qdrant/{vector_id}  [VISION]
```

### Graph Path (Full DAG)
```
DOCUMENT_VERSION
  └─ PARSE_RESULT
       └─ GRAPH_CHUNK (LightRAG's own token-based chunking)
            ├─ ENTITY (via ProvenanceInput: merged_source from multiple GRAPH_CHUNKs)
            └─ RELATION (via ProvenanceInput: merged_source from multiple GRAPH_CHUNKs)
```

ENTITY and RELATION nodes use `ProvenanceInput` (not just `primary_parent_id`) because LightRAG entities accumulate `source_id` values from multiple chunks. Each `ProvenanceInput` row records `input_role="merged_source"` linking the entity/relation back to every GRAPH_CHUNK that contributed to it.

## API Endpoints

### REST API (`/api/v1/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/documents/{id}/provenance` | GET | Full lineage DAG for a document (nodes + materializations + inputs) |
| `/provenance/{node_id}/chain` | GET | Ancestor chain from node back to root DOCUMENT_VERSION |
| `/provenance/{node_id}` | GET | Single node with its materializations and inputs |
| `/provenance/run/{run_id}` | GET | All nodes from a specific processing run |

### MCP Tools

| Tool | Description |
|------|-------------|
| `get_document_provenance(document_id)` | Full lineage DAG for a document |
| `get_provenance_chain(node_id)` | Ancestor chain from node to root |

## Files Created

| File | Purpose |
|------|---------|
| `aperag/db/models_provenance.py` | SQLAlchemy models, enums (ArtifactType, InputRole, MaterializationBackend), hash helpers (compute_content_hash, compute_lineage_hash, generate_run_id) |
| `aperag/db/repositories/provenance.py` | Repository with ON CONFLICT upserts, batch ops, chain traversal, materialization recording. Extends SyncBaseRepository. |
| `aperag/service/provenance_service.py` | Service layer: create_node (auto depth/ancestor), record_inputs, record_materialization, get_chain, get_document_lineage, delete_document_provenance. All operations fail-open. |
| `aperag/views/provenance.py` | REST API endpoints for querying provenance (document lineage, chain, node detail, run query) |

## Files Modified

| File | Change | Step |
|------|--------|------|
| `aperag/migration/env.py` | Import `models_provenance` for Alembic auto-discovery | 1 |
| `aperag/app.py` | Import and register `provenance_router` | 9 |
| `aperag/service/document_service.py` | Create DOCUMENT_VERSION node after upload (content_hash + object_path known) | 2 |
| `aperag/tasks/models.py` | Extended `ParsedDocumentData` with `run_id: str`, `parse_provenance_id: str` | 3 |
| `aperag/tasks/document.py` | Create PARSE_RESULT in parse_document(); propagate run_id/parse_provenance_id to all 5 index types; record GRAPH_CHUNK + ENTITY + RELATION provenance with ProvenanceInput DAG links | 3, 7, 8 |
| `aperag/llm/embed/embedding_utils.py` | Added provenance params to `create_embeddings_and_store()`; record TEXT_CHUNK nodes + Qdrant materializations after vector store add | 4, 5 |
| `aperag/index/vector_index.py` | Pass provenance kwargs (run_id, parse_provenance_id) through to `create_embeddings_and_store()` | 5 |
| `aperag/index/fulltext_index.py` | Record TEXT_CHUNK (shared natural key with vector) + ES materializations in `_process_chunks()` | 5 |
| `aperag/index/summary_index.py` | Create SUMMARY_TEXT node when summary finalized; pass provenance to embedding store | 6 |
| `aperag/index/vision_index.py` | Path A: IMAGE_ASSET + Qdrant materialization; Path B: IMAGE_ASSET → VLM_DESCRIPTION + Qdrant materialization | 6 |
| `aperag/graph/lightrag/operate.py` | `_merge_nodes_and_edges_impl()` returns entity_details/relation_details (name + source_ids) for provenance | 8 |
| `aperag/graph/lightrag/lightrag.py` | `_grouping_process_chunk_results()` and `aprocess_graph_indexing()` bubble entity/relation details up | 8 |
| `aperag/graph/lightrag_manager.py` | `_process_document_async()` collects and returns entity_details/relation_details | 8 |
| `aperag/mcp/server.py` | Added `get_document_provenance` and `get_provenance_chain` MCP tools | 9 |

## Design Decisions

### Fail-open everywhere
Every provenance recording call is wrapped in `try/except` with logging. A provenance failure never blocks document processing. The existing pipeline runs identically with or without a working provenance database.

### Natural-key upserts for Celery idempotency
The unique constraint `(document_id, artifact_type, artifact_key)` means Celery retries produce `ON CONFLICT DO UPDATE`, not duplicates. The `artifact_key` is deterministic (e.g., `{doc_id}:chunk:{idx}:{hash[:8]}`).

### Shared TEXT_CHUNK between vector and fulltext (Step 4)
Both paths call `rechunk()` independently with the same parameters (`settings.chunk_size`, `settings.chunk_overlap_size`) and use the same `artifact_key` formula `{doc_id}:chunk:{idx}:{hash[:8]}`. Since rechunking is deterministic with identical inputs, both paths produce identical chunks and converge on the same provenance nodes via natural-key upsert. The first path to execute creates the `TEXT_CHUNK` node; the second upserts (no-op on the node) and attaches its own materialization. This achieves the goal of shared chunk provenance without requiring a full architectural refactor to compute chunks once.

### DAG for graph entities (ProvenanceInput)
LightRAG entities merge `source_id` from multiple chunks across documents. A strict `primary_parent_id` chain would be lossy. `ProvenanceInput` preserves the full many-to-many ancestry with `input_role="merged_source"`. Entity/relation details (names + source chunk IDs) are collected during the merge phase in `_merge_nodes_and_edges_impl()` and bubbled up through the return chain to `document.py` where provenance is recorded post-hoc.

### run_id propagation
A single UUID4 is generated per parse invocation, carried through `ParsedDocumentData` to all downstream Celery tasks. This scopes every artifact from one processing run, enabling reproducibility queries ("show me everything from run X").

### Lineage hash (tamper-evident)
`lineage_hash = SHA-256(content_hash | sorted(parent_lineage_hashes))`. If any ancestor's content changes, the lineage hash chain breaks — similar to OCR Provenance's chain-hash concept.

### Minimal LightRAG modification (Step 8)
Rather than threading provenance context deep into LightRAG's async internals, entity/relation details are collected as return-value additions in `_merge_nodes_and_edges_impl()` and bubbled up through existing return paths. Provenance recording happens in `document.py:create_index()` after graph processing completes. This keeps LightRAG's core async logic untouched while still capturing the full DAG ancestry.

## Not Yet Implemented

### Alembic Migration
The migration file needs to be auto-generated once a PostgreSQL database is available:
```bash
alembic revision --autogenerate -m "add provenance tables"
alembic upgrade head
```

### Search Result Attribution
`GET /search/results/{id}/provenance` — Map a search result back through its materialization to the full provenance chain. Requires integrating with the search service to resolve `(backend, external_id)` from search result metadata to `ProvenanceMaterialization` → `ProvenanceNode` → chain.
