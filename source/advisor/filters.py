def apply_filters(df, query):
    df = df.copy()

    # =========================
    # PRICE – hard constraint
    # =========================
    if "price_max" in query:
        df = df[
            df["Price (VND)"].notna() &
            (df["Price (VND)"] <= query["price_max"])
        ]

    # =========================
    # RAM
    # =========================
    if "min_ram_gb" in query:
        df = df[
            df["RAM (GB)"].isna() |
            (df["RAM (GB)"] >= query["min_ram_gb"])
        ]

    # =========================
    # STORAGE
    # =========================
    if "min_storage_gb" in query:
        df = df[
            df["Storage (GB)"].isna() |
            (df["Storage (GB)"] >= query["min_storage_gb"])
        ]

    # =========================
    # MANUFACTURER (fuzzy)
    # =========================
    if "manufacturer" in query:
        df = df[
            df["Manufacturer"]
            .str.lower()
            .str.contains(query["manufacturer"].lower(), na=False)
        ]

    # =========================
    # CPU MANUFACTURER
    # =========================
    if "cpu_manufacturer" in query:
        df = df[
            df["CPU manufacturer"]
            .str.lower()
            .str.contains(query["cpu_manufacturer"].lower(), na=False)
        ]

    # =========================
    # WEIGHT
    # =========================
    if "max_weight_kg" in query:
        df = df[
            df["Weight (kg)"].isna() |
            (df["Weight (kg)"] <= query["max_weight_kg"])
        ]

    # =========================
    # SCREEN SIZE
    # =========================
    if "min_screen_size_inch" in query:
        df = df[
            df["Screen Size (inch)"].isna() |
            (df["Screen Size (inch)"] >= query["min_screen_size_inch"])
        ]

    # =========================
    # REFRESH RATE
    # =========================
    if "min_refresh_rate_hz" in query:
        df = df[
            df["Refresh Rate (Hz)"].isna() |
            (df["Refresh Rate (Hz)"] >= query["min_refresh_rate_hz"])
        ]

    return df
