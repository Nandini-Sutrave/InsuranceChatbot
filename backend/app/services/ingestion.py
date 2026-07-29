import os
import time
import uuid
from typing import List, Dict, Any, Optional
import pypdf
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma

# Refactored to utilize global RAG vector store and embedding configurations


class IngestionService:
    @staticmethod
    def split_pdf_locally(file_path: str, pages_per_chunk: int = 6) -> List[str]:
        """
        Splits a PDF file into multiple smaller temporary PDF files of N pages each.
        This prevents hitting Gemini output token limits on large policy handbooks.
        """
        reader = pypdf.PdfReader(file_path)
        total_pages = len(reader.pages)
        temp_files = []
        
        for start_page in range(0, total_pages, pages_per_chunk):
            end_page = min(start_page + pages_per_chunk, total_pages)
            writer = pypdf.PdfWriter()
            
            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])
                
            temp_filename = f"{file_path}_temp_{start_page}_{end_page}.pdf"
            with open(temp_filename, "wb") as f:
                writer.write(f)
            temp_files.append(temp_filename)
            
        return temp_files

    @classmethod
    def extract_layout_markdown_with_gemini(cls, file_path: str) -> str:
        """
        Uploads PDF segments to Gemini File API and prompts gemini-1.5-flash to output
        a layout-preserving Markdown string.
        """
        import google.generativeai as genai
        
        if not settings.GEMINI_API_KEY:
            # If no API key, fallback to local text extraction
            print("No GEMINI_API_KEY found, falling back to local text extraction.")
            return cls.fallback_local_extract(file_path)

        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        # Split PDF into 6-page sub-files to stay within output limits
        temp_pdfs = cls.split_pdf_locally(file_path, pages_per_chunk=6)
        markdown_segments = []

        try:
            for index, temp_path in enumerate(temp_pdfs):
                print(f"Parsing segment {index + 1}/{len(temp_pdfs)} of {os.path.basename(file_path)}...")
                
                # Upload to Gemini File API
                uploaded_file = genai.upload_file(path=temp_path, mime_type="application/pdf")
                
                # Wait for active status
                while uploaded_file.state.name == "PROCESSING":
                    time.sleep(1)
                    uploaded_file = genai.get_file(uploaded_file.name)
                
                if uploaded_file.state.name == "FAILED":
                    raise ValueError(f"Gemini File API processing failed for segment in {file_path}")

                prompt = (
                    "Convert this PDF document page-by-page into a structure-preserving markdown representation. "
                    "Ensure that multi-column layouts are flattened correctly, headings are formatted as markdown headers (# or ##), "
                    "and all tables/grids are strictly converted to markdown tables (| Col 1 | Col 2 |). "
                    "Do not summarize or omit any policy details, waiting periods, rules, or exclusions. "
                    "Preserve bold terms and keep sections clear. Use `---` as a page separator."
                )

                model = genai.GenerativeModel("gemini-1.5-flash")
                
                # Exponential backoff retry handler for free-tier rate limits
                retries = 3
                for attempt in range(retries):
                    try:
                        response = model.generate_content([uploaded_file, prompt])
                        markdown_segments.append(response.text)
                        break
                    except Exception as e:
                        if attempt == retries - 1:
                            raise e
                        sleep_time = (attempt + 1) * 10
                        print(f"Rate limit or network error hit, retrying in {sleep_time}s... Error: {e}")
                        time.sleep(sleep_time)
                
                # Clean up file in Gemini
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass

                # Respect free-tier rate limits (15 RPM)
                time.sleep(5)

        finally:
            # Clean up local temporary PDF files
            for temp_path in temp_pdfs:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

        return "\n\n---\n\n".join(markdown_segments)

    @staticmethod
    def fallback_local_extract(file_path: str) -> str:
        """Fallback local parser if Gemini API key is missing."""
        try:
            reader = pypdf.PdfReader(file_path)
            pages_text = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)
            return "\n\n---\n\n".join(pages_text)
        except Exception as e:
            print(f"Local fallback parser failed for {file_path}: {e}")
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(10000)

    @staticmethod
    def split_markdown_by_headings(text: str) -> List[str]:
        """
        Custom splitter that splits a structure-preserving markdown string
        by its headings (#, ##, ###, ####), keeping the heading line with its content
        to preserve logical sections.
        """
        lines = text.split("\n")
        chunks = []
        current_chunk = []
        
        for line in lines:
            if line.strip().startswith(("# ", "## ", "### ", "#### ")):
                if current_chunk:
                    chunks.append("\n".join(current_chunk).strip())
                current_chunk = [line]
            else:
                current_chunk.append(line)
                
        if current_chunk:
            chunks.append("\n".join(current_chunk).strip())
            
        final_chunks = []
        # Fallback recursive splitter for sections that are exceptionally large
        sub_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=250)
        
        for chunk in chunks:
            if not chunk.strip():
                continue
            if len(chunk) > 1800:
                # If a section is too big, sub-split it but try to keep the header line if possible
                header_line = ""
                body_lines = chunk.split("\n")
                if body_lines[0].strip().startswith(("# ", "## ", "### ", "#### ")):
                    header_line = body_lines[0] + "\n"
                    body_text = "\n".join(body_lines[1:])
                else:
                    body_text = chunk
                
                sub_chunks = sub_splitter.split_text(body_text)
                for sc in sub_chunks:
                    final_chunks.append(f"{header_line}{sc}".strip())
            else:
                final_chunks.append(chunk)
                
        return final_chunks

    @classmethod
    def ingest_document(cls, document_id: uuid.UUID, custom_metadata: Optional[Dict[str, str]] = None) -> None:
        """
        Executes the layout-aware ingestion pipeline:
        1. Sends PDF to Gemini for structure-preserving Markdown extraction.
        2. Splits text into hierarchical Parent-Child chunks.
        3. Embeds child chunks in ChromaDB with parent text stored in metadata.
        4. Updates document status in relational DB.
        """
        db: Session = SessionLocal()
        stmt = select(Document).where(Document.id == document_id)
        doc = db.scalar(stmt)
        
        if not doc:
            db.close()
            return
 
        try:
            doc.status = "processing"
            db.commit()
 
            # 1. Extract markdown layout-aware representation
            markdown_text = cls.extract_layout_markdown_with_gemini(doc.file_path)
            if not markdown_text.strip():
                markdown_text = (
                    f"This document '{doc.filename}' appears to be a scanned PDF or contains non-extractable text layouts. "
                    f"To parse scanned PDFs via multimodal OCR, please set up a valid GEMINI_API_KEY in backend/.env. "
                    f"In offline mode, this is a placeholder chunk representing the document structure."
                )
                print(f"Warning: Extracted text for {doc.filename} is empty. Using placeholder chunk in offline/mock mode.")
 
            # 2. Hierarchical Chunking (split by page first, then by parent-child chunks)
            pages = [p.strip() for p in markdown_text.split("---") if p.strip()]
            child_splitter = RecursiveCharacterTextSplitter(chunk_size=350, chunk_overlap=75)
 
            texts_to_embed = []
            metadatas = []
            ids = []
            
            chunk_counter = 0
            for page_index, page_text in enumerate(pages):
                page_number = page_index + 1
                parent_chunks = cls.split_markdown_by_headings(page_text)
                
                for parent_text in parent_chunks:
                    # Split parent chunk into child chunks
                    child_chunks = child_splitter.split_text(parent_text)
                    
                    for child_text in child_chunks:
                        texts_to_embed.append(child_text)
                        
                        # Store parent text in metadata for parent-child reconstruction
                        meta = {
                            "document_id": str(doc.id),
                            "product_id": str(doc.product_id),
                            "filename": doc.filename,
                            "parent_text": parent_text,
                            "chunk_index": chunk_counter,
                            "page_number": page_number
                        }
                        
                        # Merge custom tags (LOB, Carrier)
                        if custom_metadata:
                            meta.update(custom_metadata)
 
                        metadatas.append(meta)
                        ids.append(f"{doc.id}_{chunk_counter}")
                        chunk_counter += 1

            # 3. Add to ChromaDB Vector Store using RAG utils
            from app.rag.utils.vector_store import VectorStoreManager
            from app.rag.utils.embedding_service import EmbeddingService
            from langchain_core.documents import Document as LCDocument
            
            v_store = VectorStoreManager()
            embedding_model = EmbeddingService().get_model()
            
            lc_docs = []
            for idx, text in enumerate(texts_to_embed):
                meta = metadatas[idx]
                meta["chunk_id"] = ids[idx]  # Ensure chunk_id is present in metadata
                lc_docs.append(LCDocument(page_content=text, metadata=meta))
                
            v_store.add_documents(lc_docs, embedding_model)

            # Update relational DB state
            doc.status = "completed"
            doc.error_message = None
            db.commit()
            print(f"Document {doc.filename} fully indexed inside ChromaDB. Generated {chunk_counter} child chunks.")

        except Exception as e:
            db.rollback()
            doc.status = "failed"
            doc.error_message = str(e)[:1000]
            db.commit()
            print(f"Failed to ingest document {doc.filename}: {e}")
        finally:
            db.close()

    @staticmethod
    def remove_document_vectors(document_id: uuid.UUID) -> None:
        """Removes all vector nodes associated with a document ID from ChromaDB and prunes the catalog."""
        try:
            import json
            from app.rag.utils.vector_store import VectorStoreManager
            from app.rag.utils.embedding_service import EmbeddingService
            
            v_store = VectorStoreManager()
            db = v_store._get_client(EmbeddingService().get_model())
            db.delete(where={"document_id": str(document_id)})
            print(f"Successfully deleted vectors for document ID: {document_id}")
            
            # Prune the local documents.jsonl catalog file to keep them in sync
            catalog_path = v_store.catalog_path
            if os.path.exists(catalog_path):
                temp_path = catalog_path + ".tmp"
                doc_id_str = str(document_id)
                with open(catalog_path, "r", encoding="utf-8") as fin, open(temp_path, "w", encoding="utf-8") as fout:
                    for line in fin:
                        if not line.strip():
                            continue
                        try:
                            row = json.loads(line)
                            if row.get("metadata", {}).get("document_id") == doc_id_str:
                                continue
                            fout.write(line)
                        except Exception:
                            fout.write(line)
                os.replace(temp_path, catalog_path)
                print(f"Successfully pruned catalog entries for document ID: {document_id}")
        except Exception as e:
            print(f"Failed to clean vectors from ChromaDB for document {document_id}: {e}")
