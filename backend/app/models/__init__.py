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
from app.models.faculty import Faculty, FacultyAvailability, FacultySubject  # noqa: F401
from app.models.resource import Resource, ResourceEquipment  # noqa: F401
from app.models.timeslot import Break, TimeSlot  # noqa: F401
