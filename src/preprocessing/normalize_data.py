import pandas as pd
import numpy as np
import os
import re

# ===============================
# PATHS
# ===============================
INPUT_PATH = r"C:\Users\ASUS\OneDrive - Hanoi University of Science and Technology\Desktop\DS_AI\DS_AI-Laptop-Advisor-System\src\EDA\clean_final_v3.csv"
OUTPUT_PATH = r"C:\Users\ASUS\OneDrive - Hanoi University of Science and Technology\Desktop\DS_AI\DS_AI-Laptop-Advisor-System\data\processed\laptops_normalized.csv"

# ===============================
# UTILS
# ===============================
def min_max(series):
    return (series - series.min()) / (series.max() - series.min())

# ===============================
# 1. LOAD DATA
# ===============================
df = pd.read_csv(INPUT_PATH)

# ===============================
# 2. BASIC CLEANING
# ===============================

# ---------- PRICE ----------
df["is_contact_price"] = df["Price (VND)"].isna()

# ❗ KHÔNG fill giá = 0
# giữ nguyên NaN

# ---------- NUMERIC FIELDS ----------
num_fill_median = [
    "RAM (GB)",
    "Storage (GB)",
    "Weight (kg)",
    "CPU Speed (GHz)",
    "Screen Size (inch)"
]

for col in num_fill_median:
    df[col] = pd.to_numeric(df[col], errors="coerce")
    df[col] = df[col].fillna(df[col].median())

# đảm bảo Price là numeric nhưng giữ NaN
df["Price (VND)"] = pd.to_numeric(df["Price (VND)"], errors="coerce")

# ===============================
# 3. NORMALIZATION (NaN-SAFE)
# ===============================

def ram_score(gb):
    if gb >= 32: return 1.0
    if gb >= 16: return 0.8
    if gb >= 8:  return 0.6
    return 0.4

def storage_score(gb):
    if gb >= 1024: return 1.0
    if gb >= 512:  return 0.8
    if gb >= 256:  return 0.6
    return 0.4

df["norm_ram"] = df["RAM (GB)"].apply(ram_score)
df["norm_storage"] = df["Storage (GB)"].apply(storage_score)

df["norm_cpu"] = df["CPU Speed (GHz)"].rank(pct=True)
df["norm_weight"] = (
    1 - df["Weight (kg)"].rank(pct=True)
)

# -------- SCREEN SIZE (neutral scale) --------
df["norm_screen"] = df["Screen Size (inch)"].rank(pct=True)

# ---------- PRICE (ONLY IF AVAILABLE) ----------
df["norm_price"] = np.nan
price_mask = ~df["is_contact_price"]

if price_mask.any():
    df.loc[price_mask, "norm_price"] = min_max(
        df.loc[price_mask, "Price (VND)"]
    )

# Giá phụ trợ cho advisor (NaN-safe)
df["price_million"] = (df["Price (VND)"] / 1_000_000).round(2)

# ===============================
# 4. BASE SCORES (NO PRICE INSIDE)
# ===============================

df["base_performance_score"] = (
    df["norm_cpu"] * 0.5 +
    df["norm_ram"] * 0.3 +
    df["norm_storage"] * 0.2
).round(3)

df["base_portability_score"] = df["norm_weight"].round(3)

# ===============================
# 5. ADVISOR FLAGS (VERY IMPORTANT)
# ===============================

df["has_price"] = ~df["is_contact_price"]
df["ready_for_budget_filter"] = df["has_price"]
df["ready_for_performance_advice"] = True

# ===============================
# EXTRA FLAGS FOR ADVISOR
# ===============================
df["is_light"] = df["Weight (kg)"] < 1.6
df["is_heavy"] = df["Weight (kg)"] > 2.3

df["is_small_screen"] = df["Screen Size (inch)"] <= 14
df["is_large_screen"] = df["Screen Size (inch)"] >= 15.6



def normalize_text(t: str) -> str:
    return (
        t.lower()
        .replace("\u00a0", " ")     # non-breaking space
        .replace("-", "-")          # unicode hyphen
        .replace("–", "-")
        .replace(",", ".")          # 52,6 -> 52.6
    )


import re
import numpy as np

import re
import numpy as np

def normalize_text(t: str) -> str:
    if not isinstance(t, str):
        return ""

    t = t.lower()
    t = re.sub(r"[\u00a0]", " ", t)
    t = re.sub(r"[\u2010\u2011\u2012\u2013\u2014]", "-", t)
    t = t.replace(",", ".")
    return t

def parse_battery_wh(text):
    if not isinstance(text, str):
        return np.nan

    t = normalize_text(text)
    print(t)

    patterns = [
        # 58.2-wh, 70wh, 52.4 wh
        r"(\d+(?:\.\d+)?)\s*wh\b",

        # 52.4 (whr), 99.9 battery (whr)
        r"(\d+(?:\.\d+)?)\s*\(?\s*whrs?\s*\)?",


        # 66.5 watt-giờ / watt giờ
        r"(\d+(?:\.\d+)?)\s*watt\s*-?\s*gi(?:ờ|o)",

        # 58.2-watt-hour / 58.2 watt hour
        r"(\d+(?:\.\d+)?)[\s-]*watt[\s-]*hour",

        # 53.5 Wh / 53.5 Whr / (Whr)
        r"(\d+(?:\.\d+)?)\s*whrs?\b",

        # 72 battery (whr)
        r"(\d+(?:\.\d+)?)[\s-]*battery\s*\(?\s*whrs?\s*\)?",

        #Thời gian xem video trực tuyến lên đến 18 giờ Thời gian duyệt web trên mạng không dây lên đến 15 giờ Pin Li-Po 66.5 watt‑giờ tích hợp
        r"(\d+(?:\.\d+)?)\s*watt\s*[-\-–—]?\s*gi(?:ờ|o)"
    ]

    for pat in patterns:
        m = re.search(pat, t)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return np.nan

    return np.nan




df["Battery (Wh)"] = df["Battery"].apply(parse_battery_wh)
battery_mask = df["Battery (Wh)"].notna()
df["norm_battery"] = np.nan

if battery_mask.any():
    df.loc[battery_mask, "norm_battery"] = min_max(df.loc[battery_mask, "Battery (Wh)"])


# ===============================
# 6. SAVE
# ===============================
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

print("✅ preprocessing.py completed successfully")
print(df[[
    "Product Name",
    "base_performance_score",
    "base_portability_score",
    "price_million",
    "has_price"
]].head())
