import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Union

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.rag.ingestion.chunk_builder import StructuredChunkBuilder
from app.rag.ingestion.cleaner import ContentCleanerV2
from app.rag.ingestion.diagnostics import (
    build_diagnostics_report,
    print_diagnostics_summary,
    write_diagnostics_report,
)
from app.rag.ingestion.loader import HybridPDFLoader
from app.rag.ingestion.section_tree import DocumentTree, SectionTreeBuilder
from app.rag.utils.embedding_service import EmbeddingService
from app.rag.utils.vector_store import VectorStoreManager
from app.rag.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("DocumentIngestionPipeline")


class DocumentIngestor:
    """
    Generic enterprise document-intelligence ingestion pipeline:

        PDF Discovery -> Folder Metadata Extraction -> Layout Parsing ->
        Section Tree -> Structured Chunk Builder -> Metadata Enrichment ->
        Embedding -> Vector Store

    Nothing below is specific to insurance, or to any other single domain --
    the same pipeline ingests legal, finance, HR, medical, government, or
    technical-manual corpora unchanged, driven entirely by folder structure
    and generic document-type vocabulary.
    """

    def __init__(
        self,
        raw_docs_dir: Union[str, Path],
        max_chars: int = 1000,
        combine_chars: int = 500,
    ):
        self.raw_docs_dir = Path(raw_docs_dir)
        self.loader = HybridPDFLoader(
            dir_path=self.raw_docs_dir,
            enable_ocr_fallback=getattr(settings, "ENABLE_OCR_FALLBACK", True),
            ocr_min_chars=getattr(settings, "OCR_MIN_TEXT_CHARS", 20),
            ocr_dpi=getattr(settings, "OCR_RENDER_DPI", 200),
        )
        self.cleaner = ContentCleanerV2()
        self.tree_builder = SectionTreeBuilder()
        self.chunk_builder = StructuredChunkBuilder(max_characters=max_chars)
        # Model name is configurable (settings.EMBEDDING_MODEL_NAME) rather than
        # hardcoded -- see retrieval/retriever.py for the matching query-time load.
        embedding_model_name = getattr(
            settings, "EMBEDDING_MODEL_NAME", "BAAI/bge-base-en-v1.5"
        )
        self.embedding_service = EmbeddingService(model_name=embedding_model_name)
        self.vector_store_manager = VectorStoreManager()

    def _build_document_trees(self) -> tuple:
        loaded_documents = self.loader.discover_documents()
        trees: List[DocumentTree] = []
        pages_loaded = 0

        for doc in loaded_documents:
            pages_loaded += len(doc.pages)
            cleaned_pages = self.cleaner.clean_pages(doc.pages)
            tree = self.tree_builder.build(
                cleaned_pages=cleaned_pages,
                document_id=doc.document_id,
                source=doc.source,
                relative_path=doc.relative_path,
                document_type=doc.document_type,
                document_priority=doc.document_priority,
                folder_metadata=doc.folder_metadata,
            )
            trees.append(tree)

        return trees, pages_loaded

    def run_pipeline(self) -> Dict[str, Any]:
        logger.info("=== STARTING DOCUMENT INGESTION PIPELINE ===")

        import shutil
        import os
        if self.vector_store_manager.persist_directory and os.path.exists(self.vector_store_manager.persist_directory):
            logger.info("Clearing existing vector store directory at %s...", self.vector_store_manager.persist_directory)
            shutil.rmtree(self.vector_store_manager.persist_directory)

        trees, pages_loaded = self._build_document_trees()
        if pages_loaded == 0:
            logger.error("No source content loaded. Aborting ingestion process.")
            return {"status": "FAILED", "reason": "No pages extracted"}

        documents = self.chunk_builder.build_corpus_chunks(trees)
        if not documents:
            logger.error("No chunks were produced from the parsed documents. Aborting.")
            return {"status": "FAILED", "reason": "No chunks produced"}

        # Detect duplicates and filter out from embedding
        import hashlib
        seen_hashes = set()
        unique_documents = []
        duplicate_count = 0
        for doc in documents:
            normalized = " ".join(doc.page_content.lower().split())
            h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            if h in seen_hashes:
                duplicate_count += 1
            else:
                seen_hashes.add(h)
                unique_documents.append(doc)

        logger.info(
            "Passing %s unique documents to embedding and Chroma (skipped %s duplicates).",
            len(unique_documents),
            duplicate_count,
        )
        self.vector_store_manager.add_documents(
            documents=unique_documents,
            embedding_model=self.embedding_service.get_model(),
        )

        diagnostics_report = build_diagnostics_report(trees, documents)
        diagnostics_path = Path(self.vector_store_manager.persist_directory) / "ingestion_diagnostics.json"
        write_diagnostics_report(diagnostics_report, diagnostics_path)
        print_diagnostics_summary(diagnostics_report)

        # Write Ingestion Inspector file
        import json
        inspector_path = Path(self.vector_store_manager.persist_directory) / "ingested_chunks_inspector.json"
        inspect_data = []
        for doc in unique_documents:
            inspect_data.append({
                "chunk_id": doc.metadata.get("chunk_id"),
                "heading_path": doc.metadata.get("heading_path"),
                "chunk_type": doc.metadata.get("chunk_type"),
                "page_start": doc.metadata.get("page_start"),
                "page_end": doc.metadata.get("page_end"),
                "semantic_type": doc.metadata.get("semantic_type"),
                "text": doc.page_content
            })
        with open(inspector_path, "w", encoding="utf-8") as fh:
            json.dump(inspect_data, fh, indent=2, ensure_ascii=True)
        logger.info("Wrote ingestion inspector file to '%s'.", inspector_path)

        metrics_report = {
            "Documents Discovered": len(trees),
            "Pages Loaded": pages_loaded,
            "Chunks Created": len(documents),
            "Collection Size": self.vector_store_manager.get_collection_count(),
            "Diagnostics Report": str(diagnostics_path),
        }

        logger.info("=== DOCUMENT INGESTION PIPELINE PROCESSING RUN COMPLETE ===")
        print("\n" + "=" * 44)
        print("    DOCUMENT INGESTION METRICS REPORT")
        print("=" * 44)
        for metric_name, value in metrics_report.items():
            print(f"- {metric_name:22}: {value}")
        print("=" * 44 + "\n")

        return metrics_report


# Backward-compatible alias for any external code still importing the old name.
InsuranceIngestor = DocumentIngestor


if __name__ == "__main__":
    data_dir = ROOT_DIR.parent / "docs"

    try:
        DocumentIngestor(raw_docs_dir=data_dir).run_pipeline()
    except Exception as exc:
        logger.critical(
            "Ingestion execution failed at execution step: %s",
            exc,
            exc_info=True,
        )
