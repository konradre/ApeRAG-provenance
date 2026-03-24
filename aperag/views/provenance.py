# Copyright 2025 ApeCloud, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from aperag.db.models import User
from aperag.service.provenance_service import ProvenanceService
from aperag.views.auth import required_user

logger = logging.getLogger(__name__)

router = APIRouter()


def _node_to_dict(node) -> Dict[str, Any]:
    """Convert a ProvenanceNode to a serializable dict."""
    return {
        "id": node.id,
        "document_id": node.document_id,
        "collection_id": node.collection_id,
        "run_id": node.run_id,
        "artifact_type": node.artifact_type,
        "artifact_key": node.artifact_key,
        "primary_parent_id": node.primary_parent_id,
        "depth": node.depth,
        "ancestor_ids": node.ancestor_ids or [],
        "path_types": node.path_types or [],
        "content_hash": node.content_hash,
        "input_hash": node.input_hash,
        "lineage_hash": node.lineage_hash,
        "processor": node.processor,
        "processor_version": node.processor_version,
        "processing_params": node.processing_params or {},
        "location": node.location,
        "quality_score": float(node.quality_score) if node.quality_score is not None else None,
        "duration_ms": node.duration_ms,
        "metadata": node.metadata_,
        "gmt_created": node.gmt_created.isoformat() if node.gmt_created else None,
    }


def _materialization_to_dict(mat) -> Dict[str, Any]:
    """Convert a ProvenanceMaterialization to a serializable dict."""
    return {
        "id": mat.id,
        "node_id": mat.node_id,
        "index_type": mat.index_type,
        "backend": mat.backend,
        "external_id": mat.external_id,
        "locator": mat.locator,
        "metadata": mat.metadata_,
        "gmt_created": mat.gmt_created.isoformat() if mat.gmt_created else None,
    }


def _input_to_dict(inp) -> Dict[str, Any]:
    """Convert a ProvenanceInput to a serializable dict."""
    return {
        "node_id": inp.node_id,
        "input_node_id": inp.input_node_id,
        "input_role": inp.input_role,
        "input_order": inp.input_order,
    }


@router.get("/documents/{document_id}/provenance", tags=["provenance"])
async def get_document_provenance(
    request: Request,
    document_id: str,
    user: User = Depends(required_user),
) -> Dict[str, Any]:
    """Get the full provenance lineage DAG for a document.

    Returns all provenance nodes for the document, ordered by depth,
    along with their materializations and DAG inputs.
    """
    try:
        prov = ProvenanceService()
        nodes = prov.get_document_lineage(document_id)

        if not nodes:
            return {"document_id": document_id, "nodes": [], "materializations": [], "inputs": []}

        all_materializations = []
        all_inputs = []

        node_dicts = []
        for node in nodes:
            node_dicts.append(_node_to_dict(node))

            mats = prov.get_materializations(node.id)
            for mat in (mats or []):
                all_materializations.append(_materialization_to_dict(mat))

            inputs = prov.get_inputs(node.id)
            for inp in (inputs or []):
                all_inputs.append(_input_to_dict(inp))

        return {
            "document_id": document_id,
            "nodes": node_dicts,
            "materializations": all_materializations,
            "inputs": all_inputs,
        }

    except Exception as e:
        logger.error(f"Failed to get provenance for document {document_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve provenance: {str(e)}")


@router.get("/provenance/{node_id}/chain", tags=["provenance"])
async def get_provenance_chain(
    request: Request,
    node_id: str,
    user: User = Depends(required_user),
) -> Dict[str, Any]:
    """Get the ancestor chain from a provenance node back to the root document.

    Walks the primary_parent_id chain to produce a linear path from
    the root DOCUMENT_VERSION to the specified node.
    """
    try:
        prov = ProvenanceService()
        chain = prov.get_chain(node_id)

        if not chain:
            raise HTTPException(status_code=404, detail=f"Provenance node {node_id} not found")

        return {
            "node_id": node_id,
            "chain": [_node_to_dict(n) for n in chain],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get provenance chain for node {node_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve provenance chain: {str(e)}")


@router.get("/provenance/{node_id}", tags=["provenance"])
async def get_provenance_node(
    request: Request,
    node_id: str,
    user: User = Depends(required_user),
) -> Dict[str, Any]:
    """Get a single provenance node with its materializations and inputs."""
    try:
        prov = ProvenanceService()

        # Use chain to get the node (chain of length 1 if leaf, or walk to find it)
        chain = prov.get_chain(node_id)
        if not chain:
            raise HTTPException(status_code=404, detail=f"Provenance node {node_id} not found")

        # The requested node is the last in the chain
        node = chain[-1]
        mats = prov.get_materializations(node_id) or []
        inputs = prov.get_inputs(node_id) or []

        return {
            "node": _node_to_dict(node),
            "materializations": [_materialization_to_dict(m) for m in mats],
            "inputs": [_input_to_dict(i) for i in inputs],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get provenance node {node_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve provenance node: {str(e)}")


@router.get("/provenance/run/{run_id}", tags=["provenance"])
async def get_provenance_by_run(
    request: Request,
    run_id: str,
    user: User = Depends(required_user),
) -> Dict[str, Any]:
    """Get all provenance nodes from a specific processing run."""
    try:
        from sqlalchemy import select

        from aperag.config import get_sync_session
        from aperag.db.models_provenance import ProvenanceNode

        nodes = []
        for session in get_sync_session():
            stmt = (
                select(ProvenanceNode)
                .where(ProvenanceNode.run_id == run_id)
                .order_by(ProvenanceNode.depth, ProvenanceNode.gmt_created)
            )
            result = session.execute(stmt)
            nodes = result.scalars().all()

        return {
            "run_id": run_id,
            "nodes": [_node_to_dict(n) for n in nodes],
        }

    except Exception as e:
        logger.error(f"Failed to get provenance for run {run_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve provenance by run: {str(e)}")
