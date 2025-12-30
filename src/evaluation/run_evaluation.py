#!/usr/bin/env python3
# src/evaluation/run_evaluation.py
"""
CLI script to run evaluation on the Laptop Advisor System.

Usage:
    # Evaluate from test queries file
    python -m src.evaluation.run_evaluation --file data/test_queries.json

    # Evaluate a single query (requires running API)
    python -m src.evaluation.run_evaluation --query "Tôi cần laptop gaming giá 25 triệu"

    # Evaluate with custom top_k
    python -m src.evaluation.run_evaluation --file data/test_queries.json --top-k 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

from src.evaluation.evaluator import RecommendationEvaluator


# Load environment variables
load_dotenv()


def call_chat_api(
    query: str,
    api_url: str = "http://localhost:8000/chat"
) -> Dict[str, Any]:
    """
    Call the /chat API endpoint to get recommendations.
    """
    response = requests.post(
        api_url,
        json={"text": query},
        headers={"Content-Type": "application/json"},
        timeout=60
    )
    response.raise_for_status()
    return response.json()


def load_test_queries(file_path: str) -> List[Dict[str, Any]]:
    """
    Load test queries from JSON file.

    Expected format:
    [
        {
            "query": "Tôi cần laptop gaming giá 25 triệu",
            "expected_constraints": {
                "is_gaming_ready": true,
                "price_min": 23000000,
                "price_max": 27000000
            }
        },
        ...
    ]
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_from_file(
    file_path: str,
    evaluator: RecommendationEvaluator,
    api_url: str = "http://localhost:8000/chat"
) -> Dict[str, Any]:
    """
    Run evaluation on all queries from a test file.
    """
    test_queries = load_test_queries(file_path)
    test_cases = []

    print(f"📋 Loaded {len(test_queries)} test queries from {file_path}")
    print("🔄 Fetching recommendations from API...\n")

    for i, tq in enumerate(test_queries):
        query = tq["query"]
        print(f"  [{i+1}/{len(test_queries)}] {query[:60]}...")

        try:
            api_response = call_chat_api(query, api_url)
            recommendations = api_response.get("recommendations", [])

            test_cases.append({
                "query": query,
                "recommendations": recommendations,
                "expected_constraints": tq.get("expected_constraints"),
                "api_intent": api_response.get("intent"),
            })
        except Exception as e:
            print(f"    ⚠️ API error: {e}")
            test_cases.append({
                "query": query,
                "recommendations": [],
                "expected_constraints": tq.get("expected_constraints"),
                "error": str(e),
            })

    print("\n" + "=" * 60)
    print("🧠 Running Gemini relevance evaluation...")
    print("=" * 60 + "\n")

    results = evaluator.evaluate_batch(test_cases)
    return results


def evaluate_single_query(
    query: str,
    evaluator: RecommendationEvaluator,
    api_url: str = "http://localhost:8000/chat"
) -> Dict[str, Any]:
    """
    Evaluate a single query.
    """
    print(f"📝 Query: {query}\n")
    print("🔄 Fetching recommendations from API...")

    api_response = call_chat_api(query, api_url)
    recommendations = api_response.get("recommendations", [])

    print(f"✓ Got {len(recommendations)} recommendations\n")

    print("🧠 Running Gemini relevance evaluation...\n")

    result = evaluator.evaluate_single_query(
        query=query,
        recommendations=recommendations
    )

    return result


def print_single_result(result: Dict[str, Any]):
    """Pretty print single query evaluation result."""
    print("\n" + "=" * 60)
    print("📊 EVALUATION RESULT")
    print("=" * 60)

    print(f"\n📝 Query: {result['query']}")
    print(f"📦 Recommendations evaluated: {result['top_k']}")

    print(f"\n📈 Metrics:")
    print(f"   • Precision@{result['top_k']}: {result['precision_at_k']:.2%}")
    print(f"   • NDCG@{result['top_k']}: {result['ndcg_at_k']:.4f}")

    if "csr" in result:
        print(f"   • CSR: {result['csr']:.2%}")

    print(f"\n🔍 Relevance Scores: {result['relevances']}")

    print("\n📋 Detailed Judgments:")
    for j in result["judgments"]:
        emoji = "✅" if j["relevance_score"] == 2 else ("🟡" if j["relevance_score"] == 1 else "❌")
        print(f"   {emoji} [{j['relevance_score']}] {j['laptop_name']}")
        print(f"      └─ {j['short_reason']}")


def print_batch_result(result: Dict[str, Any]):
    """Pretty print batch evaluation result."""
    print("\n" + "=" * 60)
    print("📊 AGGREGATE EVALUATION RESULTS")
    print("=" * 60)

    agg = result["aggregate"]
    print(f"\n📈 Tested {result['num_queries']} queries (Top-{result['top_k']})")
    print(f"\n📉 Aggregate Metrics:")
    print(f"   • Avg Precision@K: {agg['avg_precision_at_k']:.2%}")
    print(f"   • Avg NDCG@K: {agg['avg_ndcg_at_k']:.4f}")
    print(f"   • MRR: {agg['mrr']:.4f}")

    if agg["avg_csr"] is not None:
        print(f"   • Avg CSR: {agg['avg_csr']:.2%}")

    print("\n" + "-" * 60)
    print("📋 Per-Query Results:")
    print("-" * 60)

    for i, r in enumerate(result["per_query_results"]):
        status = "✅" if r["precision_at_k"] >= 0.66 else ("🟡" if r["precision_at_k"] > 0 else "❌")
        print(f"\n{i+1}. {status} {r['query'][:50]}...")
        print(f"   P@K: {r['precision_at_k']:.2%} | NDCG@K: {r['ndcg_at_k']:.4f} | Relevances: {r['relevances']}")


def save_metrics_summary(result: Dict[str, Any], output_path: str):
    """
    Save metrics summary to a separate file.
    Includes timestamp and aggregate metrics only.
    """
    from datetime import datetime
    
    if "aggregate" in result:
        # Batch evaluation
        agg = result["aggregate"]
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "num_queries": result["num_queries"],
            "top_k": result["top_k"],
            "metrics": {
                "precision_at_k": agg["avg_precision_at_k"],
                "ndcg_at_k": agg["avg_ndcg_at_k"],
                "mrr": agg["mrr"],
                "csr": agg["avg_csr"],
            }
        }
    else:
        # Single query evaluation
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "query": result["query"],
            "top_k": result["top_k"],
            "metrics": {
                "precision_at_k": result["precision_at_k"],
                "ndcg_at_k": result["ndcg_at_k"],
                "csr": result.get("csr"),
            },
            "relevances": result["relevances"],
        }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    
    return metrics


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Laptop Advisor System recommendations"
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Path to JSON file containing test queries"
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        help="Single query to evaluate"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000/chat",
        help="API endpoint URL (default: http://localhost:8000/chat)"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of top recommendations to evaluate (default: 3)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output file for full JSON results"
    )
    parser.add_argument(
        "--metrics-output", "-m",
        type=str,
        help="Output file for metrics summary (compact version with scores only)"
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.5,
        help="Sleep duration between Gemini calls (default: 1.5s)"
    )

    args = parser.parse_args()

    if not args.file and not args.query:
        parser.error("Either --file or --query must be provided")

    # Initialize evaluator
    evaluator = RecommendationEvaluator(
        top_k=args.top_k,
        sleep_between_calls=args.sleep
    )

    try:
        if args.file:
            result = evaluate_from_file(args.file, evaluator, args.api_url)
            print_batch_result(result)
        else:
            result = evaluate_single_query(args.query, evaluator, args.api_url)
            print_single_result(result)

        # Save full results if requested
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Full results saved to {args.output}")

        # Save metrics summary if requested
        if args.metrics_output:
            metrics = save_metrics_summary(result, args.metrics_output)
            print(f"📊 Metrics saved to {args.metrics_output}")

    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to API. Make sure the server is running:")
        print("   uvicorn src.api.main:app --port 8000")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"❌ Error: File not found: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

