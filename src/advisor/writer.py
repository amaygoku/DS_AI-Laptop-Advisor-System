from __future__ import annotations

from typing import Any, Dict, List, Optional


def _pick_intent_text(query: Dict[str, Any]) -> str:
    if "user_types" in query:
        mapping = {
            "gaming": "chơi game",
            "ai": "AI/đồ hoạ/render",
            "study": "học tập",
            "student": "học sinh/sinh viên",
            "business": "văn phòng/kinh doanh",
            "general": "nhu cầu phổ thông",
        }
        parts = [mapping.get(x, x) for x in query["user_types"]]
        return " + ".join(parts)

    ut = query.get("user_type", "general")
    mapping = {
        "gaming": "chơi game",
        "ai": "AI/đồ hoạ/render",
        "study": "học tập",
        "student": "học sinh/sinh viên",
        "business": "văn phòng/kinh doanh",
        "general": "nhu cầu phổ thông",
    }
    return mapping.get(ut, ut)


def _fmt_vnd(x: Optional[int]) -> str:
    if x is None:
        return ""
    # 20000000 -> "20.000.000"
    s = f"{x:,}".replace(",", ".")
    return f"{s}đ"


def write_advice_text(query: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
    """
    Deterministic text writer.
    - Không gọi LLM.
    - Không chấm điểm lại.
    - Chỉ diễn giải từ query + top results.
    """
    intent_txt = _pick_intent_text(query)

    # preferences
    pref_bits = []
    if query.get("pref_cheap") is True:
        pref_bits.append("ưu tiên giá rẻ")
    if query.get("pref_light") is True or ("max_weight_kg" in query):
        pref_bits.append("ưu tiên máy nhẹ")
    if query.get("pref_light") is False:
        pref_bits.append("không ưu tiên trọng lượng")

    # constraints
    constraints = []
    if "price_max" in query:
        constraints.append(f"ngân sách tối đa {_fmt_vnd(int(query['price_max']))}")
    if "min_ram_gb" in query:
        constraints.append(f"RAM từ {query['min_ram_gb']}GB")
    if "min_storage_gb" in query:
        constraints.append(f"lưu trữ từ {query['min_storage_gb']}GB")
    if "max_weight_kg" in query:
        constraints.append(f"cân nặng không quá {query['max_weight_kg']}kg")

    head = f"Tôi đề xuất theo nhu cầu: {intent_txt}"
    if pref_bits:
        head += " (" + ", ".join(pref_bits) + ")"
    if constraints:
        head += ". Điều kiện: " + ", ".join(constraints) + "."

    if not results:
        return head + " Hiện chưa có mẫu máy nào thỏa các điều kiện lọc hiện tại."

    # Summarize top picks
    lines = [head, "", "Gợi ý nổi bật:"]
    for i, r in enumerate(results[:3], start=1):
        name = r.get("product_name") or "Laptop"
        manu = r.get("manufacturer")
        title = f"{i}. {name}" + (f" ({manu})" if manu else "")

        price = r.get("price_vnd")
        weight = r.get("weight_kg")
        ram = r.get("ram_gb")
        storage = r.get("storage_gb")

        bullets = []
        if isinstance(price, int):
            bullets.append(f"Giá tham khảo: {_fmt_vnd(price)}")
        if weight is not None:
            bullets.append(f"Nặng khoảng {weight}kg")
        if ram is not None:
            bullets.append(f"RAM {ram}GB")
        if storage is not None:
            bullets.append(f"Lưu trữ {storage}GB")

        # reasons from scores if available
        if r.get("task_score") is not None:
            bullets.append(f"Độ phù hợp nhu cầu: {r['task_score']:.2f}")
        if r.get("affordability_score") is not None and query.get("pref_cheap") is True:
            bullets.append(f"Phù hợp tiêu chí giá: {r['affordability_score']:.2f}")
        if r.get("weight_score") is not None and (query.get("pref_light") is True or "max_weight_kg" in query):
            bullets.append(f"Phù hợp tiêu chí nhẹ: {r['weight_score']:.2f}")

        lines.append(title)
        for b in bullets[:6]:
            lines.append(f"- {b}")

        # Add a blank line between picks
        lines.append("")

    # Actionable next step
    lines.append("Nếu bạn cho thêm ngân sách cụ thể (hoặc RAM/SSD tối thiểu), tôi sẽ lọc chặt hơn và kết quả chính xác hơn.")

    return "\n".join(lines).strip()
