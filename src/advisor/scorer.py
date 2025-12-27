# src/advisor/scorer.py
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src.advisor.utils import normalize_user_types

# giữ nguyên INTENT_SCORE_MAP, AFFORDABILITY_WEIGHT, WEIGHT_PREF_WEIGHT như file của bạn


def _norm_brand(s: str) -> str:
    return (s or "").strip().lower()


def _parse_battery_wh(battery_text: Any) -> Optional[float]:
    if battery_text is None:
        return None
    txt = str(battery_text)
    m = re.search(r"(\d+(?:\.\d+)?)\s*Wh", txt, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def apply_scoring(df, query):
    df = df.copy()
    user_types = normalize_user_types(query)
    single_intent = "user_type" in query

    # =========================
    # TASK SCORE (existing)
    # =========================
    INTENT_SCORE_MAP = {
        "gaming": ["gaming_score"],
        "ai": ["ai_graphics_score"],
        "business": ["office_score"],
        "office": ["office_score"],
        "study": ["office_score", "portability_score"],
        "student": ["office_score", "portability_score"],
        "general": ["general_score"],
    }

    if single_intent:
        ut = user_types[0]
        cols = INTENT_SCORE_MAP.get(ut, ["general_score"])
        cols = [c for c in cols if c in df.columns]
        if not cols:
            cols = ["office_score"] if "office_score" in df.columns else df.columns[:1].tolist()
        df["task_score"] = df[cols].mean(axis=1)
    else:
        cols = []
        for ut in user_types:
            cols.extend(INTENT_SCORE_MAP.get(ut, []))
        cols = list(set(cols))
        cols = [c for c in cols if c in df.columns]
        if not cols:
            cols = ["office_score"] if "office_score" in df.columns else df.columns[:1].tolist()
        df["task_score"] = df[cols].min(axis=1)

    # =========================
    # PRICE / AFFORDABILITY (existing)
    # =========================
    if "price_max" in query:
        budget = query["price_max"]
        ratio = df["Price (VND)"] / budget
        ideal = 0.8 if single_intent and user_types[0] == "gaming" else 0.75
        df["price_fit"] = (1 - abs(ratio - ideal)).clip(0, 1)
        df["affordability_score"] = df["price_fit"]
    else:
        price = df["Price (VND)"]
        p10 = price.quantile(0.10)
        p90 = price.quantile(0.90)
        denom = (p90 - p10) if (p90 - p10) != 0 else 1.0
        price_norm = ((price - p10) / denom).clip(0, 1)
        df["affordability_score"] = (1 - price_norm).clip(0, 1)
        df["price_fit"] = 0.5

    # =========================
    # WEIGHT SCORE (existing)
    # =========================
    w = df["Weight (kg)"]
    w10 = w.quantile(0.10)
    w90 = w.quantile(0.90)
    denom_w = (w90 - w10) if (w90 - w10) != 0 else 1.0
    w_norm = ((w - w10) / denom_w).clip(0, 1)
    df["weight_score"] = (1 - w_norm).clip(0, 1)

    # =========================
    # FINAL SCORE (existing logic + advanced bonus)
    # =========================
    AFFORDABILITY_WEIGHT = {
        "student": 0.35,
        "study": 0.25,
        "business": 0.15,
        "office": 0.15,
        "general": 0.20,
        "ai": 0.10,
        "gaming": 0.05,
    }
    WEIGHT_PREF_WEIGHT = {
        "student": 0.20,
        "study": 0.25,
        "business": 0.15,
        "office": 0.15,
        "general": 0.15,
        "ai": 0.10,
        "gaming": 0.05,
    }

    if single_intent and user_types[0] == "gaming":
        df["final_score"] = df["task_score"]
    else:
        if single_intent:
            base_aff = AFFORDABILITY_WEIGHT.get(user_types[0], 0.20)
            base_wt = WEIGHT_PREF_WEIGHT.get(user_types[0], 0.15)
        else:
            base_aff = max(AFFORDABILITY_WEIGHT.get(ut, 0.20) for ut in user_types)
            base_wt = max(WEIGHT_PREF_WEIGHT.get(ut, 0.15) for ut in user_types)

        if query.get("pref_cheap") is True:
            base_aff = max(base_aff, 0.35)

        if query.get("pref_light") is True:
            base_wt = max(base_wt, 0.25)
        elif query.get("pref_light") is False:
            base_wt = min(base_wt, 0.05)

        w_aff = min(base_aff, 0.45)
        w_wt = min(base_wt, 0.35)
        w_task = max(0.0, 1.0 - w_aff - w_wt)

        df["final_score"] = (
            df["task_score"] * w_task
            + df["affordability_score"] * w_aff
            + df["weight_score"] * w_wt
        )

    # =========================
    # ADVANCED SOFT BONUSES
    # =========================
    bonus = 0.0

    # Brand prefer bonus
    brand_pref = query.get("brand_preferences") or {}
    prefer = set(_norm_brand(x) for x in (brand_pref.get("prefer") or []) if x)
    if prefer and "Manufacturer" in df.columns:
        df["_brand_prefer"] = df["Manufacturer"].fillna("").map(_norm_brand).isin(prefer).astype(float)
        bonus += 0.03 * df["_brand_prefer"]

    # Battery bonus if requested
    batt = query.get("battery_requirements")
    if isinstance(batt, dict) and batt.get("min_wh") is not None and "Battery" in df.columns:
        min_wh = float(batt["min_wh"])
        df["_battery_wh"] = df["Battery"].apply(_parse_battery_wh)
        # if above requirement, small boost; if missing, 0
        df["_battery_ok"] = (df["_battery_wh"].fillna(0) >= min_wh).astype(float)
        bonus += 0.02 * df["_battery_ok"]

    # Display bonus if requested
    disp = query.get("display_requirements")
    if isinstance(disp, dict) and disp.get("min_refresh_hz") is not None and "Refresh Rate (Hz)" in df.columns:
        min_hz = float(disp["min_refresh_hz"])
        df["_hz_ok"] = (df["Refresh Rate (Hz)"].fillna(0) >= min_hz).astype(float)
        bonus += 0.02 * df["_hz_ok"]

    # Apply bonus
    df["final_score"] = (df["final_score"] + bonus).clip(0, 1).round(4)

    return df
