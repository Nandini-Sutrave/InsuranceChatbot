"""
Ingestion diagnostics.

Produces a structured report of what the pipeline actually extracted, at
every level of the hierarchy:

    Document -> Sections -> Subsections -> Chunks -> Tables -> Lists

plus corpus-wide chunk-size and chunk-type distributions, so ingestion
quality can be inspected and regressions caught without re-reading PDFs by
hand.
"""
import json
import logging
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from langchain_core.documents import Document

from .section_tree import DocumentTree, Section

logger = logging.getLogger(__name__)


def _count_sections(section: Section) -> Dict[str, int]:
    sections = 0
    subsections = 0
    tables = 0
    lists = 0
    for node in section.iter_all():
        if node.level == 1:
            sections += 1
        elif node.level >= 2:
            subsections += 1
        for block in node.blocks:
            if block.block_type == "table":
                tables += 1
            elif block.block_type == "bullet_group":
                lists += 1
    return {"sections": sections, "subsections": subsections, "tables": tables, "lists": lists}


def build_diagnostics_report(trees: List[DocumentTree], chunks: List[Document]) -> Dict[str, Any]:
    import hashlib
    import statistics

    chunks_by_document: Dict[str, List[Document]] = {}
    for chunk in chunks:
        doc_id = chunk.metadata.get("document_id", "unknown")
        chunks_by_document.setdefault(doc_id, []).append(chunk)

    document_reports = []
    for tree in trees:
        counts = _count_sections(tree.root)
        doc_chunks = chunks_by_document.get(tree.document_id, [])
        chunk_sizes = [len(c.page_content) for c in doc_chunks]
        
        # Calculate duplicates within document
        seen_doc_hashes = set()
        doc_duplicates = 0
        for c in doc_chunks:
            normalized = " ".join(c.page_content.lower().split())
            h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            if h in seen_doc_hashes:
                doc_duplicates += 1
            else:
                seen_doc_hashes.add(h)
                
        document_reports.append({
            "document_id": tree.document_id,
            "source": tree.source,
            "relative_path": tree.relative_path,
            "document_type": tree.document_type,
            "document_priority": tree.document_priority,
            "sections": counts["sections"],
            "subsections": counts["subsections"],
            "tables": counts["tables"],
            "lists": counts["lists"],
            "chunks": len(doc_chunks),
            "average_chunk_size": round(mean(chunk_sizes), 1) if chunk_sizes else 0,
            "duplicate_chunks": doc_duplicates,
            "unique_chunks": len(doc_chunks) - doc_duplicates,
        })

    all_sizes = [len(c.page_content) for c in chunks]
    
    # Global de-duplication stats
    seen_hashes = set()
    duplicate_chunks_count = 0
    empty_chunks_count = 0
    
    for chunk in chunks:
        content = chunk.page_content
        if not content or not content.strip():
            empty_chunks_count += 1
            continue
        
        normalized = " ".join(content.lower().split())
        h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if h in seen_hashes:
            duplicate_chunks_count += 1
        else:
            seen_hashes.add(h)
            
    total_raw_chunks = len(chunks)
    unique_chunks_count = total_raw_chunks - duplicate_chunks_count - empty_chunks_count
    duplicate_ratio = duplicate_chunks_count / total_raw_chunks if total_raw_chunks > 0 else 0.0

    chunk_type_distribution: Dict[str, int] = {}
    for chunk in chunks:
        chunk_type = chunk.metadata.get("chunk_type", "unknown")
        chunk_type_distribution[chunk_type] = chunk_type_distribution.get(chunk_type, 0) + 1

    # Metadata completeness
    expected_keys = [
        "document_id", "source", "relative_path", "document_type", 
        "document_priority", "section_number", "section_title", 
        "heading_path", "chunk_type", "page_start", "page_end"
    ]
    key_counts = {k: 0 for k in expected_keys}
    for chunk in chunks:
        for k in expected_keys:
            val = chunk.metadata.get(k)
            if val is not None and val != "":
                key_counts[k] += 1
                
    metadata_completeness = {
        k: round(count / total_raw_chunks, 3) if total_raw_chunks > 0 else 0.0
        for k, count in key_counts.items()
    }

    # Largest tables
    tables = [c for c in chunks if c.metadata.get("chunk_type") == "table"]
    tables_sorted = sorted(tables, key=lambda c: len(c.page_content), reverse=True)
    largest_tables = [
        {
            "source": t.metadata.get("source"),
            "section_title": t.metadata.get("section_title"),
            "heading_path": t.metadata.get("heading_path"),
            "length": len(t.page_content),
            "page_start": t.metadata.get("page_start"),
        }
        for t in tables_sorted[:10]
    ]

    # Largest bullet groups
    bullets = [c for c in chunks if c.metadata.get("chunk_type") == "bullet_group"]
    bullets_sorted = sorted(bullets, key=lambda c: len(c.page_content), reverse=True)
    largest_bullet_groups = [
        {
            "source": b.metadata.get("source"),
            "section_title": b.metadata.get("section_title"),
            "heading_path": b.metadata.get("heading_path"),
            "length": len(b.page_content),
            "bullet_count": b.metadata.get("bullet_count", 0),
            "page_start": b.metadata.get("page_start"),
        }
        for b in bullets_sorted[:10]
    ]

    report = {
        "documents_processed": len(trees),
        "total_chunks": total_raw_chunks,
        "unique_chunks": unique_chunks_count,
        "duplicate_chunks": duplicate_chunks_count,
        "duplicate_ratio": round(duplicate_ratio, 4),
        "empty_chunks": empty_chunks_count,
        "skipped_chunks": duplicate_chunks_count + empty_chunks_count,
        "average_chunk_size": round(mean(all_sizes), 1) if all_sizes else 0,
        "average_chunk_length": round(mean(all_sizes), 1) if all_sizes else 0,
        "median_chunk_length": int(statistics.median(all_sizes)) if all_sizes else 0,
        "max_chunk_length": max(all_sizes) if all_sizes else 0,
        "min_chunk_length": min(all_sizes) if all_sizes else 0,
        "average_chunks_per_document": round(total_raw_chunks / len(trees), 1) if trees else 0.0,
        "chunk_type_distribution": chunk_type_distribution,
        "chunk_type_histogram": chunk_type_distribution,
        "metadata_completeness": metadata_completeness,
        "largest_tables": largest_tables,
        "largest_bullet_groups": largest_bullet_groups,
        "documents": document_reports,
    }
    return report


def write_diagnostics_report(report: Dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=True)
    logger.info("Wrote ingestion diagnostics report to '%s'.", output_path)


def print_diagnostics_summary(report: Dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("    INGESTION DIAGNOSTICS")
    print("=" * 60)
    print(f"- Documents processed   : {report['documents_processed']}")
    print(f"- Total raw chunks      : {report['total_chunks']}")
    print(f"- Unique chunks         : {report['unique_chunks']}")
    print(f"- Duplicate chunks      : {report['duplicate_chunks']} (ratio: {report['duplicate_ratio']:.2%})")
    print(f"- Empty chunks          : {report['empty_chunks']}")
    print(f"- Average chunk size    : {report['average_chunk_size']} chars")
    print(f"- Median chunk size     : {report.get('median_chunk_length', 0)} chars")
    print(f"- Max chunk size        : {report.get('max_chunk_length', 0)} chars")
    print(f"- Min chunk size        : {report.get('min_chunk_length', 0)} chars")
    print("- Chunk type distribution:")
    for chunk_type, count in sorted(report["chunk_type_distribution"].items(), key=lambda kv: -kv[1]):
        print(f"    {chunk_type:15}: {count}")
    print("- Per-document breakdown:")
    for doc in report["documents"]:
        print(
            f"    {doc['relative_path']:45} "
            f"sections={doc['sections']:<3} subsections={doc['subsections']:<3} "
            f"tables={doc['tables']:<3} lists={doc['lists']:<3} chunks={doc['chunks']:<4} "
            f"avg_size={doc['average_chunk_size']}"
        )
    print("=" * 60 + "\n")
