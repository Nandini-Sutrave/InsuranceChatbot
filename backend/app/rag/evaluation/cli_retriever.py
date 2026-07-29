import sys
import json
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from app.rag.retrieval.retriever import HybridRetriever

logging.basicConfig(level=logging.WARNING)

def load_benchmark_queries():
    benchmark_path = Path(__file__).resolve().parent / "benchmark.json"
    if benchmark_path.exists():
        try:
            with open(benchmark_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [item["query"] for item in data if "query" in item]
        except Exception as e:
            print(f"Error loading benchmark queries: {e}")
    return []

def run_retrieval_for_query(retriever, query: str):
    print("\n" + "=" * 80)
    print(f"QUERY: \"{query}\"")
    print("=" * 80)
    
    chunks = retriever.retrieve_relevant_chunks(query)
    if not chunks:
        print("No chunks retrieved.")
        return
        
    print(f"Retrieved {len(chunks)} chunks:")
    print("-" * 80)
    for idx, doc in enumerate(chunks, 1):
        # Handle dict or LangChain document format safely
        metadata = doc.metadata if hasattr(doc, "metadata") else doc.get("metadata", {})
        content = doc.page_content if hasattr(doc, "page_content") else doc.get("text", "")
        
        filename = metadata.get("filename", "Unknown File")
        page = metadata.get("page_number", "Unknown")
        c_path = metadata.get("context_path", "N/A")
        score = metadata.get("retrieval_score", 0.0)
        
        print(f"Rank {idx} | Score: {score:.4f} | File: {filename} (Page {page})")
        if c_path and c_path != "N/A":
            print(f"  Context Path: {c_path}")
        
        snippet = " ".join(content.strip().split())[:180]
        print(f"  Snippet: {snippet}...")
        print("-" * 80)

def main():
    retriever = HybridRetriever(k=4)
    
    if len(sys.argv) > 1:
        # Single CLI Query Mode
        query = " ".join(sys.argv[1:])
        print("\n========================================================")
        print("      HYBRID RETRIEVER TEST TOOL (SINGLE QUERY)")
        print("========================================================\n")
        run_retrieval_for_query(retriever, query)
    else:
        # Benchmark Batch Mode
        print("\n========================================================")
        print("      HYBRID RETRIEVER TEST TOOL (BENCHMARK BATCH)")
        print("========================================================\n")
        queries = load_benchmark_queries()
        if not queries:
            print("No queries found in 3_benchmark.json.")
            return
            
        print(f"Running retrieval for all {len(queries)} benchmark queries:")
        for query in queries:
            run_retrieval_for_query(retriever, query)
        print("\nBenchmark retrieval run complete.\n")

if __name__ == "__main__":
    main()
