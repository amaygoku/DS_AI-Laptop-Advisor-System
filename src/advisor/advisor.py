from src.advisor.filters import apply_filters
from src.advisor.scorer import apply_scoring


def explain(row, user_type):
    reasons = []

    # Basic suitability based on intent
    if user_type in ["business", "office", "study", "student"]:
        if row.get("is_business_ready") or row.get("is_ultrabook") or row.get("office_score", 0) >= 0.7:
            reasons.append("Phù hợp cho văn phòng / học tập")
        if row.get("is_ultrabook"):
            reasons.append("Thiết kế mỏng nhẹ cao cấp (Ultrabook)")
        elif row.get("is_light"):
            reasons.append("Nhẹ, dễ di chuyển")

    if user_type == "gaming":
        if row.get("is_gaming_ready"):
            reasons.append("Cấu hình tối ưu cho gaming")
        gs = row.get("gaming_score", 0)
        if gs >= 0.75:
            reasons.append("Hiệu năng chơi game đỉnh cao")
        elif gs >= 0.55:
            reasons.append("Chiến tốt các tựa game hiện nay")
        elif gs >= 0.40:
            reasons.append("Chơi ổn các game eSports")
            
    if user_type == "ai":
        if row.get("is_ai_ready"):
            reasons.append("Hỗ trợ tốt các tác vụ AI / Học máy")
        if row.get("ai_graphics_score", 0) >= 0.7:
            reasons.append("Xử lý đồ họa / AI mạnh mẽ")

    # General features
    if row.get("is_small_screen"):
        reasons.append("Màn hình nhỏ gọn")
    elif row.get("is_large_screen"):
        reasons.append("Màn hình lớn, không gian làm việc rộng")

    if row.get("battery_score", 0) >= 0.7:
        reasons.append("Thời lượng pin ấn tượng")

    if row.get("price_fit", 0) >= 0.8:
        reasons.append("Rất sát với ngân sách đề ra")
    elif row.get("price_fit", 0) >= 0.6:
        reasons.append("Mức giá hợp lý so với cấu hình")

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