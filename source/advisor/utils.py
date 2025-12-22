def normalize_user_types(query):
    """
    STRICT intent semantics:
    - user_type: single intent (string)
    - user_types: multi intent (list, length >=2)
    """
    if "user_types" in query:
        uts = query["user_types"]
        if isinstance(uts, list):
            if len(uts) < 2:
                raise ValueError(
                    "user_types must contain >= 2 intents. "
                    "Use user_type for single intent."
                )
            return [u.lower() for u in uts if isinstance(u, str)]

    if "user_type" in query:
        ut = query["user_type"]
        if isinstance(ut, str):
            return [ut.lower()]

    return ["general"]
