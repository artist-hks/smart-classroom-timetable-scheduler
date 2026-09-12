"""
End-to-End and Hard Constraint Verification Tests for Google OR-Tools CP-SAT Solver (SB2/US9).
"""

import pytest
from app.algorithms.cpsat_solver import CPSATScheduler, FacultySpec
from app.algorithms.session_generator import (
    CourseToSessionGenerator,
    ParticipantGroupResolver,
    ParticipantGroupSpec,
)
from app.algorithms.timeslot_grid import ScheduleGrid
from app.models.academic import ResourceType, SessionType


@pytest.fixture
def piet_grid():
    """5 days, 7 periods per day, Period 4 (12:00-13:00) is Lunch Break."""
    return ScheduleGrid.create_standard_piet_grid(
        days=5,
        periods_per_day=7,
        period_duration_minutes=60,
        lunch_period_index=4,
    )


@pytest.fixture
def piet_academic_setup():
    """
    Setup realistic PIET CSE 3rd Year (Semester 5) Section D data:
    - 60 students divided into Sub-batches D1 (20), D2 (20), D3 (20)
    - 5 Courses:
      1. DBMS (CS501): 3 Lectures (60m) + 1 Practical (120m) for each of D1, D2, D3
      2. OS (CS502): 3 Lectures (60m) + 1 Practical (120m) for each of D1, D2, D3
      3. TOC (CS503): 4 Lectures (60m)
      4. CN (CS504): 3 Lectures (60m) + 1 Practical (120m) for each of D1, D2, D3
      5. Web Tech (CS505): 3 Lectures (60m)
    - 6 Faculty members (ID 101 to 106)
    """
    sec_d = ParticipantGroupResolver.resolve_section_group(
        department_id=1, section_name="D", subbatches=[(1, 20), (2, 20), (3, 20)], group_id=10
    )
    d1 = ParticipantGroupResolver.resolve_subbatch_group(1, 1, "D1", 20, group_id=11)
    d2 = ParticipantGroupResolver.resolve_subbatch_group(1, 2, "D2", 20, group_id=12)
    d3 = ParticipantGroupResolver.resolve_subbatch_group(1, 3, "D3", 20, group_id=13)

    participant_groups = {
        10: sec_d,
        11: d1,
        12: d2,
        13: d3,
    }

    section_groups = {
        "lecture": sec_d,
        "lab_D1": d1,
        "lab_D2": d2,
        "lab_D3": d3,
    }

    faculty_members = {
        101: FacultySpec(faculty_id=101, name="Dr. A. Sharma (DBMS)", max_weekly_hours=16.0),
        102: FacultySpec(faculty_id=102, name="Prof. B. Verma (OS)", max_weekly_hours=16.0),
        103: FacultySpec(faculty_id=103, name="Dr. C. Gupta (TOC)", max_weekly_hours=16.0),
        104: FacultySpec(faculty_id=104, name="Prof. D. Singh (CN)", max_weekly_hours=16.0),
        105: FacultySpec(faculty_id=105, name="Prof. E. Jain (WebTech)", max_weekly_hours=16.0),
        106: FacultySpec(faculty_id=106, name="Prof. F. Khan (Lab Asst)", max_weekly_hours=16.0),
    }

    # Generate sessions for the 5 courses
    courses_config = [
        # DBMS
        {
            "id": 1, "code": "CS501_DBMS",
            "configs": [
                {"course_session_type_id": 1, "session_type": SessionType.LECTURE, "sessions_per_week": 3, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM},
                {"course_session_type_id": 2, "session_type": SessionType.PRACTICAL, "sessions_per_week": 1, "duration_minutes": 120, "required_resource_type": ResourceType.LABORATORY},
            ],
            "faculty": {"lecture": [101], "lab_D1": [101, 106], "lab_D2": [101, 106], "lab_D3": [101, 106]},
        },
        # OS
        {
            "id": 2, "code": "CS502_OS",
            "configs": [
                {"course_session_type_id": 3, "session_type": SessionType.LECTURE, "sessions_per_week": 3, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM},
                {"course_session_type_id": 4, "session_type": SessionType.PRACTICAL, "sessions_per_week": 1, "duration_minutes": 120, "required_resource_type": ResourceType.LABORATORY},
            ],
            "faculty": {"lecture": [102], "lab_D1": [102], "lab_D2": [102], "lab_D3": [102]},
        },
        # TOC
        {
            "id": 3, "code": "CS503_TOC",
            "configs": [
                {"course_session_type_id": 5, "session_type": SessionType.LECTURE, "sessions_per_week": 4, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM},
            ],
            "faculty": {"lecture": [103]},
        },
        # CN
        {
            "id": 4, "code": "CS504_CN",
            "configs": [
                {"course_session_type_id": 6, "session_type": SessionType.LECTURE, "sessions_per_week": 3, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM},
                {"course_session_type_id": 7, "session_type": SessionType.PRACTICAL, "sessions_per_week": 1, "duration_minutes": 120, "required_resource_type": ResourceType.LABORATORY},
            ],
            "faculty": {"lecture": [104], "lab_D1": [104], "lab_D2": [104], "lab_D3": [104]},
        },
        # Web Tech
        {
            "id": 5, "code": "CS505_WT",
            "configs": [
                {"course_session_type_id": 8, "session_type": SessionType.LECTURE, "sessions_per_week": 3, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM},
            ],
            "faculty": {"lecture": [105]},
        },
    ]

    all_sessions = []
    for c in courses_config:
        sessions = CourseToSessionGenerator.generate_sessions_for_course(
            course_id=c["id"],
            course_code=c["code"],
            department_id=1,
            configs=c["configs"],
            section_groups=section_groups,
            faculty_mapping=c["faculty"],
        )
        all_sessions.extend(sessions)

    return {
        "participant_groups": participant_groups,
        "faculty_members": faculty_members,
        "sessions": all_sessions,
    }


def test_cpsat_solver_feasible_piet_dataset(piet_grid, piet_academic_setup):
    """
    Test CP-SAT solver against a realistic full semester PIET dataset.
    Verifies all non-resource hard constraints:
    - HC-01 (Faculty clash)
    - HC-03 & HC-04 (Section & Sub-batch clash)
    - HC-11 (All sessions scheduled)
    - HC-14 (Continuous 2-hour lab periods)
    - HC-15 (Lunch break non-overlap)
    """
    scheduler = CPSATScheduler(
        grid=piet_grid,
        sessions=piet_academic_setup["sessions"],
        participant_groups=piet_academic_setup["participant_groups"],
        faculty_members=piet_academic_setup["faculty_members"],
    )

    result = scheduler.solve(time_limit_seconds=15.0)

    # 1. Feasibility check
    assert result.is_feasible is True
    assert result.status_label in ("FEASIBLE", "OPTIMAL")
    assert result.total_sessions_scheduled == len(piet_academic_setup["sessions"])
    assert result.solve_time_seconds < 2.0  # Must be fast (< 2.0s)

    # 2. Verify Constraint HC-01 (No Faculty Clash)
    # At any (day, period), each faculty member teaches at most 1 session
    faculty_time_map: dict[tuple[int, int, int], list[str]] = {}
    for a in result.assignments:
        for fid in a.faculty_ids:
            for slot_id in a.occupied_slot_ids:
                key = (fid, slot_id)
                assert key not in faculty_time_map, (
                    f"HC-01 Violation: Faculty {fid} scheduled in overlapping sessions: "
                    f"{faculty_time_map[key]} and {a.label} at slot {slot_id}"
                )
                faculty_time_map[key] = [a.label]

    # 3. Verify Constraint HC-03 & HC-04 (No Sub-batch / Section Clash)
    # At any (day, period), each sub-batch is in at most 1 session
    subbatch_time_map: dict[tuple[int, int], str] = {}
    for a in result.assignments:
        for sbid in a.subbatch_ids:
            for slot_id in a.occupied_slot_ids:
                key = (sbid, slot_id)
                assert key not in subbatch_time_map, (
                    f"HC-04 Violation: Sub-batch {sbid} scheduled in overlapping sessions: "
                    f"{subbatch_time_map[key]} and {a.label} at slot {slot_id}"
                )
                subbatch_time_map[key] = a.label

    # 4. Verify Constraint HC-15 (Lunch break non-overlap)
    lunch_slot_ids = {s.slot_id for s in piet_grid.slots if s.is_break}
    for a in result.assignments:
        for slot_id in a.occupied_slot_ids:
            assert slot_id not in lunch_slot_ids, (
                f"HC-15 Violation: Session {a.label} scheduled during lunch break slot {slot_id}"
            )

    # 5. Verify Constraint HC-14 (Multi-hour continuous 2h practicals)
    for a in result.assignments:
        if a.duration_minutes == 120:
            assert len(a.occupied_slot_ids) == 2
            s1, s2 = a.occupied_slot_ids[0], a.occupied_slot_ids[1]
            slot1 = piet_grid.slot_by_id[s1]
            slot2 = piet_grid.slot_by_id[s2]
            assert slot1.day == slot2.day
            assert slot2.period == slot1.period + 1


def test_cpsat_infeasibility_faculty_workload_exceeded(piet_grid, piet_academic_setup):
    """
    Test infeasibility diagnostic when faculty workload exceeds max limit (HC-10).
    """
    faculty_members = dict(piet_academic_setup["faculty_members"])
    # Set Dr. Sharma max workload to only 2 hours (while DBMS requires ~9 hours)
    faculty_members[101] = FacultySpec(faculty_id=101, name="Dr. A. Sharma", max_weekly_hours=2.0)

    scheduler = CPSATScheduler(
        grid=piet_grid,
        sessions=piet_academic_setup["sessions"],
        participant_groups=piet_academic_setup["participant_groups"],
        faculty_members=faculty_members,
    )

    result = scheduler.solve()
    assert result.is_feasible is False
    assert any("HC-10" in diag and "Dr. A. Sharma" in diag for diag in result.diagnostics)


def test_cpsat_infeasibility_faculty_availability(piet_grid, piet_academic_setup):
    """
    Test infeasibility diagnostic when faculty is unavailable for all slots (HC-05).
    """
    faculty_members = dict(piet_academic_setup["faculty_members"])
    # Block all slots for Dr. Sharma
    all_slot_ids = {s.slot_id for s in piet_grid.slots}
    faculty_members[101] = FacultySpec(
        faculty_id=101, name="Dr. A. Sharma", max_weekly_hours=16.0, unavailable_slot_ids=all_slot_ids
    )

    scheduler = CPSATScheduler(
        grid=piet_grid,
        sessions=piet_academic_setup["sessions"],
        participant_groups=piet_academic_setup["participant_groups"],
        faculty_members=faculty_members,
    )

    result = scheduler.solve()
    assert result.is_feasible is False
    assert any("HC-05" in diag for diag in result.diagnostics)
