import logging
from typing import List, Optional

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)

# BGE-family models are documented to retrieve meaningfully better when the
# QUERY (not the document/passage) is prefixed with this instruction at
# encode time; passages are embedded as-is, with no prefix. This is a real,
# model-specific quirk: getting it wrong (or just not knowing about it)
# doesn't error, it just quietly gives up part of the accuracy gain the
# model swap was for. langchain_huggingface's HuggingFaceEmbeddings has no
# built-in instruction-prefixing (that only existed on the now-deprecated
# HuggingFaceBgeEmbeddings class), so it's handled explicitly here instead.
_BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def _default_query_instruction(model_name: str) -> Optional[str]:
    name = model_name.lower()
    if "bge" in name:
        return _BGE_QUERY_INSTRUCTION
    # e5-family models want "query: " / "passage: " on BOTH sides, which is
    # a different shape of fix (documents need it too, at ingestion time) --
    # intentionally not silently handled here to avoid re-embedding under a
    # wrong assumption. If you swap to an e5 model, say so explicitly.
    return None


class _QueryInstructionEmbeddings(Embeddings):
    """
    Wraps a base Embeddings object and prepends a fixed instruction string
    to queries only (embed_query / aembed_query). embed_documents is passed
    through untouched, since Chroma calls embed_documents() at ingestion
    time and embed_query() at retrieval time on whatever embedding object
    it's handed -- this lets the two paths diverge correctly.
    """

    def __init__(self, base: Embeddings, query_instruction: str):
        self._base = base
        self._query_instruction = query_instruction

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._base.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._base.embed_query(self._query_instruction + text)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        return await self._base.aembed_documents(texts)

    async def aembed_query(self, text: str) -> List[float]:
        return await self._base.aembed_query(self._query_instruction + text)


class EmbeddingService:
    """
    Embedding service for the insurance RAG corpus.

    Uses normalized SentenceTransformers embeddings so Chroma distance scores
    remain stable across policy wording, brochure, and handbook chunks.

    `query_instruction`, if not explicitly passed, is auto-selected based on
    `model_name` (see `_default_query_instruction`) -- currently this means
    BGE-family models automatically get the recommended query-side prefix
    with no config needed, and unrecognized model families get none (safer
    than guessing wrong).
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", query_instruction: Optional[str] = None):
        logger.info("Initializing insurance embedding model: %s", model_name)
        self.model_name = model_name
        self.encode_kwargs = {"normalize_embeddings": True}

        try:
            base = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={"local_files_only": True},
                encode_kwargs=self.encode_kwargs,
            )
            logger.info("Embedding model loaded from local files.")
        except Exception as local_exc:
            logger.warning("Local embedding load failed: %s. Attempting online model load.", local_exc)
            base = HuggingFaceEmbeddings(
                model_name=model_name,
                encode_kwargs=self.encode_kwargs,
            )
            logger.info("Embedding model loaded from Hugging Face.")

        resolved_instruction = (
            query_instruction if query_instruction is not None else _default_query_instruction(model_name)
        )
        if resolved_instruction:
            logger.info(
                "Using query-side embedding instruction for '%s': %r",
                model_name, resolved_instruction,
            )
            self.embeddings = _QueryInstructionEmbeddings(base, resolved_instruction)
        else:
            self.embeddings = base

    def get_model(self) -> Embeddings:
        return self.embeddings
