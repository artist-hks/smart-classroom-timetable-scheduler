"""
Import every model module here so Alembic's env.py (which imports
app.models) registers all tables on Base.metadata for autogenerate.
"""

from app.models.academic import (  # noqa: F401
    AcademicYear,
    Course,
    CourseSessionTypeConfig,
    Department,
    ParticipantGroup,
    ParticipantGroupMember,
    Section,
    Semester,
    Session,
    SessionFaculty,
    SessionParticipantGroup,
    SubBatch,
)

from app.models.auth import User, UserRole  # noqa: F401
