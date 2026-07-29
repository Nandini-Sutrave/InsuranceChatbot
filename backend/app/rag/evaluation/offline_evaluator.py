import os
import sys

# Force mock provider to guarantee zero cloud API usage unless "--live" is passed
if "--live" not in sys.argv:
    os.environ["LLM_PROVIDER"] = "mock"

import time
import re
import json
from pathlib import Path
from collections import Counter
from typing import List, Dict, Any

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.rag.generation.generator import InsuranceAssistant

def load_human_benchmark() -> List[Dict[str, Any]]:
    eval_dir = Path(__file__).resolve().parent
    filepath = eval_dir / "human_benchmark.json"
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading human_benchmark.json: {e}")
    else:
        print(f"Warning: human_benchmark.json not found at {filepath}")
    return []

def extract_entities_and_nouns(text: str) -> set:
    entities = set()
    
    # 1. Numeric entities, money, percentages, durations
    numeric_patterns = [
        r'\b\d+(?:,\d+)*(?:\.\d+)?\b',                  # General numbers
        r'\bRs\.\s*\d+(?:,\d+)*\b',                     # Currency Rs.
        r'\b\d+%\b',                                    # Percentages
        r'\b\d+\s*(?:days|months|years|lakhs|lakh)\b'   # Durations/Money words
    ]
    for pattern in numeric_patterns:
        entities.update(re.findall(pattern, text, re.IGNORECASE))
        
    # 2. Uppercase abbreviations (e.g. ICU, OPD, PTD, AYUSH, COVID)
    abbrev_pattern = r'\b[A-Z]{3,5}\b'
    entities.update(re.findall(abbrev_pattern, text))
    
    # 3. Capitalized word sequences (Named Entities)
    cap_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
    words = re.findall(cap_pattern, text)
    for w in words:
        if w.lower() not in {"the", "this", "my", "if", "there", "does", "what", "is", "are", "we", "how", "can"}:
            entities.add(w)
            
    # 4. Key Noun Phrases
    noun_pattern = r'\b[a-zA-Z]+\s+(?:treatment|benefit|policy|period|grant|cover|charges|fee|limit|donor|hospitalization|exclusion|disease|consult|cancellation|age|copay|co-pay)\b'
    entities.update(re.findall(noun_pattern, text, re.IGNORECASE))
    
    return {e.strip() for e in entities if e.strip()}

def extract_citations(text: str) -> List[Dict[str, Any]]:
    citations = []
    # Match page numbers
    page_matches = re.finditer(r'\bpage\s*(\d+)\b', text, re.IGNORECASE)
    for m in page_matches:
        pg = int(m.group(1))
        context_start = max(0, m.start() - 100)
        lookback = text[context_start:m.start()].lower()
        
        doc_type = "unknown"
        if "sbi" in lookback:
            doc_type = "sbi"
        elif "hdfc" in lookback:
            doc_type = "hdfc"
            
        citations.append({
            "page": pg,
            "doc_type": doc_type
        })
    return citations

def compute_citation_correctness(citations: List[Dict[str, Any]], retrieved_sources: List[Dict[str, Any]]) -> float:
    if not citations:
        return 1.0
        
    valid_count = 0
    for cit in citations:
        cit_pg = cit["page"]
        cit_doc = cit["doc_type"]
        
        match_found = False
        for src in retrieved_sources:
            meta = src.get("metadata", {})
            src_pg = meta.get("page_number") or meta.get("page_start")
            src_fn = str(meta.get("filename") or "").lower()
            src_carrier = str(meta.get("carrier") or "").lower()
            
            # Handle float pages
            try:
                src_pg_int = int(float(src_pg)) if src_pg is not None else None
            except ValueError:
                src_pg_int = None
                
            page_matches = (src_pg_int is not None and src_pg_int == cit_pg)
            doc_matches = (cit_doc == "unknown") or (cit_doc in src_fn or cit_doc in src_carrier)
            
            if page_matches and doc_matches:
                match_found = True
                break
        if match_found:
            valid_count += 1
            
    return valid_count / len(citations)

def evaluate_answers():
    print("\n" + "=" * 100)
    print("            INSURANCE POLICY ANSWER QUALITY EVALUATOR (GROUNDEDNESS & CITATIONS)")
    print("=" * 100)
    
    dataset = load_human_benchmark()
    if not dataset:
        print("No human benchmark queries found. Aborting.")
        return
        
    print(f"Loaded {len(dataset)} human queries. Initializing assistant...")
    assistant = InsuranceAssistant()
    
    results = []
    total_latency = 0.0
    total_groundedness = 0.0
    total_citations_correct = 0.0
    total_precision = 0.0
    total_recall = 0.0
    total_f1 = 0.0
    
    for idx, item in enumerate(dataset, 1):
        query = item["query"]
        expected_keywords = item["expected_keywords"]
        
        start_time = time.time()
        res = assistant.generate_answer(query)
        latency = time.time() - start_time
        
        generated = res.get("answer", "")
        sources = res.get("sources", [])
        
        # 1. Compute Keyword-level Precision, Recall, F1
        gen_lower = generated.lower()
        keyword_matches = sum(1 for kw in expected_keywords if kw.lower() in gen_lower)
        
        # Simple F1 approximations against target assertions
        precision = (keyword_matches / len(re.findall(r'\b\w{3,}\b', generated))) if generated else 0.0
        recall = keyword_matches / len(expected_keywords) if expected_keywords else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        
        # 2. Compute Groundedness (Entities Overlap)
        ans_entities = extract_entities_and_nouns(generated)
        
        # Concatenate all retrieved chunks text
        retrieved_text = ""
        retrieved_results = res.get("retrieved_chunks", [])
        if not retrieved_results and hasattr(assistant, "retriever"):
            # If retrieved chunks not returned in assistant result dict, fetch them directly
            retrieved_results = assistant.retriever.retrieve_relevant_chunks(query)
            
        for r in retrieved_results:
            retrieved_text += " " + r.get("text", "")
            
        retrieved_text_lower = retrieved_text.lower()
        
        grounded_count = 0
        for ent in ans_entities:
            if ent.lower() in retrieved_text_lower:
                grounded_count += 1
                
        groundedness = (grounded_count / len(ans_entities)) if ans_entities else 1.0
        hallucination_rate = 1.0 - groundedness
        
        # 3. Compute Citation Correctness
        citations = extract_citations(generated)
        citations_correct = compute_citation_correctness(citations, retrieved_results)
        
        total_latency += latency
        total_groundedness += groundedness
        total_citations_correct += citations_correct
        total_precision += precision
        total_recall += recall
        total_f1 += f1
        
        results.append({
            "query": query,
            "latency_ms": round(latency * 1000, 2),
            "keyword_recall": round(recall, 4),
            "groundedness": round(groundedness, 4),
            "hallucination_rate": round(hallucination_rate, 4),
            "citation_correctness": round(citations_correct, 4),
            "citations_found": len(citations)
        })
        
        print(f"\n{idx}. Query: {query}")
        print(f"   Intent: {res.get('intent', 'unknown')}")
        print(f"   Primary Policy: {res.get('primary_policy', 'unknown')}")
        print(f"   Recall Score: {recall * 100:.1f}% ({keyword_matches}/{len(expected_keywords)} keywords)")
        print(f"   Groundedness: {groundedness * 100:.1f}% (Entities: {grounded_count}/{len(ans_entities)})")
        print(f"   Hallucination Rate: {hallucination_rate * 100:.1f}%")
        print(f"   Citation Correctness: {citations_correct * 100:.1f}% ({len(citations)} citations)")
        
    num_queries = len(dataset)
    avg_latency = total_latency / num_queries
    avg_groundedness = total_groundedness / num_queries
    avg_citations = total_citations_correct / num_queries
    avg_recall = total_recall / num_queries
    
    print("\n" + "=" * 100)
    print("                              GENERATION QUALITY SUMMARY")
    print("-" * 100)
    print(f"- Total Queries evaluated   : {num_queries}")
    print(f"- Average Latency           : {avg_latency:.3f}s")
    print(f"- Average Keyword Recall     : {avg_recall * 100:.2f}%")
    print(f"- Average Fact Groundedness : {avg_groundedness * 100:.2f}%")
    print(f"- Average Hallucination Rate: {(1.0 - avg_groundedness) * 100:.2f}%")
    print(f"- Average Citation Validity : {avg_citations * 100:.2f}%")
    print("=" * 100 + "\n")

if __name__ == "__main__":
    evaluate_answers()
