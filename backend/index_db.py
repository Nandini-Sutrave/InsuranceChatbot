import os
import sys
import json
import time
import pickle
import shutil
import logging
import re
from pathlib import Path
from typing import List, Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("IndexDB")

# Add project root to sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from langchain_core.documents import Document
from langchain_chroma import Chroma
from rank_bm25 import BM25Okapi
from app.rag.utils.embedding_service import EmbeddingService

TOKEN_PATTERN = re.compile(r"\b\w{3,}\b")

def tokenize(text: str) -> List[str]:
    return TOKEN_PATTERN.findall((text or "").lower())

def run_indexing():
    logger.info("=== STARTING DENSE & SPARSE DB INDEXING (PHASE 2) ===")
    
    # 1. Load parsed chunks from Phase 1
    chunks_path = backend_dir / "parsed_chunks_debug.json"
    if not chunks_path.exists():
        logger.error(f"Parsed chunks debug file not found: {chunks_path}")
        return
        
    with open(chunks_path, "r", encoding="utf-8") as f:
        parsed_chunks = json.load(f)
        
    logger.info(f"Loaded {len(parsed_chunks)} unique chunks from {chunks_path.name}.")
    
    # Initialize Embedding Service
    embedding_service = EmbeddingService()
    embedding_model = embedding_service.get_model()
    
    # Persistent Chroma DB Path
    chroma_dir = backend_dir / "chroma_db"
    
    # Check if Chroma directory and collection are already fully indexed
    skip_indexing = False
    if chroma_dir.exists():
        try:
            db_check = Chroma(
                collection_name="insurance_kb",
                persist_directory=str(chroma_dir),
                embedding_function=embedding_model
            )
            existing_count = len(db_check.get()["ids"])
            if existing_count == len(parsed_chunks):
                logger.info(f"Chroma collection 'insurance_kb' is already fully indexed with {existing_count} chunks. Skipping re-indexing.")
                db = db_check
                skip_indexing = True
        except Exception as e:
            logger.warning(f"Error checking existing Chroma DB, starting fresh: {e}")
            
    if not skip_indexing:
        # Clear directory if it exists to start fresh
        if chroma_dir.exists():
            logger.info(f"Clearing existing Chroma directory at {chroma_dir}...")
            shutil.rmtree(chroma_dir)
            
        os.makedirs(chroma_dir, exist_ok=True)
        
        # Convert dict chunks to LangChain Document objects
        documents = []
        ids = []
        for chunk in parsed_chunks:
            doc = Document(
                page_content=chunk["text"],
                metadata=chunk["metadata"]
            )
            documents.append(doc)
            ids.append(chunk["metadata"]["chunk_id"])
            
        # 2. Batch upload documents to Chroma
        t_start = time.time()
        db = Chroma(
            collection_name="insurance_kb",
            persist_directory=str(chroma_dir),
            embedding_function=embedding_model
        )
        
        BATCH_SIZE = 500
        total_docs = len(documents)
        logger.info(f"Indexing {total_docs} document chunks in batches of {BATCH_SIZE}...")
        
        for i in range(0, total_docs, BATCH_SIZE):
            batch_docs = documents[i : i + BATCH_SIZE]
            batch_ids = ids[i : i + BATCH_SIZE]
            db.add_documents(documents=batch_docs, ids=batch_ids)
            if (i + BATCH_SIZE) % 1000 == 0 or (i + BATCH_SIZE) >= total_docs:
                logger.info(f"Indexed {min(i + BATCH_SIZE, total_docs)}/{total_docs} chunks...")
                
        t_end = time.time()
        dense_time = t_end - t_start
        logger.info(f"Dense vector store indexing completed in {dense_time:.2f} seconds.")
    else:
        # Recreate documents and ids lists for subsequent BM25 indexing
        documents = []
        for chunk in parsed_chunks:
            doc = Document(
                page_content=chunk["text"],
                metadata=chunk["metadata"]
            )
            documents.append(doc)
    
    # 3. Build & Save BM25 Index state
    t_start = time.time()
    tokenized_corpus = [tokenize(doc.page_content) for doc in documents]
    bm25 = BM25Okapi(tokenized_corpus)
    
    bm25_path = backend_dir / "bm25_index.pkl"
    with open(bm25_path, "wb") as f:
        pickle.dump(bm25, f)
        
    # 4. Save documents.jsonl catalog
    catalog_path = chroma_dir / "documents.jsonl"
    with open(catalog_path, "w", encoding="utf-8") as f:
        for doc in documents:
            f.write(json.dumps({
                "page_content": doc.page_content,
                "metadata": doc.metadata
            }, ensure_ascii=True) + "\n")
            
    t_end = time.time()
    sparse_time = t_end - t_start
    logger.info(f"Sparse index & catalog saved in {sparse_time:.2f} seconds.")
    
    # Verification checks
    collection = db.get()
    collection_count = len(collection["ids"])
    
    # Run test metadata query
    logger.info("Running verification test query: carrier=SBI, line_of_business=Health...")
    test_results = db.get(where={"$and": [{"carrier": "SBI"}, {"line_of_business": "Health"}]}, limit=1)
    
    print("\n" + "=" * 65)
    print("    PHASE 2 INDEXING SUMMARY REPORT (V3 ARCHITECTURE)")
    print("=" * 65)
    print(f"- Chroma DB Collection name: insurance_kb")
    print(f"- Persistent Directory     : {chroma_dir.resolve()}")
    print(f"- Total Chroma Records     : {collection_count} (Expected 8680)")
    print(f"- BM25 Index Saved Path    : {bm25_path.resolve()}")
    print(f"- Catalog JSONL Saved Path : {catalog_path.resolve()}")
    
    if test_results["ids"]:
        retrieved_id = test_results["ids"][0]
        retrieved_text = test_results["documents"][0]
        retrieved_meta = test_results["metadatas"][0]
        print(f"\n- Sample Verification Query Result:")
        print(f"  * Retrieved Chunk ID: {retrieved_id}")
        print(f"  * Filename          : {retrieved_meta.get('filename')}")
        print(f"  * Product Name      : {retrieved_meta.get('product_name')}")
        print(f"  * Page Number       : {retrieved_meta.get('page_number')}")
        print(f"  * text snippet      : {retrieved_text[:180]}...")
    else:
        print("\n[WARNING] Verification query returned 0 results!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    run_indexing()
