import os
import sys
import json
import re
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[3]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

def clean_heading(h: str) -> str:
    # Get last part of heading path
    parts = [p.strip() for p in h.split(">") if p.strip()]
    if not parts:
        return "the policy"
    return parts[-1]

def extract_keywords(text: str, heading: str) -> list:
    keywords = set()
    h_words = [w.lower() for w in re.findall(r"\b\w{4,}\b", heading)]
    for hw in h_words:
        if hw not in {"policy", "wording", "general", "insurance", "limited", "company", "clause", "section", "number"}:
            keywords.add(hw)
            
    # Add numbers, durations, money
    numbers = re.findall(r"\b\d+(?:\.\d+)?\s*%?", text)
    for num in numbers:
        keywords.add(num)
        
    durations = re.findall(r"\b\d+\s*(?:day|days|month|months|year|years|week|weeks|hour|hours)\b", text, re.IGNORECASE)
    for dur in durations:
        keywords.add(dur.lower())
        
    money = re.findall(r"(?:₹|rs\.?|inr)\s*\d+[\d,]*", text, re.IGNORECASE)
    for mon in money:
        keywords.add(mon.lower())
        
    return sorted(list(keywords))

def main():
    inspector_path = Path("E:/InsuranceBot/backend/data/vector_store/chroma_hybrid/ingested_chunks_inspector.json")
    if not inspector_path.exists():
        print(f"Error: Ingested chunks inspector not found at {inspector_path}")
        return

    with open(inspector_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    boilerplate_keywords = [
        "corporate office", "registered office", "regd office", "tollfree", "cin:", "irdai", 
        "lotus park", "wagle industrial", "mumbai", "floor", "road", "tel:", "phone", "email",
        "ombudsman", "grievance", "customer care", "bima bharosa", "stage 1", "stage 2", 
        "stage 3", "stage 4", "available 24/7", "servicing", "things to", "description", 
        "no. title", "terms and", "insurance company limited", "customer.care",
        "ombudsmen", "annexure i", "annexure-i", "list of", "tel.", "toll free", "sonepat",
        "telangana", "lakshadweep", "c.r. avenue", "vasofix safety", "optional", "cumulative"
    ]
    
    clean_chunks = []
    for c in chunks:
        h_lower = c["heading_path"].lower()
        c_lower = c["text"].lower()
        
        # Skip if too short or has boilerplate keywords
        if len(c_lower) < 60:
            continue
        if any(kw in h_lower for kw in boilerplate_keywords) or any(kw in c_lower for kw in ["corporate & registered office", "u66000mh", "tollfree", "customer.care@"]):
            continue
            
        clean_chunks.append(c)

    print(f"Total clean chunks: {len(clean_chunks)}")
    
    # Generate queries
    eval_data = []
    used_queries = set()
    
    for c in clean_chunks:
        heading = c["heading_path"]
        last_heading = clean_heading(heading)
        sem_type = c.get("semantic_type", "general")
        text = c["text"]
        
        query = ""
        if sem_type == "exclusion":
            query = f"What are the exclusions under {last_heading}?"
        elif sem_type == "benefit" or sem_type == "coverage":
            query = f"Explain the coverage and benefits for {last_heading}."
        elif sem_type == "waiting_period":
            query = f"What is the waiting period for {last_heading}?"
        elif sem_type == "eligibility":
            query = f"What is the eligibility criteria for {last_heading}?"
        elif sem_type == "claim_process":
            query = f"How to file a claim or process claims for {last_heading}?"
        elif "definition" in heading.lower() or "definitions" in heading.lower():
            query = f"Define the term {last_heading} under definitions."
        else:
            query = f"What is the policy details for {last_heading}?"
            
        # De-duplicate queries
        if query in used_queries:
            continue
            
        keywords = extract_keywords(text, last_heading)
        if not keywords:
            continue
            
        eval_data.append({
            "query": query,
            "expected_heading": heading,
            "expected_keywords": keywords
        })
        used_queries.add(query)
        
        # Stop once we have 100 queries
        if len(eval_data) >= 100:
            break

    # If we couldn't get 100, relax constraints
    if len(eval_data) < 100:
        print(f"Warning: Only generated {len(eval_data)} queries, relaxing filters...")
        # (Fall back to any remaining clean chunks)
        for c in clean_chunks:
            heading = c["heading_path"]
            last_heading = clean_heading(heading)
            query = f"Details about {last_heading}"
            if query in used_queries:
                continue
            keywords = extract_keywords(c["text"], last_heading)
            eval_data.append({
                "query": query,
                "expected_heading": heading,
                "expected_keywords": keywords
            })
            used_queries.add(query)
            if len(eval_data) >= 100:
                break

    # Save to evaluation.json
    output_dir = Path(__file__).resolve().parent
    output_path = output_dir / "evaluation.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(eval_data[:100], f, indent=2)

    print(f"Generated evaluation dataset with {len(eval_data[:100])} queries at {output_path}")

if __name__ == "__main__":
    main()
