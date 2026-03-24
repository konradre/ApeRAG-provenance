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

from aperag.db.models import DocumentIndexType
from aperag.tasks.models import IndexTaskResult, LocalDocumentInfo, ParsedDocumentData
from aperag.tasks.utils import parse_document_content

logger = logging.getLogger(__name__)


class DocumentIndexTask:
    """
    Document index task orchestrator
    """

    def parse_document(self, document_id: str) -> ParsedDocumentData:
        """
        Parse document content

        Args:
            document_id: Document ID to parse

        Returns:
            ParsedDocumentData containing all parsed information
        """
        logger.info(f"Parsing document {document_id}")

        from aperag.tasks.utils import get_document_and_collection

        document, collection = get_document_and_collection(document_id)
        content, doc_parts, local_doc = parse_document_content(document, collection)

        local_doc_info = LocalDocumentInfo(path=local_doc.path, is_temp=getattr(local_doc, "is_temp", False))

        # Record PARSE_RESULT provenance
        run_id = None
        parse_provenance_id = None
        try:
            from aperag.db.models_provenance import ArtifactType, compute_content_hash, generate_run_id
            from aperag.service.provenance_service import ProvenanceService

            run_id = generate_run_id()
            prov = ProvenanceService()

            # Look up the DOCUMENT_VERSION parent node
            doc_version_node = prov.get_node_by_natural_key(
                document_id=document_id,
                artifact_type=ArtifactType.DOCUMENT_VERSION.value,
                artifact_key=document.content_hash or "",
            )
            parent_id = doc_version_node.id if doc_version_node else None
            parent_lineage_hash = doc_version_node.lineage_hash if doc_version_node else None

            parse_node = prov.create_node(
                document_id=document_id,
                collection_id=collection.id,
                run_id=run_id,
                artifact_type=ArtifactType.PARSE_RESULT.value,
                artifact_key=f"{document_id}:{run_id}",
                content_hash=compute_content_hash(content),
                processor="document_parser",
                processor_version="1.0",
                processing_params={
                    "parser": getattr(collection, "doc_parser", "default"),
                },
                primary_parent_id=parent_id,
                parent_lineage_hash=parent_lineage_hash,
            )
            if parse_node:
                parse_provenance_id = parse_node.id
        except Exception:
            logger.warning("Failed to record PARSE_RESULT provenance for doc %s", document_id)

        return ParsedDocumentData(
            document_id=document_id,
            collection_id=collection.id,
            content=content,
            doc_parts=doc_parts,
            file_path=local_doc.path,
            local_doc_info=local_doc_info,
            run_id=run_id,
            parse_provenance_id=parse_provenance_id,
        )

    def create_index(self, document_id: str, index_type: str, parsed_data: ParsedDocumentData) -> IndexTaskResult:
        """
        Create a single index for a document using parsed data

        Args:
            document_id: Document ID
            index_type: Type of index to create
            parsed_data: Parsed document data

        Returns:
            IndexTaskResult containing operation result
        """
        logger.info(f"Creating {index_type} index for document {document_id}")

        # Get collection
        from aperag.tasks.utils import get_document_and_collection

        _, collection = get_document_and_collection(document_id)

        try:
            if index_type == DocumentIndexType.VECTOR.value:
                from aperag.index.vector_index import vector_indexer

                result = vector_indexer.create_index(
                    document_id=document_id,
                    content=parsed_data.content,
                    doc_parts=parsed_data.doc_parts,
                    collection=collection,
                    file_path=parsed_data.file_path,
                    run_id=parsed_data.run_id,
                    parse_provenance_id=parsed_data.parse_provenance_id,
                )
                if not result.success:
                    raise Exception(result.error)
                result_data = result.data or {"success": True}

            elif index_type == DocumentIndexType.FULLTEXT.value:
                from aperag.index.fulltext_index import fulltext_indexer

                result = fulltext_indexer.create_index(
                    document_id=document_id,
                    content=parsed_data.content,
                    doc_parts=parsed_data.doc_parts,
                    collection=collection,
                    file_path=parsed_data.file_path,
                    run_id=parsed_data.run_id,
                    parse_provenance_id=parsed_data.parse_provenance_id,
                )
                if not result.success:
                    raise Exception(result.error)
                result_data = result.data or {"success": True}

            elif index_type == DocumentIndexType.GRAPH.value:
                from aperag.index.graph_index import graph_indexer

                if not graph_indexer.is_enabled(collection):
                    logger.info(f"Graph indexing disabled for document {document_id}")
                    result_data = {"success": True, "message": "Graph indexing disabled"}
                else:
                    from aperag.graph.lightrag_manager import process_document_for_celery

                    result = process_document_for_celery(
                        collection=collection,
                        content=parsed_data.content,
                        doc_id=document_id,
                        file_path=parsed_data.file_path,
                    )
                    if result.get("status") != "success":
                        error_msg = result.get("message", "Unknown error")
                        raise Exception(f"Graph indexing failed: {error_msg}")
                    result_data = result

                    # Record GRAPH_CHUNK provenance
                    if parsed_data.run_id and result.get("chunks"):
                        try:
                            from aperag.db.models_provenance import ArtifactType, InputRole, compute_content_hash
                            from aperag.service.provenance_service import ProvenanceService

                            prov = ProvenanceService()
                            chunks_data = result.get("chunks_data", {})

                            # Build chunk_id → provenance_node_id mapping for entity/relation inputs
                            graph_chunk_prov_map = {}
                            for chunk_id in result.get("chunks", []):
                                chunk_content = chunks_data.get(chunk_id, {}).get("content", "")
                                chunk_hash = compute_content_hash(chunk_content) if chunk_content else chunk_id
                                chunk_node = prov.create_node(
                                    document_id=document_id,
                                    collection_id=collection.id,
                                    run_id=parsed_data.run_id,
                                    artifact_type=ArtifactType.GRAPH_CHUNK.value,
                                    artifact_key=f"{document_id}:graphchunk:{chunk_id}",
                                    content_hash=chunk_hash,
                                    processor="lightrag_chunker",
                                    processor_version="1.0",
                                    primary_parent_id=parsed_data.parse_provenance_id,
                                )
                                if chunk_node:
                                    graph_chunk_prov_map[chunk_id] = chunk_node.id

                            # Record ENTITY provenance (DAG via ProvenanceInput)
                            for ent in result.get("entity_details", []):
                                ent_name = ent.get("entity_name", "")
                                ent_source_ids = ent.get("source_ids", [])
                                if not ent_name:
                                    continue
                                ent_hash = compute_content_hash(ent_name)
                                ent_node = prov.create_node(
                                    document_id=document_id,
                                    collection_id=collection.id,
                                    run_id=parsed_data.run_id,
                                    artifact_type=ArtifactType.ENTITY.value,
                                    artifact_key=f"{document_id}:entity:{ent_hash[:16]}",
                                    content_hash=ent_hash,
                                    processor="lightrag_entity_extractor",
                                    processor_version="1.0",
                                    processing_params={"entity_type": ent.get("entity_type", "")},
                                    primary_parent_id=parsed_data.parse_provenance_id,
                                )
                                if ent_node and ent_source_ids:
                                    inputs = []
                                    for idx, src_id in enumerate(ent_source_ids):
                                        chunk_prov_id = graph_chunk_prov_map.get(src_id)
                                        if chunk_prov_id:
                                            inputs.append({
                                                "input_node_id": chunk_prov_id,
                                                "input_role": InputRole.MERGED_SOURCE.value,
                                                "input_order": idx,
                                            })
                                    if inputs:
                                        prov.record_inputs(ent_node.id, inputs)

                            # Record RELATION provenance (DAG via ProvenanceInput)
                            for rel in result.get("relation_details", []):
                                src = rel.get("src_id", "")
                                tgt = rel.get("tgt_id", "")
                                rel_source_ids = rel.get("source_ids", [])
                                if not src or not tgt:
                                    continue
                                rel_key = f"{src}:{tgt}"
                                rel_hash = compute_content_hash(rel_key)
                                rel_node = prov.create_node(
                                    document_id=document_id,
                                    collection_id=collection.id,
                                    run_id=parsed_data.run_id,
                                    artifact_type=ArtifactType.RELATION.value,
                                    artifact_key=f"{document_id}:relation:{rel_hash[:16]}",
                                    content_hash=rel_hash,
                                    processor="lightrag_relation_extractor",
                                    processor_version="1.0",
                                    processing_params={"src": src, "tgt": tgt},
                                    primary_parent_id=parsed_data.parse_provenance_id,
                                )
                                if rel_node and rel_source_ids:
                                    inputs = []
                                    for idx, src_id in enumerate(rel_source_ids):
                                        chunk_prov_id = graph_chunk_prov_map.get(src_id)
                                        if chunk_prov_id:
                                            inputs.append({
                                                "input_node_id": chunk_prov_id,
                                                "input_role": InputRole.MERGED_SOURCE.value,
                                                "input_order": idx,
                                            })
                                    if inputs:
                                        prov.record_inputs(rel_node.id, inputs)

                        except Exception:
                            logger.debug("Failed to record graph provenance for doc %s", document_id)

            elif index_type == DocumentIndexType.SUMMARY.value:
                from aperag.index.summary_index import summary_indexer
                from aperag.schema.utils import parseCollectionConfig

                # Check if summary is enabled in collection config
                config = parseCollectionConfig(collection.config)
                if not config.enable_summary:
                    logger.info(f"Summary indexing disabled for document {document_id}")
                    result_data = {"success": True, "message": "Summary indexing disabled"}
                else:
                    result = summary_indexer.create_index(
                        document_id=document_id,
                        content=parsed_data.content,
                        doc_parts=parsed_data.doc_parts,
                        collection=collection,
                        file_path=parsed_data.file_path,
                        run_id=parsed_data.run_id,
                        parse_provenance_id=parsed_data.parse_provenance_id,
                    )
                    if not result.success:
                        raise Exception(result.error)
                    result_data = result.data or {"success": True}

            elif index_type == DocumentIndexType.VISION.value:
                from aperag.index.vision_index import vision_indexer

                if not vision_indexer.is_enabled(collection):
                    logger.info(f"Vision indexing disabled for document {document_id}")
                    result_data = {"success": True, "message": "Vision indexing disabled"}
                else:
                    result = vision_indexer.create_index(
                        document_id=document_id,
                        content=parsed_data.content,
                        doc_parts=parsed_data.doc_parts,
                        collection=collection,
                        file_path=parsed_data.file_path,
                        run_id=parsed_data.run_id,
                        parse_provenance_id=parsed_data.parse_provenance_id,
                    )
                    if not result.success:
                        raise Exception(result.error)
                    result_data = result.data or {"success": True}
            else:
                raise ValueError(f"Unknown index type: {index_type}")

            return IndexTaskResult.success_result(
                index_type=index_type,
                document_id=document_id,
                data=result_data,
                message=f"Successfully created {index_type} index",
            )

        except Exception as e:
            error_msg = f"Failed to create {index_type} index: {str(e)}"
            logger.error(f"Document {document_id}: {error_msg}")
            return IndexTaskResult.failed_result(index_type=index_type, document_id=document_id, error=error_msg)

    def delete_index(self, document_id: str, index_type: str) -> IndexTaskResult:
        """
        Delete a single index for a document

        Args:
            document_id: Document ID
            index_type: Type of index to delete

        Returns:
            IndexTaskResult containing operation result
        """
        logger.info(f"Deleting {index_type} index for document {document_id}")

        from aperag.tasks.utils import get_document_and_collection

        _, collection = get_document_and_collection(document_id, ignore_deleted=False)

        try:
            if index_type == DocumentIndexType.VECTOR.value:
                from aperag.index.vector_index import vector_indexer

                result = vector_indexer.delete_index(document_id, collection)
                if not result.success:
                    raise Exception(result.error)

            elif index_type == DocumentIndexType.FULLTEXT.value:
                from aperag.index.fulltext_index import fulltext_indexer

                result = fulltext_indexer.delete_index(document_id, collection)
                if not result.success:
                    raise Exception(result.error)

            elif index_type == DocumentIndexType.GRAPH.value:
                from aperag.index.graph_index import graph_indexer

                if graph_indexer.is_enabled(collection):
                    from aperag.graph.lightrag_manager import delete_document_for_celery

                    result = delete_document_for_celery(collection=collection, doc_id=document_id)
                    if result.get("status") != "success":
                        error_msg = result.get("message", "Unknown error")
                        raise Exception(f"Graph index deletion failed: {error_msg}")

            elif index_type == DocumentIndexType.SUMMARY.value:
                from aperag.index.summary_index import summary_indexer

                result = summary_indexer.delete_index(document_id, collection)
                if not result.success:
                    raise Exception(result.error)

            elif index_type == DocumentIndexType.VISION.value:
                from aperag.index.vision_index import vision_indexer

                result = vision_indexer.delete_index(document_id, collection)
                if not result.success:
                    raise Exception(result.error)

            else:
                raise ValueError(f"Unknown index type: {index_type}")

            return IndexTaskResult.success_result(
                index_type=index_type, document_id=document_id, message=f"Successfully deleted {index_type} index"
            )

        except Exception as e:
            error_msg = f"Failed to delete {index_type} index: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return IndexTaskResult.failed_result(index_type=index_type, document_id=document_id, error=error_msg)

    def update_index(self, document_id: str, index_type: str, parsed_data: ParsedDocumentData) -> IndexTaskResult:
        """
        Update a single index for a document using parsed data

        Args:
            document_id: Document ID
            index_type: Type of index to update
            parsed_data: Parsed document data

        Returns:
            IndexTaskResult containing operation result
        """
        logger.info(f"Updating {index_type} index for document {document_id}")

        # Get collection
        from aperag.tasks.utils import get_document_and_collection

        _, collection = get_document_and_collection(document_id)

        try:
            if index_type == DocumentIndexType.VECTOR.value:
                from aperag.index.vector_index import vector_indexer

                result = vector_indexer.update_index(
                    document_id=document_id,
                    content=parsed_data.content,
                    doc_parts=parsed_data.doc_parts,
                    collection=collection,
                    file_path=parsed_data.file_path,
                )
                if not result.success:
                    raise Exception(result.error)
                result_data = result.data or {"success": True}

            elif index_type == DocumentIndexType.FULLTEXT.value:
                from aperag.index.fulltext_index import fulltext_indexer

                result = fulltext_indexer.update_index(
                    document_id=document_id,
                    content=parsed_data.content,
                    doc_parts=parsed_data.doc_parts,
                    collection=collection,
                    file_path=parsed_data.file_path,
                )
                if not result.success:
                    raise Exception(result.error)
                result_data = result.data or {"success": True}

            elif index_type == DocumentIndexType.GRAPH.value:
                from aperag.index.graph_index import graph_indexer

                if not graph_indexer.is_enabled(collection):
                    logger.info(f"Graph indexing disabled for document {document_id}")
                    result_data = {"success": True, "message": "Graph indexing disabled"}
                else:
                    from aperag.graph.lightrag_manager import process_document_for_celery

                    result = process_document_for_celery(
                        collection=collection,
                        content=parsed_data.content,
                        doc_id=document_id,
                        file_path=parsed_data.file_path,
                    )
                    if result.get("status") != "success":
                        error_msg = result.get("message", "Unknown error")
                        raise Exception(f"Graph indexing failed: {error_msg}")
                    result_data = result

            elif index_type == DocumentIndexType.SUMMARY.value:
                from aperag.index.summary_index import summary_indexer
                from aperag.schema.utils import parseCollectionConfig

                # Check if summary is enabled in collection config
                config = parseCollectionConfig(collection.config)
                if not config.enable_summary:
                    logger.info(f"Summary indexing disabled for document {document_id}")
                    result_data = {"success": True, "message": "Summary indexing disabled"}
                else:
                    result = summary_indexer.update_index(
                        document_id=document_id,
                        content=parsed_data.content,
                        doc_parts=parsed_data.doc_parts,
                        collection=collection,
                        file_path=parsed_data.file_path,
                    )
                    if not result.success:
                        raise Exception(result.error)
                    result_data = result.data or {"success": True}

            elif index_type == DocumentIndexType.VISION.value:
                from aperag.index.vision_index import vision_indexer

                if not vision_indexer.is_enabled(collection):
                    logger.info(f"Vision indexing disabled for document {document_id}")
                    result_data = {"success": True, "message": "Vision indexing disabled"}
                else:
                    result = vision_indexer.update_index(
                        document_id=document_id,
                        content=parsed_data.content,
                        doc_parts=parsed_data.doc_parts,
                        collection=collection,
                        file_path=parsed_data.file_path,
                    )
                    if not result.success:
                        raise Exception(result.error)
                    result_data = result.data or {"success": True}
            else:
                raise ValueError(f"Unknown index type: {index_type}")

            return IndexTaskResult.success_result(
                index_type=index_type,
                document_id=document_id,
                data=result_data,
                message=f"Successfully updated {index_type} index",
            )

        except Exception as e:
            error_msg = f"Failed to update {index_type} index: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return IndexTaskResult.failed_result(index_type=index_type, document_id=document_id, error=error_msg)


document_index_task = DocumentIndexTask()
