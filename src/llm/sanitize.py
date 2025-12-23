from __future__ import annotations

import json
import re
from typing import Any, Dict
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _clean_json_string(s: str) -> str:
    """Clean malformed JSON from LLM output."""
    # Remove markdown fences
    s = re.sub(r"^```(?:json)?\\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\\s*```$", "", s)
    
    # Remove control characters that break JSON (except valid whitespace)
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
    
    # Fix common issues: unescaped quotes inside strings by finding patterns
    # This is a simplified fix - replace literal newlines inside strings with space
    # Find the JSON object first
    match = _JSON_OBJECT_RE.search(s)
    if match:
        s = match.group(0)
    
    return s


def extract_json_object(text: str) -> Dict[str, Any]:
    """
    Extract the first JSON object from model output.
    Handles markdown fences, control characters, and extra text.
    Falls back to general intent if parsing fails completely.
    """
    s = (text or "").strip()

    # Clean the string first
    s = _clean_json_string(s)
    
    if not s:
        return {"user_type": "general"}

    # Try direct parse first
    try:
        if s.startswith("{") and s.endswith("}"):
            return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Try to extract just the valid part - find first { to last }
    try:
        first_brace = s.find("{")
        last_brace = s.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidate = s[first_brace:last_brace + 1]
            # Try parsing
            return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Last resort: try to extract key fields manually using regex
    user_type_match = re.search(r'"user_type"\s*:\s*"(\w+)"', s)
    user_types_match = re.search(r'"user_types"\s*:\s*\[(.*?)\]', s)
    
    if user_types_match:
        types_str = user_types_match.group(1)
        types = re.findall(r'"(\w+)"', types_str)
        if len(types) >= 2:
            return {"user_types": types}
    
    if user_type_match:
        return {"user_type": user_type_match.group(1)}
    
    # Final fallback
    return {"user_type": "general"}


ALLOWED_INTENTS = {"gaming", "study", "student", "business", "ai", "general"}

def normalize_intent_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforce strict semantics with pragmatic auto-fix:
    - Drop unknown keys
    - Normalize casing
    - Fix common LLM mistakes:
        * user_type = "gaming | study"  -> user_types=["gaming","study"]
        * user_types=["gaming"]         -> user_type="gaming"
    - Enforce SINGLE vs MULTI rules
    """
    allowed_keys = {"user_type", "user_types", "notes"}
    data: Dict[str, Any] = {k: v for k, v in raw.items() if k in allowed_keys}

    ut = data.get("user_type")
    uts = data.get("user_types")

    # -------------------------------------------------
    # 1) Handle user_type as combined enum string
    #    e.g. "gaming | study", "gaming,study"
    # -------------------------------------------------
    if isinstance(ut, str):
        parts = [p.strip().lower() for p in re.split(r"[|/,]", ut)]
        parts = [p for p in parts if p in ALLOWED_INTENTS]

        if len(parts) >= 2:
            data.pop("user_type", None)
            data["user_types"] = parts
            ut = None
            uts = parts
        elif len(parts) == 1:
            data["user_type"] = parts[0]
            ut = parts[0]
        else:
            data.pop("user_type", None)
            ut = None

    # -------------------------------------------------
    # 2) Normalize user_types list
    # -------------------------------------------------
    if isinstance(uts, list):
        cleaned = []
        seen = set()
        for x in uts:
            if isinstance(x, str):
                x = x.lower()
                if x in ALLOWED_INTENTS and x not in seen:
                    seen.add(x)
                    cleaned.append(x)

        if len(cleaned) >= 2:
            data["user_types"] = cleaned
            data.pop("user_type", None)
            return data

        if len(cleaned) == 1:
            data["user_type"] = cleaned[0]
            data.pop("user_types", None)
            return data

        # empty list -> drop
        data.pop("user_types", None)

    # -------------------------------------------------
    # 3) Normalize single user_type
    # -------------------------------------------------
    ut = data.get("user_type")
    if isinstance(ut, str):
        ut = ut.lower()
        if ut in ALLOWED_INTENTS:
            data["user_type"] = ut
        else:
            data.pop("user_type", None)

    # -------------------------------------------------
    # 4) Final safety: ensure at least general
    # -------------------------------------------------
    if "user_type" not in data and "user_types" not in data:
        data["user_type"] = "general"

    return data

RE_GREETING = re.compile(
    r"^(chào bạn|xin chào|hello|hi|mình là|tôi là).{0,100}\n+",
    re.IGNORECASE
)

def sanitize_writer_output(text: str) -> str:
    text = text.strip()
    text = RE_GREETING.sub("", text)
    return text.strip()
