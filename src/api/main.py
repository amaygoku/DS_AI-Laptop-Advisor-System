# src/api/main.py
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.llm.schemas_v2 import IntentV2
from src.llm.gemini_client import GeminiClient
from src.llm.prompts import fallback_advice_no_llm
from src.advisor.recommend_service import build_query_from_intent, recommendations_to_json
from src.advisor.advisor import recommend_laptops
from fastapi.middleware.cors import CORSMiddleware




# ============================================================
# Bootstrap
# ============================================================

load_dotenv()

DATA_PATH = os.getenv("LAPTOPS_CSV", "data/laptops_features.csv")

app = FastAPI(title="Laptop Advisor API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hoặc cụ thể domain của frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Load dataset once
# ============================================================

try:
    df = pd.read_csv(DATA_PATH)
except FileNotFoundError as e:
    raise RuntimeError(
        f"Dataset not found: {DATA_PATH}. "
        f"Set LAPTOPS_CSV or place the CSV at the expected path."
    ) from e

# Optional: basic sanitation to avoid obvious outliers
# (keeps system stable if dataset has a few bad rows)
for col in ["Price (VND)", "RAM (GB)", "Storage (GB)", "Weight (kg)"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

if "RAM (GB)" in df.columns:
    df = df[df["RAM (GB)"].between(4, 64) | df["RAM (GB)"].isna()]  # filter absurd RAM like 80

if "Price (VND)" in df.columns:
    df = df[df["Price (VND)"].isna() | df["Price (VND)"].between(3_000_000, 300_000_000)]


# ============================================================
# Gemini client (allow running without GEMINI_API_KEY)
# ============================================================

try:
    gemini = GeminiClient(
        api_key=os.getenv("GEMINI_API_KEY"),
        model_intent=os.getenv("GEMINI_MODEL_INTENT", "gemini-2.0-flash"),
        model_advice=os.getenv("GEMINI_MODEL_ADVICE", "gemini-2.0-flash"),
    )
    USE_LLM = True
except Exception:
    gemini = None
    USE_LLM = False


# ============================================================
# API models
# ============================================================

class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    intent: Dict[str, Any]
    query: Dict[str, Any]
    recommendations: List[Dict[str, Any]]
    answer: str


# ============================================================
# Rule-based patches (robustness)
# ============================================================

_GAMING_KW = [
    "chơi game", "gaming", "fps", "valorant", "cs2", "counter strike", "pubg",
    "lol", "liên minh", "dota", "gta", "elden ring", "aaa", "game"
]

_CHEAP_KW = ["rẻ", "tiết kiệm", "giá tốt", "giá mềm", "ngon bổ rẻ"]
_LIGHT_KW = ["nhẹ", "mỏng nhẹ", "dễ mang", "di chuyển", "portable"]
_BATTERY_KW = ["pin", "pin trâu", "pin lâu", "dung lượng pin", "battery"]


def _extract_budget_vnd(text: str) -> Optional[int]:
    """
    Parse Vietnamese budget expressions.
    Examples:
    - "dưới 20 triệu", "tối đa 30tr", "<= 25 triệu", "20tr"
    Returns integer VND (e.g., 20000000) or None.
    """
    t = text.lower().strip()

    # Match "20 triệu" / "20tr" / "20 tr"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(triệu|tr)\b", t)
    if m:
        val = float(m.group(1).replace(",", "."))
        return int(val * 1_000_000)

    # Match raw VND like 20000000
    m2 = re.search(r"\b(\d{7,10})\b", t)
    if m2:
        v = int(m2.group(1))
        if 5_000_000 <= v <= 200_000_000:
            return v

    return None


def _extract_top_n(text: str) -> Optional[int]:
    """
    Detect explicit "top N" requests:
    - "top 5", "gợi ý 3 máy", "cho tôi 2 lựa chọn", "đề xuất 4 option"
    Return N (1..10) or None if user didn't mention.
    """
    t = text.lower()

    patterns = [
        r"\btop\s*(\d{1,2})\b",
        r"\bgợi\s*ý\s*(\d{1,2})\s*(máy|lựa\s*chọn|option)?\b",
        r"\bcho\s*tôi\s*(\d{1,2})\s*(máy|lựa\s*chọn|option)\b",
        r"\bđề\s*xuất\s*(\d{1,2})\s*(máy|lựa\s*chọn|option)?\b",
        r"\btôi\s*muốn\s*(\d{1,2})\s*(máy|lựa\s*chọn|option)?\b",
        r"\btôi\s*cần\s*(\d{1,2})\s*(máy|lựa\s*chọn|option)?\b",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 10:
                return n
    return None

STUDENT_PRICE_CAP_VND = 20_000_000


def _extract_cpu_gen(text: str) -> Optional[int]:
    """
    Detect CPU generation mention:
    - "đời 13", "thế hệ 12", "gen 11", "13th gen"
    """
    t = text.lower()
    patterns = [
        r"(?:đời|thế hệ|gen)\s*(\d{1,2})\b",
        r"(\d{1,2})(?:th|nd|rd|st)?\s*gen\b",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            return int(m.group(1))
    return None


    return None


def _extract_cpu_brand(text: str) -> Optional[str]:
    """
    Detect CPU brand/family:
    - "i5", "core i7", "ryzen 5", "r7"
    """
    t = text.lower()
    # Intel Core
    m = re.search(r"\b(i[3579])\b", t)
    if m:
        return m.group(1)
    
    # AMD Ryzen
    m2 = re.search(r"\b(ryzen|r)\s*([3579])\b", t)
    if m2:
        return f"ryzen {m2.group(2)}"
    
    return None


def _extract_cpu_manu(text: str) -> Optional[str]:
    """
    Detect CPU manufacturer:
    - "intel", "amd"
    """
    t = text.lower()
    if "intel" in t:
        return "Intel"
    if "amd" in t:
        return "AMD"
    return None


def patch_intent_from_text(user_text: str, intent: IntentV2) -> IntentV2:
    t = user_text.lower()

    # 1) Detect intents from text
    detected = detect_user_types_from_text(t)

    # 2) Merge with Gemini result (if any)
    gemini_types = []
    if intent.user_types:
        gemini_types = [u.lower() for u in intent.user_types]
    elif intent.user_type:
        gemini_types = [intent.user_type.lower()]

    merged = list(dict.fromkeys(gemini_types + detected))

    # 3) Decide single vs multi
    if len(merged) >= 2:
        intent.user_types = merged
        intent.user_type = None
    elif len(merged) == 1:
        intent.user_type = merged[0]
        intent.user_types = None
    else:
        # keep whatever it was; if empty -> general
        if not intent.user_type and not intent.user_types:
            intent.user_type = "general"
            intent.user_types = None

    # 4) Budget extraction from text (explicit budget always wins)
    budget = _extract_budget_vnd(user_text)
    if budget is not None:
        if any(k in t for k in ["dưới", "<=", "under", "tối đa", "max", "không quá"]):
            intent.price_max = budget
        else:
            if intent.price_max is None:
                intent.price_max = budget

    # 5) CPU Generation extraction
    cpu_gen = _extract_cpu_gen(user_text)
    if cpu_gen is not None:
        intent.min_cpu_gen = cpu_gen

    # 6) CPU Brand extraction
    cpu_brand = _extract_cpu_brand(user_text)
    if cpu_brand is not None:
        intent.cpu_brand = cpu_brand

    # 7) CPU Manufacturer extraction
    cpu_manu = _extract_cpu_manu(user_text)
    if cpu_manu is not None:
        intent.cpu_manufacturer = cpu_manu

    # 😎 Preferences from keywords
    if any(k in t for k in _CHEAP_KW):
        intent.pref_cheap = True
    if any(k in t for k in _LIGHT_KW):
        intent.pref_light = True
    if any(k in t for k in _BATTERY_KW):
        intent.pref_battery = True

    # 6) Student semantics (works for both single and multi)
    has_student = (
        (intent.user_type == "student")
        or (intent.user_types is not None and "student" in intent.user_types)
    )
    if has_student:
        # force cheap preference for student
        intent.pref_cheap = True

        # default cap only if user didn't give explicit budget
        if intent.price_max is None and intent.price_min is None and budget is None:
            intent.price_max = STUDENT_PRICE_CAP_VND

    # 7) top_n: only if explicitly mentioned
    n = _extract_top_n(user_text)
    if n is not None:
        intent.top_n = n  # explicit override

    return intent

INTENT_KW = {
    "gaming": ["chơi game", "gaming", "fps", "valorant", "cs2", "pubg", "lol", "liên minh", "dota", "game"],
    "ai": ["ai", "học máy", "machine learning", "deep learning", "cuda", "train model", "pytorch", "tensorflow", "đồ hoạ", "graphics", "nhân tạo"],
    "business": ["doanh nhân", "kinh doanh", "gặp khách", "thuyết trình", "bảo mật"],
    "office": ["văn phòng", "office", "word", "excel", "powerpoint", "kế toán", "hành chính"],
    "study": ["học tập", "đi học", "làm bài", "zoom", "meet", "teams", "học online", "lap trinh", "lập trình"],
    "student": ["học sinh", "hs", "sinh viên", "sv"],
}

def detect_user_types_from_text(t: str) -> list[str]:
    t = t.lower()
    found = []
    for ut, kws in INTENT_KW.items():
        if any(k in t for k in kws):
            found.append(ut)
    # de-duplicate but keep order
    return list(dict.fromkeys(found))




def sort_recommendations_for_intent(intent: Dict[str, Any], recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Keep as pass-through or implement generic top-level ranking.
    Since final_score now incorporates brand preference heavily, 
    we just trust the scorer's final_score.
    """
    return sorted(recs, key=lambda x: float(x.get("scores", {}).get("final_score") or 0), reverse=True)


# ============================================================
# Endpoints
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "rows": int(len(df)),
        "use_llm": USE_LLM,
        "data_path": DATA_PATH,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    user_text = req.text.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="text must not be empty")

    # 1) Extract intent
    if USE_LLM:
        intent_obj = gemini.extract_intent(user_text)  # safe default if LLM fails
    else:
        intent_obj = IntentV2(user_type="general")  # top_n defaults to 3

    # 2) Patch intent from raw text for robustness
    intent_obj = patch_intent_from_text(user_text, intent_obj)
    intent_dict = intent_obj.model_dump(exclude_none=True)

    # 3) Build query for the recommend engine (must preserve intent.user_type)
    query = build_query_from_intent(intent_obj)
    # Safety: never allow empty intent in query
    if "user_type" not in query and "user_types" not in query:
        query["user_type"] = "general"

    # 4) Recommend
    try:
        df_top = recommend_laptops(df, query, top_n=intent_obj.top_n)
        recs = recommendations_to_json(df_top, query)
        recs = sort_recommendations_for_intent(intent_dict, recs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation engine error: {e}")

    # 5) Generate advice text (natural; fallback if LLM fails)
    if USE_LLM:
        try:
            answer = gemini.generate_advice(
                user_text=user_text,
                intent=intent_dict,
                recommendations=recs,
            )
            if not answer or not answer.strip():
                answer = fallback_advice_no_llm(user_text, intent_dict, recs)
        except Exception:
            answer = fallback_advice_no_llm(user_text, intent_dict, recs)
    else:
        answer = fallback_advice_no_llm(user_text, intent_dict, recs)
    return {
        "intent": intent_dict,
        "query": query,
        "recommendations": recs,
        "answer": answer,
    }
