import pandas as pd
from bs4 import BeautifulSoup
import os
import re
import logging

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

DATA_PATH = r"D:\DS_project\DS_AI-Laptop-Advisor-System\EDA\clean_final.csv"
OUTPUT_PATH = r"D:\DS_project\DS_AI-Laptop-Advisor-System\EDA\clean_final_v3.csv"

# =========================
# GPU LABEL KEYWORDS
# =========================
GPU_LABEL_KEYWORDS = [
    "card đồ họa", "đồ họa", "graphics",
    "gpu", "vga", "card màn hình"
]

GPU_BRANDS = ["nvidia", "amd", "intel", "qualcomm", "apple"]

# =========================
# STEP 1: EXTRACT GPU RAW
# =========================
def extract_gpu_raw_from_html(html_path, row_id=None):
    if not isinstance(html_path, str) or not os.path.exists(html_path):
        logging.warning(f"[{row_id}] HTML not found")
        return None

    soup = BeautifulSoup(open(html_path, encoding="utf-8"), "html.parser")
    candidates = []

    for tag in soup.find_all(["tr", "li", "div"]):
        text = tag.get_text(" ", strip=True).lower()
        if any(k in text for k in GPU_LABEL_KEYWORDS) and any(b in text for b in GPU_BRANDS):
            candidates.append(text)

    return " | ".join(candidates) if candidates else None


def normalize_text(text):
    text = text.lower()
    text = re.sub(r"[®™]", "", text)
    return text


# =========================
# STEP 2: PARSE GPU MODEL
# =========================
def extract_gpu_model(gpu_raw):
    if not isinstance(gpu_raw, str):
        return "UNKNOWN"

    text = normalize_text(gpu_raw)

    # -------- NVIDIA --------
    m = re.search(r"nvidia.*?(quadro)\D*(\d{3,4})", text)
    if m:
        return f"QUADRO T{m.group(2)}"
    m = re.search(r"nvidia.*?(rtx)\D*(\d{3,4})", text)
    if m:
        return f"RTX {m.group(2)}"

    m = re.search(r"nvidia.*?(gtx)\D*(\d{3,4})", text)
    if m:
        return f"GTX {m.group(2)}"

    m = re.search(r"nvidia.*?(mx)\D*(\d{3,4}a?)", text)
    if m:
        return f"MX {m.group(2).upper()}"

    # -------- AMD --------
    m = re.search(r"radeon\D*(rx\s?\d{3,4}m?)", text)
    if m:
        return m.group(1).upper()

    if "radeon" in text:
        return "AMD_RADEON_GRAPHICS"

    # -------- INTEL --------
    if "intel" in text:
        if "iris" in text:
            return "INTEL_IRIS_XE"
        if "uhd" in text:
            return "INTEL_UHD"
        return "INTEL_GRAPHICS"

    # -------- QUALCOMM --------
    if "qualcomm" in text or "adreno" in text:
        return "QUALCOMM_ADRENO"

    # -------- APPLE --------
    if any(x in text for x in ["apple", "m1", "m2", "m3"]):
        return "APPLE_GPU"

    return "UNKNOWN"


# =========================
# STEP 3: GPU CLASS
# =========================
def classify_gpu(model):
    if model.startswith(("RTX", "GTX", "RX")):
        return "DISCRETE_GAMING"
    if model.startswith("QUADRO"):
        return "DISCRETE_WORKSTATION"
    if model.startswith("MX"):
        return "DISCRETE_LIGHT"
    if model.startswith(("INTEL", "AMD_RADEON")):
        return "INTEGRATED"
    if model.startswith("QUALCOMM"):
        return "INTEGRATED_ARM"
    if model.startswith("APPLE"):
        return "APPLE"
    return "UNKNOWN"


# =========================
# MAIN
# =========================
df = pd.read_csv(DATA_PATH)

df["gpu_raw"] = [
    extract_gpu_raw_from_html(p, i)
    for i, p in enumerate(df["detail_specs_html_path"])
]

df["gpu_model"] = df["gpu_raw"].apply(extract_gpu_model)
df["gpu_class"] = df["gpu_model"].apply(classify_gpu)

mask = df["GPU manufacturer"] == "Apple"

df.loc[mask, "gpu_model"] = "APPLE_GPU"
df.loc[mask, "gpu_class"] = "APPLE"

logging.info("===================================")
logging.info(f"TOTAL: {len(df)}")
logging.info(f"GPU RAW FOUND: {df['gpu_raw'].notna().sum()}")
logging.info(f"GPU MODEL FOUND: {(df['gpu_model']!='UNKNOWN').sum()}")
logging.info("===================================")
df.drop(columns=["gpu_raw"], inplace=True)
df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
logging.info("✅ GPU parsing completed")
