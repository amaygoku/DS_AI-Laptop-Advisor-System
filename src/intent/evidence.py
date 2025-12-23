from __future__ import annotations
import re
from typing import Dict, List

INTENT_EVIDENCE: Dict[str, List[str]] = {
    "gaming": [r"\bgaming\b", r"chơi game", r"\bgame\b", r"esport", r"valorant", r"\blol\b", r"cs2", r"pubg"],
    "ai": [r"\bai\b", r"render", r"đồ hoạ", r"đồ họa", r"3d\b", r"blender", r"premiere", r"after effects", r"photoshop"],
    "business": [r"văn phòng", r"office", r"kinh doanh"],
    "study": [r"học", r"học tập", r"học it", r"lập trình", r"\bcode\b", r"coding"],
    "student": [r"sinh viên", r"\bsv\b", r"học sinh", r"hoc sinh"],
    "general": [r".*"],  # always ok
}

def has_evidence(user_text: str, intent: str) -> bool:
    text = (user_text or "").strip().lower()
    pats = INTENT_EVIDENCE.get(intent, [])
    return any(re.search(p, text, flags=re.IGNORECASE) for p in pats)

def enforce_intent_evidence(user_text: str, intent_payload: dict) -> dict:
    """
    If model outputs an intent that is not evidenced by user_text, downgrade to general.
    """
    out = dict(intent_payload)

    # Multi-intent: keep only evidenced intents; if <2 -> convert to single/general
    if "user_types" in out and isinstance(out["user_types"], list):
        kept = [i for i in out["user_types"] if has_evidence(user_text, i)]
        kept = list(dict.fromkeys(kept))
        if len(kept) >= 2:
            out["user_types"] = kept
            out.pop("user_type", None)
            return out
        if len(kept) == 1:
            out["user_type"] = kept[0]
            out.pop("user_types", None)
            return out
        out.pop("user_types", None)
        out["user_type"] = "general"
        return out

    # Single intent:
    ut = out.get("user_type")
    if isinstance(ut, str) and ut != "general":
        if not has_evidence(user_text, ut):
            out["user_type"] = "general"
    return out
