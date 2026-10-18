"""Pydantic schemas for TimeSlot & Break configuration — SB2/US6/T1."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field, model_validator


def _check_order(start: datetime.time | None, end: datetime.time | None) -> None:
    if start is not None and end is not None and end <= start:
        raise ValueError("end_time must be after start_time")


class TimeSlotCreate(BaseModel):
    day_of_week: int = Field(ge=1, le=7, description="1=Monday ... 7=Sunday")
    period: int = Field(ge=1)
    start_time: datetime.time
    end_time: datetime.time
    label: str | None = Field(default=None, max_length=50)
    is_active: bool = True

    @model_validator(mode="after")
    def _order(self):
        _check_order(self.start_time, self.end_time)
        return self


class TimeSlotUpdate(BaseModel):
    day_of_week: int | None = Field(default=None, ge=1, le=7)
    period: int | None = Field(default=None, ge=1)
    start_time: datetime.time | None = None
    end_time: datetime.time | None = None
    label: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None

    @model_validator(mode="after")
    def _order(self):
        _check_order(self.start_time, self.end_time)
        return self


class TimeSlotBulkCreate(BaseModel):
    slots: list[TimeSlotCreate] = Field(min_length=1, max_length=100)


class TimeSlotOut(BaseModel):
    time_slot_id: int
    day_of_week: int
    period: int
    start_time: datetime.time
    end_time: datetime.time
    label: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class BreakCreate(BaseModel):
    label: str = Field(min_length=1, max_length=50)
    day_of_week: int | None = Field(
        default=None, ge=1, le=7, description="NULL = applies on every day"
    )
    start_time: datetime.time
    end_time: datetime.time

    @model_validator(mode="after")
    def _order(self):
        _check_order(self.start_time, self.end_time)
        return self


class BreakUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=50)
    day_of_week: int | None = Field(default=None, ge=1, le=7)
    start_time: datetime.time | None = None
    end_time: datetime.time | None = None

    @model_validator(mode="after")
    def _order(self):
        _check_order(self.start_time, self.end_time)
        return self


class BreakOut(BaseModel):
    break_id: int
    label: str
    day_of_week: int | None
    start_time: datetime.time
    end_time: datetime.time

    model_config = {"from_attributes": True}
