# src/llm/prompts.py
from __future__ import annotations

import json
from typing import Any, Dict, List


# ============================================================
# Gemini #1 - Intent Extraction (Structured JSON)
# ============================================================

# src/llm/prompts.py

# src/llm/prompts.py

INTENT_SYSTEM_PROMPT_V2 = """
You are an intent extractor for a laptop recommendation backend.

CRITICAL OUTPUT RULES:
- Output MUST be valid JSON only. No markdown, no comments.
- Do NOT output null. If a field is unknown, OMIT it.
- Do not invent specs/brands that the user didn't mention.

INTENT RULES:
- If there is exactly ONE purpose, use "user_type".
- If there are MULTIPLE purposes, use "user_types" (length >= 2) and OMIT "user_type".
- Allowed intents only: business, office, study, student, gaming, ai, general.

TOP_N RULE:
- Only include "top_n" if user explicitly asks for a number (top 5, gợi ý 4 máy...).
- If not mentioned, OMIT top_n (server defaults to 3).

NORMALIZATION RULES:
- Prices -> integers in VND.
- Brands -> lowercase, e.g., "lenovo", "asus", "acer".
- Ports must be from: LAN, HDMI, USB-A, USB-C, Thunderbolt, SD, AudioJack.
- resolution_min is one of: HD, FHD, QHD, UHD, 4K.

FIELDS TO EXTRACT (only when mentioned):
- price_min, price_max
- min_ram_gb or ram_exact_gb
- min_storage_gb
- max_weight_kg
- cpu_requirements:
  - intel: min_family (i3/i5/i7/i9), min_gen (number)
  - amd: min_family (ryzen 3/5/7/9), min_series (number like 6000)
- display_requirements:
  - screen_size_inch (float), screen_size_tolerance (float if implied), resolution_min, min_refresh_hz
- battery_requirements: min_wh
- ports_requirements: must_have list
- brand_preferences: prefer list, exclude list
- gaming_level: light/medium/hardcore
- use_case_notes: short string summarizing the user need

Return a JSON object only.
""".strip()

# Advice prompt giữ như bạn đang dùng (tự nhiên)



def build_intent_user_prompt(user_text: str) -> str:
    """
    Prompt for Gemini #1.
    In your API call, you'll combine this with Structured Outputs (response_schema).
    """
    return f"""USER_INPUT:
{user_text}

Return JSON only.
""".strip()


# ============================================================
# Gemini #2 - Advice Generation (Natural language)
# ============================================================

# src/llm/prompts.py (chỉ đoạn ADVICE_SYSTEM_PROMPT)

# src/llm/prompts.py

ADVICE_SYSTEM_PROMPT = """
You are a Vietnamese laptop buying assistant.

You will receive JSON including:
- user_text
- intent
- recommendations (list of laptops with specs/scores/flags)

Write a natural, helpful response in Vietnamese.
Style guidelines:
- Sound like a real sales advisor: friendly, direct, not overly structured.
- Use short paragraphs; bullet points only when helpful.
- Do NOT repeat the JSON field names.
- Do NOT invent products or specs; rely only on provided data.

What to include:
- 1 short sentence summarizing what the user needs.
- Recommend exactly N laptops (N = length of recommendations list).
- For each laptop: name + price (if any) + 2–3 concrete reasons derived from specs/scores/flags.
- Mention a small caveat when relevant (e.g., 60Hz, not gaming-ready, gaming_score not high).
- End with a single follow-up question only if it meaningfully improves the choice.

Special rules:
- If intent.user_type == "gaming":
  - Prefer emphasizing flags.is_gaming_ready and gaming_score.
  - If none are gaming-ready, say clearly: "Trong ngân sách này chưa có mẫu thật sự gaming-ready"
    and propose a practical next step (increase budget or accept eSports/light gaming).
- If intent.price_max exists, indicate whether each choice is within budget.
- No emojis.
""".strip()



def build_advice_user_prompt(
    user_text: str,
    intent: Dict[str, Any],
    recommendations: List[Dict[str, Any]],
) -> str:
    """
    Prompt for Gemini #2.
    We pass JSON as a single payload to reduce ambiguity.
    """
    payload = {
        "user_text": user_text,
        "intent": intent,
        "recommendations": recommendations,
    }
    # ensure stable json string (readable + deterministic)
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

    return f"""INPUT_JSON:
{payload_json}

Write the advisory text following the required format.
""".strip()


# ============================================================
# Optional: fallback templates (if Gemini fails)
# ============================================================

def fallback_advice_no_llm(
    user_text: str,
    intent: Dict[str, Any],
    recommendations: List[Dict[str, Any]],
) -> str:
    """
    A very simple deterministic fallback if Gemini #2 fails.
    """
    if not recommendations:
        return (
            "Hiện chưa có mẫu nào thỏa các điều kiện lọc cứng.\n"
            "Bạn vui lòng cho tôi biết thêm 1 thông tin: ngân sách tối đa (VND) "
            "và ưu tiên chính (văn phòng/học tập/gaming/đồ họa) để tôi gợi ý chính xác hơn."
        )

    lines: List[str] = []
    lines.append("Tóm tắt nhu cầu: " + (intent.get("user_type") or ", ".join(intent.get("user_types", ["general"]))))

    lines.append("")
    lines.append(f"Gợi ý {len(recommendations)} lựa chọn:")
    for i, item in enumerate(recommendations, start=1):
        name = item.get("name", "N/A")
        price = item.get("price_vnd")
        price_str = f"{int(price):,} VND".replace(",", ".") if isinstance(price, (int, float)) else "chưa niêm yết/giá liên hệ"
        why = item.get("why") or ""
        lines.append(f"{i}. {name} — Giá: {price_str}")
        if why:
            lines.append(f"   - {why}")

    lines.append("")
    lines.append("Nếu bạn muốn, hãy cho tôi biết bạn ưu tiên: nhẹ hơn hay mạnh hơn, và kích thước màn hình mong muốn.")
    return "\n".join(lines)
