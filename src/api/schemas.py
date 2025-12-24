from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

AllowedIntent = Literal[
    "gaming", "study", "student", "business", "ai", "general"
]


class RecommendUserRequest(BaseModel):
    """
    Schema khi user CHỌN INTENT (không dùng LLM).
    """
    user_type: Optional[AllowedIntent] = None
    user_types: Optional[List[AllowedIntent]] = None

    price_max: Optional[int] = Field(default=None, ge=0)
    min_ram_gb: Optional[int] = Field(default=None, ge=0)
    min_storage_gb: Optional[int] = Field(default=None, ge=0)
    max_weight_kg: Optional[float] = Field(default=None, ge=0)

    notes: Optional[str] = None
    top_n: int = Field(default=5, ge=1, le=50)

    @field_validator("user_types")
    @classmethod
    def _user_types_len(cls, v):
        if v is None:
            return v
        uniq = list(dict.fromkeys(v))
        if len(uniq) < 2:
            raise ValueError(
                'user_types must contain >= 2 intents. '
                'Use "user_type" for single intent.'
            )
        return uniq

    @model_validator(mode="after")
    def _single_vs_multi(self):
        if self.user_type and self.user_types:
            raise ValueError(
                'Use ONLY one of "user_type" or "user_types".'
            )
        if not self.user_type and not self.user_types:
            self.user_type = "general"
        return self

    def to_query(self):
        d = self.model_dump(exclude_none=True)
        d.pop("top_n", None)
        return d
