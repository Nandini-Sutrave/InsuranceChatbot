import time
import uuid
from typing import Any, Dict, List, Optional

from app.rag.generation.generator import InsuranceAssistant


class RAGService:
    """Production API adapter for the insurance RAG pipeline."""

    @staticmethod
    def answer_query(
        query: str,
        product_id: Optional[uuid.UUID] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        started = time.time()
        assistant = InsuranceAssistant()
        result = assistant.generate_answer(
            query=query,
            product_id=str(product_id) if product_id else None,
        )

        sources = []
        for index, chunk in enumerate(result.get("retrieved_chunks", []), start=1):
            metadata = chunk.get("metadata", {}) if isinstance(chunk, dict) else chunk.metadata
            text = chunk.get("text", "") if isinstance(chunk, dict) else chunk.page_content
            sources.append({
                "document_id": metadata.get("chunk_id"),
                "filename": metadata.get("filename", "Unknown Policy"),
                "page_number": metadata.get("page_number", "Unknown"),
                "chunk_text": text,
                "section_title": f"{metadata.get('section_id', '')} {metadata.get('section_title', '')}".strip() or "General Section",
                "clause_type": metadata.get("clause_nature", "general"),
                "relevance_rank": index,
                "relevance_score": metadata.get("retrieval_score"),
            })

        return {
            "answer": result["answer"],
            "sources": sources,
            "confidence": result.get("confidence_tier", "LOW").capitalize(),
            "intent": "InsurancePolicyQuestion",
            "clause_type": sources[0]["clause_type"] if sources else "Unknown",
            "latency_ms": (time.time() - started) * 1000,
        }
