import numpy as np

GPU_BONUS = {
    "DISCRETE_GAMING": 1.0,
    "DISCRETE_WORKSTATION": 0.95,
    "DISCRETE_LIGHT": 0.8,
    "APPLE": 0.75,
    "INTEGRATED_ARM": 0.6,
    "INTEGRATED": 0.5,
    "UNKNOWN": 0.4
}

def apply_scoring(df, query):
    df = df.copy()
    usage = query.get("usage_type", "general").lower()

    # =========================
    # GPU SCORE
    # =========================
    df["gpu_score"] = (
        df["gpu_class"]
        .map(GPU_BONUS)
        .fillna(0.4)
    )

    # =========================
    # PRICE SCORE
    # =========================
    if "price_max" in query:
        df["price_score"] = 1 - df["norm_price"]
    else:
        df["price_score"] = 0.1

    # =========================
    # FINAL SCORE
    # =========================
    if usage == "gaming":
        df["final_score"] = (
            df["base_performance_score"] * 0.55 +
            df["gpu_score"] * 0.35 +
            df["base_portability_score"] * 0.10
        )

    elif usage == "business":
        df["final_score"] = (
            df["base_performance_score"] * 0.35 +
            df["base_portability_score"] * 0.35 +
            df["gpu_score"] * 0.10 +
            df["price_score"] * 0.20
        )

    elif usage == "student":
        df["final_score"] = (
            df["base_performance_score"] * 0.30 +
            df["base_portability_score"] * 0.40 +
            df["price_score"] * 0.30
        )

    else:  # general / creator
        df["final_score"] = (
            df["base_performance_score"] * 0.45 +
            df["gpu_score"] * 0.20 +
            df["base_portability_score"] * 0.20 +
            df["price_score"] * 0.15
        )

    df["final_score"] = df["final_score"].round(3)
    return df
