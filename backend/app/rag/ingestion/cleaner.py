import re
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ContentCleanerV2:
    """
    Text cleaner for insurance policy PDFs.

    Removes parser noise, administrative headers, section clutter, table of
    contents trails, URLs, and repeated footer fragments before chunk creation.
    """
    def __init__(self):
        self.admin_text = {
            "record of changes",
            "change number",
            "change filed",
            "comments",
            "explanation of changes",
        }
        # 1. Matches revision dates like 2/20/25, 02/20/2025, or text patterns like 'February 20, 2025'
        self.date_pattern = re.compile(
            r'^\s*(\d{1,2}/\d{1,2}/\d{2,4})'  # 2/20/25
            r'|^\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', 
            re.IGNORECASE
        )
        
        # 2. Matches standalone section markers. These are kept for metadata extraction.
        self.section_marker_pattern = re.compile(r'^\s*\d+(?:-\d+){1,3}\.?\s*$')
        # 3. Matches standard URLs (http://... or https://...)
        self.url_pattern = re.compile(r'https?://\S+|www\.\S+')

        # 4. Matches Table of Contents dot trails.
        self.toc_dots_pattern = re.compile(r'\.{4,}\s*\d*.*$')
        self.spaced_toc_dots_pattern = re.compile(r'(?:\.\s*){5,}')
        self.toc_section_entry_pattern = re.compile(
            r'^\s*\d+(?:-\d+){1,3}\.?\s+.{3,100}\s+\d+(?:-\d+){1,3}\.?\s*$'
        )

        # 5. Page number remnants or standard header/footer layout noise
        self.page_noise_pattern = re.compile(r'^\s*(Page\s+\d+|\d+\s*)\s*$', re.IGNORECASE)
        self.separator_pattern = re.compile(
            r'^[-_=]{4,}$'
        )

        # 6. Columnar text detection for table preservation.
        # PyMuPDF's plain-text extraction never emits literal '|' characters,
        # so multi-column table rows would otherwise be invisible to every
        # downstream table detector. A run of 2+ consecutive spaces between
        # tokens is the standard PDF signal for a column boundary; lines with
        # 3+ such gaps (i.e. 3+ cells) are converted to markdown table rows
        # here, before the generic whitespace-collapsing step destroys the
        # column boundaries.
        self.column_gap_pattern = re.compile(r' {2,}')

    def _as_table_row(self, line: str) -> str:
        """
        Converts a columnar PDF text line into a markdown table row when it
        looks like tabular data: 3+ cells separated by runs of 2+ spaces,
        each cell reasonably short (rules out normal justified prose that
        happens to contain a wide gap).
        """
        if not self.column_gap_pattern.search(line):
            return ""
        cells = [c.strip() for c in self.column_gap_pattern.split(line.strip()) if c.strip()]
        if len(cells) < 3:
            return ""
        if any(len(c) > 60 for c in cells):
            return ""
        return "| " + " | ".join(cells) + " |"

    def clean_text(self, text: str) -> str:
        """
        Cleans a block of text line-by-line using structured patterns,
        handles custom typography normalization, and automatically repairs mid-word line-wrap breaks.
        """
        if not text or not text.strip():
            return ""

        cleaned_lines = []
        lines = text.splitlines()

        # --- STEP 1: Aggressive Filtering and Normalization ---
        for line in lines:
            stripped_line = line.strip()
            
            # Skip empty lines early
            if not stripped_line:
                continue
                
            # --- FILTER 0: Document Header ---
            if stripped_line.upper() in {"POLICY WORDING", "PROSPECTUS", "BROCHURE", "POLICY WORDINGS"}:
                continue
                
            # --- FILTER 0.1: Administrative Noise ---
            if stripped_line.lower() in self.admin_text:
                continue

            # --- FILTER 1: Skip Revision Dates ---
            if self.date_pattern.search(stripped_line):
                continue

            # --- FILTER 2: Keep standalone section markers for downstream metadata extraction ---

            # --- FILTER 3: Skip Document Structural Noise (Standalone page numbers or Doc IDs) ---
            if self.page_noise_pattern.match(stripped_line):
                continue
                
            # --- FILTER 3.1: Visual Separators ---
            if self.separator_pattern.match(stripped_line):
                continue
                
            # --- FILTER 4: Clean inline noise (URLs and TOC leaders) ---
            # Remove URLs completely from the line
            processed_line = self.url_pattern.sub("", stripped_line)
            
            # Normalize complex PDF character artifacts. Bullet glyphs are
            # normalized to a single canonical marker ("- ") rather than
            # deleted, so downstream bullet-group detection still works.
            processed_line = (
                processed_line
                .replace("−", "-")
                .replace("“", '"')
                .replace("”", '"')
                .replace("’", "'")
                .replace("ﬁ", "fi")
                .replace("ﬂ", "fl")
                .replace("ﬀ", "ff")
                .replace("ﬃ", "ffi")
                .replace("ﬄ", "ffl")
            )
            processed_line = re.sub(r'^(\s*)[•◦▪▫●○■□]\s*', r'\1- ', processed_line)

            # If the line looks like a TOC entry with dot leaders, drop it completely
            if (
                self.toc_dots_pattern.search(processed_line)
                or self.spaced_toc_dots_pattern.search(processed_line)
                or processed_line.count(".") > 10
                or self.toc_section_entry_pattern.match(processed_line)
            ):
                continue

            # --- FILTER 5: Detect columnar / tabular rows and preserve them
            # as markdown table rows before whitespace collapsing would
            # otherwise erase the column structure entirely.
            table_row = self._as_table_row(processed_line)
            if table_row:
                cleaned_lines.append(table_row)
                continue

            # Clean up residual multiple spaces left over from URL stripping
            processed_line = re.sub(r'\s+', ' ', processed_line).strip()

            if processed_line:
                cleaned_lines.append(processed_line)

        # --- STEP 2: Word De-hyphenation and Line Stitching ---
        # Repairs broken words split across dual-column layouts (e.g., "con-" + "ditions" -> "conditions")
        stitched_lines = []
        i = 0
        total_filtered_lines = len(cleaned_lines)
        
        while i < total_filtered_lines:
            current_line = cleaned_lines[i]
            
            # Look ahead and merge if the line explicitly ends in a layout hyphen split.
            # Table rows and bullet markers are never merged this way -- a table row
            # legitimately ends in a real hyphen inside a cell far more often than it
            # is a mid-word wrap, and merging would corrupt the row structure.
            is_structural_line = current_line.startswith("|") or current_line.startswith("- ")
            while (
                not is_structural_line
                and current_line.endswith("-")
                and (i + 1) < total_filtered_lines
            ):
                next_line = cleaned_lines[i + 1]
                # Strip the trailing layout hyphen and join the lines seamlessly
                current_line = current_line[:-1] + next_line
                i += 1
            
            stitched_lines.append(current_line)
            i += 1

        # Re-join clean elements using standard newline breaks for the downstream builders
        return "\n".join(stitched_lines)

    def clean_pages(self, loaded_pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Processes an entire array of loaded page dictionaries.
        
        Input: Same schema as loader.py output.
        """
        logger.info(f"Starting V2 cleaning run over {len(loaded_pages)} loaded pages.")
        cleaned_pages = []
        
        total_lines_before = 0
        total_lines_after = 0

        for page_data in loaded_pages:
            raw_text = page_data.get("text", "")
            total_lines_before += len(raw_text.splitlines())

            cleaned_text = self.clean_text(raw_text)
            total_lines_after += len(cleaned_text.splitlines())

            # Maintain contract metadata structure intact
            cleaned_pages.append({
                "source": page_data["source"],
                "page": page_data["page"],
                "text": cleaned_text
            })

        logger.info(
            f"V2 Cleaning complete. "
            f"Lines processed: {total_lines_before} -> Lines remaining: {total_lines_after}"
        )
        return cleaned_pages

# Quick validation block
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Simulating structural noise from an insurance policy document
    mock_raw_data = [
        {
            "source": "data/raw_docs/health_policy.pdf",
            "page": 12,
            "text": (
                "Record of Changes\n"
                "2/20/25\n"
                "Maternity Benefit Waiting Period.......5-9\n"
                "Hospitalization Claim Filing Procedures\n"
                "5-1-13\n"
                "For more information see https://www.insurance.com/claims\n"
                "Pre-existing Disease Exclusions\n"
                "Page 12"
            )
        }
    ]

    cleaner = ContentCleanerV2()
    results = cleaner.clean_pages(mock_raw_data)
    
    print("\n" + "="*50)
    print("CLEANED TEXT OUTPUT PREVIEW:")
    print("="*50)
    print(results[0]["text"])
    print("="*50)
