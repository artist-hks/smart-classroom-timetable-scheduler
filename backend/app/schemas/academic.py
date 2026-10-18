"""Pydantic schemas for the academic hierarchy CRUD APIs — SB2/US3/T1."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field, model_validator


# --- Department -------------------------------------------------------------
class DepartmentCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)


class DepartmentUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=150)


class DepartmentOut(BaseModel):
    department_id: int
    code: str
    name: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# --- Academic year ----------------------------------------------------------
class AcademicYearCreate(BaseModel):
    label: str = Field(min_length=1, max_length=20, examples=["2026-27"])
    start_date: datetime.date
    end_date: datetime.date
    is_active: bool = False

    @model_validator(mode="after")
    def _dates_in_order(self):
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class AcademicYearUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=20)
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    is_active: bool | None = None


class AcademicYearOut(BaseModel):
    academic_year_id: int
    label: str
    start_date: datetime.date
    end_date: datetime.date
    is_active: bool

    model_config = {"from_attributes": True}


# --- Semester ---------------------------------------------------------------
class SemesterCreate(BaseModel):
    semester_number: int = Field(ge=1, le=8)
    name: str = Field(min_length=1, max_length=30)


class SemesterUpdate(BaseModel):
    semester_number: int | None = Field(default=None, ge=1, le=8)
    name: str | None = Field(default=None, min_length=1, max_length=30)


class SemesterOut(BaseModel):
    semester_id: int
    semester_number: int
    name: str

    model_config = {"from_attributes": True}


# --- Section ----------------------------------------------------------------
class SectionCreate(BaseModel):
    department_id: int
    academic_year_id: int
    semester_id: int
    name: str = Field(min_length=1, max_length=50)
    student_strength: int = Field(gt=0)


class SectionUpdate(BaseModel):
    """department_id is intentionally not updatable (it is the isolation key)."""

    academic_year_id: int | None = None
    semester_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=50)
    student_strength: int | None = Field(default=None, gt=0)


class SectionOut(BaseModel):
    section_id: int
    department_id: int
    academic_year_id: int
    semester_id: int
    name: str
    student_strength: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# --- Sub-batch --------------------------------------------------------------
class SubBatchCreate(BaseModel):
    section_id: int
    name: str = Field(min_length=1, max_length=50)
    student_strength: int = Field(gt=0)
    practical_group_info: str | None = None


class SubBatchUpdate(BaseModel):
    """section_id is not updatable — create a new sub-batch under the other section instead."""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    student_strength: int | None = Field(default=None, gt=0)
    practical_group_info: str | None = None


class SubBatchOut(BaseModel):
    subbatch_id: int
    section_id: int
    name: str
    student_strength: int
    practical_group_info: str | None

    model_config = {"from_attributes": True}
