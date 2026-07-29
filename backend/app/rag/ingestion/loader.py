"""
PDF discovery + folder metadata extraction.

This stage is the first step of the ingestion pipeline:

    PDF Discovery -> Folder Metadata Extraction -> Layout Parsing -> ...

It is intentionally domain-agnostic: no carrier, vendor, or insurer names are
hardcoded anywhere. Every piece of document-level metadata is *inferred* from
where the file lives on disk (its folder path) and how it is named. The same
code works for an insurance corpus, a legal contract repository, a finance
archive, an HR handbook library, or a technical manual set -- the caller just
points it at a root directory and the folder structure becomes metadata.
"""
import hashlib
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OCR fallback dependencies are optional. We check availability once at
# import time rather than per-page: if pytesseract/Pillow aren't installed,
# or the `tesseract` binary isn't on PATH, OCR is silently disabled and the
# loader behaves exactly as before (native-text-only). This is intentionally
# a soft dependency -- it should never be the reason ingestion breaks on a
# machine that hasn't installed the OS-level tesseract package.
# ---------------------------------------------------------------------------
try:
    import pytesseract
    from PIL import Image
    _OCR_LIBS_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore
    Image = None  # type: ignore
    _OCR_LIBS_AVAILABLE = False

_TESSERACT_BINARY_AVAILABLE = shutil.which("tesseract") is not None
OCR_AVAILABLE = _OCR_LIBS_AVAILABLE and _TESSERACT_BINARY_AVAILABLE

if _OCR_LIBS_AVAILABLE and not _TESSERACT_BINARY_AVAILABLE:
    logger.warning(
        "pytesseract/Pillow are installed but the 'tesseract' binary was not found on "
        "PATH. OCR fallback will be skipped for low-text pages until the tesseract-ocr "
        "system package is installed."
    )
elif not _OCR_LIBS_AVAILABLE:
    logger.info(
        "pytesseract/Pillow not installed -- OCR fallback for scanned/low-text pages "
        "is disabled. Install 'pytesseract' + 'Pillow' + the tesseract-ocr system "
        "package to enable it."
    )

# ---------------------------------------------------------------------------
# Generic document-type vocabulary.
#
# These are common, cross-domain document-type words (not organization names)
# used to classify *what kind* of document a file is, and how authoritative
# it typically is relative to other documents in the same corpus. A "policy
# wording" / "contract" / "terms and conditions" style document is treated as
# more authoritative than a "brochure" / "summary" / "marketing" document
# regardless of which industry it comes from.
# ---------------------------------------------------------------------------
DOCUMENT_TYPE_RULES: List[Dict[str, Any]] = [
    {
        "document_type": "primary_agreement",
        "document_priority": 100,
        "keywords": [
            "wording", "policy wording", "contract", "agreement", "terms and conditions",
            "terms conditions", "statute", "act", "regulation", "bylaw", "constitution",
            "master policy", "plan document", "bond", "policy bond", "policy-bond",
        ],
    },
    {
        "document_type": "customer_information_sheet",
        "document_priority": 95,
        "keywords": [
            "customer information sheet", "cis", "key features document", "kfd",
        ],
    },
    {
        "document_type": "certificate_or_schedule",
        "document_priority": 90,
        "keywords": [
            "certificate", "schedule", "endorsement", "rider", "addendum", "amendment",
            "annexure", "appendix",
        ],
    },
    {
        "document_type": "procedural_guide",
        "document_priority": 70,
        "keywords": [
            "manual", "handbook", "guide", "procedure", "sop", "instructions",
            "playbook", "specification", "spec",
        ],
    },
    {
        "document_type": "summary_document",
        "document_priority": 50,
        "keywords": [
            "brochure", "prospectus", "summary", "overview", "factsheet", "fact sheet",
            "leaflet", "highlights", "at a glance",
        ],
    },
    {
        "document_type": "reference_document",
        "document_priority": 40,
        "keywords": ["faq", "glossary", "definitions", "reference", "q&a", "qanda"],
    },
    {
        "document_type": "marketing_material",
        "document_priority": 20,
        "keywords": ["marketing", "flyer", "advertisement", "promo", "presentation", "deck"],
    },
]
DEFAULT_DOCUMENT_TYPE = "general_document"
DEFAULT_DOCUMENT_PRIORITY = 55

# Generic, positional folder metadata keys. Whatever the folder is actually
# named ("StarHealth", "ContractsQ1", "HR-Policies-2026", ...) becomes the
# *value*; only the *key* is generic and positional.
FOLDER_LEVEL_KEYS = ["category_1", "category_2", "category_3", "category_4", "category_5"]

# Best-effort convenience aliases layered on top of the generic category
# levels so downstream retrieval code (written for an insurance vocabulary)
# keeps working without any hardcoded organization names. These are simply
# alternate names for "the same folder value" -- category_1 IS carrier IS
# whatever the top-level folder happens to be called in this corpus.
#
# NOTE: order matters and must match how deep folders are actually nested.
# Previous order ("carrier","product","line_of_business","sub_product") put
# the line-of-business alias one level too deep, so for a
# Carrier/LOB/Product/file.pdf layout it labelled the *product* name as
# "line_of_business" and the actual LOB folder as "product" -- silently
# breaking any downstream filter on line_of_business.
FOLDER_ALIAS_KEYS = ["carrier", "line_of_business", "product", "sub_product"]

# Known carrier tokens used to split a flattened "Carrier-LOB" folder name
# (e.g. a corpus where one carrier's docs are nested Carrier/LOB/Product/file
# but another carrier's docs sit flat as "Carrier-LOB/file", with no
# separate LOB folder level at all). Extend this if new carriers are added.
KNOWN_CARRIER_PREFIXES = ["SBI", "HDFC", "ICICI", "TATA", "BAJAJ", "LIC"]


def _split_compound_carrier_folder(folder_parts: List[str]) -> List[str]:
    """
    Normalizes folder depth across inconsistent corpora. If the first folder
    level is a single compound token like "HDFC-protection" (carrier and LOB
    fused with a hyphen/underscore, and no separate LOB folder beneath it),
    split it into two synthetic levels ["HDFC", "protection"] so it lines up
    positionally with a corpus that already nests Carrier/LOB/... separately
    (e.g. "SBI/Health/..."). Without this, one carrier's documents get a
    correct carrier + line_of_business, and the other carrier's documents get
    a mangled carrier value (the whole compound string) and no LOB at all.
    """
    if not folder_parts:
        return folder_parts
    first = folder_parts[0]
    for prefix in KNOWN_CARRIER_PREFIXES:
        for sep in ("-", "_"):
            marker = f"{prefix}{sep}"
            if first.upper().startswith(marker.upper()) and len(first) > len(marker):
                lob_part = first[len(marker):]
                return [prefix, lob_part] + folder_parts[1:]
    return folder_parts


def _normalize_lob_token(value: Optional[str]) -> Optional[str]:
    """Canonicalize a line-of-business folder value so storage and query-time
    filters compare like-for-like regardless of the source folder's casing or
    separator style ("Personal Accident" / "personal_accident" / "cyber")."""
    if value is None:
        return None
    return _normalize_token(value)


def _normalize_token(value: str) -> str:
    return re.sub(r"[_\-]+", " ", value).strip().lower()


def classify_document(relative_path: Path) -> Dict[str, Any]:
    """
    Infers document_type and document_priority from the filename and full
    relative folder path, using generic cross-domain vocabulary only.
    """
    haystack = _normalize_token(" ".join(relative_path.parts))
    for rule in DOCUMENT_TYPE_RULES:
        for keyword in rule["keywords"]:
            if keyword in haystack:
                return {
                    "document_type": rule["document_type"],
                    "document_priority": rule["document_priority"],
                }
    return {"document_type": DEFAULT_DOCUMENT_TYPE, "document_priority": DEFAULT_DOCUMENT_PRIORITY}


def extract_folder_metadata(root_dir: Path, file_path: Path) -> Dict[str, Any]:
    """
    Turns the directory hierarchy between root_dir and file_path into a
    generic, positional metadata schema. No assumptions are made about what
    the folders represent -- that is left entirely to how the corpus is
    organized on disk, except for one normalization pass (see
    _split_compound_carrier_folder) so mixed folder depths across a corpus
    still line up positionally.
    """
    relative_path = file_path.relative_to(root_dir)
    folder_parts = list(relative_path.parts[:-1])  # exclude filename itself
    folder_parts = _split_compound_carrier_folder(folder_parts)

    metadata: Dict[str, Any] = {}
    for idx, key in enumerate(FOLDER_LEVEL_KEYS):
        metadata[key] = folder_parts[idx] if idx < len(folder_parts) else None

    for idx, alias in enumerate(FOLDER_ALIAS_KEYS):
        metadata[alias] = folder_parts[idx] if idx < len(folder_parts) else None

    # Normalize carrier casing (SBI/HDFC, not "sbi"/"Hdfc") and store a
    # canonical, filter-friendly line_of_business alongside the raw folder
    # value, so retrieval-time filters don't depend on matching exact folder
    # casing/spacing/underscores.
    if metadata.get("carrier"):
        metadata["carrier"] = str(metadata["carrier"]).strip().upper()
    metadata["line_of_business_raw"] = metadata.get("line_of_business")
    metadata["line_of_business"] = _normalize_lob_token(metadata.get("line_of_business"))

    metadata["folder_hierarchy"] = " > ".join(folder_parts) if folder_parts else ""
    metadata["folder_depth"] = len(folder_parts)
    metadata["document_name"] = file_path.stem
    return metadata


@dataclass
class LoadedDocument:
    """A single discovered PDF plus everything known about it before parsing."""
    source: str                       # filename, kept for backward compatibility
    relative_path: str                # path relative to the discovery root
    document_id: str                  # stable id derived from the relative path
    document_type: str = DEFAULT_DOCUMENT_TYPE
    document_priority: int = DEFAULT_DOCUMENT_PRIORITY
    folder_metadata: Dict[str, Any] = field(default_factory=dict)
    total_pages: int = 0
    pages: List[Dict[str, Any]] = field(default_factory=list)


class HybridPDFLoader:
    """
    Recursive, folder-aware PDF loader.

    Walks the entire directory tree beneath `dir_path`, extracts text
    page-by-page with PyMuPDF, and attaches document-level metadata inferred
    purely from folder structure and filename -- no organization-specific
    logic anywhere.
    """

    def __init__(
        self,
        dir_path: Union[str, Path],
        enable_ocr_fallback: bool = True,
        ocr_min_chars: int = 20,
        ocr_dpi: int = 200,
    ):
        self.dir_path = Path(dir_path)
        if not self.dir_path.exists():
            raise FileNotFoundError(f"Target documents directory not found at: {self.dir_path}")
        if not self.dir_path.is_dir():
            raise NotADirectoryError(f"Provided path is not a directory: {self.dir_path}")

        # OCR fallback is opt-out (default True) but self-disables gracefully
        # if pytesseract/Pillow/the tesseract binary aren't available on this
        # machine -- see the OCR_AVAILABLE check above. Pages with fewer than
        # `ocr_min_chars` extracted characters are treated as "effectively
        # image-only" and rendered + OCR'd instead of silently dropped.
        self.enable_ocr_fallback = enable_ocr_fallback and OCR_AVAILABLE
        if enable_ocr_fallback and not OCR_AVAILABLE:
            logger.info(
                "enable_ocr_fallback=True was requested but OCR dependencies are not "
                "available in this environment -- continuing without OCR (low-text "
                "pages will be skipped as before)."
            )
        self.ocr_min_chars = ocr_min_chars
        self.ocr_dpi = ocr_dpi
        self.ocr_pages_recovered = 0
        self.low_text_pages_seen = 0

    def _ocr_page(self, page: "fitz.Page", relative_path: Path, page_num: int) -> str:
        """
        Renders a single PDF page to an image and runs Tesseract OCR on it.
        Only called for pages whose native text extraction came back below
        `ocr_min_chars`. Any failure here is non-fatal -- we log and fall
        back to whatever native text (even if empty) was already extracted,
        so a bad/missing OCR install degrades gracefully rather than
        crashing the whole ingestion run.
        """
        try:
            zoom = self.ocr_dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            img = Image.open(__import__("io").BytesIO(pix.tobytes("png")))
            ocr_text = pytesseract.image_to_string(img)
            return ocr_text or ""
        except Exception as exc:
            logger.warning(
                "OCR fallback failed for %s page %s: %s", relative_path, page_num, exc
            )
            return ""

    def discover_documents(self, filename_substrings: Optional[List[str]] = None) -> List[LoadedDocument]:
        """
        Recursively finds every PDF under dir_path, sorted for determinism.

        By default (filename_substrings=None) this processes the FULL corpus.
        `filename_substrings`, if given, restricts discovery to files whose
        lowercased name contains at least one of the given substrings -- this
        is an explicit, opt-in narrowing for things like a quick smoke-test
        run against a handful of benchmark documents. It must never be a
        silent default: a previous version of this method hardcoded a
        6-substring benchmark whitelist directly in the function body, which
        meant ~94% of a real corpus (everything outside those 6 substrings)
        was silently never ingested, with no warning anywhere.
        """
        pdf_files = sorted(self.dir_path.rglob("*.pdf"))
        if filename_substrings:
            pdf_files = [
                f for f in pdf_files
                if any(p.lower() in f.name.lower() for p in filename_substrings)
            ]
            logger.warning(
                "discover_documents() called with an explicit filename_substrings filter "
                "(%s) -- only files matching it will be ingested. Omit this argument to "
                "process the full corpus.",
                filename_substrings,
            )
        documents: List[LoadedDocument] = []

        seen_hashes = set()
        seen_first_page_texts = set()

        for file_path in pdf_files:
            relative_path = file_path.relative_to(self.dir_path)
            source_name = file_path.name

            try:
                file_bytes = file_path.read_bytes()
                file_hash = hashlib.sha256(file_bytes).hexdigest()
            except Exception as exc:
                logger.error("Failed to read file bytes for hashing %s: %s", relative_path, exc)
                continue

            if file_hash in seen_hashes:
                logger.info("Skipping duplicate PDF file (identical bytes hash): %s", relative_path)
                continue

            try:
                with fitz.open(file_path) as doc:
                    total_pages = len(doc)
                    if total_pages > 0:
                        first_page_text = doc[0].get_text("text").strip()
                        normalized_text = "".join(first_page_text.split()).lower()
                        text_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
                        if text_hash in seen_first_page_texts:
                            logger.info(
                                "Skipping near-identical duplicate PDF (first page text match): %s",
                                relative_path,
                            )
                            continue
                        seen_first_page_texts.add(text_hash)

                    seen_hashes.add(file_hash)

                    folder_metadata = extract_folder_metadata(self.dir_path, file_path)
                    classification = classify_document(relative_path)
                    document_id = hashlib.md5(str(relative_path).encode("utf-8")).hexdigest()[:16]

                    loaded_doc = LoadedDocument(
                        source=source_name,
                        relative_path=str(relative_path),
                        document_id=document_id,
                        document_type=classification["document_type"],
                        document_priority=classification["document_priority"],
                        folder_metadata=folder_metadata,
                        total_pages=total_pages,
                    )

                    for page_idx, page in enumerate(doc):
                        page_num = page_idx + 1
                        text = page.get_text("text")
                        used_ocr = False

                        if len(text.strip()) < self.ocr_min_chars:
                            self.low_text_pages_seen += 1
                            if self.enable_ocr_fallback:
                                ocr_text = self._ocr_page(page, relative_path, page_num)
                                if len(ocr_text.strip()) > len(text.strip()):
                                    text = ocr_text
                                    used_ocr = True
                                    self.ocr_pages_recovered += 1
                                    logger.info(
                                        "Recovered %s chars via OCR for %s page %s "
                                        "(native extraction only yielded %s chars).",
                                        len(ocr_text.strip()), relative_path, page_num,
                                        len(page.get_text('text').strip()),
                                    )

                        if not text.strip():
                            logger.warning(
                                "No extractable text (native or OCR) for %s page %s -- "
                                "this page will be absent from the index.",
                                relative_path, page_num,
                            )
                            continue

                        loaded_doc.pages.append({
                            "source": source_name,
                            "relative_path": str(relative_path),
                            "document_id": document_id,
                            "page": page_num,
                            "text": text,
                            "ocr_used": used_ocr,
                        })

                    documents.append(loaded_doc)
                    logger.info(
                        "Discovered '%s' (%s pages, type=%s, priority=%s)",
                        relative_path, total_pages, loaded_doc.document_type, loaded_doc.document_priority,
                    )

            except Exception as exc:
                logger.error("Failed to load PDF %s: %s", relative_path, exc)
                continue

        logger.info("Total documents discovered: %s", len(documents))
        if self.low_text_pages_seen:
            logger.info(
                "Low-text pages encountered: %s. Recovered via OCR: %s. %s",
                self.low_text_pages_seen,
                self.ocr_pages_recovered,
                "(OCR fallback disabled or unavailable)" if not self.enable_ocr_fallback else "",
            )
        return documents

    def load_all(self) -> List[Dict[str, Any]]:
        """
        Backward-compatible flat page list across every discovered document,
        each page now carrying document_id/relative_path/folder metadata too.

        Output format:
        [
            {
                "source": "Policy Wording.pdf",
                "relative_path": "CarrierA/ProductX/Policy Wording.pdf",
                "document_id": "...",
                "page": 1,
                "text": "...",
                "document_type": "primary_agreement",
                "document_priority": 100,
                "folder_metadata": {...},
            }
        ]
        """
        documents = self.discover_documents()
        if not documents:
            logger.warning("No PDF files found under target directory: %s", self.dir_path)
            return []

        all_pages: List[Dict[str, Any]] = []
        for doc in documents:
            for page in doc.pages:
                enriched_page = dict(page)
                enriched_page["document_type"] = doc.document_type
                enriched_page["document_priority"] = doc.document_priority
                enriched_page["folder_metadata"] = doc.folder_metadata
                all_pages.append(enriched_page)

        logger.info("Total pages combined across all PDFs: %s", len(all_pages))
        return all_pages
