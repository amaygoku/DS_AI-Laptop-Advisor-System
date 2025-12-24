from src.advisor.utils import normalize_user_types

INTENT_SCORE_MAP = {
    "gaming": ["gaming_score"],
    "ai": ["ai_graphics_score"],
    "business": ["office_score"],
    "study": ["office_score", "portability_score"],
    "student": ["office_score", "portability_score"],
    "general": ["general_score"],
}

# base weights by intent
AFFORDABILITY_WEIGHT = {
    "student": 0.35,
    "study": 0.25,
    "business": 0.15,
    "general": 0.20,
    "ai": 0.10,
    "gaming": 0.05,
}

WEIGHT_PREF_WEIGHT = {
    "student": 0.20,
    "study": 0.25,
    "business": 0.15,
    "general": 0.15,
    "ai": 0.10,
    "gaming": 0.05,
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
        cols = [c for c in cols if c in df.columns]
        if not cols:
            cols = ["general_score"]
        df["task_score"] = df[cols].mean(axis=1)
    else:
        cols = []
        for ut in user_types:
            cols.extend(INTENT_SCORE_MAP.get(ut, []))
        cols = list(set(cols))
        cols = [c for c in cols if c in df.columns]
        if not cols:
            cols = ["general_score"]
        df["task_score"] = df[cols].min(axis=1)

    # =========================
    # PRICE / AFFORDABILITY
    # =========================
    if "price_max" in query:
        budget = query["price_max"]
        ratio = df["Price (VND)"] / budget
        ideal = 0.8 if single_intent and user_types[0] == "gaming" else 0.75
        df["price_fit"] = (1 - abs(ratio - ideal)).clip(0, 1)
        df["affordability_score"] = df["price_fit"]
    else:
        price = df["Price (VND)"]
        p10 = price.quantile(0.10)
        p90 = price.quantile(0.90)
        denom = (p90 - p10) if (p90 - p10) != 0 else 1.0
        price_norm = ((price - p10) / denom).clip(0, 1)
        df["affordability_score"] = (1 - price_norm).clip(0, 1)
        df["price_fit"] = 0.5

    # =========================
    # WEIGHT SCORE (from Weight (kg))
    # =========================
    w = df["Weight (kg)"]
    w10 = w.quantile(0.10)
    w90 = w.quantile(0.90)
    denom_w = (w90 - w10) if (w90 - w10) != 0 else 1.0
    w_norm = ((w - w10) / denom_w).clip(0, 1)
    df["weight_score"] = (1 - w_norm).clip(0, 1)  # nhẹ hơn => điểm cao

    # =========================
    # FINAL SCORE
    # =========================
    if single_intent and user_types[0] == "gaming":
        # gaming thuần: giữ đúng logic của bạn
        df["final_score"] = df["task_score"]
    else:
        # base weights by intent
        if single_intent:
            base_aff = AFFORDABILITY_WEIGHT.get(user_types[0], 0.20)
            base_wt = WEIGHT_PREF_WEIGHT.get(user_types[0], 0.15)
        else:
            base_aff = max(AFFORDABILITY_WEIGHT.get(ut, 0.20) for ut in user_types)
            base_wt = max(WEIGHT_PREF_WEIGHT.get(ut, 0.15) for ut in user_types)

        # ---- soft overrides from natural text prefs (added in recommend_from_text) ----
        if query.get("pref_cheap") is True:
            base_aff = max(base_aff, 0.35)

        if query.get("pref_light") is True:
            base_wt = max(base_wt, 0.25)
        elif query.get("pref_light") is False:
            base_wt = min(base_wt, 0.05)

        # cap weights
        w_aff = min(base_aff, 0.45)
        w_wt = min(base_wt, 0.35)
        w_task = max(0.0, 1.0 - w_aff - w_wt)

        df["final_score"] = (
            df["task_score"] * w_task
            + df["affordability_score"] * w_aff
            + df["weight_score"] * w_wt
        )

    df["final_score"] = df["final_score"].round(4)
    return df
