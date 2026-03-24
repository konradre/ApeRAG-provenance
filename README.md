# ApeRAG-Provenance

> Fork of [apecloud/ApeRAG](https://github.com/apecloud/ApeRAG) with **document-scoped provenance chain tracking** across all 5 index types.

ApeRAG is a production-ready RAG (Retrieval-Augmented Generation) platform that combines Graph RAG, vector search, and full-text search with advanced AI agents. This fork adds a provenance subsystem that traces any derived artifact — chunks, embeddings, entities, relations, summaries, vision descriptions — back through its full derivation chain to the original uploaded document.

- [What's Different: Provenance](#whats-different-provenance)
- [Quick Start](#quick-start)
- [Key Features](#key-features)
- [Provenance API](#provenance-api)
- [Kubernetes Deployment (Recommended for Production)](#kubernetes-deployment-recommended-for-production)
- [Development](./docs/en-US/development-guide.md)
- [Build Docker Image](./docs/en-US/build-docker-image.md)
- [Acknowledgments](#acknowledgments)
- [License](#license)

## Quick Start

> Before installing ApeRAG, make sure your machine meets the following minimum system requirements:
>
> - CPU >= 2 Core
> - RAM >= 4 GiB
> - Docker & Docker Compose

The easiest way to start ApeRAG is through Docker Compose. Before running the following commands, make sure that [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) are installed on your machine:

```bash
git clone https://github.com/konradre/ApeRAG-provenance.git
cd ApeRAG-provenance
cp envs/env.template .env
docker-compose up -d --pull always
```

After running, you can access ApeRAG in your browser at:
- **Web Interface**: http://localhost:3000/web/
- **API Documentation**: http://localhost:8000/docs

#### MCP (Model Context Protocol) Support

ApeRAG supports [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) integration, allowing AI assistants to interact with your knowledge base directly. After starting the services, configure your MCP client with:

```json
{
  "mcpServers": {
    "aperag-mcp": {
      "url": "https://rag.apecloud.com/mcp/",
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

**Authentication** (by priority):
1. **HTTP Authorization Header** (Recommended): `Authorization: Bearer your-api-key`
2. **Environment Variable** (Fallback): `APERAG_API_KEY=your-api-key`

**Important**: Replace `https://rag.apecloud.com` with your actual ApeRAG API URL and `your-api-key-here` with a valid API key from your ApeRAG settings.

The MCP server provides:
- **Collection browsing**: List and explore your knowledge collections
- **Hybrid search**: Search using vector, full-text, and graph methods
- **Intelligent querying**: Ask natural language questions about your documents

#### Enhanced Document Parsing

For enhanced document parsing capabilities, ApeRAG supports an **advanced document parsing service** powered by MinerU, which provides superior parsing for complex documents, tables, and formulas. 

<details>
<summary><strong>Enhanced Document Parsing Commands</strong></summary>

```bash
# Enable advanced document parsing service
DOCRAY_HOST=http://aperag-docray:8639 docker compose --profile docray up -d

# Enable advanced parsing with GPU acceleration 
DOCRAY_HOST=http://aperag-docray-gpu:8639 docker compose --profile docray-gpu up -d
```

Or use the Makefile shortcuts (requires [GNU Make](https://www.gnu.org/software/make/)):
```bash
# Enable advanced document parsing service
make compose-up WITH_DOCRAY=1

# Enable advanced parsing with GPU acceleration (recommended)
make compose-up WITH_DOCRAY=1 WITH_GPU=1
```

</details>

#### Development & Contributing

For developers interested in source code development, advanced configurations, or contributing to ApeRAG, please refer to our [Development Guide](./docs/en-US/development-guide.md) for detailed setup instructions.

## What's Different: Provenance

This fork adds a **provenance subsystem** — a three-table DAG that records every derived artifact produced during document processing and links it back to its source. When a user searches and gets a result, the provenance chain answers: *where did this come from, what produced it, and what was the original input?*

### How It Works

Every document processing run generates a chain of provenance nodes:

```
DOCUMENT_VERSION (uploaded file, content hash)
  └─ PARSE_RESULT (parser output, frozen config)
       ├─ TEXT_CHUNK ──── Materialization → Qdrant (vector)
       │                  Materialization → Elasticsearch (fulltext)
       ├─ SUMMARY_TEXT ── Materialization → Qdrant (summary)
       ├─ IMAGE_ASSET
       │    └─ VLM_DESCRIPTION ── Materialization → Qdrant (vision)
       └─ GRAPH_CHUNK
            ├─ ENTITY (merged from multiple chunks via ProvenanceInput)
            └─ RELATION (merged from multiple chunks via ProvenanceInput)
```

### Schema

Three PostgreSQL tables:

| Table | Purpose |
|-------|---------|
| `provenance_node` | Core DAG — one row per derived artifact, with depth, ancestor chain, content/lineage hashes, and processing params |
| `provenance_input` | Junction table for multi-parent DAG ancestry (graph entities merged from multiple chunks) |
| `provenance_materialization` | Maps provenance nodes to external store references (Qdrant point IDs, ES doc IDs, etc.) |

### Key Properties

- **Fail-open** — provenance never blocks document processing. All recording is wrapped in try/except with logging.
- **Idempotent** — natural-key upserts (`document_id, artifact_type, artifact_key`) mean Celery retries don't create duplicates.
- **Tamper-evident** — lineage hashes chain through the DAG. If any ancestor's content changes, the hash chain breaks.
- **DAG, not tree** — LightRAG entities merge source IDs from multiple chunks across documents. `ProvenanceInput` preserves the full many-to-many ancestry.

See [PROVENANCE.md](PROVENANCE.md) for the full schema, design decisions, and implementation details.

---

## Key Features

**1. Advanced Index Types**:
Five comprehensive index types for optimal retrieval: **Vector**, **Full-text**, **Graph**, **Summary**, and **Vision** - providing multi-dimensional document understanding and search capabilities.

**2. Intelligent AI Agents**:
Built-in AI agents with MCP (Model Context Protocol) tool support that can automatically identify relevant collections, search content intelligently, and provide web search capabilities for comprehensive question answering.

**3. Enhanced Graph RAG with Entity Normalization**:
Deeply modified LightRAG implementation with advanced entity normalization (entity merging) for cleaner knowledge graphs and improved relational understanding.

**4. Multimodal Processing & Vision Support**:
Complete multimodal document processing including vision capabilities for images, charts, and visual content analysis alongside traditional text processing.

**5. Hybrid Retrieval Engine**:
Sophisticated retrieval system combining Graph RAG, vector search, full-text search, summary-based retrieval, and vision-based search for comprehensive document understanding.

**6. MinerU Integration**:
Advanced document parsing service powered by MinerU technology, providing superior parsing for complex documents, tables, formulas, and scientific content with optional GPU acceleration.

**7. Production-Grade Deployment**:
Full Kubernetes support with Helm charts and KubeBlocks integration for simplified deployment of production-grade databases (PostgreSQL, Redis, Qdrant, Elasticsearch, Neo4j).

**8. Enterprise Management**:
Built-in audit logging, LLM model management, graph visualization, comprehensive document management interface, and agent workflow management.

**9. MCP Integration**:
Full support for Model Context Protocol (MCP), enabling seamless integration with AI assistants and tools for direct knowledge base access and intelligent querying.

**10. Developer Friendly**:
FastAPI backend, React frontend, async task processing with Celery, extensive testing, comprehensive development guides, and agent development framework for easy contribution and customization.

## Provenance API

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/documents/{id}/provenance` | GET | Full lineage DAG for a document |
| `/api/v1/provenance/{node_id}/chain` | GET | Ancestor chain from node to root |
| `/api/v1/provenance/{node_id}` | GET | Single node with materializations and inputs |
| `/api/v1/provenance/run/{run_id}` | GET | All nodes from a processing run |

### MCP Tools

| Tool | Description |
|------|-------------|
| `get_document_provenance(document_id)` | Full lineage DAG for a document |
| `get_provenance_chain(node_id)` | Ancestor chain from node to root |

### Remaining Work

- **Alembic migration** — needs a live PostgreSQL instance to auto-generate (`alembic revision --autogenerate -m "add provenance tables"`)
- **Search result attribution** — `GET /search/results/{id}/provenance` mapping search hits through materializations to provenance chains

## Kubernetes Deployment (Recommended for Production)

> **Enterprise-grade deployment with high availability and scalability**

Deploy ApeRAG to Kubernetes using our provided Helm chart. This approach offers high availability, scalability, and production-grade management capabilities.

### Prerequisites

*   [Kubernetes cluster](https://kubernetes.io/docs/setup/) (v1.20+)
*   [`kubectl`](https://kubernetes.io/docs/tasks/tools/) configured and connected to your cluster
*   [Helm v3+](https://helm.sh/docs/intro/install/) installed

### Clone the Repository

First, clone the ApeRAG repository to get the deployment files:

```bash
git clone https://github.com/konradre/ApeRAG-provenance.git
cd ApeRAG-provenance
```

### Step 1: Deploy Database Services

ApeRAG requires PostgreSQL, Redis, Qdrant, and Elasticsearch. You have two options:

**Option A: Use existing databases** - If you already have these databases running in your cluster, edit `deploy/aperag/values.yaml` to configure your database connection details, then skip to Step 2.

**Option B: Deploy databases with KubeBlocks** - Use our automated database deployment (database connections are pre-configured):

```bash
# Navigate to database deployment scripts
cd deploy/databases/

# (Optional) Review configuration - defaults work for most cases
# edit 00-config.sh

# Install KubeBlocks and deploy databases
bash ./01-prepare.sh          # Installs KubeBlocks
bash ./02-install-database.sh # Deploys PostgreSQL, Redis, Qdrant, Elasticsearch

# Monitor database deployment
kubectl get pods -n default

# Return to project root for Step 2
cd ../../
```

Wait for all database pods to be in `Running` status before proceeding.

### Step 2: Deploy ApeRAG Application

```bash
# If you deployed databases with KubeBlocks in Step 1, database connections are pre-configured
# If you're using existing databases, edit deploy/aperag/values.yaml with your connection details

# Deploy ApeRAG
helm install aperag ./deploy/aperag --namespace default --create-namespace

# Monitor ApeRAG deployment
kubectl get pods -n default -l app.kubernetes.io/instance=aperag
```

### Configuration Options

**Resource Requirements**: By default, includes [`doc-ray`](https://github.com/apecloud/doc-ray) service (requires 4+ CPU cores, 8GB+ RAM). To disable: set `docray.enabled: false` in `values.yaml`.

**Advanced Settings**: Review `values.yaml` for additional configuration options including images, resources, and Ingress settings.

### Access Your Deployment

Once deployed, access ApeRAG using port forwarding:

```bash
# Forward ports for quick access
kubectl port-forward svc/aperag-frontend 3000:3000 -n default
kubectl port-forward svc/aperag-api 8000:8000 -n default

# Access in browser
# Web Interface: http://localhost:3000
# API Documentation: http://localhost:8000/docs
```

For production environments, configure Ingress in `values.yaml` for external access.

### Troubleshooting

**Database Issues**: See `deploy/databases/README.md` for KubeBlocks management, credentials, and uninstall procedures.

**Pod Status**: Check pod logs for any deployment issues:
```bash
kubectl logs -f deployment/aperag-api -n default
kubectl logs -f deployment/aperag-frontend -n default
```

## Acknowledgments

### Upstream
This fork is built on [apecloud/ApeRAG](https://github.com/apecloud/ApeRAG) (Apache 2.0).

### OCR Provenance MCP Server
The provenance chain concept is adapted from [ocr-provenance-mcp](https://www.npmjs.com/package/ocr-provenance-mcp) by ChrisRoyse. The original uses a strict 4-level tree with SQLite; this fork adapts it to a document-scoped DAG with PostgreSQL.

## License

ApeRAG is licensed under the Apache License 2.0. See the [LICENSE](./LICENSE) file for details. Provenance additions by [konradre](https://github.com/konradre).