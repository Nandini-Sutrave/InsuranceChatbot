import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

load_dotenv()

from app.rag.generation.generator import InsuranceAssistant

# Define 10 diverse benchmark queries to evaluate the RAG pipeline
BENCHMARK_QUERIES = [
    # 1. Direct Coverage / Table Retrieval (SBI - Personal Accident)
    "What is the policy coverage of sbi saral suraksha bima?",
    
    # 2. Tabular Rates / Numeric Scale (HDFC - Retirement)
    "What are the high premium benefit rates for HDFC Life Aajeevan Growth Nivesh and Income policy?",
    
    # 3. Critical Exclusion Clause (HDFC - Protection)
    "What happens to the policy if the insured commits suicide within the first year under HDFC Click 2 Protect?",
    
    # 4. Conditional Optional Cover (SBI - Personal Accident)
    "Is there any education grant for children if the insured person dies in an accident under SBI Saral Suraksha Bima?",
    
    # 5. Waiting Period / Limitations (HDFC - Health)
    "What is the waiting period for pre-existing diseases under the HDFC Health Protector plan?",
    
    # 6. Specific Sub-limit / Cap (SBI - Personal Accident)
    "What are the hospitalisation expenses limits due to an accident under SBI Saral Suraksha Bima?",
    
    # 7. Comparison Query - Multi-Carrier / Multi-LOB (SBI vs HDFC)
    "Compare the accidental death benefits between HDFC Group Term Insurance and SBI Saral Suraksha Bima.",
    
    # 8. Operational / Claims Process (HDFC - Savings/Retirement)
    "What documents are required to file a death claim under HDFC Sanchay Aajeevan Guaranteed Advantage?",
    
    # 9. Rider / Add-on details (HDFC - Riders)
    "What is the critical illness plus rider cover under HDFC Life Click 2 Protect Elite?",
    
    # 10. Out-of-Domain / Negative Test (System Guardrail)
    "Can I use this policy to get a discount on my electricity bill or gym membership?"
]

def run_benchmarks():
    print("=" * 80)
    print("            STARTING INSURANCE RAG PIPELINE BENCHMARK RUN")
    print("=" * 80)
    print(f"Loaded {len(BENCHMARK_QUERIES)} benchmark queries.")
    
    assistant = InsuranceAssistant()
    results = []
    
    for idx, query in enumerate(BENCHMARK_QUERIES, 1):
        print(f"\n[{idx}/10] Running Query: '{query}'")
        print("-" * 80)
        
        t_start = time.time()
        res = assistant.generate_answer(query)
        latency = (time.time() - start_time) * 1000 if 'start_time' in locals() else res.get("latency_ms", 0)
        
        print(f"  * Latency         : {res.get('latency_ms', 0):.2f} ms")
        print(f"  * Confidence Tier : {res.get('confidence_tier')}")
        print(f"  * Chunks Retrieved: {len(res.get('retrieved_chunks', []))}")
        print(f"  * Degraded        : {res.get('generation_degraded')}")
        print(f"  * Answer Preview  : {res.get('answer', '')[:160]}...")
        print("-" * 80)
        
        results.append({
            "index": idx,
            "query": query,
            "latency_ms": res.get("latency_ms"),
            "confidence_tier": res.get("confidence_tier"),
            "retrieved_chunks_count": len(res.get("retrieved_chunks", [])),
            "generation_degraded": res.get("generation_degraded"),
            "answer": res.get("answer"),
            "citations": [
                {
                    "filename": chunk.get("metadata", {}).get("filename"),
                    "page_number": chunk.get("metadata", {}).get("page_number")
                }
                for chunk in res.get("retrieved_chunks", [])
            ]
        })
        
    # Save results to local JSON report
    report_path = backend_dir / "logs" / "benchmark_report.json"
    os.makedirs(report_path.parent, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=True)
        
    print("\n" + "=" * 80)
    print(f"Benchmark run completed. Saved results report to: {report_path}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    run_benchmarks()
