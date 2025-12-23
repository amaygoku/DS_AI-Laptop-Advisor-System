from src.advisor.utils import normalize_user_types


def apply_filters(df, query):
    df = df.copy()

    # =========================
    # HARD CONSTRAINTS
    # =========================
    # PRICE
    if "price_min" in query:
        df = df[
            df["Price (VND)"].notna() &
            (df["Price (VND)"] >= query["price_min"])
        ]

    if "price_max" in query:
        df = df[
            df["Price (VND)"].notna() &
            (df["Price (VND)"] <= query["price_max"])
        ]

    # RAM: exact has priority over min
    if "ram_exact_gb" in query:
        df = df[df["RAM (GB)"] == query["ram_exact_gb"]]
    elif "min_ram_gb" in query:
        df = df[df["RAM (GB)"] >= query["min_ram_gb"]]

    # STORAGE
    if "min_storage_gb" in query:
        df = df[df["Storage (GB)"] >= query["min_storage_gb"]]

    # WEIGHT
    if "min_weight_kg" in query:
        df = df[df["Weight (kg)"] >= query["min_weight_kg"]]

    if "max_weight_kg" in query:
        df = df[df["Weight (kg)"] <= query["max_weight_kg"]]

    # =========================
    # INTENT-AWARE FILTER
    # =========================
    user_types = normalize_user_types(query)

    # gaming-only → bắt buộc gaming-ready
    if user_types == ["gaming"]:
        df = df[df["is_gaming_ready"]]

    return df
