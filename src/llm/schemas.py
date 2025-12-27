# src/llm/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

UserType = Literal["business", "office", "study", "student", "gaming", "ai", "general"]

class Intent(BaseModel):
    user_type: Optional[UserType] = None
    user_types: Optional[List[UserType]] = None

    price_min: Optional[int] = Field(default=None, ge=0)
    price_max: Optional[int] = Field(default=None, ge=0)

    min_ram_gb: Optional[int] = Field(default=None, ge=0)
    ram_exact_gb: Optional[int] = Field(default=None, ge=0)

    min_storage_gb: Optional[int] = Field(default=None, ge=0)

    min_weight_kg: Optional[float] = Field(default=None, ge=0)
    max_weight_kg: Optional[float] = Field(default=None, ge=0)

    pref_light: Optional[bool] = None
    pref_cheap: Optional[bool] = None

    # DEFAULT = 3 (as requested)
    top_n: int = Field(default=3, ge=1, le=10)
