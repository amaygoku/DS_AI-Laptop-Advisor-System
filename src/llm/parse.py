from __future__ import annotations

import json
from typing import Any, Dict

from src.llm.intent_schema import LLMIntent

ALLOWED_KEYS = {
    "user_type",
    "user_types",
    "price_max",
    "min_ram_gb",
    "min_storage_gb",
    "max_weight_kg",
    "notes",
}

def _drop_unknown_keys(obj: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in obj.items() if k in ALLOWED_KEYS}

def parse_llm_json_strict(llm_text: str) -> Dict[str, Any]:
    """
    Strictly parse LLM output:
    - must be raw JSON object (no markdown fences, no extra text)
    - must pass schema validation and rules
    Returns: dict query suitable for advisor.filters/scorer.
    """
    s = llm_text.strip()

    if s.startswith("```") or s.endswith("```"):
        raise ValueError("LLM output must be raw JSON only (no markdown fences).")

    try:
        raw = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from LLM: {e}") from e

    if not isinstance(raw, dict):
        raise ValueError("LLM output must be a JSON object.")

    raw = _drop_unknown_keys(raw)

    q = LLMQuery.model_validate(raw)
    return q.model_dump(exclude_none=True)
