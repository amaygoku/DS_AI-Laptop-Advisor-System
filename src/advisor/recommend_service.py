# src/advisor/recommend_service.py
from __future__ import annotations

from typing import Any, Dict, List
import pandas as pd

from src.llm.schemas_v2 import IntentV2


def _dump_model(obj):
    """Support Pydantic v2 models and normal dict."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if v is not None}
    return obj


def _norm_list_lower(xs):
    if not xs:
        return []
    return [str(x).strip().lower() for x in xs if x is not None and str(x).strip()]


def build_query_from_intent(intent):
    """
    Build query dict for recommender from Intent / IntentV2.
    Includes brand_preferences for DB filtering/scoring.
    """
    q = {}

    # ---------- intent ----------
    user_types = getattr(intent, "user_types", None)
    user_type = getattr(intent, "user_type", None)
    if user_types:
        q["user_types"] = _norm_list_lower(user_types)
    elif user_type:
        q["user_type"] = str(user_type).lower()
    else:
        q["user_type"] = "general"

    # ---------- budget ----------
    price_min = getattr(intent, "price_min", None)
    price_max = getattr(intent, "price_max", None)
    if price_min is not None:
        q["price_min"] = int(price_min)
    if price_max is not None:
        q["price_max"] = int(price_max)

    # ---------- RAM ----------
    ram_exact = getattr(intent, "ram_exact_gb", None)
    min_ram = getattr(intent, "min_ram_gb", None)
    if ram_exact is not None:
        q["ram_exact_gb"] = int(ram_exact)
    elif min_ram is not None:
        q["min_ram_gb"] = int(min_ram)

    # ---------- storage ----------
    min_storage = getattr(intent, "min_storage_gb", None)
    if min_storage is not None:
        q["min_storage_gb"] = int(min_storage)

    # ---------- weight ----------
    min_w = getattr(intent, "min_weight_kg", None)
    max_w = getattr(intent, "max_weight_kg", None)
    if min_w is not None:
        q["min_weight_kg"] = float(min_w)
    if max_w is not None:
        q["max_weight_kg"] = float(max_w)

    # ---------- CPU GEN ----------
    min_cpu_gen = getattr(intent, "min_cpu_gen", None)
    if min_cpu_gen is not None:
        q["min_cpu_gen"] = int(min_cpu_gen)

    # ---------- soft prefs ----------
    pref_light = getattr(intent, "pref_light", None)
    pref_cheap = getattr(intent, "pref_cheap", None)
    if pref_light is not None:
        q["pref_light"] = bool(pref_light)
    if pref_cheap is not None:
        q["pref_cheap"] = bool(pref_cheap)

    # =========================================================
    # ADVANCED FIELDS (forward for future filters/scoring/advice)
    # =========================================================
    cpu_req = _dump_model(getattr(intent, "cpu_requirements", None)) or {}
    cpu_brand = getattr(intent, "cpu_brand", None)
    if cpu_brand:
        cpu_req["cpu_brand"] = cpu_brand
    
    cpu_manu = getattr(intent, "cpu_manufacturer", None)
    if cpu_manu:
        cpu_req["cpu_manufacturer"] = cpu_manu

    if cpu_req:
        q["cpu_requirements"] = cpu_req

    display_req = _dump_model(getattr(intent, "display_requirements", None))
    if display_req:
        q["display_requirements"] = display_req

    battery_req = _dump_model(getattr(intent, "battery_requirements", None))
    if battery_req:
        q["battery_requirements"] = battery_req

    ports_req = _dump_model(getattr(intent, "ports_requirements", None))
    if ports_req:
        q["ports_requirements"] = ports_req

    # ---------- BRAND (NEW) ----------
    brand_pref = _dump_model(getattr(intent, "brand_preferences", None))
    if brand_pref:
        prefer = _norm_list_lower(brand_pref.get("prefer"))
        exclude = _norm_list_lower(brand_pref.get("exclude"))

        # only attach if non-empty (avoid noisy query)
        cleaned = {}
        if prefer:
            cleaned["prefer"] = prefer
        if exclude:
            cleaned["exclude"] = exclude

        if cleaned:
            q["brand_preferences"] = cleaned

    pref_battery = getattr(intent, "pref_battery", None)
    if pref_battery is not None:
        q["pref_battery"] = pref_battery

    gaming_level = getattr(intent, "gaming_level", None)
    if gaming_level:
        q["gaming_level"] = gaming_level

    use_case_notes = getattr(intent, "use_case_notes", None)
    if use_case_notes:
        q["use_case_notes"] = use_case_notes

    return q





def recommendations_to_json(df_top: pd.DataFrame, query: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return a compact JSON list for LLM. No 'why' field.
    """
    items: List[Dict[str, Any]] = []

    for idx, row in df_top.iterrows():
        r = row.to_dict()

        # derive is_light (optional)
        is_light = False
        w = r.get("Weight (kg)")
        if w is not None:
            try:
                is_light = float(w) <= 1.7
            except Exception:
                is_light = False

        items.append({
            "id": str(idx),
            "name": r.get("Product Name"),
            "brand": r.get("Manufacturer"),
            "price_vnd": r.get("Price (VND)"),
            "ram_gb": r.get("RAM (GB)"),
            "storage_gb": r.get("Storage (GB)"),
            "weight_kg": r.get("Weight (kg)"),
            "screen_inch": r.get("Screen Size (inch)"),
            "refresh_hz": r.get("Refresh Rate (Hz)"),
            "cpu_manufacturer": r.get("CPU manufacturer"),
            "cpu_brand": r.get("CPU brand modifier"),
            "cpu_generation": r.get("CPU generation"),
            "scores": {
                "final_score": r.get("final_score"),
                "general_score": r.get("general_score"),
                "office_score": r.get("office_score"),
                "gaming_score": r.get("gaming_score"),
                "ai_graphics_score": r.get("ai_graphics_score"),
                "portability_score": r.get("portability_score"),
                "battery_score": r.get("battery_score"),
                "price_fit": r.get("price_fit"),
            },
            "flags": {
                "is_light": is_light,
                "is_gaming_ready": bool(r.get("is_gaming_ready", False)),
                "is_ai_ready": bool(r.get("is_ai_ready", False)),
                "is_ultrabook": bool(r.get("is_ultrabook", False)),
                "is_business_ready": bool(r.get("is_business_ready", False)),
            }
        })

    return items
