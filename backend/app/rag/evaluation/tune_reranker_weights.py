import os
import sys
import json
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Add project root to sys.path
backend_dir = Path(__file__).resolve().parents[3]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.rag.retrieval.retriever import HybridRetriever

class CandidateFeature:
    def __init__(self, doc, rrf: float, meta_sc: float, spec: float, cov: float, boost: float, penalty: float):
        self.doc = doc
        self.rrf = rrf
        self.meta_sc = meta_sc
        self.spec = spec
        self.cov = cov
        self.boost = boost
        self.penalty = penalty

def generate_weight_combinations(step: float = 0.05) -> List[Tuple[float, float, float, float]]:
    combinations = []
    steps = [round(i * step, 2) for i in range(int(1.0 / step) + 1)]
    for w_ret in steps:
        for w_met in steps:
            if w_ret + w_met > 1.01:
                continue
            for w_spec in steps:
                if w_ret + w_met + w_spec > 1.01:
                    continue
                w_cov = round(1.0 - (w_ret + w_met + w_spec), 2)
                if w_cov >= 0.0:
                    combinations.append((w_ret, w_met, w_spec, w_cov))
    return list(set(combinations))

def evaluate_weights_optimized(fused_data: List[Dict[str, Any]], weights: Tuple[float, float, float, float], k: int, retriever: HybridRetriever) -> float:
    w_ret, w_met, w_spec, w_cov = weights
    
    mrr_sum = 0.0
    for query_item in fused_data:
        expected_heading = query_item["expected_heading"]
        expected_keywords = query_item["expected_keywords"]
        negative_keywords = query_item.get("negative_keywords", [])
        features_list: List[CandidateFeature] = query_item["features"]
        
        # Fast score calculation and sorting
        scored_candidates = []
        for feat in features_list:
            raw_score = (
                w_ret * feat.rrf +
                w_met * feat.meta_sc +
                w_spec * feat.spec +
                w_cov * feat.cov
            )
            final_score = raw_score * feat.boost * feat.penalty
            scored_candidates.append((feat.doc, final_score))
            
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        top_k = scored_candidates[:k]
        
        hit_rank = -1
        for r_idx, (doc, score) in enumerate(top_k, 1):
            meta = doc.metadata or {}
            res_heading = str(meta.get("heading_path") or "").lower()
            res_text = retriever._contextualize_text(doc).lower()
            
            heading_matches = (expected_heading.lower() in res_heading) or (res_heading in expected_heading.lower())
            
            keyword_matches = sum(1 for kw in expected_keywords if kw.lower() in res_text)
            keyword_ratio = keyword_matches / len(expected_keywords) if expected_keywords else 0.0
            
            has_neg_match = False
            for nw in negative_keywords:
                if nw.lower() in res_text:
                    has_neg_match = True
                    break
            
            if (heading_matches or keyword_ratio >= 0.65) and not has_neg_match:
                hit_rank = r_idx
                break
                
        if hit_rank != -1:
            mrr_sum += 1.0 / hit_rank
            
    return mrr_sum / len(fused_data)

def main():
    print("=" * 90)
    print("                  RERANKER WEIGHTS OPTIMIZER (DATA-DRIVEN GRID SEARCH)")
    print("=" * 90)
    
    eval_file = Path(__file__).resolve().parent / "human_benchmark.json"
    if not eval_file.exists():
        print(f"Error: human_benchmark.json not found at {eval_file}")
        return
        
    with open(eval_file, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    print(f"Loaded {len(dataset)} human queries. Pre-fetching fused candidates & extracting features...")
    retriever = HybridRetriever()
    
    fused_data = []
    stopwords = {"policy", "policies", "insurance", "under", "about", "wording", "wordings", "what", "where", "when", "does"}
    intent_keywords = {"exclude", "exclusion", "not covered", "limits", "limitations", "waiting", "period", "claim", "reimbursement", "document"}

    for idx, item in enumerate(dataset, 1):
        query = item["query"]
        expected_heading = item["expected_heading"]
        expected_keywords = item["expected_keywords"]
        neg_keywords = item.get("negative_keywords", [])
        
        intent = retriever._classify_query_intent(query)
        sub_queries = retriever._expand_query(query, intent)
        
        # 1. Fuse RRF scores across sub-queries
        fused_scores = {}
        is_comparison = retriever._is_comparison_query(query)
        detected_policy = None if is_comparison else retriever._detect_policy_in_query(query)
        
        for q_idx, sq in enumerate(sub_queries):
            q_weight = 1.0 if q_idx == 0 else 0.5
            sq_vector = retriever._vector_search(sq)
            sq_lexical = retriever._lexical_search(sq)
            
            vector_ranks = retriever._rank_map(sq_vector)
            lexical_ranks = retriever._rank_map(sq_lexical)
            
            for key in set(vector_ranks) | set(lexical_ranks):
                doc = vector_ranks.get(key, lexical_ranks.get(key))[0]
                recip_score = 0.0
                if key in vector_ranks:
                    recip_score += 1.0 / (retriever.rrf_k + vector_ranks[key][1])
                if key in lexical_ranks:
                    recip_score += 1.0 / (retriever.rrf_k + lexical_ranks[key][1])
                    
                if detected_policy:
                    meta = doc.metadata or {}
                    retriever._validate_and_normalize_metadata(meta)
                    carrier = str(meta.get("carrier") or "").lower().strip()
                    prod = str(meta.get("product_name") or meta.get("product") or "").lower().strip()
                    det = detected_policy.lower().strip()
                    det_words = set(re.findall(r"\b\w{3,}\b", det)) - {"policy", "policies", "insurance"}
                    prod_words = set(re.findall(r"\b\w{3,}\b", prod)) - {"policy", "policies", "insurance"}
                    carrier_words = set(re.findall(r"\b\w{3,}\b", carrier)) - {"policy", "policies", "insurance"}
                    
                    if (det_words & prod_words) or (det_words & carrier_words):
                        recip_score *= retriever.soft_bias_multiplier
                        
                doc_entry = fused_scores.setdefault(key, [doc, 0.0, 0.0, 0.0])
                doc_entry[1] += q_weight * recip_score
                
        fused = [(entry[0], entry[1]) for entry in fused_scores.values()]
        
        # 2. Extract and cache features for each candidate doc
        q_norm = re.sub(r"[^\w\s]", "", query.lower())
        q_words = set(re.findall(r"\b\w{3,}\b", q_norm))
        q_entity_words = q_words - stopwords
        q_intent_keywords = {w for w in q_entity_words if w in intent_keywords}
        
        features_list = []
        for doc, rrf_score in fused:
            meta = doc.metadata or {}
            retriever._validate_and_normalize_metadata(meta)
            
            # Metadata Match Score
            sec_title = str(meta.get("section_title") or "").lower()
            clause_type = str(meta.get("clause_type") or "").lower()
            struct_path = str(meta.get("heading_path") or "").lower()
            carrier = str(meta.get("carrier") or "").lower()
            prod_name = str(meta.get("product_name") or "").lower()
            
            meta_str = " ".join([sec_title, clause_type, struct_path, carrier, prod_name])
            meta_match_count = sum(1 for w in q_entity_words if w in meta_str)
            meta_score = (meta_match_count / len(q_entity_words)) if q_entity_words else 0.0
            
            # Specificity Score
            richness = sum(1 for k in ["carrier", "product_name", "document_type", "section_title", "clause_type", "page_number"] if meta.get(k))
            richness_score = richness / 6.0
            has_sec_id = 1.0 if (meta.get("section_id") or any(char.isdigit() for char in sec_title)) else 0.0
            depth = len(struct_path.split("/"))
            depth_score = min(depth / 5.0, 1.0)
            sec_specificity = 0.5 * has_sec_id + 0.5 * depth_score
            
            content = (doc.page_content or "").strip()
            tokens = re.findall(r"\b\w{3,}\b", content.lower())
            density_score = (len(set(tokens) - stopwords) / len(tokens)) if tokens else 0.0
            heading_conf = float(meta.get("heading_confidence") or 0.8)
            specificity_score = 0.2 * richness_score + 0.2 * sec_specificity + 0.3 * density_score + 0.3 * heading_conf
            
            # Coverage Score with Concept Expansion
            expanded_q_words = set(q_entity_words)
            for w in q_entity_words:
                if w in retriever.CONCEPT_EXPANSIONS:
                    expanded_q_words.update(retriever.CONCEPT_EXPANSIONS[w])
            content_lower = content.lower()
            coverage_match_count = sum(1 for w in (expanded_q_words | q_intent_keywords) if w in content_lower)
            coverage_score = (coverage_match_count / len(expanded_q_words | q_intent_keywords)) if (expanded_q_words | q_intent_keywords) else 0.0
            
            # Intent boost
            chunk_sem_type = str(meta.get("semantic_type") or "").lower()
            intent_boost = 1.25 if (intent != "general" and chunk_sem_type == intent) else 1.0
            
            # Boilerplate penalty & priority weighting
            c_norm = re.sub(r"[_\-]+", " ", content_lower)
            h_lower = struct_path.lower()
            bp_terms = ["cin:", "u66000mh", "tollfree", "toll free", "customer care", "customer.care", "email:", "website:", "registered office", "corporate office", "regd office", "irdai reg", "lotus park", "wagle industrial"]
            bp_matches = sum(1 for term in bp_terms if term in c_norm) + 2 * sum(1 for term in bp_terms if term in h_lower)
            boilerplate_score = min(bp_matches / 4.0, 1.0)
            
            priority_score = float(meta.get("document_priority") or 100.0) / 100.0
            
            # Policy routing bias
            routing_multiplier = 1.0
            if detected_policy:
                carrier_val = str(meta.get("carrier") or "").lower().strip()
                prod_val = str(meta.get("product_name") or meta.get("product") or "").lower().strip()
                
                det = detected_policy.lower().strip()
                det_words = set(re.findall(r"\b\w{3,}\b", det)) - {"policy", "policies", "insurance", "under", "about", "wording", "wordings"}
                prod_words = set(re.findall(r"\b\w{3,}\b", prod_val)) - {"policy", "policies", "insurance", "under", "about", "wording", "wordings"}
                carrier_words = set(re.findall(r"\b\w{3,}\b", carrier_val)) - {"policy", "policies", "insurance", "under", "about", "wording", "wordings"}
                
                if (det_words & prod_words) or (det_words & carrier_words):
                    routing_multiplier = retriever.soft_bias_multiplier
                else:
                    # Check if query asks for another carrier specifically
                    q_lower = query.lower()
                    other_carrier_detected = False
                    for c in retriever.known_carriers:
                        c_words = set(re.findall(r"\b\w{3,}\b", c)) - {"policy", "policies", "insurance", "under", "about", "wording", "wordings"}
                        if c_words and not (c_words & carrier_words) and all(cw in q_lower for cw in c_words):
                            other_carrier_detected = True
                            break
                    if other_carrier_detected:
                        routing_multiplier = 0.1
                        
            penalty = (1.0 - boilerplate_score) * priority_score * routing_multiplier
            
            features_list.append(CandidateFeature(
                doc=doc,
                rrf=rrf_score,
                meta_sc=meta_score,
                spec=specificity_score,
                cov=coverage_score,
                boost=intent_boost,
                penalty=penalty
            ))
            
        fused_data.append({
            "query": query,
            "expected_heading": expected_heading,
            "expected_keywords": expected_keywords,
            "negative_keywords": neg_keywords,
            "features": features_list
        })
        
    print("Candidates cached. Generating weight combinations...")
    combinations = generate_weight_combinations(step=0.05)
    print(f"Generated {len(combinations)} weight configurations. Optimizing...")
    
    best_mrr = -1.0
    best_weights = None
    
    t_start = time.time()
    for w_combo in combinations:
        mrr = evaluate_weights_optimized(fused_data, w_combo, retriever.k, retriever)
        if mrr > best_mrr:
            best_mrr = mrr
            best_weights = w_combo
            
    t_elapsed = time.time() - t_start
    print(f"Optimization completed in {t_elapsed:.2f} seconds.")
    
    print("\n" + "=" * 90)
    print("                              OPTIMAL RERANKER CONFIGURATION")
    print("-" * 90)
    print(f"- RERANK_RETRIEVED_WEIGHT  (Vector/BM25 RRF) : {best_weights[0]:.2f}")
    print(f"- RERANK_META_WEIGHT       (Metadata Match)  : {best_weights[1]:.2f}")
    print(f"- RERANK_SPECIFICITY_WEIGHT(Section Depth)   : {best_weights[2]:.2f}")
    print(f"- RERANK_COVERAGE_WEIGHT   (Term Density)    : {best_weights[3]:.2f}")
    print(f"- Best Mean Reciprocal Rank (MRR)            : {best_mrr:.4f}")
    print("-" * 90)
    print("[FUTURE WORK] For large weight spaces (e.g. adding cross-encoder weights or tuning RRF parameters),")
    print("              Bayesian Optimization (using frameworks like Optuna) should be used instead of grid search.")
    print("=" * 90 + "\n")

if __name__ == "__main__":
    main()
