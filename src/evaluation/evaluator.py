# src/evaluation/evaluator.py
"""
Evaluation module for assessing recommendation quality.
Uses Gemini LLM as a relevance judge and provides standard IR metrics.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types


# =============================================================================
# METRICS
# =============================================================================

def precision_at_k(relevances: List[int], k: int) -> float:
    """
    Precision@K: fraction of relevant items in top-K results.
    Relevance > 0 is considered relevant.
    """
    if k <= 0:
        return 0.0
    return sum(1 for r in relevances[:k] if r > 0) / k


def dcg_at_k(relevances: List[int], k: int) -> float:
    """
    Discounted Cumulative Gain at K.
    Uses log2(i+2) as discount factor (position 0 -> log2(2) = 1).
    """
    dcg = 0.0
    for i, rel in enumerate(relevances[:k]):
        dcg += (2 ** rel - 1) / math.log2(i + 2)
    return dcg


def ndcg_at_k(relevances: List[int], k: int) -> float:
    """
    Normalized DCG at K.
    Divides DCG by the ideal DCG (if items were perfectly ranked).
    """
    dcg = dcg_at_k(relevances, k)
    ideal = sorted(relevances, reverse=True)
    idcg = dcg_at_k(ideal, k)
    return dcg / idcg if idcg > 0 else 0.0


def mrr(relevances_list: List[List[int]]) -> float:
    """
    Mean Reciprocal Rank across multiple queries.
    For each query, finds the rank of the first relevant item.
    """
    rr_sum = 0.0
    for relevances in relevances_list:
        for i, rel in enumerate(relevances):
            if rel > 0:
                rr_sum += 1.0 / (i + 1)
                break
    return rr_sum / len(relevances_list) if relevances_list else 0.0


# =============================================================================
# RELEVANCE JUDGE (using Gemini)
# =============================================================================

class RelevanceJudge:
    """
    Uses Gemini LLM to judge relevance of a laptop recommendation
    given a user query. Returns scores 0, 1, or 2.
    """

    RELEVANCE_PROMPT = """You are an expert laptop reviewer and advisor.

User query:
"{query}"

Laptop specification:
- Name: {name}
- Brand: {brand}
- Price: {price_vnd:,} VND
- RAM: {ram_gb} GB
- Storage: {storage_gb} GB
- Weight: {weight_kg} kg
- Screen: {screen_inch} inch
- Refresh rate: {refresh_hz} Hz
- Gaming ready: {is_gaming_ready}
- AI ready: {is_ai_ready}
- Ultrabook: {is_ultrabook}
- Business ready: {is_business_ready}

Evaluation rubric:
Score 2 (Fully Relevant): The laptop perfectly matches the user's requirements and use case
Score 1 (Partially Relevant): The laptop matches some requirements but not all, or is a reasonable alternative
Score 0 (Not Relevant): The laptop does not match the user's requirements at all

Return JSON only:
{{
  "relevance_score": 0 | 1 | 2,
  "short_reason": "Brief explanation in Vietnamese"
}}"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-3-pro-preview",
        sleep_between_calls: float = 1.5
    ):
        api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Missing GEMINI_API_KEY or GOOGLE_API_KEY")

        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.sleep_between_calls = sleep_between_calls

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response."""
        text = (text or "").strip()
        if not text:
            raise ValueError("Empty response")

        # Try direct parse
        try:
            return json.loads(text)
        except Exception:
            pass

        # Find JSON block
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            raise ValueError(f"No JSON found in: {text[:200]}")
        return json.loads(m.group(0))

    def judge(self, query: str, laptop: Dict[str, Any]) -> Dict[str, Any]:
        """
        Judge relevance of a laptop for a given query.
        Returns dict with 'relevance_score' (0-2) and 'short_reason'.
        """
        # Extract laptop fields with safe defaults
        flags = laptop.get("flags", {})
        scores = laptop.get("scores", {})

        prompt = self.RELEVANCE_PROMPT.format(
            query=query,
            name=laptop.get("name", "Unknown"),
            brand=laptop.get("brand", "Unknown"),
            price_vnd=laptop.get("price_vnd", 0) or 0,
            ram_gb=laptop.get("ram_gb", "N/A"),
            storage_gb=laptop.get("storage_gb", "N/A"),
            weight_kg=laptop.get("weight_kg", "N/A"),
            screen_inch=laptop.get("screen_inch", "N/A"),
            refresh_hz=laptop.get("refresh_hz", "N/A"),
            is_gaming_ready=flags.get("is_gaming_ready", False),
            is_ai_ready=flags.get("is_ai_ready", False),
            is_ultrabook=flags.get("is_ultrabook", False),
            is_business_ready=flags.get("is_business_ready", False),
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            result = self._extract_json(getattr(response, "text", "") or "")
            return {
                "relevance_score": int(result.get("relevance_score", 0)),
                "short_reason": result.get("short_reason", ""),
            }
        except Exception as e:
            print(f"⚠️ Gemini parse error: {e}")
            return {"relevance_score": 0, "short_reason": f"Error: {e}"}

    def judge_batch(
        self,
        query: str,
        laptops: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Judge multiple laptops for a query, with rate limiting.
        """
        results = []
        for i, laptop in enumerate(laptops):
            result = self.judge(query, laptop)
            result["laptop_name"] = laptop.get("name", f"Laptop #{i}")
            results.append(result)

            if i < len(laptops) - 1:
                time.sleep(self.sleep_between_calls)

        return results


# =============================================================================
# CONSTRAINT SATISFACTION
# =============================================================================

def check_constraint_satisfaction(
    laptop: Dict[str, Any],
    constraints: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Check if a laptop satisfies given constraints.
    Returns dict with 'satisfied' (bool) and 'details' (dict of constraint checks).
    """
    details = {}
    all_satisfied = True

    flags = laptop.get("flags", {})
    price = laptop.get("price_vnd", 0) or 0

    # Price constraints
    if "price_min" in constraints:
        ok = price >= constraints["price_min"]
        details["price_min"] = {"required": constraints["price_min"], "actual": price, "ok": ok}
        all_satisfied = all_satisfied and ok

    if "price_max" in constraints:
        ok = price <= constraints["price_max"]
        details["price_max"] = {"required": constraints["price_max"], "actual": price, "ok": ok}
        all_satisfied = all_satisfied and ok

    # Flag constraints
    for flag_name in ["is_gaming_ready", "is_ai_ready", "is_ultrabook", "is_business_ready", "is_light"]:
        if flag_name in constraints:
            actual = flags.get(flag_name, False)
            ok = actual == constraints[flag_name]
            details[flag_name] = {"required": constraints[flag_name], "actual": actual, "ok": ok}
            all_satisfied = all_satisfied and ok

    # Weight constraint
    if "max_weight_kg" in constraints:
        weight = laptop.get("weight_kg")
        if weight is not None:
            ok = weight <= constraints["max_weight_kg"]
            details["max_weight_kg"] = {"required": constraints["max_weight_kg"], "actual": weight, "ok": ok}
            all_satisfied = all_satisfied and ok

    # RAM constraint
    if "min_ram_gb" in constraints:
        ram = laptop.get("ram_gb")
        if ram is not None:
            ok = ram >= constraints["min_ram_gb"]
            details["min_ram_gb"] = {"required": constraints["min_ram_gb"], "actual": ram, "ok": ok}
            all_satisfied = all_satisfied and ok

    return {"satisfied": all_satisfied, "details": details}


def constraint_satisfaction_rate(
    recommendations: List[Dict[str, Any]],
    constraints: Dict[str, Any]
) -> float:
    """
    Calculate Constraint Satisfaction Rate (CSR).
    Fraction of recommendations that satisfy all constraints.
    """
    if not recommendations:
        return 0.0

    satisfied = sum(
        1 for r in recommendations
        if check_constraint_satisfaction(r, constraints)["satisfied"]
    )
    return satisfied / len(recommendations)


# =============================================================================
# MAIN EVALUATOR CLASS
# =============================================================================

class RecommendationEvaluator:
    """
    Main evaluator class that combines all evaluation metrics.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
        top_k: int = 3,
        sleep_between_calls: float = 1.5
    ):
        self.judge = RelevanceJudge(
            api_key=api_key,
            model=model,
            sleep_between_calls=sleep_between_calls
        )
        self.top_k = top_k

    def evaluate_single_query(
        self,
        query: str,
        recommendations: List[Dict[str, Any]],
        expected_constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate recommendations for a single query.

        Args:
            query: User query text
            recommendations: List of recommended laptops
            expected_constraints: Optional dict of constraints to check CSR

        Returns:
            Dict with metrics and detailed judgments
        """
        # Judge relevance for top-K
        top_k_recs = recommendations[:self.top_k]
        judgments = self.judge.judge_batch(query, top_k_recs)

        # Extract relevance scores
        relevances = [j["relevance_score"] for j in judgments]

        # Calculate metrics
        result = {
            "query": query,
            "num_recommendations": len(recommendations),
            "top_k": self.top_k,
            "precision_at_k": precision_at_k(relevances, self.top_k),
            "ndcg_at_k": ndcg_at_k(relevances, self.top_k),
            "relevances": relevances,
            "judgments": judgments,
        }

        # CSR if constraints provided
        if expected_constraints:
            result["csr"] = constraint_satisfaction_rate(top_k_recs, expected_constraints)
            result["constraint_details"] = [
                check_constraint_satisfaction(r, expected_constraints)
                for r in top_k_recs
            ]

        return result

    def evaluate_batch(
        self,
        test_cases: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Evaluate multiple test cases and compute aggregate metrics.

        Args:
            test_cases: List of dicts with 'query', 'recommendations',
                       and optional 'expected_constraints'

        Returns:
            Dict with per-query results and aggregate metrics
        """
        results = []
        all_relevances = []

        for i, case in enumerate(test_cases):
            print(f"📊 Evaluating query {i+1}/{len(test_cases)}: {case['query'][:50]}...")

            result = self.evaluate_single_query(
                query=case["query"],
                recommendations=case["recommendations"],
                expected_constraints=case.get("expected_constraints")
            )
            results.append(result)
            all_relevances.append(result["relevances"])

        # Aggregate metrics
        avg_precision = sum(r["precision_at_k"] for r in results) / len(results) if results else 0
        avg_ndcg = sum(r["ndcg_at_k"] for r in results) / len(results) if results else 0

        csr_values = [r["csr"] for r in results if "csr" in r]
        avg_csr = sum(csr_values) / len(csr_values) if csr_values else None

        return {
            "num_queries": len(test_cases),
            "top_k": self.top_k,
            "aggregate": {
                "avg_precision_at_k": avg_precision,
                "avg_ndcg_at_k": avg_ndcg,
                "avg_csr": avg_csr,
                "mrr": mrr(all_relevances),
            },
            "per_query_results": results,
        }
