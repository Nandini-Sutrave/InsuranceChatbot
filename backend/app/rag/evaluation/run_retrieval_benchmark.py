import os
import sys
import time
import json
import re
import datetime
from pathlib import Path
from typing import List, Dict, Any

# Add project root to sys.path
backend_dir = Path(__file__).resolve().parents[3]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.rag.retrieval.retriever import HybridRetriever

def calculate_jaccard(text1: str, text2: str) -> float:
    words1 = set(re.findall(r"\b\w{3,}\b", text1.lower()))
    words2 = set(re.findall(r"\b\w{3,}\b", text2.lower()))
    if not words1 or not words2:
        return 0.0
    return len(words1 & words2) / len(words1 | words2)

def classify_failure(query: str, expected_heading: str, expected_keywords: List[str], results: list) -> str:
    # 1. Boilerplate check
    q_low = query.lower()
    bp_terms = ["address", "phone", "email", "ombudsman", "ombudsmen", "toll free", "tollfree", "corporate office", "registered office"]
    if any(term in q_low for term in bp_terms) or any(term in expected_heading.lower() for term in bp_terms):
        return "Boilerplate/Contact Detail"
        
    # 2. Layout/Parser check
    layout_headers = ["days", "yrs", "adults", "title", "description", "na"]
    parts = [p.strip().lower() for p in expected_heading.split(">") if p.strip()]
    if any(p in layout_headers for p in parts):
        return "Layout/Parser Noise"
        
    # 3. Recall check
    # Check if the expected document is present in the database or if keywords are completely missing
    if not results:
        return "Recall Failure (Empty Results)"
        
    # Check if we retrieved chunks from the same document at all
    expected_doc = ""
    # Simple document heuristics
    if "sbi" in q_low or "saral" in q_low:
        expected_doc = "SBI"
    elif "hdfc" in q_low or "click" in q_low or "health protector" in q_low:
        expected_doc = "HDFC"
        
    has_doc_match = False
    for res in results:
        res_meta = res.get("metadata", {})
        fn = str(res_meta.get("filename") or "").lower()
        carrier = str(res_meta.get("carrier") or "").lower()
        if expected_doc and (expected_doc.lower() in fn or expected_doc.lower() in carrier):
            has_doc_match = True
            break
            
    if expected_doc and not has_doc_match:
        return "Recall Failure (Wrong Document Policy Routed)"
        
    # 4. Ranking check (it was fetched but ranked too low)
    return "Ranking/Reranker Optimization Failure"

def main():
    use_human = "--human" in sys.argv
    eval_filename = "human_benchmark.json" if use_human else "evaluation.json"
    
    print("=" * 95)
    print(f"                  INSURANCE Policy Retrieval Engine Evaluator ({eval_filename.upper()})")
    print("=" * 95)

    eval_file = Path(__file__).resolve().parent / eval_filename
    if not eval_file.exists():
        print(f"Error: {eval_filename} not found at {eval_file}")
        return

    with open(eval_file, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    print(f"Loaded {len(dataset)} evaluation queries. Initializing HybridRetriever...")
    retriever = HybridRetriever()

    total_queries = len(dataset)
    hits = 0
    hits_at_5 = 0
    hits_at_10 = 0
    reciprocal_ranks_sum = 0.0
    latencies = []
    
    # Diversity trackers
    all_retrieved_source_pages = set()
    all_retrieved_headings = set()
    total_retrieved_chunks = 0
    duplicate_chunk_count = 0
    
    # Aggregated metrics per query
    doc_diversities = []
    sec_diversities = []
    page_diversities = []
    
    # Failure clustering
    failure_counts = {}
    
    query_details = []

    for idx, item in enumerate(dataset, 1):
        query = item["query"]
        expected_heading = item["expected_heading"]
        expected_keywords = item["expected_keywords"]
        negative_keywords = item.get("negative_keywords", [])

        start_time = time.time()
        results = retriever.retrieve_relevant_chunks(query)
        latency = time.time() - start_time
        latencies.append(latency)

        total_retrieved_chunks += len(results)

        # Check hits
        hit = False
        hit_rank = -1

        for r_idx, res in enumerate(results, 1):
            res_meta = res.get("metadata", {})
            res_heading = str(res_meta.get("heading_path") or "").lower()
            res_text = res.get("text", "").lower()
            
            # Match condition: heading path matches or keyword overlap >= 65%
            heading_matches = (expected_heading.lower() in res_heading) or (res_heading in expected_heading.lower())
            
            keyword_matches = sum(1 for kw in expected_keywords if kw.lower() in res_text)
            keyword_ratio = keyword_matches / len(expected_keywords) if expected_keywords else 0.0
            
            # Check negative keywords to verify boilerplate demotion
            has_neg_match = False
            for nw in negative_keywords:
                if nw.lower() in res_text:
                    has_neg_match = True
                    break
            
            if (heading_matches or keyword_ratio >= 0.65) and not has_neg_match:
                hit = True
                hit_rank = r_idx
                break

        # Compute metrics for this query
        is_hit = 1 if hit else 0
        is_hit_5 = 1 if (hit and hit_rank <= 5) else 0
        is_hit_10 = 1 if (hit and hit_rank <= 10) else 0
        mrr = 1.0 / hit_rank if hit else 0.0

        hits += is_hit
        hits_at_5 += is_hit_5
        hits_at_10 += is_hit_10
        reciprocal_ranks_sum += mrr

        # Calculate diversity metrics for this query's top retrieved list
        if results:
            docs = set()
            secs = set()
            pages = set()
            for res in results:
                res_meta = res.get("metadata", {})
                fn = res_meta.get("filename", "unknown")
                pg = res_meta.get("page_number", "unknown")
                h_path = res_meta.get("heading_path", "unknown")
                
                docs.add(fn)
                secs.add(h_path)
                pages.add((fn, pg))
                
                all_retrieved_source_pages.add((fn, pg))
                all_retrieved_headings.add(h_path)
                
            doc_diversities.append(len(docs) / len(results))
            sec_diversities.append(len(secs) / len(results))
            page_diversities.append(len(pages) / len(results))
        else:
            doc_diversities.append(0.0)
            sec_diversities.append(0.0)
            page_diversities.append(0.0)

        # Check duplicate similarity inside this query's retrieved chunks
        if len(results) > 1:
            for i in range(len(results)):
                for j in range(i + 1, len(results)):
                    sim = calculate_jaccard(results[i]["text"], results[j]["text"])
                    if sim > 0.85:
                        duplicate_chunk_count += 1

        # Failure Clustering
        failure_type = "None (Hit)"
        if not hit:
            failure_type = classify_failure(query, expected_heading, expected_keywords, results)
            failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1

        query_details.append({
            "query": query,
            "expected_heading": expected_heading,
            "hit": bool(hit),
            "rank": hit_rank,
            "mrr": mrr,
            "latency_ms": round(latency * 1000, 2),
            "retrieved_count": len(results),
            "failure_cluster": failure_type
        })

        if idx % 10 == 0 or idx == total_queries:
            print(f"Processed {idx}/{total_queries} queries... Current MRR: {reciprocal_ranks_sum / idx:.4f}")

    # Compute overall metrics
    avg_latency = sum(latencies) / total_queries
    hit_rate = hits / total_queries
    recall_at_5 = hits_at_5 / total_queries
    recall_at_10 = hits_at_10 / total_queries
    mrr_score = reciprocal_ranks_sum / total_queries
    
    dup_ratio = (duplicate_chunk_count / (total_retrieved_chunks / 2.0)) if total_retrieved_chunks > 1 else 0.0
    
    avg_doc_div = sum(doc_diversities) / total_queries
    avg_sec_div = sum(sec_diversities) / total_queries
    avg_page_div = sum(page_diversities) / total_queries

    # Versioning metadata
    version_meta = {
        "date": datetime.datetime.utcnow().isoformat() + "Z",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "chunk_version": "2026-07-22-V2-Ingestion",
        "retriever_version": "1.2.0-Explainability-Log",
        "generator_version": "1.0.0-Fallback"
    }

    summary = {
        "total_queries": total_queries,
        "hit_rate": round(hit_rate, 4),
        "recall_at_5": round(recall_at_5, 4),
        "recall_at_10": round(recall_at_10, 4),
        "mrr": round(mrr_score, 4),
        "avg_latency_ms": round(avg_latency * 1000, 2),
        "duplicate_ratio": round(dup_ratio, 4),
        "avg_document_diversity": round(avg_doc_div, 4),
        "avg_section_diversity": round(avg_sec_div, 4),
        "avg_page_diversity": round(avg_page_div, 4),
        "unique_source_pages_retrieved": len(all_retrieved_source_pages),
        "unique_headings_retrieved": len(all_retrieved_headings)
    }

    # Print summary report
    print("\n" + "=" * 95)
    print("                              RETRIEVAL BENCHMARK SUMMARY")
    print("-" * 95)
    print(f"- Total Queries evaluated   : {summary['total_queries']}")
    print(f"- Hit Rate (any rank)       : {summary['hit_rate'] * 100:.2f}%")
    print(f"- Recall@5                  : {summary['recall_at_5'] * 100:.2f}%")
    print(f"- Recall@10                 : {summary['recall_at_10'] * 100:.2f}%")
    print(f"- Mean Reciprocal Rank (MRR): {summary['mrr']:.4f}")
    print(f"- Average Latency           : {summary['avg_latency_ms']:.2f} ms")
    print(f"- Duplicate Chunk Ratio     : {summary['duplicate_ratio'] * 100:.2f}%")
    print(f"- Avg Document Diversity    : {summary['avg_document_diversity'] * 100:.2f}%")
    print(f"- Avg Section Diversity     : {summary['avg_section_diversity'] * 100:.2f}%")
    print(f"- Avg Page Diversity        : {summary['avg_page_diversity'] * 100:.2f}%")
    print(f"- Chunk Diversity (Pages)   : {summary['unique_source_pages_retrieved']} unique source-page pairs")
    print(f"- Chunk Diversity (Heads)   : {summary['unique_headings_retrieved']} unique heading sections")
    print("-" * 95)
    print("                              FAILURE CLUSTERING ANALYSIS")
    print("-" * 95)
    if failure_counts:
        for f_type, count in sorted(failure_counts.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_queries) * 100
            print(f"- {f_type:<40} : {count:<3} failures ({pct:.1f}%)")
    else:
        print("- No retrieval failures recorded! 100% Hit Rate.")
    print("=" * 95 + "\n")

    # Save results to file
    out_path = Path(__file__).resolve().parent / f"retrieval_benchmark_results_{'human' if use_human else 'auto'}.json"
    report = {
        "system_version": version_meta,
        "summary": summary,
        "failure_clusters": failure_counts,
        "queries": query_details
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Detailed report saved successfully to {out_path}")

if __name__ == "__main__":
    main()
