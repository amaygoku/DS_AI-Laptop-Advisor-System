import pandas as pd
from advisor.advisor import recommend_laptops

CSV_PATH = "src/data/laptops_features.csv"

def test_recommend_runs_on_real_csv():
    df = pd.read_csv(CSV_PATH)

    # Chuẩn hoá tối thiểu
    for c in ["Price (VND)", "RAM (GB)", "Storage (GB)", "Weight (kg)",
              "office_score", "portability_score", "gaming_score",
              "ai_graphics_score", "general_score"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["is_gaming_ready"] = df["is_gaming_ready"].astype(bool)

    q = {"user_type": "study", "price_max": 20000000}
    out = recommend_laptops(df, q, top_n=3)

    assert "final_score" in out.columns
    assert len(out) <= 3
