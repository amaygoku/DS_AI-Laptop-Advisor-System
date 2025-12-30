# src/advisor/scorer.py
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src.advisor.utils import normalize_user_types

# ============================================================================
# ADJUSTED FOR NEW SCORE DATA (2024-12-30)
# ============================================================================
# Changes made to work with recalculated scores in laptops_features2.csv:
# - Reduced bonus multipliers to prevent score inflation
# - Fine-tuned weight dictionaries for better balance
# - Adjusted penalty thresholds for more appropriate filtering
# ============================================================================


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
    # TASK SCORE
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
        # Ensure we use columns present in df
        cols = [c for c in cols if c in df.columns]
        if not cols:
            cols = ["general_score"] if "general_score" in df.columns else ["office_score"]
            cols = [c for c in cols if c in df.columns]
        
        if cols:
            df["task_score"] = df[cols].mean(axis=1)
        else:
            df["task_score"] = 0.5 # fallback
    else:
        cols = []
        for ut in user_types:
            cols.extend(INTENT_SCORE_MAP.get(ut, []))
        cols = list(set(cols))
        cols = [c for c in cols if c in df.columns]
        if not cols:
            cols = ["general_score"] if "general_score" in df.columns else ["office_score"]
            cols = [c for c in cols if c in df.columns]
            
        if cols:
            df["task_score"] = df[cols].min(axis=1)
        else:
            df["task_score"] = 0.5

    # =========================
    # PRICE / AFFORDABILITY
    # =========================
    if "price_max" in query:
        budget = query["price_max"]
        ratio = df["Price (VND)"] / budget
        # Gaming users often willing to pay closer to max budget for performance
        ideal = 0.85 if single_intent and user_types[0] == "gaming" else 0.75
        df["price_fit"] = (1 - abs(ratio - ideal)).clip(0, 1)
        df["affordability_score"] = df["price_fit"]
    else:
        # If no budget, use norm_price if available, otherwise calculate
        if "norm_price" in df.columns:
            df["affordability_score"] = (1 - df["norm_price"]).clip(0, 1)
        else:
            price = df["Price (VND)"]
            p10 = price.quantile(0.10)
            p90 = price.quantile(0.90)
            denom = (p90 - p10) if (p90 - p10) != 0 else 1.0
            price_norm = ((price - p10) / denom).clip(0, 1)
            df["affordability_score"] = (1 - price_norm).clip(0, 1)
        df["price_fit"] = 0.5
        
        # Extra penalty for "cheap" preference when no budget set
        # In Vietnam, "cheap" usually means < 20-22M
        if query.get("pref_cheap") is True:
            # Drop score for anything above 22M
            penalty_mask = df["Price (VND)"] > 22_000_000
            df.loc[penalty_mask, "affordability_score"] *= 0.5
            # Even harsher for > 30M
            heavy_penalty_mask = df["Price (VND)"] > 30_000_000
            df.loc[heavy_penalty_mask, "affordability_score"] *= 0.2

    # =========================
    # WEIGHT SCORE
    # =========================
    if "norm_weight" in df.columns:
        df["weight_score"] = (1 - df["norm_weight"]).clip(0, 1)
    else:
        w = df["Weight (kg)"]
        w10 = w.quantile(0.10)
        w90 = w.quantile(0.90)
        denom_w = (w90 - w10) if (w90 - w10) != 0 else 1.0
        w_norm = ((w - w10) / denom_w).clip(0, 1)
        df["weight_score"] = (1 - w_norm).clip(0, 1)

    # =========================
    # FINAL SCORE CALCULATION
    # =========================
    # ADJUSTED: Fine-tuned weights for better balance with new score data
    AFFORDABILITY_WEIGHT = {
        "student": 0.30,   # Reduced from 0.35 for better task score influence
        "study": 0.22,     # Reduced from 0.25
        "business": 0.15,  # Unchanged
        "office": 0.15,    # Unchanged
        "general": 0.18,   # Reduced from 0.20
        "ai": 0.10,        # Unchanged
        "gaming": 0.05,    # Unchanged
    }
    WEIGHT_PREF_WEIGHT = {
        "student": 0.18,   # Reduced from 0.20
        "study": 0.22,     # Reduced from 0.25
        "business": 0.15,  # Unchanged
        "office": 0.15,    # Unchanged
        "general": 0.12,   # Reduced from 0.15
        "ai": 0.08,        # Reduced from 0.10
        "gaming": 0.05,    # Unchanged
    }

    if single_intent and user_types[0] == "gaming":
        # Gaming: pure task score (performance is everything)
        df["final_score"] = df["task_score"]
    else:
        if single_intent:
            base_aff = AFFORDABILITY_WEIGHT.get(user_types[0], 0.18)
            base_wt = WEIGHT_PREF_WEIGHT.get(user_types[0], 0.12)
        else:
            base_aff = max(AFFORDABILITY_WEIGHT.get(ut, 0.18) for ut in user_types)
            base_wt = max(WEIGHT_PREF_WEIGHT.get(ut, 0.12) for ut in user_types)

        if query.get("pref_cheap") is True:
            base_aff = max(base_aff, 0.30)  # Reduced from 0.35

        if query.get("pref_light") is True:
            base_wt = max(base_wt, 0.22)  # Reduced from 0.25
        elif query.get("pref_light") is False:
            base_wt = min(base_wt, 0.05)

        w_aff = min(base_aff, 0.40)  # Reduced cap from 0.45
        w_wt = min(base_wt, 0.30)    # Reduced cap from 0.35
        w_task = max(0.0, 1.0 - w_aff - w_wt)

        df["final_score"] = (
            df["task_score"] * w_task
            + df["affordability_score"] * w_aff
            + df["weight_score"] * w_wt
        )

    # =========================
    # SOFT BONUSES
    # =========================
    # ADJUSTED: Reduced bonus multipliers to prevent score inflation
    bonus = 0.0

    # Brand preference bonus
    brand_pref = query.get("brand_preferences") or {}
    prefer = set(_norm_brand(x) for x in (brand_pref.get("prefer") or []) if x)
    if prefer and "Manufacturer" in df.columns:
        df["_brand_prefer"] = df["Manufacturer"].fillna("").map(_norm_brand).isin(prefer).astype(float)
        # ADJUSTED: Reduced from 0.4 to 0.25 to prevent over-prioritization
        bonus += 0.25 * df["_brand_prefer"]

    # Battery requirement bonus
    batt_req = query.get("battery_requirements")
    if isinstance(batt_req, dict) and batt_req.get("min_wh") is not None:
        min_wh = float(batt_req["min_wh"])
        if "Battery (Wh)" in df.columns:
            df["_battery_wh"] = df["Battery (Wh)"]
        else:
            df["_battery_wh"] = df["Battery"].apply(_parse_battery_wh)
        
        # If above requirement, small boost
        df["_battery_ok"] = (df["_battery_wh"].fillna(0) >= min_wh).astype(float)
        # ADJUSTED: Reduced from 0.03 to 0.02
        bonus += 0.02 * df["_battery_ok"]
    
    # General battery score bonus
    if "battery_score" in df.columns:
        # ADJUSTED: Reduced from 0.02 to 0.015
        bonus += 0.015 * df["battery_score"].fillna(0)

    # Display refresh rate bonus
    disp = query.get("display_requirements")
    if isinstance(disp, dict) and disp.get("min_refresh_hz") is not None and "Refresh Rate (Hz)" in df.columns:
        min_hz = float(disp["min_refresh_hz"])
        df["_hz_ok"] = (df["Refresh Rate (Hz)"].fillna(0) >= min_hz).astype(float)
        # ADJUSTED: Reduced from 0.02 to 0.015
        bonus += 0.015 * df["_hz_ok"]

    # Ready flags bonuses
    if "is_gaming_ready" in df.columns and any(ut == "gaming" for ut in user_types):
         # ADJUSTED: Reduced from 0.02 to 0.015
         bonus += 0.015 * df["is_gaming_ready"].astype(float)
    if "is_ai_ready" in df.columns and any(ut == "ai" for ut in user_types):
         # ADJUSTED: Reduced from 0.05 to 0.04
         bonus += 0.04 * df["is_ai_ready"].astype(float)
    if "is_ultrabook" in df.columns and any(ut in ["business", "office", "student"] for ut in user_types):
         # ADJUSTED: Reduced from 0.03 to 0.02
         bonus += 0.02 * df["is_ultrabook"].astype(float)

    # =========================
    # ABSOLUTE PENALTIES
    # =========================
    # ADJUSTED: More gradual weight penalties for better differentiation
    if query.get("pref_light") is True:
        # Gradual penalties for increasing weight
        penalty_1_7 = df["Weight (kg)"] > 1.7  # New: earlier threshold
        df.loc[penalty_1_7, "final_score"] *= 0.85  # Mild penalty
        
        penalty_2_0 = df["Weight (kg)"] > 2.0  # Adjusted from 1.8
        df.loc[penalty_2_0, "final_score"] *= 0.65  # Adjusted from 0.7
        
        penalty_2_3 = df["Weight (kg)"] > 2.3  # Adjusted from 2.2
        df.loc[penalty_2_3, "final_score"] *= 0.35  # Adjusted from 0.4
        
        penalty_2_6 = df["Weight (kg)"] > 2.6  # Adjusted from 2.5
        df.loc[penalty_2_6, "final_score"] *= 0.08  # Adjusted from 0.1

    # =========================
    # BATTERY PRIORITY
    # =========================
    if query.get("pref_battery") is True:
        # Give a substantial boost if battery_score is good
        if "battery_score" in df.columns:
            # ADJUSTED: Reduced from 0.1 to 0.08
            bonus += 0.08 * df["battery_score"].fillna(0)
        # Penalize if battery is unknown or small (< 45Wh)
        if "_battery_wh" in df.columns:
            penalty_mask = df["_battery_wh"].fillna(0) < 45
            # ADJUSTED: Slightly harsher penalty (0.8 -> 0.75)
            df.loc[penalty_mask, "final_score"] *= 0.75

    # Apply bonus and clip to valid range
    df["final_score"] = (df["final_score"] + bonus).clip(0, 1).round(4)

    return df