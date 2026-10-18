"""
Faculty models — SB2/US4/T1 (Faculty CRUD APIs & Workload Model).

Tables:
  faculty                — one row per teaching staff member, owned by a department.
  faculty_subjects       — which courses a faculty member is qualified/assigned to teach.
  faculty_availability   — weekly time windows in which the faculty member can be scheduled.

Workload model: `faculty.max_weekly_hours` is the configured ceiling (HC-10).
The *current* load is never stored — it is derived on demand from
`session_faculty` -> `sessions.duration_minutes` so it can't drift out of sync
with the timetable (see app/api/v1/faculty.py::compute_workload).
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Faculty(Base):
    __tablename__ = "faculty"

    faculty_id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.department_id"), nullable=False
    )
    # Optional link to a login account (users.role = FACULTY). A faculty row can
    # exist before the person has an account.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, unique=True
    )
    employee_code: Mapped[str] = mapped_column(String(30), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    max_weekly_hours: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    subjects: Mapped[list["FacultySubject"]] = relationship(
        back_populates="faculty", cascade="all, delete-orphan"
    )
    availability: Mapped[list["FacultyAvailability"]] = relationship(
        back_populates="faculty",
        cascade="all, delete-orphan",
        order_by="FacultyAvailability.day_of_week, FacultyAvailability.start_time",
    )

    __table_args__ = (
        UniqueConstraint("employee_code", name="uq_faculty_employee_code"),
        UniqueConstraint("email", name="uq_faculty_email"),
        CheckConstraint("max_weekly_hours > 0", name="ck_faculty_max_hours_positive"),
        Index("ix_faculty_department_id", "department_id"),
    )


class FacultySubject(Base):
    __tablename__ = "faculty_subjects"

    faculty_subject_id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.faculty_id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.course_id", ondelete="CASCADE"), nullable=False
    )

    faculty: Mapped["Faculty"] = relationship(back_populates="subjects")

    __table_args__ = (
        UniqueConstraint("faculty_id", "course_id", name="uq_faculty_subjects_pair"),
        Index("ix_faculty_subjects_course_id", "course_id"),
    )


class FacultyAvailability(Base):
    __tablename__ = "faculty_availability"

    availability_id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.faculty_id", ondelete="CASCADE"), nullable=False
    )
    # 1 = Monday ... 7 = Sunday (same convention as sessions.scheduled_day).
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)

    faculty: Mapped["Faculty"] = relationship(back_populates="availability")

    __table_args__ = (
        CheckConstraint(
            "day_of_week BETWEEN 1 AND 7", name="ck_faculty_availability_day_range"
        ),
        CheckConstraint(
            "end_time > start_time", name="ck_faculty_availability_time_order"
        ),
        Index("ix_faculty_availability_faculty_day", "faculty_id", "day_of_week"),
    )
