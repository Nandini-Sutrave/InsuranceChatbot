# What I actually changed, and why

Read this before dropping these files in. I looked at your real code (not just your
description of it) and found the actual bugs behind your three pain points. I fixed
those specifically rather than rewriting the whole pipeline from scratch — your
architecture (Tier 1 intent filter -> Tier 2 hybrid RRF -> cross-encoder rerank ->
confidence guardrail) is sound. It was let down by a few concrete implementation bugs.

## Important limits on what I could do here

I don't have internet access to huggingface.co in this environment (only pypi/npm/github
are reachable), so I could not actually load `all-MiniLM-L6-v2`, run the cross-encoder,
or hit the real Gemini API to test end-to-end. Everything below is verified by reading
the code and metadata schema, and syntax-checked with `py_compile`, but **you need to
run it against your real Chroma index once** before trusting it in production. I also
did not touch your Flask backend or frontend — they weren't in the upload, so if they
need changes to consume the new response shape (see "Response shape changed" below),
send them over.

## 1. Prospectus-vs-CIS collision — found the actual cause

Your ingestion (`ingestion/loader.py`) already computes a `document_priority` per file
(policy wording=100, schedule=90, prospectus=50, etc.) and stores it on every chunk's
metadata. But `retrieval/retriever.py`'s reranking step never read it — it only sorted
by the raw cross-encoder score. So a fluent Prospectus paragraph could out-rank a CIS
coverage table purely on semantic style, regardless of authority. `RERANK_META_WEIGHT`
and `RERANK_COVERAGE_WEIGHT` existed in `settings.py` too, but nothing ever consumed them.

Fixes:
- `ingestion/loader.py`: added a dedicated `customer_information_sheet` rule (priority 95)
  — CIS files were previously falling into the generic default bucket (55), barely above
  Prospectus (50), because "CIS" didn't match any keyword.
- `retrieval/retriever.py`: the final score is now a real weighted blend of
  (a) cross-encoder semantic score, (b) normalized document authority, and
  (c) a cheap "numeric/table density" signal (counts of ₹/Rs/%/decimals) that rewards
  chunks with actual payout figures over narrative marketing text. Weights come from
  `settings.RERANK_*`, so you can retune them without touching code.
- The confidence guardrail now checks the blended score (still 0.70 by default, now
  `settings.CONFIDENCE_THRESHOLD`), and each result also carries the raw `semantic_score`
  separately so you can debug/log both.

You do **not** need to re-run ingestion or re-embed — `document_priority` was already
being written to every chunk, it was just unused downstream (except CIS files, which
will get their new priority=95 only after you re-run ingestion once, since that value
is baked in at chunk-build time).

## 2. Citations — moved from inline to consolidated

`generation/generator.py`'s prompt no longer asks the model for a
`[Source: filename, Page X ...]` tag after every sentence. Instead it asks for a clean
answer, then the code appends a single deduplicated **References** block at the end,
built from the actual retrieved chunks' metadata (not model-generated, so it can't
hallucinate a wrong page number). Toggle with `settings.SHOW_REFERENCES`.

## 3. The biggest bug: your LLM calls were silently broken

`generation/generator.py` did **not** use your `providers/llm_providers.py` at all,
even though that file already has solid retry/fallback/error-classification logic.
Instead it instantiated its own `genai.Client` with `model_name = "gemini-3.5-flash"` —
**that model does not exist**. Every real call would fail with a 404, and because there
was no fallback wired to that path, it silently dropped into the degraded local
sentence-extraction fallback and returned *an* answer anyway — so you'd never see an
error, you'd just always get lower-quality answers than you should.

Fixes:
- `generation/generator.py` now calls `LLMFactory.create(settings)` and uses your real
  `GeminiProvider`, which has correct model names (`gemini-2.5-flash` with fallback to
  `gemini-2.0-flash`) and retry classification.
- `providers/llm_providers.py`: retries now use exponential backoff
  (`RETRY_BACKOFF_BASE_SECONDS ** attempt`) instead of a flat `time.sleep(1)`, which is
  what actually helps against rate limits/quota bursts.
- `settings.py`: `MAX_RETRIES` raised 1 → 3, added `RETRY_BACKOFF_BASE_SECONDS`.

## 4. Security: hardcoded API key removed

`config/settings.py` had a live Gemini API key committed in plaintext (twice — one
commented out, one active). I removed both and set `GEMINI_API_KEY = ""`, sourced from
env var only (`GeminiProvider` already checks `GOOGLE_API_KEY`/`GEMINI_API_KEY` env vars
first). **Rotate that key in Google AI Studio now** — treat it as leaked, since it was
sitting in a file that gets zipped/shared.

## Response shape changed — check your Flask layer

`generate_answer()` now returns:
- `confidence_tier`: actually reflects the retrieval score tier (was previously
  hardcoded to `"HIGH"` on every successful call, `"LOW"` only on empty retrieval).
- `generation_degraded`: new boolean — `True` if the LLM call failed after all
  retries/fallbacks and you're looking at the extractive fallback text, so your UI can
  show "answer generated from documents directly, live assistant temporarily degraded"
  instead of presenting it as a normal answer.
- `retrieved_chunks[i]["score"]`: now the blended score, not raw cross-encoder.
  `retrieved_chunks[i]["semantic_score"]`: the old raw cross-encoder score, kept
  separately for debugging.

If your Flask routes or frontend read any of these fields, update accordingly.

## What I did not change

- `ingestion/` chunking/table extraction logic (chunk_builder.py, cleaner.py,
  section_tree.py) — no reported bug there, left as-is.
- `utils/vector_store.py`, `utils/embedding_service.py` — fine as written.
- Evaluation scripts — untouched; re-run `evaluation/run_retrieval_benchmark.py` after
  you re-ingest, to confirm the priority blend actually improves your benchmark numbers
  rather than just trusting my reasoning about it.

## Round 2 — architectural improvements (not bug fixes, genuine upgrades)

These go beyond fixing what was broken; they address real gaps that were capping how
much the pipeline could answer, even once round 1's bugs were fixed.

**1. Binary confidence cutoff replaced with graduated tiers.**
Previously anything scoring under 0.70 returned nothing — the user got a ticket-raise
message even when a decent 0.55-0.69 answer existed. Now there are three bands:
`>= CONFIDENCE_THRESHOLD` (HIGH, answered normally), `[threshold-0.20, threshold)`
(MEDIUM, answered but with a visible caveat sentence + the reference list so the agent
can verify), and below that (empty list, ticket-raise fallback as before). This directly
trades "answers more questions" against "never silently overclaims" by making the
uncertainty visible instead of hiding it behind a refusal.

**2. Per-document diversity cap in the final top-K.**
`MAX_CHUNKS_PER_DOCUMENT` (default 3) stops one document's near-duplicate chunks from
crowding out complementary sources. Without this, a question needing both a CIS limit
*and* a wording exclusion clause could end up with 6 CIS chunks and zero wording
context, purely because CIS scored slightly higher across the board.

**3. Neighbor-chunk stitching for the top 2 results.**
Your chunker already stores `previous_chunk_id`/`next_chunk_id` on every chunk but
nothing consumed them. The top 2 chunks now get ~400 chars of their neighbor's text
stitched on each side before being sent to the LLM, so a table or clause that happens to
span a chunk boundary isn't handed over mid-row/mid-sentence.

**4. Carrier-balanced retrieval for SBI-vs-HDFC comparison queries.**
Detecting both carrier names bypassed the metadata filter (already existed) so both
carriers are searchable, but RRF fusion could still let one carrier's chunks dominate
the top-20 purely on relevance score — silently turning a comparison question into a
single-carrier answer. Comparison queries now pool the top ~12 RRF-ranked candidates
*per carrier* before merging, so both sides are guaranteed representation going into
reranking.

**Deliberately not done — query rewriting/typo normalization.** I considered adding a
hardcoded alias dictionary for product name typos (e.g. "saral suraksha" misspellings)
but that's a losing game long-term: it only covers what you think to add. The real fix
is an LLM-based query rewrite step before retrieval (expand abbreviations, fix obvious
typos, split compound questions). That adds one extra LLM call of latency/cost per
query, so I didn't wire it in unilaterally — say the word and I'll add it as an optional
`REWRITE_QUERY_BEFORE_RETRIEVAL` toggle.

## Round 3 — the actual dataset was inconsistent, and Tier-1 filtering was silently broken

I diffed the code's assumptions against your real folder tree (not just the file
listing you described) and found two structural bugs that are plausibly the single
biggest reason answers were incomplete — bigger than the ranking/generation issues
above, because they sit upstream of everything else: if Tier-1 pre-filtering returns
zero candidates, nothing downstream (RRF, cross-encoder, priority blend) ever gets a
chance to run.

**1. HDFC and SBI are structured differently on disk, and the loader assumed one fixed
depth.** SBI is `Carrier/LOB/Product/file.pdf` (3 levels). HDFC is flat —
`HDFC-protection/file.pdf`, `HDFC-health/file.pdf`, etc. — carrier and LOB fused into one
folder name, no product level. `loader.py` reads folders positionally
(`category_1`=carrier, `category_2`=LOB, ...), so for HDFC files `category_1` became
the literal string `"HDFC-protection"`, not `"HDFC"`. The retriever's Tier-1 filter does
an exact match on `carrier == "HDFC"` — which never matched. **Any query mentioning
"HDFC" almost certainly filtered to zero candidates and fell straight to the
"could not find an answer" fallback**, regardless of how good the reranking was.

**2. Independent of that, the alias labels were swapped for everyone.**
`FOLDER_ALIAS_KEYS = ["carrier", "product", "line_of_business", "sub_product"]` mapped
positionally to folder depth. For `SBI/Health/corona rakshak/...` that assigned
`product = "Health"` and `line_of_business = "corona rakshak"` — backwards. The
retriever filters on `line_of_business` expecting `"Health"`/`"Motor"`/etc., but the
stored value was actually the specific product name. On top of that, folder casing
(`"cyber"`, `"travel"` lowercase folders vs. `"Cyber"`, `"Travel"` in the old
`LOB_KEYWORDS` dict) would have failed an exact-match filter anyway even with the swap
fixed. **Tier-1 LOB filtering had likely never worked correctly for either carrier.**

**3. Hygiene:** found 8 leftover files in `HDFC-protection/` —
`Click-2-Protect-Optima-Secure-101Y122V05.pdf_temp_0_6.pdf`, `_temp_6_12`, `_temp_12_18`,
etc. — page-range fragments of one document sitting alongside the full original PDF,
almost certainly leftovers from a prior debugging/splitting run. That document's content
would be ingested roughly twice (once whole, once as 8 overlapping fragments), and
SHA-256 dedup won't catch it since the fragment bytes differ from the full file byte-
for-byte. **I deleted these 8 files from the copy I worked with — delete them from your
actual source dataset too before re-ingesting.**

Fixes (all in `ingestion/loader.py` + `retrieval/retriever.py`):
- `FOLDER_ALIAS_KEYS` reordered to `["carrier", "line_of_business", "product", "sub_product"]`
  to match actual folder depth.
- New `_split_compound_carrier_folder()`: detects a flattened `"Carrier-LOB"` folder
  (checked against a `KNOWN_CARRIER_PREFIXES` list — extend it if you add carriers) and
  splits it into two synthetic levels before the positional mapping runs, so HDFC and
  SBI produce consistently-shaped metadata regardless of folder depth.
- `carrier` is now uppercased and `line_of_business` is stored through a new
  `_normalize_lob_token()` (lowercase, hyphens/underscores collapsed to spaces) — a raw
  copy is kept as `line_of_business_raw` in case you need the original folder text.
- `LOB_KEYWORDS` in `retriever.py` now uses the same canonical lowercase-space keys
  (`"personal accident"`, `"cyber"`, `"protection"`, ...) instead of the old
  `"Personal_Accident"`/`"Cyber"` style that never matched stored values.
- **Safety net added regardless:** if a Tier-1 filter ever matches zero dense results
  (a future carrier not in `KNOWN_CARRIER_PREFIXES`, a folder rename, any taxonomy
  drift), the retriever now logs a warning and automatically falls back to an
  unfiltered global search rather than silently returning nothing. This is exactly the
  failure mode that was hiding real, answerable documents behind a metadata mismatch —
  worth keeping even after the root cause is fixed, as insurance against the next one.

**This requires the re-ingestion you were about to do anyway** — the fix is in the
loader, so it only takes effect on documents processed after this change.

## Other things I noticed but did not change (lower priority / need your input)

- **No OCR fallback.** `loader.py` uses PyMuPDF text extraction only. If any of your 159
  PDFs are scanned images rather than native text (common for older policy bonds), those
  pages will silently yield zero extractable text and just won't be in the index at all —
  no error, no warning. Worth a quick check: `grep`-style text-length audit across all
  159 files before you trust the corpus is fully covered.
- **Embedding model is a small general-purpose one** (`all-MiniLM-L6-v2`, 384-dim). It's
  fine for outright wrong-topic queries but has limited capacity for near-miss insurance
  terminology (e.g. distinguishing "waiting period" from "survival period" from
  "cooling-off period"). A domain-tuned or larger model (e.g. `bge-base` /
  `e5-base`) would likely improve recall on subtle distinctions, at the cost of slower
  embedding and a re-index. Not changed because it requires re-embedding all ~8,680
  chunks and I can't validate the tradeoff without running it — flag if you want this.
- **No conversation memory.** Each `generate_answer()` call is independent; a follow-up
  like "what about the co-pay for that?" has no idea what "that" refers to. Fine for a
  single-shot Q&A tool, a real gap if this is meant to be a multi-turn chat assistant.
- **No observability beyond logger.info/warning.** No structured logging of
  query → filter → tier → score → answer for later analysis, so you can't currently
  build a "which queries are getting MEDIUM/LOW confidence" report without adding it.
- Query rewriting/typo normalization — flagged in round 2, still not implemented, still
  recommend an LLM-based rewrite step over a hardcoded alias list if you want it.

None of these need to block your ingestion run — they're independent of the loader/
retriever changes above. Happy to implement any of them, just say which.

## Round 4 — the remaining items from round 3, actually finished

The previous session ended mid-way through this list (it had gotten through
the loader whitelist fix and OCR wiring in conversation, but that work never
made it into the files you exported — this zip still had the original
6-substring whitelist and no OCR code at all when I opened it). Everything
below is now actually in the files, not just described:

**1. The dataset whitelist bug — fixed.** `ingestion/loader.py`'s
`discover_documents()` had a hardcoded list of 6 filename substrings
("Focus dataset on active benchmark policy wordings to avoid long CPU index
runs") that silently limited ingestion to whatever matched them. This was
almost certainly the single biggest reason answers were incomplete: it sits
upstream of every other fix in this document. `discover_documents()` now
takes an optional `filename_substrings` parameter that defaults to `None`
(process the full corpus). Passing a list still works for a deliberate
smoke-test run, but it now logs a loud warning when used, so a restricted run
can never be mistaken for a full one again.

**2. OCR fallback for scanned/low-text pages — implemented.**
`HybridPDFLoader` now takes `enable_ocr_fallback` (default `True`),
`ocr_min_chars` (default 20), and `ocr_dpi` (default 200) constructor
params. Any page whose native PyMuPDF text comes back under `ocr_min_chars`
is rendered to an image and passed through `pytesseract`; the OCR'd text is
used only if it's longer than what native extraction found. This is a soft
dependency: if `pytesseract`/`Pillow` aren't installed, or the `tesseract`
system binary isn't on PATH, OCR silently disables itself and the loader
behaves exactly as it did before (native-text-only, page skipped with a
warning) — nothing breaks on a machine without tesseract installed.
You'll need `pip install pytesseract Pillow` and the OS-level
`tesseract-ocr` package for this to actually engage; check the logs for
"Low-text pages encountered" / "Recovered via OCR" counts after your next
ingestion run to see how much this recovers for your corpus.

**3. Configurable embedding model.** `settings.EMBEDDING_MODEL_NAME`
(default `sentence-transformers/all-MiniLM-L6-v2`) now flows through to both
`ingestion/ingestor.py` and `retrieval/retriever.py`'s `EmbeddingService`
construction, so swapping to `bge-base`/`e5-base` is a one-line settings
change. Reminder: changing it requires a full re-ingestion (re-embedding all
chunks) before retrieval will work correctly — the retriever and the stored
Chroma vectors must come from the same model.

**4. Conversation memory.** `generate_answer()` now accepts an optional
`conversation_history` parameter (list of `{"role": "user"|"assistant",
"content": "..."}` dicts, oldest first). The last `settings.
MAX_CONVERSATION_TURNS` (default 3) turns are folded into the generation
prompt so a follow-up like "what about the co-pay for that?" can resolve
"that" against the prior turn. This only affects generation — retrieval
still runs on the current query (or the rewritten query if item 6 below is
on) — so this is safe to leave off/unused for single-shot callers.

**5. Structured logging.** Every `generate_answer()` call now appends one
JSON line — `query`, `rewritten_query`, `confidence_tier`, `top_score`,
`generation_degraded`, `latency_ms` — to `settings.STRUCTURED_LOG_PATH`
(default `logs/query_log.jsonl`, relative to the backend root). This is
exactly the "which queries are getting MEDIUM/LOW confidence" report you
couldn't build before without re-instrumenting. Logging failures are
swallowed (`STRUCTURED_LOG_ENABLED` toggle available) — it will never be the
reason an answer fails to return.

**6. Query-rewrite toggle — implemented as opt-in, still off by default.**
`settings.REWRITE_QUERY_BEFORE_RETRIEVAL` (default `False`). When turned on,
one extra LLM call rewrites the query (expanding abbreviations, fixing
obvious product-name typos, resolving "that"/"it" against conversation
history) before it hits the retriever. Falls back silently to the original
query on any failure. Left off by default for the same reason as before:
it's a real latency/cost tradeoff per query that only you can decide is
worth it for your traffic volume.

**Still not done, same reasoning as round 2/3:** a hardcoded typo/alias
dictionary. If you want typo tolerance without turning on the query-rewrite
LLM call, say so and I'll look at a lightweight fuzzy-match layer instead —
that's a different, cheaper tradeoff than either of the two options above.

## Round 5 — embedding model upgrade + fuzzy carrier/LOB matching

Two specific, scoped changes, both unit-tested in isolation (this sandbox
can't reach huggingface.co, so the actual model download/load itself is
untested here — see the caveat below):

**1. Embedding model swapped to `BAAI/bge-base-en-v1.5`** (was
`all-MiniLM-L6-v2`, 384-dim general-purpose). This is a one-line
`settings.EMBEDDING_MODEL_NAME` change, but BGE models need one more thing
to actually deliver their accuracy advantage: the **query** (not the
document) needs a fixed instruction prefix at encode time
(`"Represent this sentence for searching relevant passages: "`).
`langchain_huggingface`'s `HuggingFaceEmbeddings` has no built-in support for
this (that lived on the now-deprecated `HuggingFaceBgeEmbeddings` class), and
Chroma calls `embed_query()`/`embed_documents()` directly on whatever
embedding object it's given — so I added a small wrapper
(`_QueryInstructionEmbeddings` in `utils/embedding_service.py`) that prepends
the instruction on the query path only, and leaves document/passage
embedding completely untouched. It auto-activates for any model name
containing "bge"; unrecognized model families get no prefix (safer than
guessing wrong for e.g. e5, which needs a different, two-sided fix). I
unit-tested the prefixing logic directly (fake embedder, asserting queries
get prefixed and documents don't) since real model loading isn't reachable
from this sandbox.
**Action required on your end:** re-run full ingestion before using this —
old Chroma vectors are 384-dim MiniLM vectors and won't match 768-dim BGE
query vectors. Also run `pip install langchain_huggingface` if not already
present, and verify the model downloads/loads correctly in your actual
environment (which has real internet access) before relying on it.

**2. Fuzzy carrier/LOB matching, always-on.** `retrieval/retriever.py`'s
`_detect_policy_in_query()` now runs a second pass with `rapidfuzz` if the
exact word-boundary match finds nothing — catching typos/synonyms like
"saral suraksha byma" (bima→byma) or "corana rakshak" (corona→corana) that
would otherwise silently skip the Tier-1 filter. Soft dependency: if
`rapidfuzz` isn't installed, this pass is skipped entirely and behavior is
identical to before. Controlled by `settings.FUZZY_MATCH_LOB_CARRIER`
(default `True`) and `settings.FUZZY_MATCH_THRESHOLD` (default `85`).

While building this I actually caught a real precision bug in my own first
draft before shipping it: a naive "best fuzzy score wins" approach let a
short, generic keyword fragment ("raksha", which recurs across an unrelated
home-insurance product name and a health-insurance product name in this
corpus) tie with — and sometimes beat — the correct longer, more specific
match. Fixed by requiring a minimum keyword length of 6 for the fuzzy pass
(exact matching is unaffected and still checks every keyword regardless of
length) plus a length-based tie-break. Verified against 6 test queries
(3 typo'd, 1 exact, 1 unrelated/should-not-match, 1 additional collision
case) with the actual `LOB_KEYWORDS` dict from this file before applying it.
`pip install rapidfuzz` to enable.

## Before you deploy

1. Rotate the leaked Gemini key, set the new one as `GEMINI_API_KEY` env var.
2. Re-run ingestion once (so CIS files get `document_priority=95` baked into their chunks).
3. Run `retrieval/retriever.py`'s `__main__` sanity block and your benchmark suite.
4. Grid-search `RERANK_META_WEIGHT` / `RERANK_COVERAGE_WEIGHT` a bit — I set 0.25/0.10 as
   reasonable starting points based on your existing settings, not a tuned result.
