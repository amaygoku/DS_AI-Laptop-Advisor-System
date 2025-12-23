from __future__ import annotations
import re
from typing import Any, Dict, Optional

# ---------- helpers ----------
def _parse_float(s: str) -> float:
    return float(s.replace(",", "."))

def _money_to_vnd(val: float, unit: str) -> int:
    unit = unit.lower()
    if unit in ["triệu", "tr", "củ", "m"]:
        return int(val * 1_000_000)
    if unit in ["tỷ", "ty"]:
        return int(val * 1_000_000_000)
    return int(val)

def _storage_to_gb(n: int, unit: str) -> int:
    return n * 1024 if unit.lower() == "tb" else n

# ---------- PRICE patterns ----------
RE_PRICE_MAX = re.compile(r"(dưới|<=|≤|<|không quá|tối đa|max)\s*(\d+(?:[.,]\d+)?)\s*(triệu|tr|củ|m|tỷ|ty)\b", re.I)
RE_PRICE_MIN = re.compile(r"(trên|>=|≥|>|từ)\s*(\d+(?:[.,]\d+)?)\s*(triệu|tr|củ|m|tỷ|ty)\b", re.I)

# ---------- RAM ----------
RE_RAM = re.compile(r"(?:ram|bộ nhớ)\s*(?:tối thiểu|min|>=|≥|trên|>|\b)\s*(\d+)\s*(gb|g)\b|\b(\d+)\s*(gb|g)\s*(ram|bộ nhớ)\b", re.I)

# ---------- STORAGE ----------
RE_STORAGE = re.compile(
    r"(?:ssd|hdd|ổ cứng|storage|ổ)\s*(?:tối thiểu|min|>=|≥|trên|>)?\s*(\d+)\s*(gb|tb)\b"
    r"|\b(\d+)\s*(gb|tb)\s*(?:ssd|hdd|ổ cứng|storage|ổ)\b",
    re.I,
)

# ---------- WEIGHT ----------
RE_WEIGHT_MAX = re.compile(r"(dưới|<=|≤|<|không quá|tối đa|max)\s*(\d+(?:[.,]\d+)?)\s*kg\b", re.I)
RE_WEIGHT_MIN = re.compile(r"(trên|>=|≥|>|từ)\s*(\d+(?:[.,]\d+)?)\s*kg\b", re.I)

# ---------- qualitative weight words ----------
RE_LIGHT = re.compile(r"\bnhẹ\b|mỏng nhẹ|gọn nhẹ|mang đi|di chuyển|mang theo", re.I)
RE_HEAVY = re.compile(r"\bnặng\b|cồng kềnh|to\b|đầm\b", re.I)
RE_HEAVY_OK = re.compile(r"nặng cũng được|không cần nhẹ|nặng không sao", re.I)

def extract_constraints(user_text: str) -> Dict[str, Any]:
    t = (user_text or "").strip()
    q: Dict[str, Any] = {}

    # price max/min
    m = RE_PRICE_MAX.search(t)
    if m:
        q["price_max"] = _money_to_vnd(_parse_float(m.group(2)), m.group(3))

    m = RE_PRICE_MIN.search(t)
    if m:
        q["price_min"] = _money_to_vnd(_parse_float(m.group(2)), m.group(3))

    # ram
    m = RE_RAM.search(t)
    if m:
        n = m.group(1) or m.group(3)
        if n:
            q["min_ram_gb"] = int(n)

    # storage
    m = RE_STORAGE.search(t)
    if m:
        if m.group(1) and m.group(2):
            q["min_storage_gb"] = _storage_to_gb(int(m.group(1)), m.group(2))
        elif m.group(3) and m.group(4):
            q["min_storage_gb"] = _storage_to_gb(int(m.group(3)), m.group(4))

    # weight numeric max/min
    m = RE_WEIGHT_MAX.search(t)
    if m:
        q["max_weight_kg"] = _parse_float(m.group(2))

    m = RE_WEIGHT_MIN.search(t)
    if m:
        q["min_weight_kg"] = _parse_float(m.group(2))

    # qualitative: only set if no numeric already and user didn't say heavy_ok
    heavy_ok = bool(RE_HEAVY_OK.search(t))

    if "max_weight_kg" not in q and RE_LIGHT.search(t) and not heavy_ok:
        q["max_weight_kg"] = 2.0

    # If user explicitly wants "nặng" and provided no numeric:
    # You can either do nothing (safer) OR set a soft pref. Hard min_weight_kg guessing is risky.
    if RE_HEAVY.search(t) and "min_weight_kg" not in q:
        q["pref_heavy"] = True  # soft, scorer can use this

    return q
