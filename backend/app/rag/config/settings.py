"""Central configuration settings for the generic Insurance RAG pipeline."""
from enum import Enum

class LLMProviderType(str, Enum):
    GEMINI = "gemini"
    MOCK = "mock"

# Retriever Configs
RRF_K = 45
RETRIEVER_K = 6
FETCH_K = 40
LEXICAL_K = 40

# Policy Routing Soft Biasing Boost Multiplier
SOFT_BIAS_MULTIPLIER = 2.0

# Generator Priority Bonus Scores
EXACT_PRODUCT_BONUS = 1000.0
CARRIER_BONUS = 10.0

# LLM Provider Configuration Settings
LLM_PROVIDER = LLMProviderType.GEMINI
MODEL_NAME = "gemini-3.6-flash"
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 2048
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 1.5   # exponential backoff: 1.5s, 3s, 6s, ...
MODEL_FALLBACKS = ["gemini-3.1-flash-lite", "gemini-3.5-flash"]

# Debug Configurations
LLM_DEBUG_MODE = False
SHOW_REFERENCES = True  # append a consolidated reference list at the end of the answer

# Embedding model -- now configurable rather than hardcoded, so it can be
# swapped/benchmarked (e.g. against bge-base/e5-base for subtler insurance
# terminology distinctions) without touching code. Changing this requires
# re-running ingestion (re-embedding all chunks) before it takes effect for
# retrieval, since Chroma stores vectors at the dimensionality of whatever
# model wrote them.
# Embedding model -- now configurable rather than hardcoded, so it can be
# swapped/benchmarked without touching code. Changed from the original
# all-MiniLM-L6-v2 (384-dim, general-purpose) to bge-base-en-v1.5, which is
# meaningfully stronger on subtle terminology distinctions that matter here
# ("waiting period" vs "survival period", rider vs base cover language) --
# this is the single highest-leverage retrieval-quality change available.
# IMPORTANT: changing this value requires a full re-ingestion (re-embedding
# every chunk) before retrieval will work correctly -- the retriever and the
# stored Chroma vectors must come from the same model / dimensionality.
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Fuzzy carrier/LOB matching (retrieval/retriever.py). Always-on by default:
# unlike query-rewrite, this adds no LLM call and no latency worth
# mentioning -- it only engages as a second pass, and only when the exact
# keyword match already found nothing. Catches typos/synonyms ("saral
# suraksha byma", "corana rakshak") that would otherwise silently skip the
# Tier-1 filter and fall through to an unfiltered global search. Self-
# disables gracefully if 'rapidfuzz' isn't installed.
FUZZY_MATCH_LOB_CARRIER = True
FUZZY_MATCH_THRESHOLD = 85  # 0-100, rapidfuzz score; higher = stricter

# OCR fallback for scanned/low-text PDF pages (ingestion/loader.py). Self-
# disables gracefully if pytesseract/Pillow/the tesseract binary aren't
# installed, so this is safe to leave on by default.
ENABLE_OCR_FALLBACK = True
OCR_MIN_TEXT_CHARS = 20   # pages with fewer native chars than this are OCR-candidates
OCR_RENDER_DPI = 200

# Query rewriting before retrieval -- OFF by default. This adds one extra
# LLM call of latency/cost per query to expand abbreviations, fix obvious
# typos, and split compound questions before they hit the retriever. It is
# a genuine accuracy improvement for near-miss terminology and compound
# questions, but the added latency/cost is a real tradeoff, so it is an
# explicit opt-in rather than a forced-on default.
REWRITE_QUERY_BEFORE_RETRIEVAL = False

# Conversation memory (generation/generator.py). Each generate_answer() call
# is otherwise independent, so a follow-up like "what about the co-pay for
# that?" has no idea what "that" refers to. This caps how much prior
# conversation gets folded into the prompt, to bound token growth.
MAX_CONVERSATION_TURNS = 3

# Structured logging: one JSON line per generate_answer() call, capturing
# query -> rewritten_query -> filter -> tier -> score -> degraded -> latency,
# so "which queries are getting MEDIUM/LOW confidence" can be analyzed later
# without re-instrumenting anything. Best-effort -- failures to write this
# log never block or fail the actual answer.
STRUCTURED_LOG_ENABLED = True
STRUCTURED_LOG_PATH = "logs/query_log.jsonl"

# SECURITY: never hardcode API keys here. Set GEMINI_API_KEY (or GOOGLE_API_KEY)
# as an environment variable / secret manager entry instead.
# NOTE: a real key was previously hardcoded in this file and committed - rotate
# it in the Google AI Studio / Cloud console immediately, it must be treated as
# leaked.
GEMINI_API_KEY = ""

# Reranking Weights & Context Budgets (Tuned via Grid Search)
# These now actually feed the reranker (see retrieval/retriever.py) --
# previously they were defined but never read.
RERANK_RETRIEVED_WEIGHT = 0.65   # cross-encoder semantic relevance
RERANK_META_WEIGHT = 0.25        # document authority (wording > CIS > schedule > prospectus)
RERANK_SPECIFICITY_WEIGHT = 0.00
RERANK_COVERAGE_WEIGHT = 0.10    # numeric/table density (payout figures, %, Rs.)
CONTEXT_TOKEN_BUDGET = 3500
CONFIDENCE_THRESHOLD = 0.70      # >= this = HIGH confidence; [threshold-0.20, threshold) = MEDIUM (answered with caveat); below that = empty/fallback
MAX_CHUNKS_PER_DOCUMENT = 3      # diversity cap so one document can't crowd out complementary sources