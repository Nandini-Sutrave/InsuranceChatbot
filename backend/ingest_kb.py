import os
import sys
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("IngestKB")

# Add project root to sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Standardized LOBs and Map
STANDARDIZED_LOBS = [
    "Health", "Motor", "Home", "Personal_Accident", "Cyber", "Travel", 
    "Group", "Protection", "Retirement", "Savings", "Riders", "Regulations"
]

LOB_MAP = {
    "health": "Health",
    "motor": "Motor",
    "car": "Motor",
    "two wheeler": "Motor",
    "home": "Home",
    "grih": "Home",
    "personal accident": "Personal_Accident",
    "cyber": "Cyber",
    "travel": "Travel",
    "group": "Group",
    "protection": "Protection",
    "retirement": "Retirement",
    "savings": "Savings",
    "rider": "Riders",
    "regulation": "Regulations",
    "pos": "Regulations",
    "handbook": "Regulations"
}

def process_single_pdf(file_path_str: str, kb_dir_str: str) -> List[Dict[str, Any]]:
    # Imports inside worker for ProcessPool compatibility
    import fitz
    import hashlib
    from pathlib import Path
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    
    LOB_MAP = {
        "health": "Health",
        "motor": "Motor",
        "car": "Motor",
        "two wheeler": "Motor",
        "home": "Home",
        "grih": "Home",
        "personal accident": "Personal_Accident",
        "cyber": "Cyber",
        "travel": "Travel",
        "group": "Group",
        "protection": "Protection",
        "retirement": "Retirement",
        "savings": "Savings",
        "rider": "Riders",
        "regulation": "Regulations",
        "pos": "Regulations",
        "handbook": "Regulations"
    }

    file_path = Path(file_path_str)
    kb_dir = Path(kb_dir_str)
    relative_path = file_path.relative_to(kb_dir)
    path_parts = list(relative_path.parts)
    filename = path_parts[-1]
    folder_hierarchy = path_parts[:-1]
    
    # 1. Infer carrier dynamically
    carrier = "Other"
    rel_path_lower = str(relative_path).lower()
    if "sbi" in rel_path_lower:
        carrier = "SBI"
    elif "hdfc" in rel_path_lower:
        carrier = "HDFC"
        
    # 2. Map LOB dynamically
    lob = "Other"
    found_lob = False
    for part in folder_hierarchy:
        part_lower = part.lower().replace("_", " ").replace("-", " ")
        for k, v in LOB_MAP.items():
            if k in part_lower:
                lob = v
                found_lob = True
                break
        if found_lob:
            break
    if not found_lob:
        fn_lower = filename.lower().replace("_", " ").replace("-", " ")
        for k, v in LOB_MAP.items():
            if k in fn_lower:
                lob = v
                found_lob = True
                break
                
    # 3. Infer Product Name
    if len(folder_hierarchy) >= 3:
        product_name = folder_hierarchy[2]
    else:
        product_name = file_path.stem.replace("_", " ").replace("-", " ").strip()
        
    chunks = []
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=800,
        chunk_overlap=150
    )
    
    try:
        import re
        doc = fitz.open(file_path)
        active_heading = "General"
        
        for page_idx, page in enumerate(doc):
            # Scan page blocks to update the active heading context
            page_headings = []
            try:
                blocks = page.get_text("dict").get("blocks", [])
                for b in blocks:
                    if "lines" not in b:
                        continue
                    for l in b["lines"]:
                        line_text = "".join([s.get("text", "") for s in l.get("spans", [])]).strip()
                        if not line_text or len(line_text) > 80:
                            continue
                        
                        # Filter out garbage short headings and running headers/footers
                        if len(line_text) < 4 or re.match(r"^[\d\.\s]+$", line_text) or re.match(r"^[^\w\s]+$", line_text):
                            continue
                        
                        line_lower = line_text.lower()
                        if any(term in line_lower for term in ("company limited", "insurance company", "policy wording", "prospectus", "customer information", "sheet", "policy document", "page number")):
                            continue
                        
                        # Inspect font properties
                        spans = l.get("spans", [])
                        is_bold = any((s.get("flags", 0) & 2) or "bold" in s.get("font", "").lower() for s in spans)
                        sizes = [s.get("size", 10) for s in spans]
                        avg_size = sum(sizes) / len(sizes) if sizes else 10
                        
                        starts_with_prefix = line_lower.startswith(("section", "clause", "scope", "table", "exclusion", "benefit", "coverage", "premium", "eligibility", "general", "definitions"))
                        contains_keyword = any(kw in line_lower for kw in ("exclusions", "table of benefits", "base covers", "optional covers", "preamble", "definitions", "scope of cover", "benefits", "eligibility", "general conditions"))
                        starts_with_number = re.match(r"^\d+(\.\d+)*\b", line_text) is not None
                        
                        if starts_with_prefix or contains_keyword or (is_bold and (avg_size > 11 or starts_with_number or len(line_text) < 40)):
                            page_headings.append(line_text)
            except Exception:
                pass
                
            if page_headings:
                # Update active heading context to the last matched heading on the page
                active_heading = page_headings[-1]
                
            page_text = page.get_text("text") or ""
            
            # Table extraction with try-except guard
            table_md = ""
            try:
                tables = page.find_tables()
                if tables and len(tables.tables) > 0:
                    table_mds = []
                    for t in tables:
                        try:
                            table_mds.append(t.to_markdown())
                        except Exception:
                            # fallback custom table to markdown formatter
                            data = t.extract()
                            if data and data[0]:
                                rows = []
                                for r in data:
                                    rows.append([str(cell or "").replace("\n", " ").strip() for cell in r])
                                if not all(all(cell == "" for cell in r) for r in rows):
                                    header = "| " + " | ".join(rows[0]) + " |"
                                    separator = "| " + " | ".join(["---"] * len(rows[0])) + " |"
                                    lines = [header, separator]
                                    for r in rows[1:]:
                                        lines.append("| " + " | ".join(r) + " |")
                                    table_mds.append("\n".join(lines))
                    if table_mds:
                        table_md = "\n\n" + "\n\n".join(table_mds)
            except Exception:
                table_md = ""
                
            if table_md:
                page_text += table_md
                
            if not page_text.strip():
                continue
                
            splits = splitter.split_text(page_text)
            for split in splits:
                if not split.strip():
                    continue
                
                # Prepend active heading to split text
                prepended_text = f"[Section: {active_heading}] {split}"
                
                # hash ID based on prepended text to avoid duplication collisions
                normalized_text = " ".join(prepended_text.lower().split())
                chunk_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
                
                chunks.append({
                    "text": prepended_text,
                    "metadata": {
                        "chunk_id": chunk_hash,
                        "carrier": carrier,
                        "line_of_business": lob,
                        "product_name": product_name,
                        "filename": filename,
                        "page_number": page_idx + 1,
                        "heading_context": active_heading,
                        "full_path_hierarchy": " > ".join(folder_hierarchy),
                        "version": "2026_v1"
                    }
                })
        doc.close()
    except Exception as e:
        pass
        
    return chunks

def run_ingestion():
    kb_dir = backend_dir.parent / "knowledge_base"
    if not kb_dir.exists():
        logger.error(f"Knowledge base directory does not exist: {kb_dir}")
        return
        
    logger.info("=== STARTING PARALLEL KNOWLEDGE BASE INGESTION (V3) ===")
    
    # Discover all PDF files
    pdf_files = sorted(list(kb_dir.rglob("*.pdf")))
    logger.info(f"Discovered {len(pdf_files)} PDF documents.")
    
    t_start = time.time()
    
    # Lock worker count
    max_workers = min(8, os.cpu_count() or 4)
    logger.info(f"Using ProcessPoolExecutor with max_workers={max_workers}")
    
    all_chunks = []
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks
        futures = [
            executor.submit(process_single_pdf, str(f), str(kb_dir))
            for f in pdf_files
        ]
        
        # Accumulate results as they complete
        for idx, fut in enumerate(futures, 1):
            try:
                file_chunks = fut.result()
                all_chunks.extend(file_chunks)
                if idx % 10 == 0 or idx == len(pdf_files):
                    logger.info(f"Parsed {idx}/{len(pdf_files)} files...")
            except Exception as e:
                logger.error(f"Failed to process file: {e}")
                
    # Global Deduplication
    unique_chunks = []
    seen_hashes = set()
    duplicate_count = 0
    
    for chunk in all_chunks:
        chunk_hash = chunk["metadata"]["chunk_id"]
        if chunk_hash in seen_hashes:
            duplicate_count += 1
            continue
        seen_hashes.add(chunk_hash)
        unique_chunks.append(chunk)
        
    t_end = time.time()
    elapsed_time = t_end - t_start
    
    # Write parsed chunks to temporary JSON file
    debug_path = backend_dir / "parsed_chunks_debug.json"
    with open(debug_path, "w", encoding="utf-8") as f:
        json.dump(unique_chunks, f, indent=2, ensure_ascii=True)
        
    # Analyze breakdown
    carrier_counter = Counter()
    lob_counter = Counter()
    for chunk in unique_chunks:
        carrier_counter[chunk["metadata"]["carrier"]] += 1
        lob_counter[chunk["metadata"]["line_of_business"]] += 1
        
    # Print Phase 1 summary report
    print("\n" + "=" * 65)
    print("    PHASE 1 INGESTION SUMMARY REPORT (V3 ARCHITECTURE)")
    print("=" * 65)
    print(f"- Total PDFs Processed  : {len(pdf_files)}")
    print(f"- Total Chunks Created  : {len(all_chunks)}")
    print(f"- Unique Chunks Saved   : {len(unique_chunks)}")
    print(f"- Duplicates Skipped    : {duplicate_count}")
    print(f"- Total Execution Time  : {elapsed_time:.2f} seconds (Verify < 180s)")
    print(f"- Saved Chunks Debug file: {debug_path.resolve()}")
    
    print("\n- Breakdown by Carrier:")
    for carrier, count in sorted(carrier_counter.items()):
        print(f"  * {carrier:15}: {count:6} chunks")
        
    print("\n- Breakdown by Line of Business (LOB):")
    for lob, count in sorted(lob_counter.items()):
        print(f"  * {lob:15}: {count:6} chunks")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    # Windows compatibility block for ProcessPoolExecutor multiprocessing
    run_ingestion()
