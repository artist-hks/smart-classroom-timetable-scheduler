"""Pydantic schemas for Faculty CRUD & workload — SB2/US4/T1."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class AvailabilityWindow(BaseModel):
    day_of_week: int = Field(ge=1, le=7, description="1=Monday ... 7=Sunday")
    start_time: datetime.time
    end_time: datetime.time

    @model_validator(mode="after")
    def _times_in_order(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self

    model_config = {"from_attributes": True}


class FacultyCreate(BaseModel):
    department_id: int
    user_id: int | None = Field(default=None, description="Optional linked login account")
    employee_code: str = Field(min_length=1, max_length=30)
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    designation: str | None = Field(default=None, max_length=100)
    max_weekly_hours: float = Field(gt=0, le=60)
    is_active: bool = True
    course_ids: list[int] = Field(default_factory=list, description="Subjects this faculty can teach")
    availability: list[AvailabilityWindow] = Field(default_factory=list)


class FacultyUpdate(BaseModel):
    """department_id is not updatable. Use the /subjects and /availability
    endpoints to change those collections."""

    user_id: int | None = None
    employee_code: str | None = Field(default=None, min_length=1, max_length=30)
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    designation: str | None = Field(default=None, max_length=100)
    max_weekly_hours: float | None = Field(default=None, gt=0, le=60)
    is_active: bool | None = None


class FacultyOut(BaseModel):
    faculty_id: int
    department_id: int
    user_id: int | None
    employee_code: str
    full_name: str
    email: str
    designation: str | None
    max_weekly_hours: float
    is_active: bool
    course_ids: list[int]
    availability: list[AvailabilityWindow]
    created_at: datetime.datetime
    updated_at: datetime.datetime


class SubjectAssignment(BaseModel):
    course_ids: list[int]


class AvailabilityReplace(BaseModel):
    windows: list[AvailabilityWindow]


class WorkloadOut(BaseModel):
    faculty_id: int
    max_weekly_hours: float
    assigned_hours: float
    remaining_hours: float
    utilization_pct: float
    session_count: int
    over_limit: bool
