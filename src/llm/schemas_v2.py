# src/llm/schemas_v2.py
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict

UserType = Literal["business", "office", "study", "student", "gaming", "ai", "general"]

Resolution = Literal["HD", "FHD", "QHD", "UHD", "4K"]
Port = Literal["LAN", "HDMI", "USB-A", "USB-C", "Thunderbolt", "SD", "AudioJack"]

class CPUIntelReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_family: Optional[Literal["i3", "i5", "i7", "i9"]] = None
    min_gen: Optional[int] = Field(default=None, ge=1)

class CPUAmdReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_family: Optional[Literal["ryzen 3", "ryzen 5", "ryzen 7", "ryzen 9"]] = None
    min_series: Optional[int] = Field(default=None, ge=1000)

class CPURequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # You can keep this as a hint category; optional
    min_tier: Optional[Literal["basic", "balanced", "strong_cpu", "strong_gpu"]] = None
    intel: Optional[CPUIntelReq] = None
    amd: Optional[CPUAmdReq] = None

class DisplayRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    screen_size_inch: Optional[float] = Field(default=None, gt=0)
    screen_size_tolerance: Optional[float] = Field(default=None, ge=0)
    resolution_min: Optional[Resolution] = None
    min_refresh_hz: Optional[int] = Field(default=None, ge=30)

class BatteryRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_wh: Optional[float] = Field(default=None, gt=0)

class PortsRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    must_have: Optional[List[Port]] = None

class BrandPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prefer: Optional[List[str]] = None     # normalized lowercase brand names
    exclude: Optional[List[str]] = None

class IntentV2(BaseModel):
    """
    Intent for the recommender. Omit unknown fields; never use null.
    """
    model_config = ConfigDict(extra="forbid")

    # intents
    user_type: Optional[UserType] = None
    user_types: Optional[List[UserType]] = None
    use_case_notes: Optional[str] = None

    # budget + ranking
    price_min: Optional[int] = Field(default=None, ge=0)
    price_max: Optional[int] = Field(default=None, ge=0)
    top_n: int = Field(default=3, ge=1, le=10)

    # base specs
    min_ram_gb: Optional[int] = Field(default=None, ge=0)
    ram_exact_gb: Optional[int] = Field(default=None, ge=0)
    min_storage_gb: Optional[int] = Field(default=None, ge=0)
    max_weight_kg: Optional[float] = Field(default=None, gt=0)
    min_weight_kg: Optional[float] = Field(default=None, gt=0)
    min_cpu_gen: Optional[int] = Field(default=None, ge=1)
    cpu_brand: Optional[str] = None  # e.g., "i5", "ryzen 7"
    cpu_manufacturer: Optional[str] = None  # e.g., "Intel", "AMD"


    # advanced constraints
    cpu_requirements: Optional[CPURequirements] = None
    display_requirements: Optional[DisplayRequirements] = None
    battery_requirements: Optional[BatteryRequirements] = None
    ports_requirements: Optional[PortsRequirements] = None
    brand_preferences: Optional[BrandPreferences] = None

    # preferences
    pref_light: Optional[bool] = None
    pref_cheap: Optional[bool] = None
    pref_battery: Optional[bool] = None
    gaming_level: Optional[Literal["light", "medium", "hardcore"]] = None