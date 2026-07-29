import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from app.rag.generation.generator import InsuranceAssistant

def main():
    assistant = InsuranceAssistant()
    
    # Check for dev mode flag
    dev_mode = False
    if "--dev" in sys.argv:
        dev_mode = True
        sys.argv.remove("--dev")
        
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        product_id = None
    else:
        query = input("Enter your policy question: ").strip()
        if not query:
            print("Query cannot be empty.")
            return
        product_filter = input("Enter optional product/filename filter (or press Enter to skip): ").strip()
        product_id = product_filter if product_filter else None
    
    print(f"\nProcessing query: '{query}' ...")
    result = assistant.generate_answer(query, product_id=product_id)
    
    if dev_mode:
        retrieved_policies = result.get("supporting_references", [])
        primary_policy = result.get("primary_policy")
        supporting_policies = [p for p in retrieved_policies if p != primary_policy]
        
        print("\n" + "=" * 60)
        print("DEVELOPER MODE METADATA")
        print("-" * 60)
        print(f"Intent                 : {result.get('intent', 'General')}")
        print(f"Primary Policy Selected: {primary_policy or 'None'}")
        print(f"Supporting References  : {', '.join(supporting_policies) if supporting_policies else 'None'}")
        print(f"Confidence Tier        : {result.get('confidence_tier', 'LOW')}")
        print(f"Latency                : {result.get('latency', 0.0):.3f}s")
        print("=" * 60)
        
    print("\n" + "=" * 60)
    print("ANSWER:")
    print("-" * 60)
    print(result["answer"])
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
