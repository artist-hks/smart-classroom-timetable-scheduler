"""
Unit and Integration Tests for Genetic Algorithm (GA) Optimization Engine (SB3/US3).

Verifies:
- SB3/US3/T1: DEAP setup, population evolution, genetic operators, and soft constraint evaluation
              (SC-01 utilization, SC-02 workload balance, SC-03 gaps, SC-04 distribution, SC-10 stability).
- SB3/US3/T2: Reporting of GA optimization metrics (fitness improvement, gap reduction, workload variance).
- GA Safety Requirement: Zero hard-constraint violations (HC-01 to HC-16) across all evolved candidates.
- End-to-end 3-engine pipeline: CP-SAT -> Smart Resource Allocator -> GA Optimizer on PIET dataset.
"""

import pytest

from app.algorithms.cpsat_solver import CPSATScheduler, FacultySpec, ScheduledAssignment
from app.algorithms.ga_optimizer import (
    GAOptimizationConfig,
    GAOptimizationResult,
    SessionGene,
    TimetableGAOptimizer,
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
def test_resources():
    return [
        ResourceSpec(1, "CR-101", "Classroom 101", ResourceType.CLASSROOM, 70, department_id=1, building="Block-A", floor=1, equipment={"projector": 1}),
        ResourceSpec(2, "CR-102", "Classroom 102", ResourceType.CLASSROOM, 65, department_id=1, building="Block-A", floor=1, equipment={"smart board": 1}),
        ResourceSpec(3, "LAB-1", "Computing Lab 1", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=1, equipment={"pc": 30}),
        ResourceSpec(4, "LAB-2", "Computing Lab 2", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=1, equipment={"pc": 30}),
    ]


@pytest.fixture
def test_faculty():
    return {
        101: FacultySpec(101, "Dr. Sharma", max_weekly_hours=16.0),
        102: FacultySpec(102, "Prof. Verma", max_weekly_hours=16.0),
    }


def test_ga_sc01_utilization_evaluator(test_grid, test_resources):
    """SC-01: Verify classroom capacity utilization scoring."""
    optimizer = TimetableGAOptimizer(grid=test_grid, resources=test_resources)

    # 60 students in 70-cap room: 60/70 = 0.857
    genes = [
        SessionGene(
            session_idx=0, session_id=1, course_id=10, label="CS1", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=1, occupied_slot_ids=[1], day=1, resource_id=1,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        )
    ]
    util = optimizer.evaluate_sc01_utilization(genes)
    assert 0.85 < util < 0.86


def test_ga_sc02_faculty_workload_balance(test_grid, test_resources, test_faculty):
    """SC-02: Balanced daily workload across days should score higher than unbalanced."""
    optimizer = TimetableGAOptimizer(grid=test_grid, resources=test_resources, faculty_members=test_faculty)

    # Balanced: 1 lecture per day across Mon, Tue, Wed (1 hr each day)
    balanced_genes = [
        SessionGene(
            session_idx=0, session_id=1, course_id=10, label="CS1_L1", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=1, occupied_slot_ids=[1], day=1, resource_id=1,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        ),
        SessionGene(
            session_idx=1, session_id=2, course_id=10, label="CS1_L2", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=8, occupied_slot_ids=[8], day=2, resource_id=1,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        ),
        SessionGene(
            session_idx=2, session_id=3, course_id=10, label="CS1_L3", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=15, occupied_slot_ids=[15], day=3, resource_id=1,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        ),
    ]

    # Clumped: all 3 lectures on Day 1 (3 hrs Day 1, 0 hrs other days)
    clumped_genes = [
        SessionGene(
            session_idx=0, session_id=1, course_id=10, label="CS1_L1", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=1, occupied_slot_ids=[1], day=1, resource_id=1,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        ),
        SessionGene(
            session_idx=1, session_id=2, course_id=10, label="CS1_L2", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=2, occupied_slot_ids=[2], day=1, resource_id=1,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        ),
        SessionGene(
            session_idx=2, session_id=3, course_id=10, label="CS1_L3", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=3, occupied_slot_ids=[3], day=1, resource_id=1,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        ),
    ]

    score_bal, var_bal = optimizer.evaluate_sc02_workload_balance(balanced_genes)
    score_clump, var_clump = optimizer.evaluate_sc02_workload_balance(clumped_genes)

    assert var_bal < var_clump
    assert score_bal > score_clump


def test_ga_sc03_student_idle_gaps(test_grid, test_resources):
    """SC-03: Timetable with student free periods between classes has lower gap score."""
    optimizer = TimetableGAOptimizer(grid=test_grid, resources=test_resources)

    # Compact schedule: Period 1 and Period 2 (no gaps)
    compact_genes = [
        SessionGene(
            session_idx=0, session_id=1, course_id=10, label="CS1_L1", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=1, occupied_slot_ids=[1], day=1, resource_id=1,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        ),
        SessionGene(
            session_idx=1, session_id=2, course_id=11, label="CS2_L1", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=2, occupied_slot_ids=[2], day=1, resource_id=2,
            faculty_ids=[102], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        ),
    ]

    # Gapped schedule: Period 1 and Period 5 (Periods 2, 3 are empty idle gaps)
    gapped_genes = [
        SessionGene(
            session_idx=0, session_id=1, course_id=10, label="CS1_L1", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=1, occupied_slot_ids=[1], day=1, resource_id=1,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        ),
        SessionGene(
            session_idx=1, session_id=2, course_id=11, label="CS2_L1", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=5, occupied_slot_ids=[5], day=1, resource_id=2,
            faculty_ids=[102], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        ),
    ]

    score_comp, gaps_comp = optimizer.evaluate_sc03_student_gaps(compact_genes)
    score_gap, gaps_gap = optimizer.evaluate_sc03_student_gaps(gapped_genes)

    assert gaps_comp == 0
    assert gaps_gap > 0
    assert score_comp > score_gap


def test_ga_safety_requirement_zero_violations(test_grid, test_resources, test_faculty):
    """
    SRS Section 7.3: GA safety requirement.
    Any candidate with a hard-constraint violation (HC-01 to HC-16) must be penalized.
    """
    optimizer = TimetableGAOptimizer(grid=test_grid, resources=test_resources, faculty_members=test_faculty)

    # Valid gene
    valid_genes = [
        SessionGene(
            session_idx=0, session_id=1, course_id=10, label="CS1", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=1, occupied_slot_ids=[1], day=1, resource_id=1,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=60, required_resource_type=ResourceType.CLASSROOM,
        )
    ]
    assert optimizer.count_hard_constraint_violations(valid_genes) == 0

    # Violating gene: Room capacity breach (CR-102 has cap 65, required 90)
    invalid_genes = [
        SessionGene(
            session_idx=0, session_id=1, course_id=10, label="CS1", session_type=SessionType.LECTURE.value,
            duration_minutes=60, start_slot_id=1, occupied_slot_ids=[1], day=1, resource_id=2,
            faculty_ids=[101], participant_group_id=1, subbatch_ids=[1], department_id=1,
            required_capacity=90, required_resource_type=ResourceType.CLASSROOM,
        )
    ]
    assert optimizer.count_hard_constraint_violations(invalid_genes) == 1
    # Heavily penalized fitness
    assert optimizer.evaluate_fitness(invalid_genes)[0] < 0.20


def test_ga_optimization_metrics_reporting(test_grid, test_resources, test_faculty):
    """
    SB3/US3/T2: Verify that GAMetrics reports initial fitness, final fitness,
    improvement percentage, gap count, and workload variance.
    """
    config = GAOptimizationConfig(population_size=15, num_generations=10, random_seed=42)
    optimizer = TimetableGAOptimizer(grid=test_grid, resources=test_resources, faculty_members=test_faculty, config=config)

    allocations = [
        AllocatedSession(
            session_id=1, course_id=1, label="CS1_L1", session_type=SessionType.LECTURE.value,
            day=1, start_slot_id=1, start_time="09:00", end_time="10:00", duration_minutes=60,
            occupied_slot_ids=[1], faculty_ids=[101], participant_group_id=1, subbatch_ids=[1],
            department_id=1, required_resource_type=ResourceType.CLASSROOM, required_capacity=60,
            resource_id=1, resource_code="CR-101", resource_name="Classroom 101",
            resource_type=ResourceType.CLASSROOM, resource_capacity=70, resource_score=0.85,
        ),
        AllocatedSession(
            session_id=2, course_id=1, label="CS1_L2", session_type=SessionType.LECTURE.value,
            day=2, start_slot_id=8, start_time="09:00", end_time="10:00", duration_minutes=60,
            occupied_slot_ids=[8], faculty_ids=[101], participant_group_id=1, subbatch_ids=[1],
            department_id=1, required_resource_type=ResourceType.CLASSROOM, required_capacity=60,
            resource_id=1, resource_code="CR-101", resource_name="Classroom 101",
            resource_type=ResourceType.CLASSROOM, resource_capacity=70, resource_score=0.85,
        ),
    ]

    result = optimizer.optimize(allocations, max_time_seconds=5.0)

    assert result.is_optimized is True
    assert result.status_label == "OPTIMIZED"
    assert result.metrics is not None
    assert result.metrics.final_fitness >= result.metrics.initial_fitness  # Elitism guarantee
    assert result.metrics.hard_constraint_violations == 0
    assert result.metrics.wall_clock_time_seconds > 0
    assert len(result.optimized_allocations) == len(allocations)


def test_end_to_end_three_engine_pipeline():
    """
    Full 3-Engine Integration Test:
    1. CP-SAT Feasibility Engine (Engine 1)
    2. Smart Resource Allocation Engine (Engine 2)
    3. Genetic Algorithm Optimization Engine (Engine 3)
    Tested on the full semester PIET CSE dataset.
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

    # 1. Engine 1: CP-SAT Feasibility Engine
    cpsat_scheduler = CPSATScheduler(grid=grid, sessions=all_sessions, participant_groups=participant_groups, faculty_members=faculty_members)
    cpsat_res = cpsat_scheduler.solve(time_limit_seconds=15.0)
    assert cpsat_res.is_feasible is True

    # 2. Engine 2: Smart Resource Allocation
    piet_resources = [
        ResourceSpec(1, "CR-101", "Classroom 101", ResourceType.CLASSROOM, 70, department_id=1, building="Block-A", floor=1, equipment={"projector": 1}),
        ResourceSpec(2, "CR-102", "Classroom 102", ResourceType.CLASSROOM, 65, department_id=1, building="Block-A", floor=1, equipment={"smart board": 1}),
        ResourceSpec(3, "CR-103", "Classroom 103", ResourceType.CLASSROOM, 80, department_id=1, building="Block-A", floor=2),
        ResourceSpec(4, "LAB-1", "Computing Lab 1", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=1, equipment={"pc": 30}),
        ResourceSpec(5, "LAB-2", "Computing Lab 2", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=1, equipment={"pc": 30}),
        ResourceSpec(6, "LAB-3", "Computing Lab 3", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=2, equipment={"pc": 30}),
    ]
    allocator = SmartResourceAllocator(piet_resources)
    alloc_res = allocator.allocate_and_validate(cpsat_res.assignments)
    assert alloc_res.is_feasible is True
    assert alloc_res.validation_passed is True

    # 3. Engine 3: Genetic Algorithm (GA) Optimization Engine
    ga_config = GAOptimizationConfig(population_size=20, num_generations=15, random_seed=42)
    optimizer = TimetableGAOptimizer(grid=grid, resources=piet_resources, faculty_members=faculty_members, config=ga_config)
    ga_res = optimizer.optimize(alloc_res.allocations, max_time_seconds=10.0)

    # 4. Rigorous Assertions on GA Output
    assert ga_res.is_optimized is True
    assert ga_res.status_label == "OPTIMIZED"
    assert ga_res.metrics.hard_constraint_violations == 0
    assert ga_res.metrics.final_fitness >= ga_res.metrics.initial_fitness
    assert len(ga_res.optimized_allocations) == len(all_sessions)

    # Verify zero clashes in optimized timetable
    faculty_time: dict[tuple[int, int], str] = {}
    resource_time: dict[tuple[int, int], str] = {}
    for a in ga_res.optimized_allocations:
        for sid in a.occupied_slot_ids:
            # HC-01
            for fid in a.faculty_ids:
                key = (fid, sid)
                assert key not in faculty_time, f"HC-01 Faculty clash: {fid} at {sid}"
                faculty_time[key] = a.label
            # HC-02
            res_key = (a.resource_id, sid)
            assert res_key not in resource_time, f"HC-02 Resource clash: {a.resource_id} at {sid}"
            resource_time[res_key] = a.label
