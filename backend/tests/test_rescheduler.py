"""
Unit and Integration Tests for Dynamic Rescheduling Engine (SB3/US6).

Verifies:
- SB3/US6/T1: Trigger detection and precise affected scoping (FR-3.9.1, FR-3.9.2).
- SB3/US6/T2: Subproblem isolation, preservation of unaffected assignments (EV-8 >= 85%),
              ranked alternative resolutions (time shift, substitute faculty, room swap, event replacement),
              and change-tracking audit logs (FR-3.9.3 - FR-3.9.7).
- Full end-to-end integration with CP-SAT + Smart Resource Allocator + GA timetable on PIET dataset.
"""

import pytest

from app.algorithms.cpsat_solver import CPSATScheduler, FacultySpec
from app.algorithms.ga_optimizer import GAOptimizationConfig, TimetableGAOptimizer
from app.algorithms.rescheduler import (
    DynamicRescheduler,
    RescheduleAuditEntry,
    RescheduleResolution,
    RescheduleTrigger,
    RescheduleTriggerType,
    ReschedulingResult,
)
from app.algorithms.resource_allocator import (
    AllocatedSession,
    ResourceSpec,
    SmartResourceAllocator,
)
from app.algorithms.session_generator import (
    CourseToSessionGenerator,
    ParticipantGroupResolver,
)
from app.algorithms.timeslot_grid import ScheduleGrid
from app.models.academic import ResourceType, SessionType


@pytest.fixture
def test_grid():
    return ScheduleGrid.create_standard_piet_grid(days=5, periods_per_day=7, period_duration_minutes=60, lunch_period_index=4)


@pytest.fixture
def sample_schedule():
    """Realistic timetable of 5 sessions across Monday & Tuesday."""
    return [
        AllocatedSession(
            session_id=1, course_id=101, label="CS_DBMS_L1", session_type=SessionType.LECTURE.value,
            day=1, start_slot_id=1, start_time="09:00", end_time="10:00", duration_minutes=60,
            occupied_slot_ids=[1], faculty_ids=[101], participant_group_id=10, subbatch_ids=[1, 2, 3],
            department_id=1, required_resource_type=ResourceType.CLASSROOM, required_capacity=60,
            resource_id=1, resource_code="CR-101", resource_name="Classroom 101",
            resource_type=ResourceType.CLASSROOM, resource_capacity=70, resource_score=0.9,
        ),
        AllocatedSession(
            session_id=2, course_id=102, label="CS_OS_Lab_D1", session_type=SessionType.PRACTICAL.value,
            day=1, start_slot_id=2, start_time="10:00", end_time="12:00", duration_minutes=120,
            occupied_slot_ids=[2, 3], faculty_ids=[102], participant_group_id=11, subbatch_ids=[1],
            department_id=1, required_resource_type=ResourceType.LABORATORY, required_capacity=20,
            resource_id=3, resource_code="LAB-1", resource_name="Lab 1",
            resource_type=ResourceType.LABORATORY, resource_capacity=30, resource_score=0.88,
        ),
        AllocatedSession(
            session_id=3, course_id=103, label="CS_CN_L1", session_type=SessionType.LECTURE.value,
            day=2, start_slot_id=8, start_time="09:00", end_time="10:00", duration_minutes=60,
            occupied_slot_ids=[8], faculty_ids=[101], participant_group_id=10, subbatch_ids=[1, 2, 3],
            department_id=1, required_resource_type=ResourceType.CLASSROOM, required_capacity=60,
            resource_id=1, resource_code="CR-101", resource_name="Classroom 101",
            resource_type=ResourceType.CLASSROOM, resource_capacity=70, resource_score=0.9,
        ),
        AllocatedSession(
            session_id=4, course_id=104, label="CS_WT_L1", session_type=SessionType.LECTURE.value,
            day=2, start_slot_id=9, start_time="10:00", end_time="11:00", duration_minutes=60,
            occupied_slot_ids=[9], faculty_ids=[104], participant_group_id=10, subbatch_ids=[1, 2, 3],
            department_id=1, required_resource_type=ResourceType.CLASSROOM, required_capacity=60,
            resource_id=2, resource_code="CR-102", resource_name="Classroom 102",
            resource_type=ResourceType.CLASSROOM, resource_capacity=65, resource_score=0.92,
        ),
    ]


@pytest.fixture
def sample_resources():
    return [
        ResourceSpec(1, "CR-101", "Classroom 101", ResourceType.CLASSROOM, 70, department_id=1, building="Block-A", floor=1),
        ResourceSpec(2, "CR-102", "Classroom 102", ResourceType.CLASSROOM, 65, department_id=1, building="Block-A", floor=1),
        ResourceSpec(3, "LAB-1", "Lab 1", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=1),
        ResourceSpec(4, "LAB-2", "Lab 2", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=1),
        ResourceSpec(5, "AUD-1", "Main Auditorium", ResourceType.AUDITORIUM, 300, department_id=None, building="Main Block", floor=1),
    ]


@pytest.fixture
def sample_faculty():
    return {
        101: FacultySpec(101, "Dr. Sharma", max_weekly_hours=16.0),
        102: FacultySpec(102, "Prof. Verma", max_weekly_hours=16.0),
        103: FacultySpec(103, "Dr. Gupta", max_weekly_hours=16.0),
        104: FacultySpec(104, "Prof. Singh", max_weekly_hours=16.0),
        105: FacultySpec(105, "Prof. Jain (Substitute)", max_weekly_hours=16.0),
    }


def test_affected_scoping_faculty_leave(test_grid, sample_schedule, sample_resources, sample_faculty):
    """
    SB3/US6/T1: Scopes impact strictly to sessions taught by on-leave faculty.
    Unrelated sessions and sub-batches remain preserved (FR-3.9.1, FR-3.9.2).
    """
    rescheduler = DynamicRescheduler(grid=test_grid, resources=sample_resources, faculty_members=sample_faculty)

    # Trigger: Faculty 101 takes leave on Day 2 during slot 8 (09:00 - 10:00)
    trigger = RescheduleTrigger(
        trigger_type=RescheduleTriggerType.FACULTY_UNAVAILABLE,
        day=2,
        slot_ids=[8],
        faculty_id=101,
        reason="Medical emergency",
    )

    scope = rescheduler.compute_affected_scope(sample_schedule, trigger)

    # Exactly 1 session affected: CS_CN_L1 (session_id=3)
    assert len(scope.affected_sessions) == 1
    assert scope.affected_sessions[0].label == "CS_CN_L1"

    # Other 3 sessions completely unaffected and preserved (75% preservation in 4-session toy schedule)
    assert len(scope.unaffected_sessions) == 3
    assert scope.preservation_percentage == 75.0
    assert 101 in scope.affected_faculty_ids


def test_affected_scoping_room_outage(test_grid, sample_schedule, sample_resources, sample_faculty):
    """
    SB3/US6/T1: Scopes impact strictly to sessions assigned to the outage room (FR-3.9.2).
    """
    rescheduler = DynamicRescheduler(grid=test_grid, resources=sample_resources, faculty_members=sample_faculty)

    # Trigger: LAB-1 (resource_id=3) under repair on Day 1 slots 2, 3
    trigger = RescheduleTrigger(
        trigger_type=RescheduleTriggerType.ROOM_UNAVAILABLE,
        day=1,
        slot_ids=[2, 3],
        resource_id=3,
        reason="Electrical repair",
    )

    scope = rescheduler.compute_affected_scope(sample_schedule, trigger)

    assert len(scope.affected_sessions) == 1
    assert scope.affected_sessions[0].label == "CS_OS_Lab_D1"
    assert scope.affected_sessions[0].resource_id == 3
    assert len(scope.unaffected_sessions) == 3


def test_reschedule_room_outage_reassignment(test_grid, sample_schedule, sample_resources, sample_faculty):
    """
    SB3/US6/T2: When a lab is down, rescheduler reassigns session to another available lab (LAB-2)
    without shifting time or faculty (FR-3.9.5, FR-3.9.6).
    """
    rescheduler = DynamicRescheduler(grid=test_grid, resources=sample_resources, faculty_members=sample_faculty)

    trigger = RescheduleTrigger(
        trigger_type=RescheduleTriggerType.ROOM_UNAVAILABLE,
        day=1,
        slot_ids=[2, 3],
        resource_id=3,  # LAB-1 down
        reason="A/C breakdown",
    )

    result = rescheduler.resolve_rescheduling(sample_schedule, trigger)

    assert result.is_successful is True
    assert result.status_label == "RESOLVED"
    assert result.best_resolution is not None
    assert result.best_resolution.strategy_type == "ROOM_CHANGE"

    # Verify reassigned room
    res_allocs = result.best_resolution.resolved_allocations
    lab_session = next(s for s in res_allocs if s.label == "CS_OS_Lab_D1")
    assert lab_session.resource_code == "LAB-2"  # Swapped to LAB-2
    assert lab_session.resource_id == 4
    assert lab_session.day == 1  # Day and time slot untouched!
    assert lab_session.start_slot_id == 2

    # Verify audit log entry
    assert len(result.best_resolution.audit_entries) == 1
    entry = result.best_resolution.audit_entries[0]
    assert entry.old_resource_code == "LAB-1"
    assert entry.new_resource_code == "LAB-2"


def test_reschedule_faculty_leave_substitution(test_grid, sample_schedule, sample_resources, sample_faculty):
    """
    SB3/US6/T2: When faculty is on leave, rescheduler assigns a qualified substitute
    from the substitute pool at the same time slot (FR-3.9.6).
    """
    # Course 103 (CS_CN_L1) can be taught by Faculty 105 (Prof. Jain)
    sub_pool = {103: [105]}
    rescheduler = DynamicRescheduler(
        grid=test_grid, resources=sample_resources, faculty_members=sample_faculty,
        substitute_faculty_pool=sub_pool,
    )

    trigger = RescheduleTrigger(
        trigger_type=RescheduleTriggerType.FACULTY_UNAVAILABLE,
        day=2,
        slot_ids=[8],
        faculty_id=101,  # Dr. Sharma on leave
        reason="Attending academic conference",
    )

    result = rescheduler.resolve_rescheduling(sample_schedule, trigger)

    assert result.is_successful is True
    assert result.best_resolution is not None
    assert result.best_resolution.strategy_type == "FACULTY_SUBSTITUTE"

    res_allocs = result.best_resolution.resolved_allocations
    cn_session = next(s for s in res_allocs if s.label == "CS_CN_L1")
    assert 105 in cn_session.faculty_ids  # Substitute assigned!
    assert 101 not in cn_session.faculty_ids
    assert cn_session.day == 2
    assert cn_session.start_slot_id == 8  # Time slot preserved!


def test_reschedule_academic_event_replacement(test_grid, sample_schedule, sample_resources, sample_faculty):
    """
    SB3/US6/T2 & FR-3.10: An Academic Event replaces regular sessions during event slots.
    """
    rescheduler = DynamicRescheduler(grid=test_grid, resources=sample_resources, faculty_members=sample_faculty)

    trigger = RescheduleTrigger(
        trigger_type=RescheduleTriggerType.ACADEMIC_EVENT,
        day=1,
        slot_ids=[1],
        resource_id=5,  # AUD-1
        event_details={"title": "Alumni Talk", "subbatch_ids": [1, 2, 3]},
        reason="Special alumni interactive session",
    )

    result = rescheduler.resolve_rescheduling(sample_schedule, trigger)

    assert result.is_successful is True
    res = next((r for r in result.ranked_resolutions if r.strategy_type == "EVENT_REPLACEMENT"), None)
    assert res is not None

    labels = [s.label for s in res.resolved_allocations]
    assert "EVENT_Alumni Talk" in labels
    assert "CS_DBMS_L1" not in labels  # Replaced


def test_end_to_end_piet_dynamic_rescheduling():
    """
    Full End-to-End Dynamic Rescheduling Pipeline:
    1. CP-SAT solves semester dataset.
    2. Smart Resource Allocator assigns rooms.
    3. GA optimizes soft constraints.
    4. A runtime disruption is triggered: Faculty 101 is unavailable on Tuesday (Day 2).
    5. Dynamic Rescheduler scopes affected sessions, preserves >95% of timetable,
       and provides ranked conflict-free alternatives.
    """
    grid = ScheduleGrid.create_standard_piet_grid(days=5, periods_per_day=7, period_duration_minutes=60, lunch_period_index=4)

    sec_d = ParticipantGroupResolver.resolve_section_group(1, "D", [(1, 20), (2, 20), (3, 20)], group_id=10)
    d1 = ParticipantGroupResolver.resolve_subbatch_group(1, 1, "D1", 20, group_id=11)
    d2 = ParticipantGroupResolver.resolve_subbatch_group(1, 2, "D2", 20, group_id=12)
    d3 = ParticipantGroupResolver.resolve_subbatch_group(1, 3, "D3", 20, group_id=13)

    participant_groups = {10: sec_d, 11: d1, 12: d2, 13: d3}
    section_groups = {"lecture": sec_d, "lab_D1": d1, "lab_D2": d2, "lab_D3": d3}

    faculty_members = {
        101: FacultySpec(101, "Dr. A. Sharma (DBMS)", max_weekly_hours=16.0),
        102: FacultySpec(102, "Prof. B. Verma (OS)", max_weekly_hours=16.0),
        103: FacultySpec(103, "Dr. C. Gupta (TOC)", max_weekly_hours=16.0),
        104: FacultySpec(104, "Prof. D. Singh (CN)", max_weekly_hours=16.0),
        105: FacultySpec(105, "Prof. E. Jain (WT)", max_weekly_hours=16.0),
        106: FacultySpec(106, "Prof. F. Khan (Substitute/Lab)", max_weekly_hours=16.0),
    }

    courses_config = [
        {"id": 1, "code": "CS501_DBMS", "configs": [{"course_session_type_id": 1, "session_type": SessionType.LECTURE, "sessions_per_week": 3, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM}], "faculty": {"lecture": [101]}},
        {"id": 2, "code": "CS502_OS", "configs": [{"course_session_type_id": 2, "session_type": SessionType.LECTURE, "sessions_per_week": 3, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM}], "faculty": {"lecture": [102]}},
        {"id": 3, "code": "CS503_TOC", "configs": [{"course_session_type_id": 3, "session_type": SessionType.LECTURE, "sessions_per_week": 4, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM}], "faculty": {"lecture": [103]}},
    ]

    all_sessions = []
    for c in courses_config:
        sessions = CourseToSessionGenerator.generate_sessions_for_course(
            course_id=c["id"], course_code=c["code"], department_id=1,
            configs=c["configs"], section_groups=section_groups, faculty_mapping=c["faculty"],
        )
        all_sessions.extend(sessions)

    # 1. CP-SAT Feasible Pass
    cpsat = CPSATScheduler(grid=grid, sessions=all_sessions, participant_groups=participant_groups, faculty_members=faculty_members)
    cpsat_res = cpsat.solve(time_limit_seconds=10.0)
    assert cpsat_res.is_feasible is True

    # 2. Smart Resource Allocation Pass
    piet_resources = [
        ResourceSpec(1, "CR-101", "Classroom 101", ResourceType.CLASSROOM, 70, department_id=1, building="Block-A", floor=1),
        ResourceSpec(2, "CR-102", "Classroom 102", ResourceType.CLASSROOM, 65, department_id=1, building="Block-A", floor=1),
    ]
    allocator = SmartResourceAllocator(piet_resources)
    alloc_res = allocator.allocate_and_validate(cpsat_res.assignments)
    assert alloc_res.is_feasible is True

    # 3. GA Optimization Pass
    ga_config = GAOptimizationConfig(population_size=10, num_generations=5, random_seed=42)
    optimizer = TimetableGAOptimizer(grid=grid, resources=piet_resources, faculty_members=faculty_members, config=ga_config)
    ga_res = optimizer.optimize(alloc_res.allocations, max_time_seconds=5.0)
    assert ga_res.is_optimized is True

    # 4. Find a Tuesday (Day 2) session taught by Dr. Sharma (101)
    target_session = next((s for s in ga_res.optimized_allocations if s.day == 2 and 101 in s.faculty_ids), None)
    if not target_session:
        target_session = next(s for s in ga_res.optimized_allocations if 101 in s.faculty_ids)

    # 5. Trigger: Dr. Sharma is on emergency leave at target_session time
    sub_pool = {1: [106]}  # Prof. Khan can substitute DBMS
    rescheduler = DynamicRescheduler(
        grid=grid, resources=piet_resources, faculty_members=faculty_members,
        substitute_faculty_pool=sub_pool,
    )

    trigger = RescheduleTrigger(
        trigger_type=RescheduleTriggerType.FACULTY_UNAVAILABLE,
        day=target_session.day,
        slot_ids=target_session.occupied_slot_ids,
        faculty_id=101,
        reason="Medical emergency",
    )

    reschedule_res = rescheduler.resolve_rescheduling(ga_res.optimized_allocations, trigger)

    assert reschedule_res.is_successful is True
    assert reschedule_res.status_label == "RESOLVED"
    # EV-8: Preservation stability must be >= 85%
    assert reschedule_res.scope.preservation_percentage >= 85.0
    assert len(reschedule_res.ranked_resolutions) >= 1

    # Verify zero conflicts in the resolved schedule
    best_allocs = reschedule_res.best_resolution.resolved_allocations
    faculty_time: dict[tuple[int, int], str] = {}
    resource_time: dict[tuple[int, int], str] = {}
    for a in best_allocs:
        for sid in a.occupied_slot_ids:
            for fid in a.faculty_ids:
                key = (fid, sid)
                assert key not in faculty_time, f"Clash detected for faculty {fid} at {sid}"
                faculty_time[key] = a.label
            res_key = (a.resource_id, sid)
            assert res_key not in resource_time, f"Clash detected for resource {a.resource_id} at {sid}"
            resource_time[res_key] = a.label
