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
# GPU SCORE MAP (HEURISTIC)
# ===============================
GPU_SCORE_RULES = [
    (r"RTX\s?40", 1.00),
    (r"RTX\s?30", 0.90),
    (r"RTX\s?20", 0.80),
    (r"GTX", 0.70),
    (r"QUADRO|RTX\s?A", 0.85),
    (r"RX\s?7", 0.85),
    (r"RX\s?6", 0.80),
    (r"MX", 0.50),
    (r"INTEL_IRIS", 0.45),
    (r"INTEL_UHD", 0.30),
    (r"AMD_RADEON_GRAPHICS", 0.40),
    (r"QUALCOMM_ADRENO", 0.35),
    (r"APPLE_GPU", 0.55),
]

# ===============================
# CPU GEN SCORE
# ===============================
def cpu_gen_score(gen):
    if pd.isna(gen):
        return 0.5
    gen = int(gen)
    if gen >= 13:
        return 1.0
    if gen == 12:
        return 0.9
    if gen == 11:
        return 0.8
    if gen == 10:
        return 0.7
    return 0.6

# ===============================
# GPU SCORE FUNCTION
# ===============================
def gpu_score(model):
    if not isinstance(model, str):
        return 0.4

    model = model.upper()

    for pattern, score in GPU_SCORE_RULES:
        if re.search(pattern, model):
            return score

    return 0.4

# ===============================
# MAIN
# ===============================
df = pd.read_csv(INPUT_PATH)

# ===============================
# 1. GPU SCORE
# ===============================
df["gpu_score"] = df["gpu_model"].apply(gpu_score)

# ===============================
# 2. CPU GEN SCORE
# ===============================
df["cpu_gen_score"] = df["CPU generation"].apply(cpu_gen_score)

# ===============================
# 3. TASK-SPECIFIC FEATURES
# ===============================

# 🎮 Gaming
df["gaming_score"] = (
    df["gpu_score"] * 0.6 +
    df["base_performance_score"] * 0.4
).round(3)

# 🤖 AI / Graphics / Rendering
df["ai_graphics_score"] = (
    df["gpu_score"] * 0.7 +
    df["base_performance_score"] * 0.3
).round(3)

# 🧑‍💻 Office / Study
df["office_score"] = (
    df["base_performance_score"] * 0.7 +
    df["norm_weight"] * 0.3
).round(3)

# 🎒 Portability
df["portability_score"] = (
    df["norm_weight"] * 0.6 +
    df["norm_screen"] * 0.4
).round(3)

# ===============================
# 4. ADVISOR TAGS
# ===============================
df["is_gaming_ready"] = df["gaming_score"] > 0.65
df["is_ai_ready"] = df["ai_graphics_score"] > 0.65
df["is_ultrabook"] = df["norm_weight"] > 0.7

# ===============================
# SAVE
# ===============================
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

print("✅ feature_engineering.py completed")
print(df[[
    "Product Name",
    "gpu_model",
    "gpu_score",
    "gaming_score",
    "office_score"
]].head())
