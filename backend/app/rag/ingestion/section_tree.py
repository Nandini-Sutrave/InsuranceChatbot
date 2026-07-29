"""
Layout parsing and section-tree construction.

    Layout Parsing -> Section Tree

Cleaned pages are parsed line-by-line into a hierarchical tree of Section
nodes. Every piece of content (paragraphs, bullet groups, tables) is attached
to the section it structurally belongs to, and every section knows its full
heading path back to the document root. This is what lets the chunk builder
later group "Coverage -> Base Covers -> Death / PTD / PPD" as a coherent,
navigable hierarchy instead of a flat stream of clause-sized fragments.

Heading detection is heuristic (numbered sections, ALL-CAPS lines, title-case
runs) because PDFs carry no semantic markup -- but the heuristics live in one
place, are domain-agnostic, and degrade gracefully: unrecognized "headings"
are simply treated as more paragraph text rather than corrupting the tree.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Line classification patterns
# ---------------------------------------------------------------------------
SECTION_ID_PATTERN = re.compile(r"^\s*(?:section\s+)?(\d+(?:[.-]\d+){0,4})\.?\s*$", re.IGNORECASE)
SECTION_HEADING_PATTERN = re.compile(
    r"^\s*(?:section\s+)?(\d+(?:[.-]\d+){0,4})\.?\s*[:-]?\s*(.{3,120})$", re.IGNORECASE
)
NUMBERED_HEADING_PATTERN = re.compile(
    r"^\s*(?:section\s+)?\d+(?:[.-]\d+){0,4}\.?\s*[:-]?\s*[A-Z][A-Za-z0-9,/()' -]{0,120}$", re.IGNORECASE
)
LEADING_LABEL_PATTERN = re.compile(r"^\s*([a-z]|\d+)\.\s+")
GARBAGE_HEADING_PATTERNS = [
    re.compile(r"^[0-9\-\(\)\sK\.]+$"),
    re.compile(r"^[A-Z]-\d+$"),
]
BULLET_LINE_PATTERN = re.compile(
    r"^\s*(?:"
    r"-\s+|"
    r"\(?[a-zA-Z]\)\s+|[a-zA-Z]\.\s+|"
    r"\(?[ivxIVX]{1,4}\)\s+|[ivxIVX]{1,4}\.\s+|"
    r"\(?\d{1,3}\)\s+|\d{1,3}\.\s+"
    r")"
)
STANDALONE_LIST_LABEL_PATTERN = re.compile(r"^\s*(?:[ivxIVX]+|[a-zA-Z]|\d+)\.\s*$")
TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$")

MIN_HEADING_LEN = 2
MAX_HEADING_LEN = 120


def _looks_like_heading(text: str) -> bool:
    clean_text = text.strip()
    if not clean_text or not (MIN_HEADING_LEN <= len(clean_text) <= MAX_HEADING_LEN):
        return False
    if clean_text.endswith((".", "?", "!", ";", ":")):
        return False
    if "...." in clean_text or " . . ." in clean_text:
        return False
    if LEADING_LABEL_PATTERN.match(clean_text):
        return False

    tokens = [token for token in clean_text.split() if any(char.isalnum() for char in token)]
    if not tokens:
        return False

    heading_tokens = 0
    for token in tokens:
        lowered = token.lower().strip("()[],:;")
        if (
            token[0].isupper()
            or any(char.isdigit() for char in token)
            or lowered in {"and", "or", "for", "the", "of", "in", "to", "with", "on"}
        ):
            heading_tokens += 1

    return (heading_tokens / len(tokens)) >= 0.75


def _extract_section_heading(line: str) -> Optional[Tuple[str, str]]:
    match = SECTION_HEADING_PATTERN.match(line)
    if not match:
        return None
    section_id = match.group(1).strip()
    section_title = match.group(2).strip(" .")
    if NUMBERED_HEADING_PATTERN.match(line):
        return section_id, section_title
    if not _looks_like_heading(section_title):
        return None
    return section_id, section_title


def _is_garbage_heading(title: str) -> bool:
    return (
        any(pat.match(title) for pat in GARBAGE_HEADING_PATTERNS)
        or (len(title.split()) <= 1 and any(char.isdigit() for char in title))
    )


def _heading_level(section_number: str, title: str) -> int:
    """Depth of a heading based on its numbering (3.2.1 -> level 3), falling
    back to simple ALL-CAPS-vs-title-case heuristics when unnumbered."""
    if section_number:
        parts = [p for p in re.split(r"[.-]", section_number) if p.strip()]
        return max(1, len(parts))
    if title.isupper() and len(title) < 50:
        return 1
    return 2


def compute_heading_confidence(section_number: str, title: str, level: int) -> float:
    """Computes a heuristic confidence score (0.0 to 1.0) for a detected heading."""
    confidence = 0.5
    
    # 1. Numbering
    if section_number:
        if "." in section_number or "-" in section_number:
            confidence += 0.3
        else:
            confidence += 0.15
            
    # 2. Capitalization
    title_clean = title.strip()
    if title_clean.isupper():
        if len(title_clean) < 30:
            confidence += 0.2
        else:
            confidence += 0.1
    elif title_clean.istitle() or (len(title_clean) > 0 and title_clean[0].isupper()):
        confidence += 0.05
    else:
        confidence -= 0.25
        
    # 3. Length
    title_len = len(title_clean)
    if title_len < 3 and not section_number:
        confidence -= 0.3
    elif title_len < 5:
        if not title_clean.isupper():
            confidence -= 0.1
    elif 10 <= title_len <= 50:
        confidence += 0.05
    elif title_len > 80:
        confidence -= 0.1
        
    # 4. Level consistency
    if level == 1 and title_clean.isupper():
        confidence += 0.05
    elif level > 1 and section_number:
        confidence += 0.05
        
    return round(max(0.0, min(1.0, confidence)), 2)


# ---------------------------------------------------------------------------
# Tree data structures
# ---------------------------------------------------------------------------
@dataclass
class ContentBlock:
    block_type: str          # "paragraph" | "bullet_group" | "table"
    lines: List[str]
    page_start: int
    page_end: int


@dataclass
class Section:
    section_number: str
    title: str
    level: int
    parent: Optional["Section"] = None
    children: List["Section"] = field(default_factory=list)
    blocks: List[ContentBlock] = field(default_factory=list)
    heading_path: List[str] = field(default_factory=list)
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    heading_confidence: float = 1.0

    def register_page(self, page: int) -> None:
        if self.page_start is None or page < self.page_start:
            self.page_start = page
        if self.page_end is None or page > self.page_end:
            self.page_end = page

    def iter_all(self):
        """Depth-first traversal including self."""
        yield self
        for child in self.children:
            yield from child.iter_all()


@dataclass
class DocumentTree:
    document_id: str
    source: str
    relative_path: str
    document_type: str
    document_priority: int
    folder_metadata: Dict[str, Any]
    root: Section


class SectionTreeBuilder:
    """Parses a document's cleaned pages into a DocumentTree."""

    def build(
        self,
        cleaned_pages: List[Dict[str, Any]],
        document_id: str,
        source: str,
        relative_path: str,
        document_type: str,
        document_priority: int,
        folder_metadata: Dict[str, Any],
    ) -> DocumentTree:
        root = Section(section_number="", title="", level=0, heading_path=[])
        stack: List[Section] = [root]

        state = {
            "paragraph": [],
            "paragraph_start_page": None,
            "bullets": [],
            "bullets_start_page": None,
            "table": [],
            "table_start_page": None,
            "pending_section_id": None,
        }

        def active_section() -> Section:
            return stack[-1]

        def flush_paragraph(end_page: int) -> None:
            if state["paragraph"]:
                text = " ".join(state["paragraph"]).strip()
                start_page = state["paragraph_start_page"] or end_page
                state["paragraph"] = []
                state["paragraph_start_page"] = None
                if text:
                    block = ContentBlock("paragraph", [text], start_page, end_page)
                    active_section().blocks.append(block)
                    active_section().register_page(start_page)
                    active_section().register_page(end_page)

        def flush_bullets(end_page: int) -> None:
            if state["bullets"]:
                start_page = state["bullets_start_page"] or end_page
                block = ContentBlock("bullet_group", list(state["bullets"]), start_page, end_page)
                state["bullets"] = []
                state["bullets_start_page"] = None
                active_section().blocks.append(block)
                active_section().register_page(start_page)
                active_section().register_page(end_page)

        def flush_table(end_page: int) -> None:
            if state["table"]:
                start_page = state["table_start_page"] or end_page
                block = ContentBlock("table", list(state["table"]), start_page, end_page)
                state["table"] = []
                state["table_start_page"] = None
                active_section().blocks.append(block)
                active_section().register_page(start_page)
                active_section().register_page(end_page)

        def flush_all(end_page: int) -> None:
            flush_paragraph(end_page)
            flush_bullets(end_page)
            flush_table(end_page)

        def open_section(section_number: str, title: str, page: int) -> None:
            flush_all(page)
            requested_level = _heading_level(section_number, title)
            level = min(requested_level, len(stack))
            del stack[level:]
            parent = stack[-1]
            confidence = compute_heading_confidence(section_number, title, level)
            section = Section(
                section_number=section_number,
                title=title,
                level=level,
                parent=parent,
                heading_path=parent.heading_path + ([title] if title else []),
                heading_confidence=confidence,
            )
            section.register_page(page)
            parent.children.append(section)
            stack.append(section)

        for page_data in cleaned_pages:
            page_num = page_data["page"]
            lines = page_data.get("text", "").splitlines()

            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    flush_paragraph(page_num)
                    continue

                if TABLE_ROW_PATTERN.match(line):
                    flush_paragraph(page_num)
                    flush_bullets(page_num)
                    if not state["table"]:
                        state["table_start_page"] = page_num
                    state["table"].append(line)
                    continue
                else:
                    flush_table(page_num)

                heading = _extract_section_heading(line)
                if heading and not _is_garbage_heading(heading[1]):
                    flush_bullets(page_num)
                    state["pending_section_id"] = None
                    open_section(heading[0], heading[1], page_num)
                    continue

                standalone_id = SECTION_ID_PATTERN.match(line)
                if standalone_id:
                    flush_paragraph(page_num)
                    flush_bullets(page_num)
                    state["pending_section_id"] = standalone_id.group(1)
                    continue

                if state["pending_section_id"] and _looks_like_heading(line):
                    flush_bullets(page_num)
                    open_section(state["pending_section_id"], line.strip(" ."), page_num)
                    state["pending_section_id"] = None
                    continue

                if _looks_like_heading(line) and not _is_garbage_heading(line):
                    flush_bullets(page_num)
                    open_section(state["pending_section_id"] or "", line.strip(" ."), page_num)
                    state["pending_section_id"] = None
                    continue

                if state["pending_section_id"]:
                    # The standalone number turned out to prefix ordinary text.
                    if not state["paragraph"]:
                        state["paragraph_start_page"] = page_num
                    state["paragraph"].append(state["pending_section_id"])
                    state["pending_section_id"] = None

                if BULLET_LINE_PATTERN.match(line):
                    flush_paragraph(page_num)
                    if not state["bullets"]:
                        state["bullets_start_page"] = page_num
                    state["bullets"].append(line)
                    continue

                flush_bullets(page_num)
                if not state["paragraph"]:
                    state["paragraph_start_page"] = page_num
                state["paragraph"].append(line)
                if line.endswith((".", "?", "!", '."')) and not STANDALONE_LIST_LABEL_PATTERN.match(line):
                    flush_paragraph(page_num)

            # Do not force-flush at page boundaries: paragraphs, bullet
            # groups, and tables legitimately continue across a page break.

        last_page = cleaned_pages[-1]["page"] if cleaned_pages else 0
        flush_all(last_page)

        return DocumentTree(
            document_id=document_id,
            source=source,
            relative_path=relative_path,
            document_type=document_type,
            document_priority=document_priority,
            folder_metadata=folder_metadata,
            root=root,
        )
