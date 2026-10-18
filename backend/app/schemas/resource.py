"""Pydantic schemas for Resource CRUD — SB2/US5/T1."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field

from app.models.academic import ResourceType


class EquipmentItem(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    quantity: int = Field(default=1, ge=1)

    model_config = {"from_attributes": True}


class ResourceCreate(BaseModel):
    department_id: int | None = Field(
        default=None, description="NULL = institute-wide shared resource (SYSTEM_ADMIN only)"
    )
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=150)
    resource_type: ResourceType
    capacity: int = Field(gt=0)
    building: str | None = Field(default=None, max_length=100)
    floor: int | None = None
    is_active: bool = True
    equipment: list[EquipmentItem] = Field(default_factory=list)


class ResourceUpdate(BaseModel):
    """department_id is not updatable. `equipment`, when provided, REPLACES the full list."""

    code: str | None = Field(default=None, min_length=1, max_length=30)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    resource_type: ResourceType | None = None
    capacity: int | None = Field(default=None, gt=0)
    building: str | None = Field(default=None, max_length=100)
    floor: int | None = None
    is_active: bool | None = None
    equipment: list[EquipmentItem] | None = None


class ResourceOut(BaseModel):
    resource_id: int
    department_id: int | None
    code: str
    name: str
    resource_type: ResourceType
    capacity: int
    building: str | None
    floor: int | None
    is_active: bool
    equipment: list[EquipmentItem]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}
