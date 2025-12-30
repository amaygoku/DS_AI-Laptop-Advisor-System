import pandas as pd
import numpy as np
import os
import re

# ===============================
# PATHS
# ===============================
CSV_PATH = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\processed\laptops_features.csv"

def parse_gen_intel(row):
    brand = str(row['CPU brand modifier']).lower()
    raw_gen = row['CPU generation']
    
    if pd.isna(raw_gen):
        return np.nan
    
    gen_val = float(raw_gen)
    
    # Core Ultra: 155, 125 -> 1; 255, 225 -> 2
    if "ultra" in brand:
        if 100 <= gen_val < 200:
            return 1
        if 200 <= gen_val < 300:
            return 2
        return np.nan

    # Core Series 1 (new branding): 120 -> 1
    # Check if brand modifier is just 'core 5', 'core 7' (not i5, i7)
    if re.match(r"^core\s+\d+$", brand):
        return 1

    # Core i: 1335 -> 13, 12450 -> 12, 1115 -> 11, 10110 -> 10, 8250 -> 8
    # 14700 -> 14
    if gen_val >= 1000:
        s_gen = str(int(gen_val))
        if len(s_gen) == 4:
            if s_gen.startswith('1'): # 1335, 1235, 1115, 1035
                return int(s_gen[:2])
            return int(s_gen[0]) # 8250 -> 8
        elif len(s_gen) == 5: # 13420 -> 13, 10110 -> 10
            return int(s_gen[:2])
    
    # Core i: 650 -> 1 (3 digits)
    if 100 <= gen_val < 1000:
        return 1
    
    return np.nan

def parse_gen_amd(row):
    raw_gen = row['CPU generation']
    if pd.isna(raw_gen):
        return np.nan
    
    gen_val = float(raw_gen)
    
    # Ryzen AI 300: 350, 370 -> 3
    if "ryzen ai" in str(row['CPU brand modifier']).lower():
        if 300 <= gen_val < 400:
            return 3
        # Some Ryzen AI might be listed as 7/9/8 in CPU generation column but brand has AI
        # If it's 7000/8000 series, let it fall through
    
    # Ryzen: 7530 -> 7, 5625 -> 5, 8840 -> 8, 4800 -> 4
    if gen_val >= 1000:
        return int(str(int(gen_val))[0])
        
    return np.nan

def parse_gen_qualcomm(row):
    return 1 # Currently mostly Snapdragon X Elite/Plus

def parse_gen_apple(row):
    # Apple M1, M2, M3, M4
    brand = str(row['CPU brand modifier']).upper()
    m = re.search(r"M(\d+)", brand)
    if m:
        return int(m.group(1))
    return np.nan

def main():
    if not os.path.exists(CSV_PATH):
        print(f"File not found: {CSV_PATH}")
        return

    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} rows.")

    def apply_parsing(row):
        mfr = str(row['CPU manufacturer']).lower()
        if 'intel' in mfr:
            return parse_gen_intel(row)
        if 'amd' in mfr:
            return parse_gen_amd(row)
        if 'qualcomm' in mfr:
            return parse_gen_qualcomm(row)
        if 'apple' in mfr:
            return parse_gen_apple(row)
        return np.nan

    df['cpu_gen'] = df.apply(apply_parsing, axis=1)
    
    # Export
    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    print(f"✅ Parsed CPU generations saved to new column 'cpu_gen' in {CSV_PATH}")
    
    # Preview
    preview = df[['CPU manufacturer', 'CPU brand modifier', 'CPU generation', 'cpu_gen']].drop_duplicates().head(20)
    print("\nSample mapping results:")
    print(preview)

if __name__ == "__main__":
    main()
