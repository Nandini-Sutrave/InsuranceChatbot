"""
Structured chunk builder + metadata enrichment.

    Section Tree -> Structured Chunk Builder -> Metadata Enrichment

Chunks are built by walking the section tree and packing content in
structural units -- whole bullet groups, whole tables (plus row-level child
chunks for precise retrieval), and sentence-safe paragraph packs -- never by
slicing on arbitrary clause boundaries. A bullet list such as

    Coverage
      Base Covers
        Death
        PTD
        PPD

is kept as one bullet_group chunk under "Coverage > Base Covers" instead of
being split into three unrelated fragments.

Every chunk carries a rich, retrieval-oriented metadata schema (heading_path,
section_number/title, page range, chunk_type, contains_* content flags,
document authority signals, and the generic folder-derived taxonomy from the
loader). Nothing here is domain-specific.
"""
import hashlib
import re
from typing import Any, Dict, List, Tuple, Optional

from langchain_core.documents import Document

from .section_tree import ContentBlock, DocumentTree, Section

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")

CONTAINS_PERCENTAGE = re.compile(r"\d+(\.\d+)?\s*%")
CONTAINS_DURATION = re.compile(
    r"\b\d+\s*(day|days|month|months|year|years|week|weeks|hour|hours)\b", re.IGNORECASE
)
CONTAINS_MONEY = re.compile(
    r"(₹|rs\.?\s?\d|inr\s?\d|\$\s?\d|usd\s?\d|€\s?\d|£\s?\d|\d[\d,]*\s?(rs\.?|inr|usd|₹|\$|€|£))",
    re.IGNORECASE,
)
CONTAINS_NUMBER = re.compile(r"\d")

# A chunk below this size is never dropped -- it is merged into a
# structurally adjacent chunk within the same section instead. Important
# short clauses (a single sentence definition, a one-line waiting period)
# must survive, not be discarded.
MIN_MERGE_CHARACTERS = 120


def _generate_chunk_id(document_id: str, heading_path: str, block_index: Any, text: str) -> str:
    norm_text = " ".join(text.lower().split())
    norm_path = " ".join(heading_path.lower().split())
    hash_input = f"{document_id}_{norm_path}_{block_index}_{norm_text}"
    return hashlib.md5(hash_input.encode("utf-8")).hexdigest()


def _content_flags(text: str) -> Dict[str, bool]:
    return {
        "contains_numbers": bool(CONTAINS_NUMBER.search(text)),
        "contains_percentage": bool(CONTAINS_PERCENTAGE.search(text)),
        "contains_duration": bool(CONTAINS_DURATION.search(text)),
        "contains_money": bool(CONTAINS_MONEY.search(text)),
    }


REF_REGEX = re.compile(
    r"\b("
    r"(?:Section|Sec\.|Clause|Cl\.|Annexure|Annex\.|Schedule|Sched\.)"
    r"\s+"
    r"(?:"
    r"(?:\d+(?:\.\d+)*[a-z]?|[A-Z]+|[I|V|X|L|C|D|M]+)\([a-z0-9]\)"
    r"|"
    r"(?:\d+(?:\.\d+)*[a-z]?|[A-Z]+|[I|V|X|L|C|D|M]+)\b"
    r")"
    r")",
    re.IGNORECASE
)


def detect_references(text: str) -> str:
    matches = REF_REGEX.findall(text)
    normalized_matches = []
    for m in matches:
        m_clean = " ".join(m.split())
        normalized_matches.append(m_clean)
    
    unique_refs = []
    seen = set()
    for ref in normalized_matches:
        ref_lower = ref.lower()
        if ref_lower not in seen:
            seen.add(ref_lower)
            unique_refs.append(ref)
            
    return "|".join(unique_refs)


def infer_semantic_type(text: str, chunk_type: str, heading_path: str) -> str:
    text_lower = text.lower()
    path_lower = heading_path.lower()
    combined = f"{path_lower} \n {text_lower}"
    
    if chunk_type in ("table", "table_row") or "[Context: " in text and "| Col " in text:
        return "table"
        
    faq_keywords = {"faq", "frequently asked questions", "q&a", "questions and answers"}
    if any(k in combined for k in faq_keywords):
        return "faq"
    if re.search(r"\b(what|how|why|when|who|where|is\s+there|can\s+i)\b.*\?", text_lower):
        return "faq"
        
    exclusion_keywords = {"exclusion", "exclusions", "exclude", "excluded", "not covered", "what is not covered", "permanent exclusion"}
    if any(k in combined for k in exclusion_keywords):
        return "exclusion"
        
    waiting_keywords = {"waiting period", "waiting periods", "wait period", "wait periods", "survival period"}
    if any(k in combined for k in waiting_keywords):
        return "waiting_period"
        
    claim_keywords = {"claim process", "claims procedure", "claim settlement", "reimbursement", "cashless", "how to claim", "claim notification", "claim form", "submitting claim"}
    if any(k in combined for k in claim_keywords):
        return "claim_process"
    if "claim" in path_lower or "claims" in path_lower:
        return "claim_process"
        
    premium_keywords = {"premium", "premiums", "premium rate", "premium payment", "payment of premium", "grace period"}
    if any(k in combined for k in premium_keywords):
        return "premium"
        
    eligibility_keywords = {"eligibility", "eligible", "age limit", "entry age", "maximum age", "who can buy", "who is eligible"}
    if any(k in combined for k in eligibility_keywords):
        return "eligibility"
        
    network_keywords = {"network hospital", "network provider", "network clinic", "hospital network", "non-network", "preferred provider", "cashless facility"}
    if any(k in combined for k in network_keywords):
        return "hospital_network"
        
    definition_keywords = {"definition", "definitions", "defined term", "means", "refers to", "shall mean"}
    if "definition" in path_lower or "definitions" in path_lower:
        return "definition"
    if re.match(r"^\s*\"?[A-Z][a-zA-Z\s]{1,30}\"?\s+(means|refers to|shall mean)\b", text):
        return "definition"
        
    benefit_keywords = {"benefit", "benefits", "sum insured", "restore benefit", "reinsurance", "cumulative bonus", "no claim bonus", "maternity benefit"}
    if any(k in combined for k in benefit_keywords):
        return "benefit"
        
    coverage_keywords = {"coverage", "coverages", "cover", "scope of cover", "what we cover", "hospitalization cover", "in-patient cover"}
    if any(k in combined for k in coverage_keywords):
        return "coverage"
        
    contact_keywords = {"helpline", "toll-free", "customer care", "email support", "contact us", "phone number", "website", "address", "call center"}
    if any(k in combined for k in contact_keywords):
        return "contact"
        
    return "general"


class StructuredChunkBuilder:
    """Builds enriched, structure-preserving chunks from a DocumentTree."""

    def __init__(self, max_characters: int = 1000, table_row_prefix: str = "Table"):
        self.max_characters = max_characters
        self.table_row_prefix = table_row_prefix

    def _enrich_metadata(self, text: str, chunk_type: str, heading_path: str) -> Dict[str, Any]:
        flags = _content_flags(text)
        flags["references"] = detect_references(text)
        flags["semantic_type"] = infer_semantic_type(text, chunk_type, heading_path)
        return flags

    # -- table handling ----------------------------------------------------
    def _build_table_chunks(
        self, block: ContentBlock, section: Section, base_metadata: Dict[str, Any], block_index: int
    ) -> List[Document]:
        table_text = "\n".join(block.lines)
        parent_id = _generate_chunk_id(base_metadata["document_id"], base_metadata.get("heading_path", ""), block_index, table_text)

        parent_metadata = dict(base_metadata)
        parent_metadata.update({
            "chunk_id": parent_id,
            "chunk_type": "table",
            "is_parent": True,
            "contains_table": True,
            "contains_bullets": False,
            "page_start": block.page_start,
            "page_end": block.page_end,
        })
        parent_metadata.update(self._enrich_metadata(table_text, "table", parent_metadata.get("heading_path", "")))
        documents = [Document(page_content=self._with_context(table_text, section, base_metadata), metadata=parent_metadata)]

        cleaned_rows = [row.strip() for row in block.lines if row.strip()]
        headers: List[str] = []
        if cleaned_rows:
            headers = [h.strip() for h in cleaned_rows[0].strip("|").split("|") if h.strip()]

        data_start_idx = 1
        if len(cleaned_rows) > 1 and all(c in "-:| " for c in cleaned_rows[1]):
            data_start_idx = 2

        for row_idx, row in enumerate(cleaned_rows[data_start_idx:], 1):
            cells = [c.strip() for c in row.strip("|").split("|") if c.strip()]
            if not cells:
                continue
            row_content = "; ".join(f"{h} = {c}" for h, c in zip(headers, cells)) if headers else "; ".join(cells)
            row_text = f"{self.table_row_prefix} ({section.title or 'Data'}): {row_content}."
            row_metadata = dict(base_metadata)
            row_metadata.update({
                "chunk_id": f"{parent_id}_row_{row_idx}",
                "parent_chunk_id": parent_id,
                "parent_id": parent_id,
                "chunk_type": "table_row",
                "is_parent": False,
                "contains_table": True,
                "contains_bullets": False,
                "page_start": block.page_start,
                "page_end": block.page_end,
            })
            row_metadata.update(self._enrich_metadata(row_text, "table_row", row_metadata.get("heading_path", "")))
            documents.append(Document(page_content=self._with_context(row_text, section), metadata=row_metadata))

        return documents

    # -- bullet handling -----------------------------------------------------
    def _build_bullet_chunks(
        self, block: ContentBlock, section: Section, base_metadata: Dict[str, Any], block_index: int
    ) -> List[Document]:
        items = block.lines
        groups: List[List[str]] = []
        current: List[str] = []
        current_len = 0

        for item in items:
            if current and current_len + len(item) > int(self.max_characters * 1.5):
                groups.append(current)
                current = []
                current_len = 0
            current.append(item)
            current_len += len(item) + 1
        if current:
            groups.append(current)

        documents = []
        for group_idx, group in enumerate(groups):
            text = "\n".join(group)
            chunk_id = _generate_chunk_id(base_metadata["document_id"], base_metadata.get("heading_path", ""), f"{block_index}_{group_idx}", text)
            metadata = dict(base_metadata)
            metadata.update({
                "chunk_id": chunk_id,
                "chunk_type": "bullet_group",
                "contains_table": False,
                "contains_bullets": True,
                "bullet_count": len(group),
                "page_start": block.page_start,
                "page_end": block.page_end,
            })
            metadata.update(self._enrich_metadata(text, "bullet_group", metadata.get("heading_path", "")))
            documents.append(Document(page_content=self._with_context(text, section, base_metadata), metadata=metadata))
        return documents

    # -- paragraph handling ---------------------------------------------------
    def _pack_paragraphs(
        self, blocks: List[ContentBlock], section: Section, base_metadata: Dict[str, Any], start_index: int
    ) -> List[Document]:
        """Packs consecutive paragraph blocks of one section into
        sentence-safe, max_characters-bounded chunks. Short leftovers are
        merged forward rather than dropped."""
        if not blocks:
            return []

        # Flatten to sentences while tracking each sentence's source page range.
        sentence_entries: List[Tuple[str, int, int]] = []
        for block in blocks:
            text = " ".join(block.lines).strip()
            if not text:
                continue
            sentences = [s.strip() for s in SENTENCE_BOUNDARY.split(text) if s.strip()]
            if not sentences:
                sentences = [text]
            for sentence in sentences:
                sentence_entries.append((sentence, block.page_start, block.page_end))

        packs: List[Tuple[str, int, int]] = []
        current_text = ""
        current_start = None
        current_end = None

        def close_pack():
            nonlocal current_text, current_start, current_end
            if current_text.strip():
                packs.append((current_text.strip(), current_start, current_end))
            current_text = ""
            current_start = None
            current_end = None

        for sentence, page_start, page_end in sentence_entries:
            if current_start is None:
                current_start = page_start
            current_end = page_end
            candidate = f"{current_text} {sentence}".strip() if current_text else sentence
            if len(candidate) > self.max_characters and current_text:
                close_pack()
                current_start = page_start
                current_end = page_end
                current_text = sentence
            else:
                current_text = candidate
        close_pack()

        # Merge any pack shorter than MIN_MERGE_CHARACTERS into a neighbor so
        # meaningful short clauses are preserved rather than discarded.
        merged: List[Tuple[str, int, int]] = []
        for pack in packs:
            text, page_start, page_end = pack
            if merged and len(text) < MIN_MERGE_CHARACTERS and len(merged[-1][0]) + len(text) <= self.max_characters * 1.4:
                prev_text, prev_start, prev_end = merged[-1]
                merged[-1] = (f"{prev_text} {text}".strip(), prev_start, max(prev_end, page_end))
            else:
                merged.append(pack)
        # A single very short pack with nothing to merge into is still kept --
        # it may be the only (and most important) sentence in the section.

        documents = []
        for idx, (text, page_start, page_end) in enumerate(merged):
            chunk_id = _generate_chunk_id(base_metadata["document_id"], base_metadata.get("heading_path", ""), start_index + idx, text)
            metadata = dict(base_metadata)
            metadata.update({
                "chunk_id": chunk_id,
                "chunk_type": "paragraph",
                "contains_table": False,
                "contains_bullets": False,
                "page_start": page_start,
                "page_end": page_end,
            })
            metadata.update(self._enrich_metadata(text, "paragraph", metadata.get("heading_path", "")))
            documents.append(Document(page_content=self._with_context(text, section, base_metadata), metadata=metadata))
        return documents

    def _with_context(self, text: str, section: Section, base_metadata: Optional[Dict[str, Any]] = None) -> str:
        heading_path = " > ".join([p for p in section.heading_path if p])
        prefix_parts = []
        if base_metadata:
            carrier = base_metadata.get("carrier") or base_metadata.get("category_1")
            if carrier:
                prefix_parts.append(f"Carrier: {carrier}")
            
            lob = base_metadata.get("line_of_business")
            sp = base_metadata.get("sub_product")
            prod = base_metadata.get("product")
            doc_name = base_metadata.get("document_name")
            product_name = ""
            if lob:
                product_name = lob
            elif sp:
                product_name = sp
            elif prod:
                product_name = prod
            elif doc_name:
                import re
                clean_name = re.sub(r"_(?:policy|wording|prospectus|cis|claim|form|bond|uin).*", "", doc_name, flags=re.IGNORECASE)
                clean_name = clean_name.replace("_", " ").strip()
                product_name = clean_name
            if product_name:
                prefix_parts.append(f"Product: {product_name}")
        if heading_path:
            prefix_parts.append(f"Heading: {heading_path}")
            
        if not prefix_parts:
            return text
            
        prefix = " | ".join(prefix_parts)
        return f"[Context: {prefix}] \n\n{text}"

    # -- section-level orchestration -----------------------------------------
    def _base_metadata(self, tree: DocumentTree, section: Section) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "document_id": tree.document_id,
            "source": tree.source,
            "filename": tree.source,
            "relative_path": tree.relative_path,
            "document_type": tree.document_type,
            "document_priority": tree.document_priority,
            "section_number": section.section_number,
            "section_title": section.title,
            "section_level": section.level,
            "heading_path": " > ".join([p for p in section.heading_path if p]),
            "heading_confidence": getattr(section, "heading_confidence", 1.0),
            "parent_chunk_id": "",
        }
        for key, value in tree.folder_metadata.items():
            metadata[key] = value if value is not None else ""
        return metadata

    def build_document_chunks(self, tree: DocumentTree) -> List[Document]:
        documents: List[Document] = []

        for section in tree.root.iter_all():
            if not section.blocks:
                continue
            base_metadata = self._base_metadata(tree, section)

            # Group this section's *own* blocks (not its children's) into
            # runs of the same type so bullet groups and tables stay intact
            # while adjacent paragraph blocks get packed together.
            paragraph_run: List[ContentBlock] = []
            block_counter = 0

            def flush_paragraph_run():
                nonlocal paragraph_run, block_counter
                if paragraph_run:
                    documents.extend(
                        self._pack_paragraphs(paragraph_run, section, base_metadata, block_counter)
                    )
                    block_counter += len(paragraph_run)
                    paragraph_run = []

            for block in section.blocks:
                if block.block_type == "table":
                    flush_paragraph_run()
                    documents.extend(self._build_table_chunks(block, section, base_metadata, block_counter))
                    block_counter += 1
                elif block.block_type == "bullet_group":
                    flush_paragraph_run()
                    documents.extend(self._build_bullet_chunks(block, section, base_metadata, block_counter))
                    block_counter += 1
                else:
                    paragraph_run.append(block)
            flush_paragraph_run()

        # Assign globally unique chunk_index + retrieval_text for BM25/hybrid search.
        for idx, doc in enumerate(documents):
            doc.metadata["chunk_index"] = idx
            if idx > 0:
                doc.metadata["previous_chunk_id"] = documents[idx - 1].metadata.get("chunk_id", "")
            else:
                doc.metadata["previous_chunk_id"] = ""
            if idx < len(documents) - 1:
                doc.metadata["next_chunk_id"] = documents[idx + 1].metadata.get("chunk_id", "")
            else:
                doc.metadata["next_chunk_id"] = ""
            retrieval_parts = [
                str(doc.metadata.get("section_number", "") or ""),
                str(doc.metadata.get("section_title", "") or ""),
                str(doc.metadata.get("heading_path", "") or ""),
                doc.page_content,
            ]
            doc.metadata["retrieval_text"] = " ".join(p for p in retrieval_parts if p)

        return documents

    def build_corpus_chunks(self, trees: List[DocumentTree]) -> List[Document]:
        all_documents: List[Document] = []
        for tree in trees:
            all_documents.extend(self.build_document_chunks(tree))
        for idx, doc in enumerate(all_documents):
            doc.metadata["chunk_index"] = idx
        return all_documents
