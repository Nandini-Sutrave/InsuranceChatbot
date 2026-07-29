import os
import re
import sys
import json
import time
import pickle
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Setup logging
logger = logging.getLogger(__name__)

# Add project root to sys.path
backend_dir = Path(__file__).resolve().parents[3]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from langchain_core.documents import Document
from langchain_chroma import Chroma
from sentence_transformers import CrossEncoder
from rank_bm25 import BM25Okapi
from app.rag.utils.embedding_service import EmbeddingService
from app.rag.config import settings

# Load Cross-Encoder model globally at module startup
logger.info("Loading Cross-Encoder model: cross-encoder/ms-marco-MiniLM-L-6-v2")
global_cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
logger.info("Cross-Encoder loaded successfully globally.")

# Fuzzy matching is a soft dependency, same pattern as the OCR fallback in
# ingestion/loader.py: if rapidfuzz isn't installed, Tier-1 carrier/LOB
# detection just falls back to the original exact word-boundary match --
# nothing breaks, it just loses typo/synonym tolerance.
try:
    from rapidfuzz import fuzz as _rf_fuzz
    FUZZY_MATCH_AVAILABLE = True
except ImportError:
    _rf_fuzz = None
    FUZZY_MATCH_AVAILABLE = False
    logger.info(
        "rapidfuzz not installed -- Tier-1 carrier/LOB detection will use exact "
        "keyword matching only (no typo/synonym tolerance). Install 'rapidfuzz' "
        "to enable fuzzy matching."
    )

# Standardized LOBs and Keywords.
# Values here (dict keys) are now the CANONICAL normalized form -- lowercase,
# spaces not underscores -- matching exactly what loader.py's
# _normalize_lob_token() stores in chunk metadata. Previously these keys were
# ad-hoc capitalized/underscored strings ("Personal_Accident", "Cyber") that
# never matched the actual stored folder-derived values ("Personal Accident",
# "cyber"), so this filter silently matched nothing at query time.
LOB_KEYWORDS = {
    "health": ["health", "medical", "hospital", "mediclaim", "disease", "illness", "treatment", "doctor", "copay", "maternity", "pregnancy", "icu", "opd", "waiting period", "corona", "rakshak", "surrogacy", "oocyte", "donor", "divyang", "alpha", "edge", "easy health"],
    "motor": ["motor", "car", "package", "bike", "two wheeler", "twowheeler", "vehicle", "driver", "own damage", "third party", "tpl", "act only", "residual", "value"],
    "home": ["home", "house", "grih", "raksha", "building", "structure", "flexi home", "fire", "earthquake"],
    "personal accident": ["accident", "personal accident", "accidental death", "disability", "ptd", "ppd", "saral suraksha", "injury", "injured"],
    "cyber": ["cyber", "vault", "edge", "hacking", "fraud", "hacker", "phishing", "online theft", "digital"],
    "travel": ["travel", "trip", "flight", "holiday", "baggage", "passport", "visa", "medical evacuation"],
    "group": ["group", "employee", "gratuity", "employer", "credit protect", "shield", "master policy", "poorna", "jeevan suraksha"],
    "protection": ["protection", "term", "death benefit", "click 2 protect", "elite", "supreme", "ultimate", "smart term", "life cover"],
    "retirement": ["retirement", "pension", "annuity", "immediate annuity", "systematic pension", "age-at-entry"],
    "savings": ["savings", "fixed maturity", "sanchay", "wealth", "sampoorn", "sampoorna", "par advantage", "income plan", "invest"],
    "rider": ["rider", "add-on", "addon", "cash benefit", "waiver of premium", "critical illness plus"],
    "regulations": ["regulation", "guidelines", "pos", "posp", "salesperson", "handbook", "agent", "training"]
}

TOKEN_PATTERN = re.compile(r"\b\w{3,}\b")

def tokenize(text: str) -> List[str]:
    return TOKEN_PATTERN.findall((text or "").lower())

class HybridRetriever:
    """
    Two-Tier Hybrid Retriever for Insurance/Scheme Knowledge Base.
    Uses ChromaDB for dense retrieval and BM25 for sparse retrieval, combined via RRF
    and reranked using a Cross-Encoder with a strict confidence threshold.
    """
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "insurance_kb",
    ):
        if persist_directory is None:
            persist_directory = os.path.join(backend_dir, "chroma_db")
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.catalog_path = os.path.join(self.persist_directory, "documents.jsonl")
        
        logger.info(f"Loading HybridRetriever from persist_directory: {self.persist_directory}")
        
        # 1. Initialize Embedding model and Chroma client
        # Model name is configurable (settings.EMBEDDING_MODEL_NAME) rather than
        # hardcoded, so it can be swapped/benchmarked without a code change.
        # NOTE: if you change this, you must re-run ingestion so Chroma holds
        # vectors from the same model this retriever will query with.
        embedding_model_name = getattr(
            settings, "EMBEDDING_MODEL_NAME", "BAAI/bge-base-en-v1.5"
        )
        self.embedding_service = EmbeddingService(model_name=embedding_model_name)
        self.embedding_model = self.embedding_service.get_model()
        
        self.db = Chroma(
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
            embedding_function=self.embedding_model
        )
        
        # 2. Load documents.jsonl catalog
        self.catalog_documents = self._load_catalog()
        
        # 3. Load BM25 index
        bm25_pkl_path = os.path.join(backend_dir, "bm25_index.pkl")
        if os.path.exists(bm25_pkl_path):
            try:
                with open(bm25_pkl_path, "rb") as f:
                    self.global_bm25 = pickle.load(f)
                logger.info(f"Loaded BM25 index from {bm25_pkl_path}")
            except Exception as e:
                logger.warning(f"Failed to load BM25 index pickle: {e}. Building on demand.")
                self.global_bm25 = self._build_bm25_index(self.catalog_documents)
        else:
            logger.warning("BM25 index pickle not found. Building on demand.")
            self.global_bm25 = self._build_bm25_index(self.catalog_documents)
            
        # 4. Load Cross-Encoder model
        self.cross_encoder = global_cross_encoder
        logger.info("Cross-Encoder reference loaded successfully.")

        # 5. chunk_id -> Document lookup, used to stitch in neighbor chunks
        # (previous_chunk_id/next_chunk_id are already computed at ingestion
        # time but were previously never used downstream).
        self.chunk_id_to_doc: Dict[str, Document] = {
            doc.metadata.get("chunk_id"): doc
            for doc in self.catalog_documents
            if doc.metadata.get("chunk_id")
        }

        # 6. (filename, page_number) -> Document lookup, used for sibling context expansion
        self.filename_page_to_doc: Dict[Tuple[str, int], Document] = {}
        for doc in self.catalog_documents:
            filename = doc.metadata.get("filename")
            page_num = doc.metadata.get("page_number")
            if filename and page_num is not None:
                try:
                    self.filename_page_to_doc[(filename, int(page_num))] = doc
                except (ValueError, TypeError):
                    pass

    def _load_catalog(self) -> List[Document]:
        if not os.path.exists(self.catalog_path):
            logger.warning(f"No catalog found at {self.catalog_path}")
            return []
            
        documents = []
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                documents.append(
                    Document(
                        page_content=row.get("page_content", ""),
                        metadata=row.get("metadata", {}) or {}
                    )
                )
        logger.info(f"Loaded {len(documents)} catalog documents.")
        return documents

    def _build_bm25_index(self, documents: List[Document]) -> BM25Okapi:
        tokenized_corpus = [tokenize(doc.page_content) for doc in documents]
        return BM25Okapi(tokenized_corpus)

    def _detect_policy_in_query(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Tier 1: Detect Carrier and Line of Business (LOB) from user query.

        Runs an exact word-boundary pass first (cheap, precise, zero false
        positives). If that finds nothing, and settings.FUZZY_MATCH_LOB_CARRIER
        is on and rapidfuzz is installed, a second fuzzy pass catches typos and
        near-misses ("saral suraksha byma", "corana rakshak") that would
        otherwise silently fall through to an unfiltered global search --
        which is safe, but throws away a real, cheap accuracy win the exact
        filter could have given.
        """
        q_low = query.lower()

        # 1. Detect carrier (exact pass)
        carrier = None
        if "sbi" in q_low and "hdfc" in q_low:
            carrier = None  # bypass filtering; retrieve_relevant_chunks() balances both carriers explicitly
        elif "sbi" in q_low:
            carrier = "SBI"
        elif "hdfc" in q_low:
            carrier = "HDFC"

        # 2. Detect Line of Business (exact pass)
        detected_lob = None
        for lob, keywords in LOB_KEYWORDS.items():
            for kw in keywords:
                # Use word boundary search to prevent false positive substring matches
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, q_low):
                    detected_lob = lob
                    break
            if detected_lob:
                break

        # 3. Fuzzy fallback pass -- only runs for whichever of carrier/LOB the
        #    exact pass didn't find, and only if enabled + available.
        fuzzy_enabled = getattr(settings, "FUZZY_MATCH_LOB_CARRIER", True) and FUZZY_MATCH_AVAILABLE
        if fuzzy_enabled:
            threshold = getattr(settings, "FUZZY_MATCH_THRESHOLD", 85)

            if carrier is None and not ("sbi" in q_low and "hdfc" in q_low):
                fuzzy_carrier = self._fuzzy_detect_carrier(q_low, threshold)
                if fuzzy_carrier:
                    logger.info("Fuzzy match found carrier '%s' (no exact match).", fuzzy_carrier)
                    carrier = fuzzy_carrier

            if detected_lob is None:
                fuzzy_lob = self._fuzzy_detect_lob(q_low, threshold)
                if fuzzy_lob:
                    logger.info("Fuzzy match found LOB '%s' (no exact match).", fuzzy_lob)
                    detected_lob = fuzzy_lob

        return carrier, detected_lob

    @staticmethod
    def _fuzzy_detect_carrier(q_low: str, threshold: float) -> Optional[str]:
        """Token-level fuzzy match against known carrier names. Only compares
        whole query tokens (not arbitrary substrings) to avoid false
        positives on short 3-4 letter carrier codes like 'SBI'."""
        candidates = {"SBI": "sbi", "HDFC": "hdfc"}
        best_carrier, best_score = None, 0.0
        for token in TOKEN_PATTERN.findall(q_low):
            for carrier_name, alias in candidates.items():
                score = _rf_fuzz.ratio(token, alias)
                if score > best_score:
                    best_score, best_carrier = score, carrier_name
        return best_carrier if best_score >= threshold else None

    @staticmethod
    def _fuzzy_detect_lob(q_low: str, threshold: float) -> Optional[str]:
        """Fuzzy substring match (rapidfuzz.partial_ratio) against every LOB
        keyword, including multi-word phrases ("corona rakshak", "saral
        suraksha"). Picks the single best-scoring keyword across all LOBs,
        tie-broken by keyword length, rather than the first one to clear the
        threshold.

        min_kw_len=6 matters here, not just as an arbitrary cutoff: several
        product-name fragments recur as generic words across multiple LOBs
        in this corpus (e.g. "raksha" appears in both a health product name
        and a home product name), so a naive short-substring match can tie
        the correct LOB with a wrong one on nothing but a shared common word.
        Length-based tie-breaking additionally prefers the more specific
        (longer) keyword when two LOBs still score equally."""
        best_lob, best_score, best_kw_len = None, 0.0, 0
        min_kw_len = 6
        for lob, keywords in LOB_KEYWORDS.items():
            for kw in keywords:
                if len(kw) < min_kw_len:
                    continue
                score = _rf_fuzz.partial_ratio(kw, q_low)
                if score > best_score or (score == best_score and len(kw) > best_kw_len):
                    best_score, best_lob, best_kw_len = score, lob, len(kw)
        return best_lob if best_score >= threshold else None

    def retrieve_relevant_chunks(self, query: str) -> List[Dict[str, Any]]:
        logger.info(f"Retrieving relevant chunks for query: '{query}'")
        
        # Tier 1: Intent Pre-Filtering
        carrier, lob = self._detect_policy_in_query(query)
        
        # Identify administrative/claim intent to expand search query and disable LOB pre-filtering
        admin_keywords = ["document", "documents", "required", "file", "claim", "claims", "form", "forms", "procedure", "process", "checklist"]
        query_lower = query.lower()
        is_admin_query = any(k in query_lower for k in admin_keywords)

        if is_admin_query:
            logger.info("Admin/Claim query detected: skipping LOB pre-filter to prevent taxonomy/folder mismatches.")
            lob = None

        where = None
        if carrier and lob:
            where = {"$and": [{"carrier": carrier}, {"line_of_business": lob}]}
            logger.info(f"Pre-filter matched Carrier: {carrier} | LOB: {lob}")
        elif carrier:
            where = {"carrier": carrier}
            logger.info(f"Pre-filter matched Carrier: {carrier}")
        elif lob:
            where = {"line_of_business": lob}
            logger.info(f"Pre-filter matched LOB: {lob}")
        else:
            logger.info("No query filters applied (global search).")
            
        search_query = query
        if is_admin_query:
            # Append administrative context keywords to assist matching administrative sections
            search_query = query + " claim form documents checklist required proof submission"
            logger.info(f"Admin/Claim intent detected. Expanded query for search: '{search_query}'")
            
        # Tier 2: Hybrid Retrieval
        # A. Dense search (Top 25)
        dense_docs_with_score = self.db.similarity_search_with_score(search_query, k=25, filter=where)
        dense_results = [doc for doc, _ in dense_docs_with_score]

        # Safety net: a Tier-1 filter that matches nothing (taxonomy drift,
        # a new carrier not yet in KNOWN_CARRIER_PREFIXES, a folder rename)
        # should degrade to an unfiltered search, not silently return empty.
        # This is exactly the failure mode that was previously masking real,
        # answerable documents behind a metadata mismatch.
        if where and not dense_results:
            logger.warning(f"Tier-1 filter {where} matched 0 documents - falling back to unfiltered global search.")
            where = None
            dense_docs_with_score = self.db.similarity_search_with_score(search_query, k=25, filter=None)
            dense_results = [doc for doc, _ in dense_docs_with_score]
        
        # B. Sparse search (Top 25) restricted to filtered subset
        filtered_docs = []
        for doc in self.catalog_documents:
            meta = doc.metadata or {}
            match = True
            if where:
                if "$and" in where:
                    for cond in where["$and"]:
                        for k, v in cond.items():
                            if meta.get(k) != v:
                                match = False
                                break
                else:
                    for k, v in where.items():
                        if meta.get(k) != v:
                            match = False
                            break
            if match:
                filtered_docs.append(doc)
                
        # Build local BM25 index for the filtered subset if applicable
        if where and filtered_docs:
            local_bm25 = self._build_bm25_index(filtered_docs)
            q_tokens = tokenize(search_query)
            sparse_scores = local_bm25.get_scores(q_tokens)
            top_sparse_indices = np.argsort(sparse_scores)[::-1][:25]
            sparse_results = [filtered_docs[idx] for idx in top_sparse_indices if sparse_scores[idx] > 0]
        else:
            q_tokens = tokenize(search_query)
            sparse_scores = self.global_bm25.get_scores(q_tokens)
            top_sparse_indices = np.argsort(sparse_scores)[::-1][:25]
            sparse_results = [self.catalog_documents[idx] for idx in top_sparse_indices if sparse_scores[idx] > 0]
            
        # C. Reciprocal Rank Fusion (K=60)
        dense_ranks = {doc.metadata["chunk_id"]: idx for idx, doc in enumerate(dense_results)}
        sparse_ranks = {doc.metadata["chunk_id"]: idx for idx, doc in enumerate(sparse_results)}
        
        rrf_scores = {}
        doc_map = {}
        for doc in dense_results:
            doc_map[doc.metadata["chunk_id"]] = doc
        for doc in sparse_results:
            doc_map[doc.metadata["chunk_id"]] = doc
            
        for chunk_id, rank in dense_ranks.items():
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1.0 / (60.0 + rank)
        for chunk_id, rank in sparse_ranks.items():
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1.0 / (60.0 + rank)
            
        is_comparison_query = "sbi" in query.lower() and "hdfc" in query.lower()

        if is_comparison_query:
            # C2. Carrier-balanced pooling: RRF alone can let one carrier
            # dominate the top-15 purely on relevance score, silently
            # answering a comparison question with only one side. Take the
            # top-ranked chunks per carrier separately, then merge.
            per_carrier_ids: Dict[str, List[str]] = {}
            for cid in sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True):
                doc = doc_map[cid]
                carrier_val = (doc.metadata.get("carrier") or "OTHER").upper()
                per_carrier_ids.setdefault(carrier_val, []).append(cid)
            balanced_ids: List[str] = []
            per_side = 8  # up to 8 candidates per carrier for a total of 15
            for carrier_val, ids in per_carrier_ids.items():
                balanced_ids.extend(ids[:per_side])
            # keep overall RRF order within the balanced set
            balanced_ids.sort(key=lambda x: rrf_scores[x], reverse=True)
            sorted_chunk_ids = balanced_ids[:15]
        else:
            sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:15]

        candidates = [doc_map[cid] for cid in sorted_chunk_ids]
        
        # D. Cross-Encoder Reranking
        pairs = [[query, doc.page_content] for doc in candidates]
        if pairs:
            logits = self.cross_encoder.predict(pairs)
            # Sigmoid normalization: score = 1 / (1 + exp(-logit))
            semantic_scores = 1.0 / (1.0 + np.exp(-logits))

            # D2. Authority blend: fold in document_priority (set at ingestion
            # time from doc-type: policy wording > CIS > schedule > prospectus
            # > reference > marketing) so authoritative sources win ties
            # against fluent-but-shallow marketing copy. This uses metadata
            # that was already being computed but never consumed.
            meta_weight = getattr(settings, "RERANK_META_WEIGHT", 0.0)
            coverage_weight = getattr(settings, "RERANK_COVERAGE_WEIGHT", 0.0)
            retrieved_weight = getattr(settings, "RERANK_RETRIEVED_WEIGHT", 1.0)
            # normalize so the three weights always sum to 1 even if settings drift
            weight_sum = max(retrieved_weight + meta_weight + coverage_weight, 1e-6)

            final_scores = []
            for doc, sem_score in zip(candidates, semantic_scores):
                priority = doc.metadata.get("document_priority", 55)
                try:
                    priority_norm = min(float(priority), 100.0) / 100.0
                except (TypeError, ValueError):
                    priority_norm = 0.55

                # Cheap proxy for "this chunk has concrete coverage data"
                # (sums, %, tables) rather than narrative text -- rewards
                # CIS/wording payout tables over descriptive prose.
                text = doc.page_content or ""
                numeric_hits = len(re.findall(r"(?:rs\.?|inr|₹|\d+%|\d+\.\d+|\btable\b)", text.lower()))
                coverage_signal = min(numeric_hits / 8.0, 1.0)

                blended = (
                    retrieved_weight * float(sem_score)
                    + meta_weight * priority_norm
                    + coverage_weight * coverage_signal
                ) / weight_sum
                
                # Sibling Procedural Boost: reward chunks containing procedural terms 
                # (claim form, documents required, death registration, etc.) when the query intent is administrative.
                if is_admin_query:
                    doc_text_lower = text.lower()
                    if any(t in doc_text_lower for t in ["claim form", "basic documentation", "documents in support", "claimant's identity", "death certificate", "death registration", "police report"]):
                        blended += 0.35 # significant boost to pull procedural pages to rank #1
                
                # Product Name Match Boost: reward chunks matching the specific policy name keyword in the query
                product_boost = 0.0
                filename_lower = (doc.metadata.get("filename") or "").lower()
                filename_norm = filename_lower.replace("-", " ").replace("_", " ")
                for kw in ["sanchay aajeevan", "sanchay plus", "sanchay par", "fixed maturity", "saral suraksha", "corona rakshak", "click 2 protect", "group term", "health protector", "smart pension", "livewell", "group health shield", "group illness"]:
                    if kw in query_lower and kw in filename_norm:
                        product_boost = 0.40
                        break
                blended += product_boost

                final_scores.append(blended)

            scored_docs = list(zip(candidates, final_scores, semantic_scores))
            scored_docs.sort(key=lambda x: x[1], reverse=True)
        else:
            scored_docs = []

        # E. Graduated confidence, not a binary cutoff.
        # A hard "< 0.70 -> return nothing" throws away perfectly usable
        # medium-confidence answers. Below HIGH we still answer, but the
        # caller (generator.py) is told the tier so it can add a caveat
        # instead of presenting it as certain. Only genuinely low scores
        # (no real match at all) trigger the empty-list / ticket-raise path.
        low_threshold = getattr(settings, "CONFIDENCE_THRESHOLD", 0.70) - 0.20  # e.g. 0.50
        high_threshold = getattr(settings, "CONFIDENCE_THRESHOLD", 0.70)

        top_score = scored_docs[0][1] if scored_docs else 0.0
        if not scored_docs or top_score < low_threshold:
            logger.warning(f"Top score {top_score:.4f} below low-confidence floor ({low_threshold:.2f}). Returning empty list.")
            return []

        tier = "HIGH" if top_score >= high_threshold else "MEDIUM"

        # F. Diversity cap: don't let one document's near-duplicate chunks
        # crowd out complementary sources (e.g. all 6 slots from the same CIS
        # page, leaving no room for a wording-doc exclusion clause).
        max_per_document = getattr(settings, "MAX_CHUNKS_PER_DOCUMENT", 3)
        per_doc_count: Dict[str, int] = {}
        selected: List[Tuple[Any, float, float]] = []
        overflow: List[Tuple[Any, float, float]] = []
        for doc, blended_score, sem_score in scored_docs:
            doc_id = doc.metadata.get("document_id") or doc.metadata.get("filename")
            count = per_doc_count.get(doc_id, 0)
            if count < max_per_document:
                selected.append((doc, blended_score, sem_score))
                per_doc_count[doc_id] = count + 1
            else:
                overflow.append((doc, blended_score, sem_score))
            if len(selected) >= 5: # Capped at top 5 chunks
                break
        # backfill from overflow if the diversity cap left slots unfilled
        # (e.g. fewer distinct documents than 5)
        while len(selected) < 5 and overflow:
            selected.append(overflow.pop(0))

        # G. Neighbor-chunk stitching for the top 2 results only (cheap, and
        # those are the chunks most likely to anchor the final answer). Pulls
        # in previous_chunk_id/next_chunk_id text so a table/clause split
        # across a chunk boundary isn't handed to the LLM half-truncated.
        token_budget = getattr(settings, "CONTEXT_TOKEN_BUDGET", 3500)
        total_tokens = 0
        added_chunk_ids = set()
        final_results = []

        for i, (doc, blended_score, sem_score) in enumerate(selected):
            chunk_id = doc.metadata.get("chunk_id")
            if chunk_id in added_chunk_ids:
                continue

            text = doc.page_content
            if i < 2:
                prev_id = doc.metadata.get("previous_chunk_id")
                next_id = doc.metadata.get("next_chunk_id")
                prev_doc = self.chunk_id_to_doc.get(prev_id) if prev_id else None
                next_doc = self.chunk_id_to_doc.get(next_id) if next_id else None
                if prev_doc is not None:
                    text = prev_doc.page_content[-400:] + "\n" + text
                if next_doc is not None:
                    text = text + "\n" + next_doc.page_content[:400]

            chunk_tokens = max(1, len(text) // 4)
            if total_tokens + chunk_tokens <= token_budget:
                final_results.append({
                    "text": text,
                    "metadata": doc.metadata,
                    "score": float(blended_score),
                    "semantic_score": float(sem_score),
                    "confidence_tier": tier,
                })
                total_tokens += chunk_tokens
                added_chunk_ids.add(chunk_id)
            else:
                logger.warning(f"Context token budget reached ({total_tokens}/{token_budget}). Skipping chunk {chunk_id}.")
                continue

            # Sibling Chunk Expansion: check for adjacent page_number + 1 sibling chunk in the same document
            filename = doc.metadata.get("filename")
            page_num = doc.metadata.get("page_number")
            if filename and page_num is not None:
                try:
                    page_int = int(page_num)
                    sib_doc = self.filename_page_to_doc.get((filename, page_int + 1))
                    if sib_doc:
                        sib_id = sib_doc.metadata.get("chunk_id")
                        if sib_id and sib_id not in added_chunk_ids:
                            sib_text = sib_doc.page_content
                            sib_tokens = max(1, len(sib_text) // 4)
                            if total_tokens + sib_tokens <= token_budget:
                                final_results.append({
                                    "text": sib_text,
                                    "metadata": sib_doc.metadata,
                                    "score": float(blended_score),
                                    "semantic_score": float(sem_score),
                                    "confidence_tier": tier,
                                    "is_sibling_expansion": True
                                })
                                total_tokens += sib_tokens
                                added_chunk_ids.add(sib_id)
                                logger.info(f"Sibling chunk context expansion added: {filename} page {page_int + 1} ({sib_tokens} tokens)")
                            else:
                                logger.warning(f"Context token budget reached ({total_tokens}/{token_budget}). Skipping sibling chunk {sib_id}.")
                except (ValueError, TypeError):
                    pass

        logger.info(
            f"Retrieved {len(final_results)} chunks (tier={tier}, top blended score: {top_score:.4f}, "
            f"semantic: {scored_docs[0][2]:.4f}, total tokens: {total_tokens}/{token_budget})"
        )
        return final_results

if __name__ == "__main__":
    # Sanity checks
    logging.basicConfig(level=logging.INFO)
    retriever = HybridRetriever()
    
    print("\n" + "=" * 80)
    print("    RUNNING RETRIEVER VERIFICATION QUERIES (PHASE 3)")
    print("=" * 80)
    
    # Query A: SBI + Health LOB
    print("\n[TEST A] Query: 'What is covered under SBI Corona Rakshak policy?'")
    results_a = retriever.retrieve_relevant_chunks("What is covered under SBI Corona Rakshak policy?")
    print(f"  * Results count: {len(results_a)}")
    if results_a:
        print(f"  * Top Chunk ID : {results_a[0]['metadata']['chunk_id']}")
        print(f"  * Top Score    : {results_a[0]['score']:.4f}")
        print(f"  * Carrier/LOB  : {results_a[0]['metadata'].get('carrier')} | {results_a[0]['metadata'].get('line_of_business')}")
        print(f"  * Text snippet  : {results_a[0]['text'][:160].encode('ascii', 'ignore').decode('ascii').replace(chr(10), ' ')}...")
        
    # Query B: HDFC + Protection LOB
    print("\n[TEST B] Query: 'What are the death benefits in HDFC Group Term Insurance?'")
    results_b = retriever.retrieve_relevant_chunks("What are the death benefits in HDFC Group Term Insurance?")
    print(f"  * Results count: {len(results_b)}")
    if results_b:
        print(f"  * Top Chunk ID : {results_b[0]['metadata']['chunk_id']}")
        print(f"  * Top Score    : {results_b[0]['score']:.4f}")
        print(f"  * Carrier/LOB  : {results_b[0]['metadata'].get('carrier')} | {results_b[0]['metadata'].get('line_of_business')}")
        print(f"  * Text snippet  : {results_b[0]['text'][:160].encode('ascii', 'ignore').decode('ascii').replace(chr(10), ' ')}...")
        
    # Query C: Fallback check
    print("\n[TEST C] Query: 'What is the capital of Mars?'")
    results_c = retriever.retrieve_relevant_chunks("What is the capital of Mars?")
    print(f"  * Results count: {len(results_c)} (Expected: 0)")

    # Query D: Procedural Claim Documents test
    print("\n[TEST D] Query: 'What documents are required to file a death claim under HDFC Sanchay Aajeevan Guaranteed Advantage?'")
    results_d = retriever.retrieve_relevant_chunks("What documents are required to file a death claim under HDFC Sanchay Aajeevan Guaranteed Advantage?")
    print(f"  * Results count: {len(results_d)}")
    if results_d:
        print(f"  * Top Chunk ID : {results_d[0]['metadata']['chunk_id']}")
        print(f"  * Top Score    : {results_d[0]['score']:.4f}")
        print(f"  * Page Number  : {results_d[0]['metadata'].get('page_number')} (Expected: 21)")
        print(f"  * Text snippet  : {results_d[0]['text'][:160].encode('ascii', 'ignore').decode('ascii').replace(chr(10), ' ')}...")
    print("=" * 80 + "\n")
