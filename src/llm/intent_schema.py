from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, field_validator, model_validator

AllowedIntent = Literal["gaming", "study", "student", "business", "ai", "general"]

class LLMIntent(BaseModel):
    user_type: Optional[AllowedIntent] = None
    user_types: Optional[List[AllowedIntent]] = None
    notes: Optional[str] = None

    @field_validator("user_types")
    @classmethod
    def _min_len_and_unique(cls, v):
        if v is None:
            return v
        seen = set()
        uniq = []
        for x in v:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        if len(uniq) < 2:
            raise ValueError('user_types must contain >= 2 intents. Use "user_type" for single intent.')
        return uniq

    @model_validator(mode="after")
    def _single_vs_multi(self):
        if self.user_type and self.user_types:
            raise ValueError('Use ONLY one of "user_type" or "user_types".')
        if not self.user_type and not self.user_types:
            self.user_type = "general"
        return self
