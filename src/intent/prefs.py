from __future__ import annotations

import re
from typing import Any, Dict, Optional


# =========================
# SOFT PREFS (non-numeric)
# =========================
RE_CHEAP = re.compile(r"giá rẻ|rẻ thôi|tiết kiệm|giá mềm|ngon bổ rẻ|bình dân", re.IGNORECASE)

RE_LIGHT = re.compile(r"\bnhẹ\b|gọn nhẹ|mang đi|di chuyển|mang theo|mỏng nhẹ|dễ mang", re.IGNORECASE)
RE_HEAVY_OK = re.compile(r"nặng cũng được|không cần nhẹ|nặng không sao|cồng kềnh cũng được", re.IGNORECASE)
RE_HEAVY = re.compile(r"\bnặng\b|cồng kềnh|to\b|đầm\b", re.IGNORECASE)

RE_NOT_TOO_HEAVY = re.compile(r"đừng nặng|không quá nặng|nhẹ vừa thôi", re.IGNORECASE)
RE_BATTERY = re.compile(r"pin trâu|pin tốt|pin ổn|dùng lâu|pin lâu", re.IGNORECASE)


# =========================
# NUMERIC CONSTRAINTS
# =========================
# Money: max/min + unit triệu/tr/củ/m, tỷ/ty
RE_PRICE_MAX = re.compile(
    r"(?:dưới|<=|≤|<|không quá|tối đa|max)\s*(\d+(?:[.,]\d+)?)\s*(triệu|tr|củ|m|tỷ|ty)\b",
    re.IGNORECASE,
)
RE_PRICE_MIN = re.compile(
    r"(?:trên|>=|≥|>|từ)\s*(\d+(?:[.,]\d+)?)\s*(triệu|tr|củ|m|tỷ|ty)\b",
    re.IGNORECASE,
)
RE_PRICE_RANGE = re.compile(
    r"(?:từ|khoảng)?\s*(\d+(?:[.,]\d+)?)\s*[-–~]\s*(\d+(?:[.,]\d+)?)\s*(triệu|tr|củ|m|tỷ|ty)\b",
    re.IGNORECASE,
)

# RAM: exact vs min markers
RE_RAM = re.compile(
    r"\bram\s*(?:là)?\s*(\d+)\s*(gb|g)\b|\b(\d+)\s*(gb|g)\s*ram\b",
    re.IGNORECASE,
)
RE_RAM_MIN_MARKERS = re.compile(r"tối thiểu|ít nhất|>=|≥|trở lên|min", re.IGNORECASE)

# Storage: capture number + unit
RE_STORAGE = re.compile(
    r"(?:ssd|hdd|ổ cứng|storage|ổ)\s*(?:tối thiểu|ít nhất|min|>=|≥|trên|>)?\s*(\d+)\s*(gb|tb)\b"
    r"|\b(\d+)\s*(gb|tb)\s*(?:ssd|hdd|ổ cứng|storage|ổ)\b",
    re.IGNORECASE,
)

# Weight numeric max/min
RE_WEIGHT_MAX = re.compile(
    r"(?:dưới|<=|≤|<|không quá|tối đa|max|nhẹ hơn)\s*(\d+(?:[.,]\d+)?)\s*kg\b",
    re.IGNORECASE,
)
RE_WEIGHT_MIN = re.compile(
    r"(?:trên|>=|≥|>|từ|nặng hơn)\s*(\d+(?:[.,]\d+)?)\s*kg\b",
    re.IGNORECASE,
)


def _parse_float(s: str) -> float:
    return float(s.replace(",", "."))


def _money_to_vnd(val: float, unit: str) -> int:
    u = unit.lower()
    if u in ["triệu", "tr", "củ", "m"]:
        return int(val * 1_000_000)
    if u in ["tỷ", "ty"]:
        return int(val * 1_000_000_000)
    return int(val)


def _storage_to_gb(n: int, unit: str) -> int:
    return n * 1024 if unit.lower() == "tb" else n


def extract_prefs(user_text: str) -> Dict[str, Any]:
    """
    Extract BOTH:
    - soft prefs: pref_cheap, pref_light, pref_heavy
    - numeric constraints: price_min/price_max, ram_exact_gb/min_ram_gb, min_storage_gb, max/min_weight_kg

    Important semantics:
    - "ram 16gb" => ram_exact_gb = 16 (default exact)
    - "ram tối thiểu 16gb" / ">=16gb" => min_ram_gb = 16
    - "nhẹ" => max_weight_kg = 2.0 (heuristic) unless user said heavy_ok or numeric given
    - "nặng" => pref_heavy=True (soft), DO NOT guess min_weight_kg unless numeric present
    """
    t = (user_text or "").strip()
    out: Dict[str, Any] = {}

    # -------------------------
    # Soft prefs
    # -------------------------
    if RE_CHEAP.search(t):
        out["pref_cheap"] = True

    heavy_ok = bool(RE_HEAVY_OK.search(t))
    light_hint = bool(RE_LIGHT.search(t) or RE_NOT_TOO_HEAVY.search(t))

    if RE_HEAVY.search(t) and not light_hint:
        out["pref_heavy"] = True

    # pref_light semantics
    if heavy_ok and not light_hint:
        out["pref_light"] = False
    elif light_hint and not heavy_ok:
        out["pref_light"] = True
    elif heavy_ok and light_hint:
        # conflict: prefer "heavy_ok" for soft preference
        out["pref_light"] = False

    # -------------------------
    # Numeric constraints: PRICE
    # -------------------------
    m_range = RE_PRICE_RANGE.search(t)
    if m_range:
        # use range upper bound as price_max
        hi = _parse_float(m_range.group(2))
        unit = m_range.group(3)
        out["price_max"] = _money_to_vnd(hi, unit)
    else:
        m_max = RE_PRICE_MAX.search(t)
        if m_max:
            out["price_max"] = _money_to_vnd(_parse_float(m_max.group(1)), m_max.group(2))

    m_min = RE_PRICE_MIN.search(t)
    if m_min:
        out["price_min"] = _money_to_vnd(_parse_float(m_min.group(1)), m_min.group(2))

    # -------------------------
    # Numeric constraints: RAM (exact vs min)
    # -------------------------
    m_ram = RE_RAM.search(t)
    if m_ram:
        n = m_ram.group(1) or m_ram.group(3)
        if n:
            ram_val = int(n)
            if RE_RAM_MIN_MARKERS.search(t):
                out["min_ram_gb"] = ram_val
            else:
                out["ram_exact_gb"] = ram_val

    # -------------------------
    # Numeric constraints: STORAGE
    # -------------------------
    m_st = RE_STORAGE.search(t)
    if m_st:
        if m_st.group(1) and m_st.group(2):
            out["min_storage_gb"] = _storage_to_gb(int(m_st.group(1)), m_st.group(2))
        elif m_st.group(3) and m_st.group(4):
            out["min_storage_gb"] = _storage_to_gb(int(m_st.group(3)), m_st.group(4))

    # -------------------------
    # Numeric constraints: WEIGHT
    # -------------------------
    m_wmax = RE_WEIGHT_MAX.search(t)
    if m_wmax:
        out["max_weight_kg"] = _parse_float(m_wmax.group(1))

    m_wmin = RE_WEIGHT_MIN.search(t)
    if m_wmin:
        out["min_weight_kg"] = _parse_float(m_wmin.group(1))

    # Heuristic weight only if:
    # - no numeric weight constraint
    # - user hints portability
    # - user did NOT say heavy_ok
    if "max_weight_kg" not in out and "min_weight_kg" not in out:
        if light_hint and not heavy_ok:
            out["max_weight_kg"] = 2.0
        elif RE_BATTERY.search(t) and not heavy_ok:
            out["max_weight_kg"] = 2.2

    return out
