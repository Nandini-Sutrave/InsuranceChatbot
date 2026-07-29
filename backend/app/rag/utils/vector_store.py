import json
import os
import logging
from typing import List, Optional
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

logger = logging.getLogger(__name__)
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

class VectorStoreManager:
    """
    Vector store manager for the insurance RAG corpus.

    Orchestrates document persistence, lexical catalog writes, and access to
    the local persistent Chroma vector database.
    """
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "insurance_policy_sections",
    ):
        if persist_directory is None:
            persist_directory = os.path.join(ROOT_DIR, "data", "vector_store", "chroma_hybrid")
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.catalog_path = os.path.join(self.persist_directory, "documents.jsonl")
        self._db = None

    def _get_client(self, embedding_model: HuggingFaceEmbeddings) -> Chroma:
        """Internal helper to instantiate or load the persistent Chroma client safely."""
        if self._db is None:
            os.makedirs(os.path.dirname(self.persist_directory), exist_ok=True)
            self._db = Chroma(
                collection_name=self.collection_name,
                persist_directory=self.persist_directory,
                embedding_function=embedding_model
            )
        return self._db

    def add_documents(self, documents: List[Document], embedding_model: HuggingFaceEmbeddings):
        """
        Loads incoming LangChain chunks into the Chroma collection.
        Batches the writes automatically to bypass Chroma's max batch size limit of 5461.
        """
        if not documents:
            logger.warning("No documents received to persist in vector store.")
            return

        db = self._get_client(embedding_model)
        ids = [doc.metadata["chunk_id"] for doc in documents]
        
        # Define a safe batch size well below the 5461 threshold
        BATCH_SIZE = 1000
        total_docs = len(documents)
        
        logger.info(f"Writing {total_docs} document chunks to Chroma at '{self.persist_directory}'...")

        # Process and upload chunks in chunks!
        for i in range(0, total_docs, BATCH_SIZE):
            batch_docs = documents[i : i + BATCH_SIZE]
            batch_ids = ids[i : i + BATCH_SIZE]
            
            logger.info(f"Uploading batch {i // BATCH_SIZE + 1} ({len(batch_docs)} chunks)...")
            db.add_documents(documents=batch_docs, ids=batch_ids)
            
        logger.info("Chroma persistence update operation complete.")

        self._write_catalog(documents)

    def _write_catalog(self, documents: List[Document]):
        """Persists chunk text and metadata for lexical/hybrid retrieval."""
        os.makedirs(self.persist_directory, exist_ok=True)
        with open(self.catalog_path, "a", encoding="utf-8") as catalog:
            for doc in documents:
                catalog.write(
                    json.dumps(
                        {
                            "page_content": doc.page_content,
                            "metadata": doc.metadata,
                        },
                        ensure_ascii=True,
                    )
                    + "\n"
                )
        logger.info("Wrote lexical retrieval catalog to '%s'.", self.catalog_path)

    def load_catalog(self) -> List[Document]:
        """Loads the persisted chunk catalog for non-vector retrieval stages."""
        if not os.path.exists(self.catalog_path):
            logger.warning("No lexical catalog found at '%s'.", self.catalog_path)
            return []

        documents: List[Document] = []
        with open(self.catalog_path, "r", encoding="utf-8") as catalog:
            for line in catalog:
                if not line.strip():
                    continue
                row = json.loads(line)
                documents.append(
                    Document(
                        page_content=row.get("page_content", ""),
                        metadata=row.get("metadata", {}),
                    )
                )
        return documents
    def get_collection_count(self) -> int:
        """Returns total vectors stored inside the current database footprint."""
        if self._db is None:
            return 0
        try:
            # Safely grab the internal collection item array size
            return len(self._db.get()["ids"])
        except Exception:
            return 0

    def get_store(self, embedding_model: HuggingFaceEmbeddings) -> Chroma:
        """Returns active database client pointer required for querying."""
        return self._get_client(embedding_model)
