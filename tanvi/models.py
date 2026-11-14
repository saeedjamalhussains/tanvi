"""Input schema describing the organisation being planned for."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CONTROL_IDS = (
    "mfa", "edr", "offline_backups", "patch_management", "asset_inventory",
    "security_training", "incident_response_plan", "central_logging",
    "vulnerability_scanning", "least_privilege", "email_security",
    "data_encryption", "vendor_risk", "network_segmentation",
    "secure_sdlc", "security_owner",
)


class OrgProfile(BaseModel):
    org_name: str = Field("", max_length=120)
    industry: str = Field("general", max_length=60)
    employees: Literal["1-10", "11-50", "51-250", "251-1000", "1001-5000", "5000+"] = "51-250"
    regions: list[str] = Field(default_factory=list, max_length=20)
    data_types: list[str] = Field(default_factory=list, max_length=20)
    infrastructure: list[str] = Field(default_factory=list, max_length=20)
    compliance: list[str] = Field(default_factory=list, max_length=20)
    controls: dict[str, bool] = Field(default_factory=dict)
    budget: Literal["minimal", "moderate", "substantial"] = "moderate"
    security_staff: int = Field(0, ge=0, le=10000)
    timeframe_months: int = Field(12, ge=3, le=36)
    recent_incidents: str = Field("", max_length=2000)
    concerns: str = Field("", max_length=2000)
    goals: str = Field("", max_length=2000)

    def has(self, control_id: str) -> bool:
        return bool(self.controls.get(control_id))
