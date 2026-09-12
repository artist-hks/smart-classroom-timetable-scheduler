"""
Academic hierarchy models — SB2/US2/T2.

Implements exactly the schema designed in SB2/US2/T1
(docs/design/SB2_US2_T1_ERD_Design.md). Five referenced entities
(Faculty, Resource, TimeSlot, User/Role, Timetable family) are NOT
defined here — they belong to SB2/US4, SB2/US5, SB2/US6, SB2/US7 and
Sprint-III respectively. Columns that will eventually reference them
(`sessions.resource_id`, `session_faculty.faculty_id`) are created as
plain BIGINT columns without a DB-level FK constraint for now; the FK
constraint is added later, once the target table exists, in the
migration that creates that table (see migration docstring).
"""

from __future__ import annotations

import enum

import datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from app.db.base import Base


# ---------------------------------------------------------------------------
# Enums (native PostgreSQL ENUM types — see ERD design decision 11)
# ---------------------------------------------------------------------------
class SessionType(str, enum.Enum):
    LECTURE = "LECTURE"
    PRACTICAL = "PRACTICAL"
    TUTE_ASSIGNMENT = "TUTE_ASSIGNMENT"
    PROJECT = "PROJECT"
    SEMINAR = "SEMINAR"
    EVENT = "EVENT"


class ResourceType(str, enum.Enum):
    CLASSROOM = "CLASSROOM"
    LABORATORY = "LABORATORY"
    SEMINAR_HALL = "SEMINAR_HALL"
    AUDITORIUM = "AUDITORIUM"


class SessionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    FEASIBLE = "FEASIBLE"
    RESOURCE_ALLOCATED = "RESOURCE_ALLOCATED"
    VALIDATED = "VALIDATED"
    CANCELLED = "CANCELLED"
    REPLACED_BY_EVENT = "REPLACED_BY_EVENT"


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------
class Department(Base):
    __tablename__ = "departments"

    department_id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    sections: Mapped[list["Section"]] = relationship(back_populates="department")
    courses: Mapped[list["Course"]] = relationship(back_populates="department")


# ---------------------------------------------------------------------------
# AcademicYear
# ---------------------------------------------------------------------------
class AcademicYear(Base):
    __tablename__ = "academic_years"

    academic_year_id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    start_date: Mapped[Date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        server_default=expression.false(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("end_date > start_date", name="ck_academic_years_date_order"),
    )


# ---------------------------------------------------------------------------
# Semester (shared lookup — see ERD design decision 12)
# ---------------------------------------------------------------------------
class Semester(Base):
    __tablename__ = "semesters"

    semester_id: Mapped[int] = mapped_column(primary_key=True)
    semester_number: Mapped[int] = mapped_column(SmallInteger, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(30), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "semester_number BETWEEN 1 AND 8", name="ck_semesters_number_range"
        ),
    )


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------
class Section(Base):
    __tablename__ = "sections"

    section_id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.department_id"), nullable=False
    )
    academic_year_id: Mapped[int] = mapped_column(
        ForeignKey("academic_years.academic_year_id"), nullable=False
    )
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.semester_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    student_strength: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    department: Mapped["Department"] = relationship(back_populates="sections")
    sub_batches: Mapped[list["SubBatch"]] = relationship(back_populates="section")

    __table_args__ = (
        UniqueConstraint(
            "department_id",
            "academic_year_id",
            "semester_id",
            "name",
            name="uq_sections_dept_year_sem_name",
        ),
        CheckConstraint("student_strength > 0", name="ck_sections_strength_positive"),
    )


# ---------------------------------------------------------------------------
# SubBatch
# ---------------------------------------------------------------------------
class SubBatch(Base):
    __tablename__ = "sub_batches"

    subbatch_id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.section_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    student_strength: Mapped[int] = mapped_column(nullable=False)
    practical_group_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    section: Mapped["Section"] = relationship(back_populates="sub_batches")

    __table_args__ = (
        UniqueConstraint("section_id", "name", name="uq_subbatches_section_name"),
        CheckConstraint("student_strength > 0", name="ck_subbatches_strength_positive"),
        Index("ix_subbatches_section_id", "section_id"),
    )


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------
class Course(Base):
    __tablename__ = "courses"

    course_id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.department_id"), nullable=False
    )
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.semester_id"), nullable=False
    )
    required_weekly_hours: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)

    department: Mapped["Department"] = relationship(back_populates="courses")
    session_type_configs: Mapped[list["CourseSessionTypeConfig"]] = relationship(
        back_populates="course"
    )

    __table_args__ = (
        UniqueConstraint(
            "department_id", "semester_id", "code", name="uq_courses_dept_sem_code"
        ),
        CheckConstraint(
            "required_weekly_hours > 0", name="ck_courses_hours_positive"
        ),
    )


# ---------------------------------------------------------------------------
# CourseSessionTypeConfig
# ---------------------------------------------------------------------------
class CourseSessionTypeConfig(Base):
    __tablename__ = "course_session_type_configs"

    course_session_type_id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.course_id"), nullable=False
    )
    session_type: Mapped[SessionType] = mapped_column(
        SAEnum(SessionType, name="session_type_enum"), nullable=False
    )
    sessions_per_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    required_resource_type: Mapped[ResourceType | None] = mapped_column(
        SAEnum(ResourceType, name="resource_type_enum"), nullable=True
    )

    course: Mapped["Course"] = relationship(back_populates="session_type_configs")

    __table_args__ = (
        UniqueConstraint(
            "course_id", "session_type", name="uq_course_session_type_configs_course_type"
        ),
        CheckConstraint("sessions_per_week > 0", name="ck_cstc_sessions_per_week_positive"),
        CheckConstraint("duration_minutes > 0", name="ck_cstc_duration_positive"),
    )


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.course_id"), nullable=False
    )
    course_session_type_id: Mapped[int] = mapped_column(
        ForeignKey("course_session_type_configs.course_session_type_id"), nullable=False
    )
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.department_id"), nullable=False
    )
    session_type: Mapped[SessionType] = mapped_column(
        SAEnum(SessionType, name="session_type_enum"), nullable=False
    )
    duration_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    required_resource_type: Mapped[ResourceType | None] = mapped_column(
        SAEnum(ResourceType, name="resource_type_enum"), nullable=True
    )
    required_capacity: Mapped[int | None] = mapped_column(nullable=True)
    scheduled_day: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    start_time: Mapped[Time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[Time | None] = mapped_column(Time, nullable=True)
    # NOTE: no ForeignKey() here on purpose — `resources` table does not exist
    # yet (owned by SB2/US5/T2). Add the FK constraint in that migration via:
    #   op.create_foreign_key(..., 'sessions', 'resources', ['resource_id'], ['resource_id'])
    resource_id: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(SessionStatus, name="session_status_enum"),
        nullable=False,
        server_default=SessionStatus.DRAFT.value,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "scheduled_day IS NULL OR scheduled_day BETWEEN 1 AND 7",
            name="ck_sessions_day_range",
        ),
        Index("ix_sessions_dept_day_start", "department_id", "scheduled_day", "start_time"),
        Index("ix_sessions_course_session_type_id", "course_session_type_id"),
    )


# ---------------------------------------------------------------------------
# SessionFaculty (junction — Faculty table owned by SB2/US4/T2)
# ---------------------------------------------------------------------------
class SessionFaculty(Base):
    __tablename__ = "session_faculty"

    session_faculty_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    # NOTE: no ForeignKey() here on purpose — `faculty` table does not exist
    # yet (owned by SB2/US4/T2). Add the FK constraint in that migration.
    faculty_id: Mapped[int] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "faculty_id", name="uq_session_faculty_pair"),
        Index("ix_session_faculty_faculty_id", "faculty_id"),
    )


# ---------------------------------------------------------------------------
# ParticipantGroup
# ---------------------------------------------------------------------------
class ParticipantGroup(Base):
    __tablename__ = "participant_groups"

    participant_group_id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.department_id"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    combined_strength: Mapped[int] = mapped_column(nullable=False, server_default="0")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# ParticipantGroupMember (junction)
# ---------------------------------------------------------------------------
class ParticipantGroupMember(Base):
    __tablename__ = "participant_group_members"

    participant_group_member_id: Mapped[int] = mapped_column(primary_key=True)
    participant_group_id: Mapped[int] = mapped_column(
        ForeignKey("participant_groups.participant_group_id", ondelete="CASCADE"),
        nullable=False,
    )
    subbatch_id: Mapped[int] = mapped_column(
        ForeignKey("sub_batches.subbatch_id"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "participant_group_id", "subbatch_id", name="uq_pgm_group_subbatch"
        ),
        Index("ix_pgm_subbatch_id", "subbatch_id"),
    )


# ---------------------------------------------------------------------------
# SessionParticipantGroup (junction)
# ---------------------------------------------------------------------------
class SessionParticipantGroup(Base):
    __tablename__ = "session_participant_groups"

    session_participant_group_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    participant_group_id: Mapped[int] = mapped_column(
        ForeignKey("participant_groups.participant_group_id"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "session_id", "participant_group_id", name="uq_spg_session_group"
        ),
    )
