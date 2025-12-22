from advisor.filters import apply_filters
from advisor.scorer import apply_scoring


def explain(row, user_type):
    reasons = []

    if user_type in ["business", "office", "study", "student"]:
        if row["office_score"] >= 0.7:
            reasons.append("Phù hợp cho công việc văn phòng / học tập")
        if row.get("is_light", False):
            reasons.append("Thiết kế nhẹ, dễ mang theo")

    if row.get("price_fit", 0) >= 0.75:
        reasons.append("Giá rất phù hợp ngân sách")

    if user_type == "gaming" and row["gaming_score"] >= 0.7:
        reasons.append("Hiệu năng chơi game tốt")

    return "; ".join(reasons)



def recommend_laptops(df, query, top_n=5):
    df_f = apply_filters(df, query)
    print(f"{len(df_f)} laptops after filtering")

    if df_f.empty:
        print("⚠️ No laptops match hard constraints")
        return df_f

    df_s = apply_scoring(df_f, query)

    return (
        df_s
        .sort_values("final_score", ascending=False)
        .head(top_n)
    )
