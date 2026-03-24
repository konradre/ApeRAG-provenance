import logging
from typing import List, Optional

from aperag.db.models import random_id
from aperag.db.models_provenance import (
    ArtifactType,
    compute_content_hash,
    compute_lineage_hash,
    generate_run_id,
)
from aperag.db.repositories.provenance import ProvenanceRepositoryMixin

logger = logging.getLogger(__name__)


class ProvenanceService:
    def __init__(self, session=None):
        self._repo = ProvenanceRepositoryMixin(session=session)

    def create_node(
        self,
        document_id: str,
        collection_id: str,
        run_id: str,
        artifact_type: str,
        artifact_key: str,
        content_hash: str,
        processor: str,
        processor_version: str,
        processing_params: dict = None,
        primary_parent_id: str = None,
        parent_lineage_hash: str = None,
        location: dict = None,
        quality_score: float = None,
        duration_ms: int = None,
        metadata: dict = None,
        input_hash: str = None,
        depth: int = None,
        ancestor_ids: list = None,
        path_types: list = None,
    ):
        if processing_params is None:
            processing_params = {}

        lineage_hash = compute_lineage_hash(
            content_hash,
            [parent_lineage_hash] if parent_lineage_hash else [],
        )

        # Compute depth and ancestor chain from parent if not explicitly provided
        if depth is None:
            if primary_parent_id:
                parent_node = self._get_parent_node(primary_parent_id)
                if parent_node:
                    depth = parent_node.depth + 1
                    ancestor_ids = (parent_node.ancestor_ids or []) + [parent_node.id]
                    path_types = (parent_node.path_types or []) + [parent_node.artifact_type]
                else:
                    depth = 0
                    ancestor_ids = []
                    path_types = []
            else:
                depth = 0

        if ancestor_ids is None:
            ancestor_ids = []
        if path_types is None:
            path_types = []

        node_data = {
            "id": "pn_" + random_id(),
            "document_id": document_id,
            "collection_id": collection_id,
            "run_id": run_id,
            "artifact_type": artifact_type,
            "artifact_key": artifact_key,
            "primary_parent_id": primary_parent_id,
            "depth": depth,
            "ancestor_ids": ancestor_ids,
            "path_types": path_types,
            "content_hash": content_hash,
            "input_hash": input_hash,
            "lineage_hash": lineage_hash,
            "processor": processor,
            "processor_version": processor_version,
            "processing_params": processing_params,
            "location": location,
            "quality_score": quality_score,
            "duration_ms": duration_ms,
            "metadata": metadata,
        }

        try:
            return self._repo.upsert_node(node_data)
        except Exception:
            logger.exception("Failed to create provenance node: %s/%s", artifact_type, artifact_key)
            return None

    def _get_parent_node(self, parent_id: str):
        from sqlalchemy import select
        from aperag.db.models_provenance import ProvenanceNode

        def _query(session):
            result = session.execute(
                select(ProvenanceNode).where(ProvenanceNode.id == parent_id)
            )
            return result.scalars().first()

        return self._repo._execute_query(_query)

    def record_inputs(self, node_id: str, inputs: List[dict]) -> None:
        try:
            self._repo.record_inputs(node_id, inputs)
        except Exception:
            logger.exception("Failed to record provenance inputs for node: %s", node_id)

    def record_materialization(
        self,
        node_id: str,
        index_type: str,
        backend: str,
        external_id: str,
        locator: dict = None,
        metadata: dict = None,
    ):
        mat_data = {
            "id": "pm_" + random_id(),
            "node_id": node_id,
            "index_type": index_type,
            "backend": backend,
            "external_id": external_id,
            "locator": locator,
            "metadata": metadata,
        }
        try:
            return self._repo.record_materialization(mat_data)
        except Exception:
            logger.exception("Failed to record materialization for node: %s", node_id)
            return None

    def get_chain(self, node_id: str):
        return self._repo.get_chain(node_id)

    def get_document_lineage(self, document_id: str):
        return self._repo.get_nodes_by_document(document_id)

    def get_node_by_natural_key(self, document_id: str, artifact_type: str, artifact_key: str):
        return self._repo.get_node_by_natural_key(document_id, artifact_type, artifact_key)

    def get_materializations(self, node_id: str):
        return self._repo.get_materializations_for_node(node_id)

    def get_inputs(self, node_id: str):
        return self._repo.get_inputs_for_node(node_id)

    def delete_document_provenance(self, document_id: str) -> int:
        return self._repo.delete_by_document(document_id)
