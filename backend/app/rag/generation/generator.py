import os
import sys
import json
import time
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

backend_dir = Path(__file__).resolve().parents[3]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.rag.config import settings
from app.rag.retrieval.retriever import HybridRetriever
from app.rag.providers.llm_providers import LLMFactory, LLMProviderError, LLMResponseError


def _write_structured_log(record: Dict[str, Any]) -> None:
    """
    Appends one JSON line per generate_answer() call so query -> filter ->
    tier -> score -> degraded -> latency can be analyzed later (e.g. "which
    queries are getting MEDIUM/LOW confidence") without re-instrumenting
    anything. Best-effort and silent on failure -- logging must never be the
    reason an answer fails to return.
    """
    if not getattr(settings, "STRUCTURED_LOG_ENABLED", True):
        return
    try:
        log_path = Path(getattr(settings, "STRUCTURED_LOG_PATH", "logs/query_log.jsonl"))
        if not log_path.is_absolute():
            log_path = backend_dir / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception as exc:
        logger.debug("Structured logging failed (non-fatal): %s", exc)


class InsuranceAssistant:
    """
    Generation engine for the Insurance RAG Pipeline.

    Delegates all LLM calls to LLMFactory / GeminiProvider (providers/llm_providers.py),
    which already implements model fallbacks + retry/backoff classification. This class
    used to instantiate its own genai.Client with a hardcoded, non-existent model name
    ("gemini-3.5-flash"), which meant real calls always 404'd and every answer silently
    came from the degraded local-extractor fallback. That is now fixed.
    """

    def __init__(self, retriever: Optional[HybridRetriever] = None):
        self.retriever = retriever or HybridRetriever()
        self.provider = LLMFactory.create(settings)

    # ------------------------------------------------------------------
    def generate_answer(
        self,
        query: str,
        product_id: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        conversation_history: optional list of prior turns, oldest first, each
        shaped like {"role": "user"|"assistant", "content": "..."}. Without
        this, every call is stateless and a follow-up like "what about the
        co-pay for that?" has no idea what "that" refers to. Only the most
        recent `settings.MAX_CONVERSATION_TURNS` turns are used, to bound
        prompt growth.
        """
        started = time.time()
        original_query = query
        rewritten_query = None

        # 0. Optional query rewrite (OFF by default -- settings.REWRITE_QUERY_BEFORE_RETRIEVAL).
        #    Adds one extra LLM call of latency/cost per query to expand
        #    abbreviations, fix obvious typos, and split compound questions
        #    before retrieval. Falls back to the original query on any failure.
        if getattr(settings, "REWRITE_QUERY_BEFORE_RETRIEVAL", False):
            rewritten_query = self._rewrite_query(query, conversation_history)
            if rewritten_query and rewritten_query.strip() and rewritten_query.strip() != query.strip():
                logger.info("Query rewritten: '%s' -> '%s'", query, rewritten_query)
                query = rewritten_query.strip()

        # 1. Retrieve chunks
        retrieved_chunks = self.retriever.retrieve_relevant_chunks(query)

        # 2. Fallback Trigger: if empty, return the exact fallback text
        if not retrieved_chunks:
            logger.info("Retrieved chunks are empty. Triggering fallback response.")
            latency_ms = (time.time() - started) * 1000
            _write_structured_log({
                "query": original_query,
                "rewritten_query": rewritten_query,
                "confidence_tier": "LOW",
                "top_score": None,
                "generation_degraded": None,
                "latency_ms": latency_ms,
            })
            return {
                "answer": "I could not find a definitive answer in the official policy documents. Would you like me to raise a ticket for a support specialist?",
                "retrieved_chunks": [],
                "confidence_tier": "LOW",
                "latency_ms": latency_ms,
            }

        # 3. System prompt: answer cleanly, no inline per-sentence citations.
        #    References are consolidated and appended after generation instead,
        #    which is what actually renders well for dense policy answers.
        system_instruction = (
            "You are a professional enterprise insurance underwriting and compliance assistant. "
            "Answer the user's question using ONLY the provided policy contexts below.\n\n"
            "RULES:\n"
            "1. Do not over-summarize: retain exact numerical values, percentages, waiting periods, "
            "co-pay ratios, deductible amounts, sub-limits, and room-rent caps exactly as written.\n"
            "2. Write a clean, well-structured, directly readable answer (use short paragraphs or "
            "bullet points for lists of conditions/limits). Do NOT add inline citation tags, "
            "footnote markers, or bracketed source references inside the answer text itself - "
            "references are handled separately after your answer.\n"
            "3. If the provided contexts conflict (e.g. a summary document vs. the policy wording), "
            "prefer the more detailed/authoritative source and note the discrepancy briefly if it "
            "materially changes the answer.\n"
            "4. If the contexts do not actually contain the answer, say so plainly instead of guessing.\n"
            "5. Write for a POSP insurance agent: precise, scannable, no marketing language."
        )

        context_blocks = []
        for idx, chunk in enumerate(retrieved_chunks, start=1):
            meta = chunk.get("metadata", {})
            context_blocks.append(
                f"--- Context {idx} | {meta.get('filename')} (p.{meta.get('page_number')}, "
                f"{meta.get('document_type', 'document')}, {meta.get('carrier')}/{meta.get('line_of_business')}) ---\n"
                f"{chunk.get('text', '')}"
            )
        context_text = "\n\n".join(context_blocks)

        history_block = self._format_conversation_history(conversation_history)

        prompt = (
            f"{history_block}"
            f"User Question: {original_query}\n\n"
            f"Retrieved Policy Contexts:\n{context_text}\n\n"
            f"Write the answer now, following the rules above. If the current "
            f"question refers back to the conversation above (e.g. \"that\", "
            f"\"it\", \"the previous one\"), resolve the reference using the "
            f"conversation history before answering."
        )

        # 4. Generate via the shared provider (retry + model fallback handled inside)
        answer = None
        last_error = None
        try:
            answer = self.provider.generate(prompt, system_prompt=system_instruction)
        except Exception as e:
            last_error = str(e)
            logger.warning("LLM provider failed after retries/fallbacks (%s). Using local grounded extractor.", e)

        # 5. Local grounded extractor fallback if the LLM call ultimately failed
        if not answer:
            answer = self._local_extractive_fallback(retrieved_chunks)
            degraded = True
        else:
            degraded = False

        # 6. Confidence tier comes from the retriever's graduated scoring
        #    (HIGH >= CONFIDENCE_THRESHOLD, MEDIUM = answered-but-uncertain
        #    band). Generation failure downgrades HIGH -> MEDIUM regardless
        #    of retrieval confidence, since we're now on the extractive
        #    fallback text rather than a synthesized answer.
        confidence_tier = retrieved_chunks[0].get("confidence_tier", "MEDIUM")
        if degraded and confidence_tier == "HIGH":
            confidence_tier = "MEDIUM"

        if confidence_tier == "MEDIUM" and not degraded:
            answer = (
                answer.rstrip()
                + "\n\n_Note: this answer is based on the closest matching policy sections found, "
                "but the match confidence was moderate - please double-check the exact figures "
                "against the source document below before relying on this for a customer._"
            )

        # 7. Consolidated references, appended once, deduped by (filename, page)
        if getattr(settings, "SHOW_REFERENCES", True):
            answer = answer.rstrip() + "\n\n" + self._build_reference_block(retrieved_chunks)

        latency_ms = (time.time() - started) * 1000
        _write_structured_log({
            "query": original_query,
            "rewritten_query": rewritten_query,
            "confidence_tier": confidence_tier,
            "top_score": retrieved_chunks[0].get("score") if retrieved_chunks else None,
            "generation_degraded": degraded,
            "latency_ms": latency_ms,
            "error_msg": last_error
        })

        return {
            "answer": answer,
            "retrieved_chunks": retrieved_chunks,
            "confidence_tier": confidence_tier,
            "generation_degraded": degraded,
            "latency_ms": latency_ms,
        }

    # ------------------------------------------------------------------
    def _format_conversation_history(self, conversation_history: Optional[List[Dict[str, str]]]) -> str:
        """Renders the last N turns (settings.MAX_CONVERSATION_TURNS) as a
        short block prepended to the prompt. Returns "" if there's no history,
        so single-shot callers see no behavior change at all."""
        if not conversation_history:
            return ""
        max_turns = getattr(settings, "MAX_CONVERSATION_TURNS", 3)
        recent = conversation_history[-max_turns:]
        lines = []
        for turn in recent:
            role = turn.get("role", "user")
            content = (turn.get("content") or "").strip()
            if not content:
                continue
            label = "User" if role == "user" else "Assistant"
            lines.append(f"{label}: {content}")
        if not lines:
            return ""
        return "Prior conversation (most recent last):\n" + "\n".join(lines) + "\n\n"

    # ------------------------------------------------------------------
    def _rewrite_query(
        self, query: str, conversation_history: Optional[List[Dict[str, str]]]
    ) -> Optional[str]:
        """
        Uses the same LLM provider to expand abbreviations, fix obvious typos,
        resolve conversational references ("what about the co-pay for that?"),
        and split compound questions into a single retrieval-friendly query,
        before the real retrieval call runs. OFF by default
        (settings.REWRITE_QUERY_BEFORE_RETRIEVAL) since it costs one extra
        LLM call per query. Any failure here falls back to the original
        query untouched -- this step must never block an answer.
        """
        history_block = self._format_conversation_history(conversation_history)
        system_prompt = (
            "You rewrite a user's insurance question into a single, self-contained, "
            "search-friendly query. Expand obvious abbreviations, fix obvious typos in "
            "product/company names, and resolve pronouns/references using the prior "
            "conversation if given. Output ONLY the rewritten query text, nothing else "
            "-- no preamble, no quotes, no explanation."
        )
        prompt = f"{history_block}Original question: {query}\n\nRewritten query:"
        try:
            rewritten = self.provider.generate(prompt, system_prompt=system_prompt)
            if rewritten:
                # Defensive cleanup in case the model adds quotes/prefixes anyway.
                cleaned = rewritten.strip().strip('"').strip()
                if cleaned:
                    return cleaned
        except (LLMResponseError, LLMProviderError) as e:
            logger.warning("Query rewrite step failed, using original query: %s", e)
        return None

    # ------------------------------------------------------------------
    @staticmethod
    def _build_reference_block(retrieved_chunks: List[Dict[str, Any]]) -> str:
        seen = set()
        refs = []
        for chunk in retrieved_chunks:
            meta = chunk.get("metadata", {})
            key = (meta.get("filename"), meta.get("page_number"))
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                f"- {meta.get('filename')}, p.{meta.get('page_number')} "
                f"({meta.get('carrier')} | {meta.get('line_of_business')})"
            )
        if not refs:
            return ""
        return "**References**\n" + "\n".join(refs)

    @staticmethod
    def _local_extractive_fallback(retrieved_chunks: List[Dict[str, Any]]) -> str:
        """Used only if the LLM provider fails after all retries/fallbacks."""
        lines = []
        seen = set()
        for chunk in retrieved_chunks:
            for line in (chunk.get("text", "") or "").split("\n"):
                line = line.strip()
                if line and not line.startswith("---") and len(line) > 40 and line not in seen:
                    seen.add(line)
                    lines.append(line)
        if not lines:
            return "I could not generate an answer right now due to an LLM provider issue, and the retrieved text had no extractable content."
        return (
            "The live assistant model is temporarily unavailable, so here are the most relevant "
            "excerpts directly from the policy documents:\n\n" + "\n\n".join(f"- {l}" for l in lines[:5])
        )
