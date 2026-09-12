"""
Scheduler Service Layer.

Provides high-level methods to:
1. Generate sessions from courses and configs
2. Run CP-SAT feasibility engine
3. Provide diagnostics and formatted schedule representation
"""

from __future__ import annotations

from typing import Any, Sequence

from app.algorithms.cpsat_solver import CPSATScheduler, CPSATSolverResult, FacultySpec
from app.algorithms.session_generator import (
    CourseToSessionGenerator,
    GeneratedSession,
    ParticipantGroupResolver,
    ParticipantGroupSpec,
)
from app.algorithms.timeslot_grid import GridSlot, ScheduleGrid
from app.models.academic import ResourceType, SessionType


class TimetableSchedulerService:
    """
    Service facade orchestrating Course-to-Session generation and CP-SAT solving.
    """

    @staticmethod
    def create_piet_standard_grid(
        days: int = 5,
        periods_per_day: int = 7,
        lunch_period_index: int = 4,
    ) -> ScheduleGrid:
        """Create standard PIET college weekly schedule grid."""
        return ScheduleGrid.create_standard_piet_grid(
            days=days,
            periods_per_day=periods_per_day,
            period_duration_minutes=60,
            lunch_period_index=lunch_period_index,
        )

    @staticmethod
    def generate_sessions(
        courses_data: list[dict[str, Any]],
        section_groups: dict[str, ParticipantGroupSpec],
        faculty_assignments: dict[str, dict[str, list[int]]],  # course_code -> {role: [fac_ids]}
    ) -> list[GeneratedSession]:
        """
        Generates all atomic sessions for a list of courses.
        """
        all_sessions: list[GeneratedSession] = []

        for cdata in courses_data:
            c_id = cdata["course_id"]
            code = cdata["code"]
            dept_id = cdata["department_id"]
            configs = cdata["configs"]
            fac_map = faculty_assignments.get(code, {})

            sessions = CourseToSessionGenerator.generate_sessions_for_course(
                course_id=c_id,
                course_code=code,
                department_id=dept_id,
                configs=configs,
                section_groups=section_groups,
                faculty_mapping=fac_map,
            )
            all_sessions.extend(sessions)

        return all_sessions

    @staticmethod
    def solve_timetable(
        grid: ScheduleGrid,
        sessions: list[GeneratedSession],
        participant_groups: dict[int, ParticipantGroupSpec],
        faculty_members: dict[int, FacultySpec],
        reserved_slot_ids: set[int] | None = None,
        time_limit_seconds: float = 15.0,
    ) -> CPSATSolverResult:
        """
        Runs the Google OR-Tools CP-SAT scheduler on generated sessions.
        """
        scheduler = CPSATScheduler(
            grid=grid,
            sessions=sessions,
            participant_groups=participant_groups,
            faculty_members=faculty_members,
            reserved_slot_ids=reserved_slot_ids,
        )
        return scheduler.solve(time_limit_seconds=time_limit_seconds)
