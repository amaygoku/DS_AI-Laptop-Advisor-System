import pandas as pd
import numpy as np
import os
import re

# ===============================
# PATHS
# ===============================
INPUT_PATH = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\processed\laptops_normalized.csv"
OUTPUT_PATH = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\processed\laptops_features.csv"

# ===============================
# LOAD
# ===============================
df = pd.read_csv(INPUT_PATH)

# ===============================
# GPU SCORE (PERCEIVED POWER)
# ===============================
GPU_SCORE_RULES = [
    (r"RTX\s?40", 1.00),
    (r"RTX\s?30", 0.90),
    (r"RTX\s?20", 0.80),
    (r"GTX", 0.70),
    (r"QUADRO|RTX\s?A", 0.85),
    (r"RX\s?7", 0.85),
    (r"RX\s?6", 0.80),
    (r"MX", 0.55),
    (r"INTEL_IRIS", 0.55),
    (r"INTEL_UHD", 0.45),
    (r"AMD_RADEON_GRAPHICS", 0.50),
    (r"QUALCOMM_ADRENO", 0.45),
    (r"APPLE_GPU", 0.60),
]

def gpu_score(model):
    if not isinstance(model, str):
        return 0.45
    model = model.upper()
    for pattern, score in GPU_SCORE_RULES:
        if re.search(pattern, model):
            return score
    return 0.45

df["gpu_score"] = df["gpu_model"].apply(gpu_score)

# ===============================
# BATTERY SCORE (NaN-SAFE)
# ===============================
# chỉ dùng khi có dữ liệu
df["battery_score"] = df["norm_battery"]
df["battery_available"] = df["battery_score"].notna().astype(int)

# ===============================
# TASK SCORES (CORE SIGNALS)
# ===============================

# 🎮 GAMING — GPU dominant, battery irrelevant
df["gaming_score"] = (
    df["gpu_score"] * 0.60 +
    df["base_performance_score"] * 0.25 +
    df["norm_ram"] * 0.15
)

# 🤖 AI / GRAPHICS / RENDER
df["ai_graphics_score"] = (
    df["gpu_score"] * 0.55 +
    df["base_performance_score"] * 0.30 +
    df["norm_ram"] * 0.15
)

# 🧑‍💼 OFFICE / BUSINESS — mượt + nhẹ + pin
df["office_score"] = (
    df["base_performance_score"] * 0.45 +
    df["norm_weight"] * 0.35 +
    df["battery_score"].fillna(0.5) * 0.20
)

# 🎒 PORTABILITY / STUDY — nhẹ + pin là chính
df["portability_score"] = (
    df["norm_weight"] * 0.45 +
    df["battery_score"].fillna(0.5) * 0.35 +
    (1 - df["norm_screen"]) * 0.20
)

# 🧩 GENERAL / BALANCED
df["general_score"] = (
    df["office_score"] * 0.45 +
    df["base_performance_score"] * 0.35 +
    df["portability_score"] * 0.20
)

# ===============================
# OPTIONAL: RESCALE (KHÔNG BẮT BUỘC)
# ===============================
def robust_rescale(series, low_q=0.05, high_q=0.95):
    lo = series.quantile(low_q)
    hi = series.quantile(high_q)
    if hi - lo == 0:
        return series
    return ((series - lo) / (hi - lo)).clip(0, 1)

# 👉 nếu muốn bật rescale thì uncomment
# for col in [
#     "gaming_score",
#     "ai_graphics_score",
#     "office_score",
#     "portability_score",
#     "general_score"
# ]:
#     df[col] = robust_rescale(df[col])

# ===============================
# TAGS (FOR FILTER & EXPLAIN)
# ===============================
df["is_gaming_ready"] = df["gaming_score"] >= 0.6
df["is_ai_ready"] = df["ai_graphics_score"] >= 0.6
df["is_business_ready"] = df["office_score"] >= 0.6
df["is_ultrabook"] = (
    (df["norm_weight"] >= 0.7) &
    (df["battery_score"].fillna(0.5) >= 0.6)
)

# ===============================
# SAVE
# ===============================
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

print("✅ feature_engineering.py (BATTERY-AWARE) completed")
print(
    df[[
        "gaming_score",
        "office_score",
        "ai_graphics_score",
        "portability_score",
        "general_score"
    ]].describe()
)
