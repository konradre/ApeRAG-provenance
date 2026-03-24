import hashlib
import uuid
from enum import Enum

from sqlalchemy import (
    ARRAY,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from aperag.db.models import Base, EnumColumn, random_id
from aperag.utils.utils import utc_now


class ArtifactType(str, Enum):
    DOCUMENT_VERSION = "DOCUMENT_VERSION"
    PARSE_RESULT = "PARSE_RESULT"
    TEXT_CHUNK = "TEXT_CHUNK"
    IMAGE_ASSET = "IMAGE_ASSET"
    SUMMARY_TEXT = "SUMMARY_TEXT"
    EMBEDDING = "EMBEDDING"
    GRAPH_CHUNK = "GRAPH_CHUNK"
    ENTITY = "ENTITY"
    RELATION = "RELATION"
    VLM_DESCRIPTION = "VLM_DESCRIPTION"


class InputRole(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    MERGED_SOURCE = "merged_source"
    IMAGE_SOURCE = "image_source"


class MaterializationBackend(str, Enum):
    QDRANT = "qdrant"
    ELASTICSEARCH = "elasticsearch"
    LIGHTRAG_PG = "lightrag_pg"
    NEO4J = "neo4j"
    OBJECT_STORE = "object_store"


def generate_run_id() -> str:
    return uuid.uuid4().hex


def compute_content_hash(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def compute_lineage_hash(content_hash: str, parent_lineage_hashes: list[str]) -> str:
    parts = [content_hash] + sorted(parent_lineage_hashes)
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


class ProvenanceNode(Base):
    __tablename__ = "provenance_node"
    __table_args__ = (
        UniqueConstraint("document_id", "artifact_type", "artifact_key", name="uq_provenance_natural_key"),
        Index("ix_provenance_node_document_id", "document_id"),
        Index("ix_provenance_node_collection_id", "collection_id"),
        Index("ix_provenance_node_run_id", "run_id"),
        Index("ix_provenance_node_artifact_type", "artifact_type"),
        Index("ix_provenance_node_primary_parent_id", "primary_parent_id"),
        Index("ix_provenance_node_content_hash", "content_hash"),
        Index("ix_provenance_node_input_hash", "input_hash"),
        Index("ix_provenance_node_lineage_hash", "lineage_hash"),
    )

    id = Column(String(24), primary_key=True, default=lambda: "pn_" + random_id())
    document_id = Column(String(24), ForeignKey("document.id"), nullable=False)
    collection_id = Column(String(24), nullable=False)
    run_id = Column(String(36), nullable=False)
    artifact_type = Column(EnumColumn(ArtifactType), nullable=False)
    artifact_key = Column(String(255), nullable=False)
    primary_parent_id = Column(String(24), ForeignKey("provenance_node.id"), nullable=True)
    depth = Column(Integer, nullable=False, default=0)
    ancestor_ids = Column(ARRAY(String), nullable=False, default=list)
    path_types = Column(ARRAY(String), nullable=False, default=list)
    content_hash = Column(String(64), nullable=False)
    input_hash = Column(String(64), nullable=True)
    lineage_hash = Column(String(64), nullable=False)
    processor = Column(String(128), nullable=False)
    processor_version = Column(String(64), nullable=False)
    processing_params = Column(JSONB, nullable=False, default=dict)
    location = Column(JSONB, nullable=True)
    quality_score = Column(Numeric, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
    gmt_created = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProvenanceInput(Base):
    __tablename__ = "provenance_input"

    node_id = Column(
        String(24), ForeignKey("provenance_node.id", ondelete="CASCADE"), primary_key=True
    )
    input_node_id = Column(
        String(24), ForeignKey("provenance_node.id"), primary_key=True
    )
    input_role = Column(EnumColumn(InputRole), nullable=False)
    input_order = Column(Integer, nullable=True)


class ProvenanceMaterialization(Base):
    __tablename__ = "provenance_materialization"
    __table_args__ = (
        UniqueConstraint("backend", "external_id", name="uq_materialization_backend_external"),
        Index("ix_materialization_node_id", "node_id"),
        Index("ix_materialization_index_type_backend", "index_type", "backend"),
    )

    id = Column(String(24), primary_key=True, default=lambda: "pm_" + random_id())
    node_id = Column(
        String(24), ForeignKey("provenance_node.id", ondelete="CASCADE"), nullable=False
    )
    index_type = Column(String(32), nullable=True)
    backend = Column(String(32), nullable=False)
    external_id = Column(String(255), nullable=False)
    locator = Column(JSONB, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
    gmt_created = Column(DateTime(timezone=True), default=utc_now, nullable=False)
