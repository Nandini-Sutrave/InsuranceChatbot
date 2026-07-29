from dotenv import load_dotenv
load_dotenv()

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)

# Add project root to sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.rag.generation.generator import InsuranceAssistant

def run_e2e_tests():
    print("=" * 80)
    print("         INSURANCE RAG END-TO-END PIPELINE TEST (V3 ARCHITECTURE)")
    print("=" * 80)
    
    # Initialize assistant
    assistant = InsuranceAssistant()
    
    # Query 1: SBI Saral Suraksha Bima coverage
    query_1 = "benefits HDFC-Life-Aajeevan-Growth-Nivesh-and-Income-Policy"
    print(f"\n[QUERY 1] '{query_1}'")
    print("-" * 80)
    result_1 = assistant.generate_answer(query_1)
    print(f"Latency: {result_1['latency_ms']:.2f} ms")
    print(f"Confidence Tier: {result_1['confidence_tier']}")
    print(f"Retrieved Chunks: {len(result_1['retrieved_chunks'])}")
    print(f"Generated Answer:\n{result_1['answer'].encode('ascii', 'ignore').decode('ascii')}")
    print("-" * 80)
    
    # Query 2: Out of domain fallback
    query_2 = "What is the capital of Mars?"
    print(f"\n[QUERY 2] '{query_2}'")
    print("-" * 80)
    result_2 = assistant.generate_answer(query_2)
    print(f"Latency: {result_2['latency_ms']:.2f} ms")
    print(f"Confidence Tier: {result_2['confidence_tier']}")
    print(f"Retrieved Chunks: {len(result_2['retrieved_chunks'])}")
    print(f"Generated Answer:\n{result_2['answer'].encode('ascii', 'ignore').decode('ascii')}")
    print("-" * 80)

if __name__ == "__main__":
    run_e2e_tests()
