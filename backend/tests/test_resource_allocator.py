"""
Unit and Integration Tests for Smart Resource Allocation & Mandatory Validation Engine (SB3/US1, SB3/US2).

Verifies:
- SB3/US1/T1: Filter candidate resources by required type, capacity, availability (FR-3.8.1).
- SB3/US1/T2: Compute resource score and assign best match (FR-3.8.2, FR-3.8.3).
- SB3/US2/T1: Mandatory revalidation across capacity, type, availability, clashes (FR-3.8.4).
- SB3/US2/T2: Revalidation failure handling and infeasibility diagnostics (FR-3.8.5).
- End-to-end integration with CP-SAT Feasibility Engine output on realistic PIET dataset.
"""

import pytest

from app.algorithms.cpsat_solver import CPSATScheduler, FacultySpec, ScheduledAssignment
from app.algorithms.resource_allocator import (
    AllocatedSession,
    AllocationDiagnostic,
    ResourceAllocationResult,
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
def sample_resources():
    """Collection of realistic department and shared resources."""
    return [
        ResourceSpec(
            resource_id=1,
            code="CR-101",
            name="Classroom 101",
            resource_type=ResourceType.CLASSROOM,
            capacity=70,
            department_id=1,
            building="Block-A",
            floor=1,
            equipment={"projector": 1, "whiteboard": 1},
        ),
        ResourceSpec(
            resource_id=2,
            code="CR-102",
            name="Classroom 102",
            resource_type=ResourceType.CLASSROOM,
            capacity=65,
            department_id=1,
            building="Block-A",
            floor=1,
            equipment={"projector": 1, "smart board": 1},
        ),
        ResourceSpec(
            resource_id=3,
            code="CR-201",
            name="Classroom 201 (Small)",
            resource_type=ResourceType.CLASSROOM,
            capacity=35,
            department_id=1,
            building="Block-A",
            floor=2,
            equipment={"whiteboard": 1},
        ),
        ResourceSpec(
            resource_id=4,
            code="LAB-OOPS",
            name="OOPS Computing Lab",
            resource_type=ResourceType.LABORATORY,
            capacity=30,
            department_id=1,
            building="Block-B",
            floor=1,
            equipment={"pc": 30, "projector": 1},
        ),
        ResourceSpec(
            resource_id=5,
            code="LAB-OS",
            name="Operating Systems Lab",
            resource_type=ResourceType.LABORATORY,
            capacity=30,
            department_id=1,
            building="Block-B",
            floor=1,
            equipment={"pc": 30, "smart board": 1},
        ),
        ResourceSpec(
            resource_id=6,
            code="LAB-AI",
            name="AI/ML Specialization Lab",
            resource_type=ResourceType.LABORATORY,
            capacity=25,
            department_id=1,
            building="Block-B",
            floor=2,
            equipment={"pc": 25, "gpu": 10},
        ),
        ResourceSpec(
            resource_id=7,
            code="AUD-MAIN",
            name="Main Auditorium",
            resource_type=ResourceType.AUDITORIUM,
            capacity=300,
            department_id=None,  # Institute-wide shared resource
            building="Central Block",
            floor=1,
            equipment={"projector": 2, "audio system": 1},
        ),
        ResourceSpec(
            resource_id=8,
            code="CR-MECH",
            name="Mechanical Dept Classroom",
            resource_type=ResourceType.CLASSROOM,
            capacity=80,
            department_id=2,  # Other department
            building="Block-C",
            floor=1,
        ),
        ResourceSpec(
            resource_id=9,
            code="CR-MAINT",
            name="Classroom Under Maintenance",
            resource_type=ResourceType.CLASSROOM,
            capacity=70,
            department_id=1,
            is_active=False,  # Inactive / maintenance
        ),
    ]


def test_filter_candidate_resources_type_and_active(sample_resources):
    """
    SB3/US1/T1: Verify filtering excludes inactive resources and enforces
    exact resource type matching (FR-3.8.1, HC-08).
    """
    allocator = SmartResourceAllocator(sample_resources)

    # Session requiring LABORATORY
    lab_session = ScheduledAssignment(
        session_id=101,
        course_id=1,
        label="CS501_Lab_D1",
        session_type=SessionType.PRACTICAL.value,
        day=1,
        start_slot_id=2,
        start_time="10:00",
        end_time="12:00",
        duration_minutes=120,
        occupied_slot_ids=[2, 3],
        faculty_ids=[101],
        participant_group_id=11,
        subbatch_ids=[1],
        department_id=1,
        required_resource_type=ResourceType.LABORATORY,
        required_capacity=20,
    )

    candidates, _ = allocator.filter_candidate_resources(lab_session, current_bookings={})

    # Must only match active LABORATORY rooms in Dept 1 or Shared
    candidate_codes = {c.code for c in candidates}
    assert candidate_codes == {"LAB-OOPS", "LAB-OS", "LAB-AI"}
    assert "CR-101" not in candidate_codes  # Classroom excluded
    assert "AUD-MAIN" not in candidate_codes  # Auditorium excluded


def test_filter_candidate_resources_department_isolation(sample_resources):
    """
    SB3/US1/T1: Verify Department Isolation (HC-12).
    Dept 1 sessions cannot use Dept 2 rooms, but can use institute-wide shared rooms.
    """
    allocator = SmartResourceAllocator(sample_resources)

    session = ScheduledAssignment(
        session_id=102,
        course_id=2,
        label="CS501_Lecture",
        session_type=SessionType.LECTURE.value,
        day=1,
        start_slot_id=1,
        start_time="09:00",
        end_time="10:00",
        duration_minutes=60,
        occupied_slot_ids=[1],
        faculty_ids=[101],
        participant_group_id=10,
        subbatch_ids=[1, 2, 3],
        department_id=1,
        required_resource_type=ResourceType.CLASSROOM,
        required_capacity=60,
    )

    candidates, _ = allocator.filter_candidate_resources(session, current_bookings={})
    candidate_codes = {c.code for c in candidates}

    # CR-MECH belongs to Dept 2 -> Must be excluded
    assert "CR-MECH" not in candidate_codes
    # Inactive CR-MAINT -> Excluded
    assert "CR-MAINT" not in candidate_codes
    # CR-201 capacity 35 < 60 -> Excluded
    assert "CR-201" not in candidate_codes
    # CR-101 and CR-102 have capacity >= 60 and belong to Dept 1 -> Included
    assert "CR-101" in candidate_codes
    assert "CR-102" in candidate_codes


def test_filter_candidate_resources_equipment_sufficiency(sample_resources):
    """
    SB3/US1/T1: Verify equipment sufficiency filter (HC-09).
    """
    allocator = SmartResourceAllocator(sample_resources)

    session = ScheduledAssignment(
        session_id=103,
        course_id=3,
        label="CS502_AI_Practical",
        session_type=SessionType.PRACTICAL.value,
        day=2,
        start_slot_id=5,
        start_time="13:00",
        end_time="15:00",
        duration_minutes=120,
        occupied_slot_ids=[5, 6],
        faculty_ids=[102],
        participant_group_id=11,
        subbatch_ids=[1],
        department_id=1,
        required_resource_type=ResourceType.LABORATORY,
        required_capacity=20,
    )

    # Requires GPU equipment
    candidates, _ = allocator.filter_candidate_resources(
        session, current_bookings={}, required_equipment={"gpu": 4}
    )

    candidate_codes = {c.code for c in candidates}
    # Only LAB-AI has GPUs
    assert candidate_codes == {"LAB-AI"}


def test_candidate_scoring_capacity_fit(sample_resources):
    """
    SB3/US1/T2: Verify capacity fit scoring (FR-3.8.2, SC-01).
    A 65-seat classroom should score higher than a 300-seat auditorium for a 60-student class.
    """
    allocator = SmartResourceAllocator(sample_resources)

    session = ScheduledAssignment(
        session_id=104,
        course_id=1,
        label="CS501_Lecture",
        session_type=SessionType.LECTURE.value,
        day=1,
        start_slot_id=1,
        start_time="09:00",
        end_time="10:00",
        duration_minutes=60,
        occupied_slot_ids=[1],
        faculty_ids=[101],
        participant_group_id=10,
        subbatch_ids=[1, 2, 3],
        department_id=1,
        required_resource_type=None,  # flexible
        required_capacity=60,
    )

    cr102 = next(r for r in sample_resources if r.code == "CR-102")  # cap 65
    aud = next(r for r in sample_resources if r.code == "AUD-MAIN")   # cap 300

    score_cr102, bd_cr102 = allocator.compute_candidate_score(cr102, session)
    score_aud, bd_aud = allocator.compute_candidate_score(aud, session)

    # CR-102 utilization is 60/65 (~92%), AUD is 60/300 (20%)
    assert bd_cr102["capacity"] > bd_aud["capacity"]
    # Total score for well-fitted room should be significantly higher
    assert score_cr102 > score_aud


def test_candidate_scoring_resource_stability(sample_resources):
    """
    SB3/US1/T2: Verify Resource Stability (SC-10).
    A course previously assigned to CR-101 scores higher for CR-101 in subsequent sessions.
    """
    allocator = SmartResourceAllocator(sample_resources)

    session = ScheduledAssignment(
        session_id=105,
        course_id=1,
        label="CS501_Lecture_S2",
        session_type=SessionType.LECTURE.value,
        day=2,
        start_slot_id=2,
        start_time="10:00",
        end_time="11:00",
        duration_minutes=60,
        occupied_slot_ids=[2],
        faculty_ids=[101],
        participant_group_id=10,
        subbatch_ids=[1, 2, 3],
        department_id=1,
        required_resource_type=ResourceType.CLASSROOM,
        required_capacity=60,
    )

    cr101 = next(r for r in sample_resources if r.code == "CR-101")
    cr102 = next(r for r in sample_resources if r.code == "CR-102")

    # If course 1 was previously scheduled in CR-101 (resource_id 1)
    prior_allocs = {1: 1}

    _, bd_cr101 = allocator.compute_candidate_score(cr101, session, prior_course_allocations=prior_allocs)
    _, bd_cr102 = allocator.compute_candidate_score(cr102, session, prior_course_allocations=prior_allocs)

    assert bd_cr101["stability"] == 1.0
    assert bd_cr102["stability"] < 1.0


def test_mandatory_resource_validation_success(sample_resources):
    """
    SB3/US2/T1: Verify validation passes for conflict-free, constraint-compliant allocations (FR-3.8.4).
    """
    allocator = SmartResourceAllocator(sample_resources)

    allocations = [
        AllocatedSession(
            session_id=1,
            course_id=1,
            label="CS501_Lec_1",
            session_type=SessionType.LECTURE.value,
            day=1,
            start_slot_id=1,
            start_time="09:00",
            end_time="10:00",
            duration_minutes=60,
            occupied_slot_ids=[1],
            faculty_ids=[101],
            participant_group_id=10,
            subbatch_ids=[1, 2, 3],
            department_id=1,
            required_resource_type=ResourceType.CLASSROOM,
            required_capacity=60,
            resource_id=1,
            resource_code="CR-101",
            resource_name="Classroom 101",
            resource_type=ResourceType.CLASSROOM,
            resource_capacity=70,
            resource_score=0.92,
        ),
        AllocatedSession(
            session_id=2,
            course_id=2,
            label="CS502_Lab_D1",
            session_type=SessionType.PRACTICAL.value,
            day=1,
            start_slot_id=2,
            start_time="10:00",
            end_time="12:00",
            duration_minutes=120,
            occupied_slot_ids=[2, 3],
            faculty_ids=[102],
            participant_group_id=11,
            subbatch_ids=[1],
            department_id=1,
            required_resource_type=ResourceType.LABORATORY,
            required_capacity=20,
            resource_id=4,
            resource_code="LAB-OOPS",
            resource_name="OOPS Computing Lab",
            resource_type=ResourceType.LABORATORY,
            resource_capacity=30,
            resource_score=0.88,
        ),
    ]

    is_valid, errors = allocator.validate_allocation(allocations)
    assert is_valid is True
    assert len(errors) == 0


def test_mandatory_resource_validation_catches_clash(sample_resources):
    """
    SB3/US2/T1: Verify validation detects HC-02 (Resource Clash) when two sessions
    are assigned the same room at the same time slot.
    """
    allocator = SmartResourceAllocator(sample_resources)

    # Deliberate clash: both assigned to CR-101 (ID 1) at slot 1
    clashing_allocations = [
        AllocatedSession(
            session_id=1,
            course_id=1,
            label="CS501_Lec",
            session_type=SessionType.LECTURE.value,
            day=1,
            start_slot_id=1,
            start_time="09:00",
            end_time="10:00",
            duration_minutes=60,
            occupied_slot_ids=[1],
            faculty_ids=[101],
            participant_group_id=10,
            subbatch_ids=[1, 2, 3],
            department_id=1,
            required_resource_type=ResourceType.CLASSROOM,
            required_capacity=60,
            resource_id=1,
            resource_code="CR-101",
            resource_name="Classroom 101",
            resource_type=ResourceType.CLASSROOM,
            resource_capacity=70,
            resource_score=0.9,
        ),
        AllocatedSession(
            session_id=2,
            course_id=2,
            label="CS502_Lec",
            session_type=SessionType.LECTURE.value,
            day=1,
            start_slot_id=1,
            start_time="09:00",
            end_time="10:00",
            duration_minutes=60,
            occupied_slot_ids=[1],
            faculty_ids=[102],
            participant_group_id=20,
            subbatch_ids=[4, 5, 6],
            department_id=1,
            required_resource_type=ResourceType.CLASSROOM,
            required_capacity=60,
            resource_id=1,  # Same resource, same slot!
            resource_code="CR-101",
            resource_name="Classroom 101",
            resource_type=ResourceType.CLASSROOM,
            resource_capacity=70,
            resource_score=0.9,
        ),
    ]

    is_valid, errors = allocator.validate_allocation(clashing_allocations)
    assert is_valid is False
    assert any("HC-02 Violation" in err for err in errors)


def test_mandatory_resource_validation_catches_capacity_breach(sample_resources):
    """
    SB3/US2/T1: Verify validation detects HC-07/HC-16 when assigned room capacity
    is less than student strength.
    """
    allocator = SmartResourceAllocator(sample_resources)

    # CR-201 has capacity 35, session requires 60
    invalid_capacity_allocation = [
        AllocatedSession(
            session_id=1,
            course_id=1,
            label="CS501_Lec",
            session_type=SessionType.LECTURE.value,
            day=1,
            start_slot_id=1,
            start_time="09:00",
            end_time="10:00",
            duration_minutes=60,
            occupied_slot_ids=[1],
            faculty_ids=[101],
            participant_group_id=10,
            subbatch_ids=[1, 2, 3],
            department_id=1,
            required_resource_type=ResourceType.CLASSROOM,
            required_capacity=60,
            resource_id=3,
            resource_code="CR-201",
            resource_name="Classroom 201 (Small)",
            resource_type=ResourceType.CLASSROOM,
            resource_capacity=35,  # Breached!
            resource_score=0.5,
        ),
    ]

    is_valid, errors = allocator.validate_allocation(invalid_capacity_allocation)
    assert is_valid is False
    assert any("HC-07 Violation" in err for err in errors)


def test_revalidation_failure_handling_and_infeasibility_reporting():
    """
    SB3/US2/T2: Verify that when candidate resources are completely exhausted
    (e.g., only 1 lab exists but 2 parallel labs are scheduled at the same time),
    the allocator returns a clean INFEASIBLE result with detailed diagnostic reports (FR-3.8.5).
    """
    scarce_resources = [
        ResourceSpec(
            resource_id=10,
            code="ONLY-ONE-LAB",
            name="Single Computing Lab",
            resource_type=ResourceType.LABORATORY,
            capacity=30,
            department_id=1,
            is_active=True,
        )
    ]
    allocator = SmartResourceAllocator(scarce_resources)

    # 2 concurrent practical sessions at the exact same day and slots
    parallel_labs = [
        ScheduledAssignment(
            session_id=201,
            course_id=1,
            label="CS501_Lab_D1",
            session_type=SessionType.PRACTICAL.value,
            day=1,
            start_slot_id=1,
            start_time="09:00",
            end_time="11:00",
            duration_minutes=120,
            occupied_slot_ids=[1, 2],
            faculty_ids=[101],
            participant_group_id=11,
            subbatch_ids=[1],
            department_id=1,
            required_resource_type=ResourceType.LABORATORY,
            required_capacity=20,
        ),
        ScheduledAssignment(
            session_id=202,
            course_id=2,
            label="CS502_Lab_D2",
            session_type=SessionType.PRACTICAL.value,
            day=1,
            start_slot_id=1,
            start_time="09:00",
            end_time="11:00",
            duration_minutes=120,
            occupied_slot_ids=[1, 2],
            faculty_ids=[102],
            participant_group_id=12,
            subbatch_ids=[2],
            department_id=1,
            required_resource_type=ResourceType.LABORATORY,
            required_capacity=20,
        ),
    ]

    result = allocator.allocate_and_validate(parallel_labs)

    assert result.is_feasible is False
    assert "INFEASIBLE" in result.status_label
    assert result.total_allocated == 1
    assert len(result.unallocated) == 1
    unalloc = result.unallocated[0]
    assert unalloc.session_label == "CS502_Lab_D2"
    assert "No eligible resource available" in unalloc.reason


def test_end_to_end_piet_cpsat_to_resource_allocation():
    """
    End-to-End Pipeline Integration Test (Engine 1 -> Engine 2):
    1. CP-SAT solves the full PIET CSE 3rd Year semester dataset.
    2. Smart Resource Allocator assigns concrete classrooms and labs to all scheduled sessions.
    3. Mandatory Resource Validation verifies zero clashes and 100% constraint satisfaction.
    """
    grid = ScheduleGrid.create_standard_piet_grid(days=5, periods_per_day=7, period_duration_minutes=60, lunch_period_index=4)

    sec_d = ParticipantGroupResolver.resolve_section_group(1, "D", [(1, 20), (2, 20), (3, 20)], group_id=10)
    d1 = ParticipantGroupResolver.resolve_subbatch_group(1, 1, "D1", 20, group_id=11)
    d2 = ParticipantGroupResolver.resolve_subbatch_group(1, 2, "D2", 20, group_id=12)
    d3 = ParticipantGroupResolver.resolve_subbatch_group(1, 3, "D3", 20, group_id=13)

    participant_groups = {10: sec_d, 11: d1, 12: d2, 13: d3}
    section_groups = {"lecture": sec_d, "lab_D1": d1, "lab_D2": d2, "lab_D3": d3}

    faculty_members = {
        101: FacultySpec(faculty_id=101, name="Dr. A. Sharma", max_weekly_hours=16.0),
        102: FacultySpec(faculty_id=102, name="Prof. B. Verma", max_weekly_hours=16.0),
        103: FacultySpec(faculty_id=103, name="Dr. C. Gupta", max_weekly_hours=16.0),
        104: FacultySpec(faculty_id=104, name="Prof. D. Singh", max_weekly_hours=16.0),
        105: FacultySpec(faculty_id=105, name="Prof. E. Jain", max_weekly_hours=16.0),
        106: FacultySpec(faculty_id=106, name="Prof. F. Khan", max_weekly_hours=16.0),
    }

    courses_config = [
        {
            "id": 1, "code": "CS501_DBMS",
            "configs": [
                {"course_session_type_id": 1, "session_type": SessionType.LECTURE, "sessions_per_week": 3, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM},
                {"course_session_type_id": 2, "session_type": SessionType.PRACTICAL, "sessions_per_week": 1, "duration_minutes": 120, "required_resource_type": ResourceType.LABORATORY},
            ],
            "faculty": {"lecture": [101], "lab_D1": [101, 106], "lab_D2": [101, 106], "lab_D3": [101, 106]},
        },
        {
            "id": 2, "code": "CS502_OS",
            "configs": [
                {"course_session_type_id": 3, "session_type": SessionType.LECTURE, "sessions_per_week": 3, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM},
                {"course_session_type_id": 4, "session_type": SessionType.PRACTICAL, "sessions_per_week": 1, "duration_minutes": 120, "required_resource_type": ResourceType.LABORATORY},
            ],
            "faculty": {"lecture": [102], "lab_D1": [102], "lab_D2": [102], "lab_D3": [102]},
        },
        {
            "id": 3, "code": "CS503_TOC",
            "configs": [
                {"course_session_type_id": 5, "session_type": SessionType.LECTURE, "sessions_per_week": 4, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM},
            ],
            "faculty": {"lecture": [103]},
        },
        {
            "id": 4, "code": "CS504_CN",
            "configs": [
                {"course_session_type_id": 6, "session_type": SessionType.LECTURE, "sessions_per_week": 3, "duration_minutes": 60, "required_resource_type": ResourceType.CLASSROOM},
                {"course_session_type_id": 7, "session_type": SessionType.PRACTICAL, "sessions_per_week": 1, "duration_minutes": 120, "required_resource_type": ResourceType.LABORATORY},
            ],
            "faculty": {"lecture": [104], "lab_D1": [104], "lab_D2": [104], "lab_D3": [104]},
        },
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

    # 1. Run CP-SAT Solver (Engine 1)
    cpsat_scheduler = CPSATScheduler(
        grid=grid,
        sessions=all_sessions,
        participant_groups=participant_groups,
        faculty_members=faculty_members,
    )
    cpsat_res = cpsat_scheduler.solve(time_limit_seconds=15.0)
    assert cpsat_res.is_feasible is True
    assert len(cpsat_res.assignments) == len(all_sessions)

    # 2. Setup Resources for PIET CSE Department
    piet_resources = [
        ResourceSpec(1, "CR-101", "Classroom 101", ResourceType.CLASSROOM, 70, department_id=1, building="Block-A", floor=1, equipment={"projector": 1}),
        ResourceSpec(2, "CR-102", "Classroom 102", ResourceType.CLASSROOM, 65, department_id=1, building="Block-A", floor=1, equipment={"smart board": 1}),
        ResourceSpec(3, "CR-103", "Classroom 103", ResourceType.CLASSROOM, 80, department_id=1, building="Block-A", floor=2),
        ResourceSpec(4, "LAB-1", "Computing Lab 1", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=1, equipment={"pc": 30}),
        ResourceSpec(5, "LAB-2", "Computing Lab 2", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=1, equipment={"pc": 30}),
        ResourceSpec(6, "LAB-3", "Computing Lab 3", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=2, equipment={"pc": 30}),
    ]

    # 3. Run Smart Resource Allocation (Engine 2)
    allocator = SmartResourceAllocator(piet_resources)
    alloc_res = allocator.allocate_and_validate(cpsat_res.assignments)

    # 4. Verify Full Feasibility and Resource Validation
    assert alloc_res.is_feasible is True
    assert alloc_res.validation_passed is True
    assert alloc_res.status_label == "RESOURCE_VALIDATED"
    assert alloc_res.total_allocated == len(all_sessions)
    assert len(alloc_res.unallocated) == 0
    assert len(alloc_res.validation_errors) == 0

    # 5. Verify HC-02 (No Resource Clashes)
    booked_slots: dict[tuple[int, int], str] = {}
    for alloc in alloc_res.allocations:
        for slot_id in alloc.occupied_slot_ids:
            key = (alloc.resource_id, slot_id)
            assert key not in booked_slots, f"Resource clash: {alloc.resource_code} double-booked at slot {slot_id}"
            booked_slots[key] = alloc.label

    # 6. Verify HC-08 (Resource Suitability: Classrooms for Lectures, Labs for Practicals)
    for alloc in alloc_res.allocations:
        if alloc.session_type == SessionType.LECTURE.value:
            assert alloc.resource_type == ResourceType.CLASSROOM
            assert alloc.resource_capacity >= 60
        elif alloc.session_type == SessionType.PRACTICAL.value:
            assert alloc.resource_type == ResourceType.LABORATORY
            assert alloc.resource_capacity >= 20

    # 7. Check Metrics
    metrics = alloc_res.metrics
    assert metrics["average_utilization"] > 0.5
    assert metrics["rooms_used_count"] >= 3
    assert metrics["department_match_ratio"] == 1.0  # All department resources
