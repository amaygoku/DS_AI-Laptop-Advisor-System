# src/evaluation/__init__.py
"""
Evaluation module for Laptop Advisor System.
Provides metrics and relevance judging for recommendation quality.
"""

from src.evaluation.evaluator import (
    RelevanceJudge,
    RecommendationEvaluator,
    precision_at_k,
    dcg_at_k,
    ndcg_at_k,
)

__all__ = [
    "RelevanceJudge",
    "RecommendationEvaluator",
    "precision_at_k",
    "dcg_at_k",
    "ndcg_at_k",
]
