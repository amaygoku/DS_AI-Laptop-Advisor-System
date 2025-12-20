# source/advisor/advisor.py

from advisor.filters import apply_filters
from advisor.scorer import apply_scoring


def recommend_laptops(df, query, top_n=5):
    df_filtered = apply_filters(df, query)
    print(df_filtered.shape[0], "laptops after filtering")

    if df_filtered.empty:
        print("⚠️ Filter returned 0 rows")
        return df_filtered

    df_scored = apply_scoring(df_filtered, query)
    return df_scored.sort_values("final_score", ascending=False).head(top_n)

