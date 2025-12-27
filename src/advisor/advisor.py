from src.advisor.filters import apply_filters
from src.advisor.scorer import apply_scoring


def explain(row, user_type):
    reasons = []

    if user_type in ["business", "office", "study", "student"]:
        if row.get("office_score", 0) >= 0.6:
            reasons.append("Phù hợp cho văn phòng / học tập")
        if row.get("is_light", False):
            reasons.append("Nhẹ, dễ mang theo")

    if user_type == "gaming":
        if row.get("is_gaming_ready", False):
            reasons.append("Cấu hình thiên về chơi game (gaming-ready)")
        # nới ngưỡng để luôn có mô tả tương đối
        gs = row.get("gaming_score", 0)
        if gs >= 0.55:
            reasons.append("Hiệu năng game khá")
        elif gs >= 0.40:
            reasons.append("Chơi game eSports mức vừa")
        else:
            reasons.append("Phù hợp game nhẹ, không tối ưu game nặng")

    if row.get("price_fit", 0) >= 0.75:
        reasons.append("Giá rất sát ngân sách")

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