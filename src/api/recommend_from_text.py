from __future__ import annotations
from src.intent.prefs import extract_prefs
from src.intent.evidence import enforce_intent_evidence
import math
import re
from src.llm.ollama_writer import call_ollama_writer
from src.intent.constraints import extract_constraints
from src.llm.sanitize import sanitize_writer_output
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.advisor.writer import write_advice_text
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.advisor.advisor import recommend_laptops
from src.llm.intent_schema import LLMIntent
from src.llm.ollama_client import call_ollama_json_only
from src.llm.sanitize import extract_json_object, normalize_intent_payload

router = APIRouter(tags=["recommendation"])
WRITER_PROMPT = Path("src/llm/writer_prompt.txt").read_text(encoding="utf-8")


# ---------- Conversation detection ----------
GREETING_PATTERNS = [
    r"^(xin\s+)?chào",
    r"^hi+\b",
    r"^hello",
    r"^hey",
    r"^alo+",
    r"^(bạn\s+)?khoẻ\s+không",
    r"^cảm\s+ơn",
    r"^thanks?",
    r"^thank\s+you",
    r"^tạm\s+biệt",
    r"^bye",
    r"^good\s*(morning|afternoon|evening|night)",
    r"^(bạn\s+)?là\s+ai",
    r"^tên\s+(bạn|của\s+bạn)",
]

CONVERSATION_RESPONSES = {
    "greeting": "Xin chào! 👋 Mình là Laptop Advisor, trợ lý tư vấn laptop của bạn. Bạn cần tìm laptop cho mục đích gì ạ?",
    "thanks": "Không có gì ạ! Nếu bạn cần tư vấn thêm về laptop, cứ hỏi mình nhé! 😊",
    "bye": "Tạm biệt bạn! Chúc bạn tìm được laptop ưng ý. Hẹn gặp lại! 👋",
    "who_are_you": "Mình là Laptop Advisor - trợ lý AI giúp bạn tìm laptop phù hợp nhất với nhu cầu và ngân sách của bạn. Hãy mô tả nhu cầu của bạn (ví dụ: học IT, chơi game, làm việc văn phòng, giá rẻ...) để mình tư vấn nhé!",
    "acknowledgment": "Vâng, mình hiểu rồi! 😊 Bạn cần tư vấn laptop gì thêm không ạ? Hãy mô tả nhu cầu của bạn nhé!",
}


def detect_conversation(text: str) -> Optional[str]:
    """Detect if text is casual conversation. Returns response key or None."""
    text_lower = text.lower().strip()

    # Check greeting patterns
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, text_lower):
            if any(w in text_lower for w in ["cảm ơn", "thanks", "thank"]):
                return "thanks"
            if any(w in text_lower for w in ["tạm biệt", "bye"]):
                return "bye"
            if any(w in text_lower for w in ["là ai", "tên"]):
                return "who_are_you"
            return "greeting"

    # Very short messages without laptop-related keywords
    if len(text_lower.split()) <= 4:
        laptop_keywords = ["laptop", "máy tính", "máy", "gaming", "game", "học", "làm việc", "văn phòng", "it", "lập trình", "code", "giá", "triệu", "ram", "ssd", "tư vấn", "gợi ý", "tìm", "mua", "cần"]
        if not any(kw in text_lower for kw in laptop_keywords):
            # Short acknowledgment messages
            if any(w in text_lower for w in ["ừ", "ok", "oké", "oke", "được", "vâng", "uh", "uhm", "à", "ờ", "rồi", "hiểu", "biết rồi"]):
                return "acknowledgment"
    return None


# ---------- LLM prompt ----------
PROMPT = Path("src/llm/intent_only_prompt.txt").read_text(encoding="utf-8")

# ---------- CSV loading (cached) ----------
CSV_PATH = "src/data/laptops_features.csv"

REQUIRED_COLUMNS = [
    "Price (VND)",
    "RAM (GB)",
    "Storage (GB)",
    "Weight (kg)",
    "is_gaming_ready",
    "office_score",
    "portability_score",
    "gaming_score",
    "ai_graphics_score",
]

_df_cache: Optional[pd.DataFrame] = None


def _nan_to_none(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def load_laptops_cached() -> pd.DataFrame:
    global _df_cache
    if _df_cache is not None:
        return _df_cache

    df = pd.read_csv(CSV_PATH)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(f"Missing required columns in CSV: {missing}")

    # numeric normalization
    numeric_cols = [
        "Price (VND)",
        "RAM (GB)",
        "Storage (GB)",
        "Weight (kg)",
        "office_score",
        "portability_score",
        "gaming_score",
        "ai_graphics_score",
        "base_performance_score",
        "base_portability_score",
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["is_gaming_ready"] = df["is_gaming_ready"].astype(bool)

    # ensure general_score exists for "general" intent
    if "general_score" not in df.columns:
        if "base_performance_score" in df.columns and "base_portability_score" in df.columns:
            df["general_score"] = (df["base_performance_score"] + df["base_portability_score"]) / 2
        else:
            df["general_score"] = df[
                ["office_score", "portability_score", "gaming_score", "ai_graphics_score"]
            ].mean(axis=1)

    df["general_score"] = pd.to_numeric(df["general_score"], errors="coerce")

    _df_cache = df
    return _df_cache


# ---------- API schema ----------
class ConversationMessage(BaseModel):
    role: str
    content: str

class RecommendFromTextRequest(BaseModel):
    user_text: str = Field(..., min_length=1)
    top_n: int = Field(default=5, ge=1, le=50)

    # Optional hard constraints (user nhập số -> dùng luôn; LLM không đụng)
    price_max: Optional[int] = Field(default=None, ge=0)
    min_ram_gb: Optional[int] = Field(default=None, ge=0)
    min_storage_gb: Optional[int] = Field(default=None, ge=0)
    max_weight_kg: Optional[float] = Field(default=None, ge=0)

    # Conversation history for context (last 2-3 messages)
    conversation_history: Optional[List[ConversationMessage]] = Field(default=None)


@router.post("/recommend_from_text")
async def recommend_from_text(req: RecommendFromTextRequest):
    # 0) Check for casual conversation (greetings, thanks, etc.)
    conv_type = detect_conversation(req.user_text)
    if conv_type and conv_type in CONVERSATION_RESPONSES:
        return {
            "intent": None,
            "query_used": None,
            "total_after_filter": 0,
            "results": [],
            "advice_text": CONVERSATION_RESPONSES[conv_type],
        }

    # 1) Call Ollama to get INTENT ONLY
    try:
        llm_text = await call_ollama_json_only(PROMPT, req.user_text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama call failed: {e}")

    # 2) Extract JSON + normalize (remove ``` fences, fix user_types len1, etc.) + validate schema
    try:
        raw0 = extract_json_object(llm_text)
        raw1 = normalize_intent_payload(raw0)
        intent = LLMIntent.model_validate(raw1).model_dump(exclude_none=True)
        intent = enforce_intent_evidence(req.user_text, intent)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Invalid/unsatisfiable LLM intent JSON: {e}",
                "raw_llm_text": llm_text,
            },
        )

    # 3) Build recommender query from intent + explicit constraints (explicit overrides everything)
    query: Dict[str, Any] = dict(intent)
    auto_constraints = extract_constraints(req.user_text)
    query.update(auto_constraints)

    # add prefs extracted from natural text (cheap/light/heavy...)
    prefs = extract_prefs(req.user_text)
    query.update(prefs)

    if req.price_max is not None:
        query["price_max"] = req.price_max
    if req.min_ram_gb is not None:
        query["min_ram_gb"] = req.min_ram_gb
    if req.min_storage_gb is not None:
        query["min_storage_gb"] = req.min_storage_gb
    if req.max_weight_kg is not None:
        query["max_weight_kg"] = req.max_weight_kg

    # (Optional) keep original text for explain/debug
    query.setdefault("notes", req.user_text.strip())

    # 4) Load CSV
    try:
        df = load_laptops_cached()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dataset load error: {e}")

    # 5) Recommend from CSV
    try:
        out = recommend_laptops(df, query, top_n=req.top_n)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation error: {e}")

    # 6) Shape response
    results: List[Dict[str, Any]] = []
    for _, row in out.iterrows():
        results.append(
            {
                "product_name": _nan_to_none(row.get("Product Name")),
                "manufacturer": _nan_to_none(row.get("Manufacturer")),
                "price_vnd": _nan_to_none(int(row["Price (VND)"]) if pd.notna(row.get("Price (VND)")) else None),
                "weight_kg": _nan_to_none(row.get("Weight (kg)")),
                "ram_gb": _nan_to_none(int(row["RAM (GB)"]) if pd.notna(row.get("RAM (GB)")) else None),
                "storage_gb": _nan_to_none(int(row["Storage (GB)"]) if pd.notna(row.get("Storage (GB)")) else None),
                "general_score": _nan_to_none(row.get("general_score")),
                "office_score": _nan_to_none(row.get("office_score")),
                "portability_score": _nan_to_none(row.get("portability_score")),
                "gaming_score": _nan_to_none(row.get("gaming_score")),
                "ai_graphics_score": _nan_to_none(row.get("ai_graphics_score")),
                "base_performance_score": _nan_to_none(row.get("base_performance_score")),
                "base_portability_score": _nan_to_none(row.get("base_portability_score")),
                "is_gaming_ready": _nan_to_none(row.get("is_gaming_ready")),
            }
        )
    writer_input = {
        "query_used": query,
        "results": results[: req.top_n],
        "conversation_history": [{"role": m.role, "content": m.content} for m in (req.conversation_history or [])],
    }
    try:
        advice_text = await call_ollama_writer(WRITER_PROMPT, writer_input)
        advice_text = sanitize_writer_output(advice_text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama writer failed: {e}")

    return {
        "intent": intent,          # intent LLM xác định
        "query_used": query,       # query thực tế đưa vào recommender
        "total_after_filter": len(out),
        "results": results,
        "advice_text": advice_text,
    }
