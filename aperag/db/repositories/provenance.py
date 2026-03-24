from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from aperag.db.models_provenance import (
    ProvenanceInput,
    ProvenanceMaterialization,
    ProvenanceNode,
)
from aperag.db.repositories.base import AsyncBaseRepository, SyncBaseRepository


class ProvenanceRepositoryMixin(SyncBaseRepository):
    def upsert_node(self, node_data: dict) -> ProvenanceNode:
        def _operation(session):
            stmt = pg_insert(ProvenanceNode).values(**node_data)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_provenance_natural_key",
                set_={
                    "run_id": stmt.excluded.run_id,
                    "content_hash": stmt.excluded.content_hash,
                    "input_hash": stmt.excluded.input_hash,
                    "lineage_hash": stmt.excluded.lineage_hash,
                    "processor": stmt.excluded.processor,
                    "processor_version": stmt.excluded.processor_version,
                    "processing_params": stmt.excluded.processing_params,
                    "location": stmt.excluded.location,
                    "quality_score": stmt.excluded.quality_score,
                    "duration_ms": stmt.excluded.duration_ms,
                    "metadata": stmt.excluded.metadata,
                },
            )
            session.execute(stmt)
            # Fetch the upserted row
            fetch = select(ProvenanceNode).where(
                ProvenanceNode.document_id == node_data["document_id"],
                ProvenanceNode.artifact_type == node_data["artifact_type"],
                ProvenanceNode.artifact_key == node_data["artifact_key"],
            )
            result = session.execute(fetch)
            return result.scalars().first()

        return self._execute_transaction(_operation)

    def upsert_nodes_batch(self, nodes_data: List[dict]) -> int:
        def _operation(session):
            for node_data in nodes_data:
                stmt = pg_insert(ProvenanceNode).values(**node_data)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_provenance_natural_key",
                    set_={
                        "run_id": stmt.excluded.run_id,
                        "content_hash": stmt.excluded.content_hash,
                        "lineage_hash": stmt.excluded.lineage_hash,
                        "processor": stmt.excluded.processor,
                        "processor_version": stmt.excluded.processor_version,
                        "processing_params": stmt.excluded.processing_params,
                    },
                )
                session.execute(stmt)
            return len(nodes_data)

        return self._execute_transaction(_operation)

    def record_inputs(self, node_id: str, inputs: List[dict]) -> None:
        def _operation(session):
            for inp in inputs:
                stmt = pg_insert(ProvenanceInput).values(
                    node_id=node_id,
                    input_node_id=inp["input_node_id"],
                    input_role=inp["input_role"],
                    input_order=inp.get("input_order"),
                )
                stmt = stmt.on_conflict_do_nothing()
                session.execute(stmt)

        self._execute_transaction(_operation)

    def record_materialization(self, mat_data: dict) -> ProvenanceMaterialization:
        def _operation(session):
            stmt = pg_insert(ProvenanceMaterialization).values(**mat_data)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_materialization_backend_external",
                set_={
                    "node_id": stmt.excluded.node_id,
                    "index_type": stmt.excluded.index_type,
                    "locator": stmt.excluded.locator,
                    "metadata": stmt.excluded.metadata,
                },
            )
            session.execute(stmt)
            fetch = select(ProvenanceMaterialization).where(
                ProvenanceMaterialization.backend == mat_data["backend"],
                ProvenanceMaterialization.external_id == mat_data["external_id"],
            )
            result = session.execute(fetch)
            return result.scalars().first()

        return self._execute_transaction(_operation)

    def get_node_by_natural_key(
        self, document_id: str, artifact_type: str, artifact_key: str
    ) -> Optional[ProvenanceNode]:
        def _query(session):
            stmt = select(ProvenanceNode).where(
                ProvenanceNode.document_id == document_id,
                ProvenanceNode.artifact_type == artifact_type,
                ProvenanceNode.artifact_key == artifact_key,
            )
            result = session.execute(stmt)
            return result.scalars().first()

        return self._execute_query(_query)

    def get_chain(self, node_id: str) -> List[ProvenanceNode]:
        def _query(session):
            node = session.execute(
                select(ProvenanceNode).where(ProvenanceNode.id == node_id)
            ).scalars().first()
            if not node:
                return []
            chain = [node]
            current = node
            while current.primary_parent_id:
                current = session.execute(
                    select(ProvenanceNode).where(ProvenanceNode.id == current.primary_parent_id)
                ).scalars().first()
                if not current:
                    break
                chain.append(current)
            return list(reversed(chain))

        return self._execute_query(_query)

    def get_nodes_by_document(self, document_id: str) -> List[ProvenanceNode]:
        def _query(session):
            stmt = (
                select(ProvenanceNode)
                .where(ProvenanceNode.document_id == document_id)
                .order_by(ProvenanceNode.depth, ProvenanceNode.gmt_created)
            )
            result = session.execute(stmt)
            return result.scalars().all()

        return self._execute_query(_query)

    def get_materializations_for_node(self, node_id: str) -> List[ProvenanceMaterialization]:
        def _query(session):
            stmt = select(ProvenanceMaterialization).where(
                ProvenanceMaterialization.node_id == node_id
            )
            result = session.execute(stmt)
            return result.scalars().all()

        return self._execute_query(_query)

    def get_inputs_for_node(self, node_id: str) -> List[ProvenanceInput]:
        def _query(session):
            stmt = (
                select(ProvenanceInput)
                .where(ProvenanceInput.node_id == node_id)
                .order_by(ProvenanceInput.input_order)
            )
            result = session.execute(stmt)
            return result.scalars().all()

        return self._execute_query(_query)

    def delete_by_document(self, document_id: str) -> int:
        def _operation(session):
            nodes = session.execute(
                select(ProvenanceNode.id).where(ProvenanceNode.document_id == document_id)
            ).scalars().all()
            if not nodes:
                return 0
            # CASCADE handles ProvenanceInput and ProvenanceMaterialization
            from sqlalchemy import delete
            count = session.execute(
                delete(ProvenanceNode).where(ProvenanceNode.document_id == document_id)
            ).rowcount
            return count

        return self._execute_transaction(_operation)
