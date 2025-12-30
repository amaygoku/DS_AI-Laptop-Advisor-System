import pandas as pd
import numpy as np
import re
import os

INPUT_PATH = r"D:\DS_project\DS_AI-Laptop-Advisor-System\EDA\FinalData.csv"
OUTPUT_PATH = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\processed\laptops_clean.csv"



from pathlib import Path



def ensure_dir(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def clean_price(x):
    if pd.isna(x):
        return np.nan
    return float(x)


def clean_ram(x):
    return float(x) if not pd.isna(x) else np.nan


def clean_storage(x):
    """
    Assumption:
    - Nếu Storage >= 1000 và < 2000 → có thể là TB đã convert sai → giữ nguyên
    - Nếu text kiểu '1TB' → convert về 1024
    """
    if pd.isna(x):
        return np.nan
    return float(x)


def clean_cpu_generation(x):
    """
    Giữ số, bỏ chữ nếu có (125H → 125)
    """
    if pd.isna(x):
        return np.nan
    m = re.search(r"\d+", str(x))
    return m.group() if m else np.nan


def clean_weight(x):
    return float(x) if not pd.isna(x) else np.nan


def clean_numeric(df):
    numeric_cols = [
        "CPU Speed (GHz)",
        "RAM (GB)",
        "Bus (MHz)",
        "Storage (GB)",
        "Screen Size (inch)",
        "Refresh Rate (Hz)",
        "Weight (kg)",
        "Price (VND)"
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def clean_category(df):
    cat_cols = [
        "Manufacturer",
        "CPU manufacturer",
        "GPU manufacturer",
        "RAM Type"
    ]

    for col in cat_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.lower()
                .replace("nan", np.nan)
            )
    return df


def main():
    df = pd.read_csv(INPUT_PATH)

    df = clean_numeric(df)
    df = clean_category(df)

    df["CPU generation"] = df["CPU generation"].apply(clean_cpu_generation)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    ensure_dir(OUTPUT_PATH)
    df.to_csv(OUTPUT_PATH, index=False)

    print("✅ Cleaned data saved to:", OUTPUT_PATH)
    print(df.info())


if __name__ == "__main__":
    main()
