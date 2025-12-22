from advisor.utils import normalize_user_types

INTENT_SCORE_MAP = {
    "gaming": ["gaming_score"],
    "ai": ["ai_graphics_score"],
    "business": ["office_score"],
    "study": ["office_score", "portability_score"],
    "student": ["office_score", "portability_score"],
    "general": ["general_score"]
}

def apply_scoring(df, query):
    df = df.copy()
    user_types = normalize_user_types(query)

    single_intent = "user_type" in query

    # =========================
    # TASK SCORE
    # =========================
    if single_intent:
        ut = user_types[0]
        cols = INTENT_SCORE_MAP.get(ut, ["general_score"])
        df["task_score"] = df[cols].mean(axis=1)
    else:
        # multi-intent → intersection
        cols = []
        for ut in user_types:
            cols.extend(INTENT_SCORE_MAP.get(ut, []))
        cols = list(set(cols))

        df["task_score"] = df[cols].min(axis=1)

    # =========================
    # PRICE FIT
    # =========================
    if "price_max" in query:
        budget = query["price_max"]
        ratio = df["Price (VND)"] / budget
        ideal = 0.8 if single_intent and user_types[0] == "gaming" else 0.75
        df["price_fit"] = (1 - abs(ratio - ideal)).clip(0, 1)
    else:
        df["price_fit"] = 0.5

    # =========================
    # FINAL SCORE
    # =========================
    if single_intent and user_types[0] == "gaming":
        df["final_score"] = df["task_score"]  # gaming thuần
    else:
        df["final_score"] = (
            df["task_score"] * 0.75 +
            df["price_fit"] * 0.25
        )

    df["final_score"] = df["final_score"].round(4)
    return df
