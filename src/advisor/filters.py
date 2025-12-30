# src/advisor/filters.py
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src.advisor.utils import normalize_user_types


def _norm_brand(s: str) -> str:
    return (s or "").strip().lower()


def _parse_battery_wh(battery_text: Any) -> Optional[float]:
    """
    Battery column examples:
      '3-cell, 52.5 Wh Li-ion polymer'
      '3 Cell Int (59.16Wh)'
      'Pin ... 41 Wh'
    """
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


def _parse_resolution_wh(res_text: Any) -> Optional[Tuple[int, int]]:
    """
    Screen Resolution examples:
      '1920 x 1080'
      '2880 x 1800'
    """
    if res_text is None:
        return None
    txt = str(res_text).lower().replace("×", "x")
    m = re.search(r"(\d{3,4})\s*x\s*(\d{3,4})", txt)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _intel_gen_from_cpu_number(cpu_num: Any) -> Optional[int]:
    """
    Dataset 'CPU generation' is actually CPU model number-ish:
      1335 -> i5-1335U => gen 13
      13420 -> 13th gen H series => gen 13
      125 / 155 (Core Ultra) => treat as >=14
    """
    if cpu_num is None:
        return None
    try:
        n = int(float(cpu_num))
    except Exception:
        return None

    # Core Ultra style: 125, 155...
    if 100 <= n < 1000:
        return 14

    s = str(n)
    if len(s) >= 4:
        # 1335 -> 13, 1115 -> 11, 13420 -> 13, 12450 -> 12
        return int(s[:2])
    return None


def _amd_series_from_cpu_number(cpu_num: Any) -> Optional[int]:
    """
    AMD examples:
      7530 -> series 7000
      8840 -> series 8000
      350 -> old (treat as 0xxx)
    """
    if cpu_num is None:
        return None
    try:
        n = int(float(cpu_num))
    except Exception:
        return None

    s = str(n)
    if len(s) >= 4:
        return int(s[0]) * 1000
    if len(s) == 3:
        return int(s[0]) * 100
    return None


def _cpu_passes_requirements(row: Dict[str, Any], cpu_req: Dict[str, Any]) -> bool:
    """
    Accept if row satisfies Intel OR AMD constraints (when both provided).
    """
    manu = str(row.get("CPU manufacturer", "")).lower()
    cpu_num = row.get("CPU generation", None)
    modifier = str(row.get("CPU brand modifier", "")).lower()

    cpu_manu_req = cpu_req.get("cpu_manufacturer")
    if cpu_manu_req and cpu_manu_req.lower() not in manu:
        return False

    intel_req = cpu_req.get("intel")
    amd_req = cpu_req.get("amd")
    cpu_brand = cpu_req.get("cpu_brand") # new unified field

    ok = False

    if (intel_req or cpu_brand) and "intel" in manu:
        min_gen = (intel_req or {}).get("min_gen")
        min_family = (intel_req or {}).get("min_family") or cpu_brand
        gen = _intel_gen_from_cpu_number(cpu_num)

        family_ok = True
        if min_family:
            # modifier values look like: "Core i5", "Core I5", etc.
            family_ok = (min_family.lower() in modifier)

        gen_ok = True
        if min_gen is not None:
            gen_ok = (gen is not None and gen >= int(min_gen))

        ok = ok or (family_ok and gen_ok)

    if (amd_req or cpu_brand) and "amd" in manu:
        min_series = (amd_req or {}).get("min_series")
        min_family = (amd_req or {}).get("min_family") or cpu_brand
        series = _amd_series_from_cpu_number(cpu_num)

        family_ok = True
        if min_family:
            min_family_clean = min_family.lower().replace("ryzen", "").strip()
            # check if numbers like '5' or '7' are in modifier
            family_ok = (min_family_clean in modifier)

        series_ok = True
        if min_series is not None:
            series_ok = (series is not None and series >= int(min_series))

        ok = ok or (family_ok and series_ok)

    # If cpu_req exists but neither matched manufacturer, fail (strict)
    # Added cpu_manufacturer to the condition
    if (intel_req or amd_req or cpu_brand or cpu_manu_req) and not ok:
        # If we only had manufacturer req and it passed the first check, we are potentially ok
        if cpu_manu_req and not (intel_req or amd_req or cpu_brand):
            return True
        return False

    return True


def _cpu_gen_passes(row: Dict[str, Any], min_gen: int) -> bool:
    cpu_num = row.get("CPU generation")
    manu = str(row.get("CPU manufacturer", "")).lower()
    
    if "intel" in manu:
        gen = _intel_gen_from_cpu_number(cpu_num)
        return gen is not None and gen >= min_gen
    
    # AMD is trickier with 'generation', usually we use 'series'
    # But for a general 'min_cpu_gen' query, we can try to guess or skip
    return True 


def apply_filters(df, query):
    df = df.copy()

    # =========================
    # HARD CONSTRAINTS (existing)
    # =========================
    # PRICE
    if "price_min" in query:
        df = df[df["Price (VND)"].notna() & (df["Price (VND)"] >= query["price_min"])]

    if "price_max" in query:
        df = df[df["Price (VND)"].notna() & (df["Price (VND)"] <= query["price_max"])]

    # RAM
    if "ram_exact_gb" in query:
        df = df[df["RAM (GB)"] == query["ram_exact_gb"]]
    elif "min_ram_gb" in query:
        df = df[df["RAM (GB)"] >= query["min_ram_gb"]]

    # STORAGE
    if "min_storage_gb" in query:
        df = df[df["Storage (GB)"] >= query["min_storage_gb"]]

    # WEIGHT
    if "min_weight_kg" in query:
        df = df[df["Weight (kg)"] >= query["min_weight_kg"]]
    if "max_weight_kg" in query:
        df = df[df["Weight (kg)"] <= query["max_weight_kg"]]

    # =========================
    # ADVANCED HARD CONSTRAINTS
    # =========================

    # --- Brand exclude / prefer ---
    brand_pref = query.get("brand_preferences") or {}
    exclude = set(_norm_brand(x) for x in (brand_pref.get("exclude") or []) if x)
    prefer = set(_norm_brand(x) for x in (brand_pref.get("prefer") or []) if x)

    if exclude:
        df = df[~df["Manufacturer"].fillna("").map(_norm_brand).isin(exclude)]

    # NOTE: prefer is handled in scoring (soft). Do NOT hard-filter prefer by default.

    # --- CPU requirements ---
    cpu_req = query.get("cpu_requirements")
    if isinstance(cpu_req, dict) and (cpu_req.get("intel") or cpu_req.get("amd")):
        # strict filter: must satisfy intel OR amd req
        mask = df.apply(lambda r: _cpu_passes_requirements(r.to_dict(), cpu_req), axis=1)
        df = df[mask]

    min_cpu_gen = query.get("min_cpu_gen")
    if min_cpu_gen is not None:
        mask = df.apply(lambda r: _cpu_gen_passes(r.to_dict(), int(min_cpu_gen)), axis=1)
        df = df[mask]

    # --- Display requirements ---
    disp = query.get("display_requirements")
    if isinstance(disp, dict):
        size = disp.get("screen_size_inch")
        tol = disp.get("screen_size_tolerance", None)
        if size is not None:
            tol = float(tol) if tol is not None else 0.2
            lo = float(size) - tol
            hi = float(size) + tol
            df = df[df["Screen Size (inch)"].notna() & (df["Screen Size (inch)"] >= lo) & (df["Screen Size (inch)"] <= hi)]

        min_hz = disp.get("min_refresh_hz")
        if min_hz is not None and "Refresh Rate (Hz)" in df.columns:
            df = df[df["Refresh Rate (Hz)"].notna() & (df["Refresh Rate (Hz)"] >= int(min_hz))]

        res_min = disp.get("resolution_min")
        if res_min is not None and "Screen Resolution" in df.columns:
            # Only implement FHD and above reliably
            target = str(res_min).upper()
            if target in {"FHD", "QHD", "UHD", "4K"}:
                def _res_ok(x):
                    wh = _parse_resolution_wh(x)
                    if not wh:
                        return False
                    w, h = wh
                    if target == "FHD":
                        return (w >= 1920 and h >= 1080)
                    if target == "QHD":
                        return (w >= 2560 and h >= 1440)
                    # UHD/4K
                    return (w >= 3840 and h >= 2160)
                df = df[df["Screen Resolution"].apply(_res_ok)]

    batt = query.get("battery_requirements")
    if isinstance(batt, dict):
        min_wh = batt.get("min_wh")
        if min_wh is not None:
            if "Battery (Wh)" in df.columns:
                df = df[df["Battery (Wh)"].notna() & (df["Battery (Wh)"] >= float(min_wh))]
            elif "Battery" in df.columns:
                df["_battery_wh"] = df["Battery"].apply(_parse_battery_wh)
                df = df[df["_battery_wh"].notna() & (df["_battery_wh"] >= float(min_wh))]

    # --- Ports requirements (dataset currently lacks ports) ---
    # If later you add a column like "Ports" or "has_lan"/"has_hdmi",
    # you can enforce it here. For now: ignore to avoid false filtering.
    # ports = query.get("ports_requirements")

    # =========================
    # INTENT-AWARE FILTER (existing)
    # =========================
    user_types = normalize_user_types(query)

    # gaming-only → bắt buộc gaming-ready
    if user_types == ["gaming"]:
        df = df[df["is_gaming_ready"]]

    return df