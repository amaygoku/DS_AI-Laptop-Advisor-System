from advisor.utils import normalize_user_types

def apply_filters(df, query):
    df = df.copy()

    # =========================
    # HARD CONSTRAINTS
    # =========================
    if "price_max" in query:
        df = df[
            df["Price (VND)"].notna() &
            (df["Price (VND)"] <= query["price_max"])
        ]

    if "min_ram_gb" in query:
        df = df[df["RAM (GB)"] >= query["min_ram_gb"]]

    if "min_storage_gb" in query:
        df = df[df["Storage (GB)"] >= query["min_storage_gb"]]

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
