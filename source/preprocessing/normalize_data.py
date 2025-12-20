import pandas as pd
import numpy as np
import os

# ===============================
# PATHS
# ===============================
INPUT_PATH = r"D:\DS_project\DS_AI-Laptop-Advisor-System\EDA\clean_final_v3.csv"
OUTPUT_PATH = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\processed\laptops_normalized.csv"

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

df["norm_ram"] = min_max(df["RAM (GB)"])
df["norm_storage"] = min_max(df["Storage (GB)"])
df["norm_cpu"] = min_max(df["CPU Speed (GHz)"])
df["norm_screen"] = min_max(df["Screen Size (inch)"])

# Weight: nhẹ hơn = tốt hơn
df["norm_weight"] = min_max(df["Weight (kg)"].max() - df["Weight (kg)"])

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
