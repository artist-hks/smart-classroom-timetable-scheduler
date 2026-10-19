"""Focused regression tests for guards and edge cases across scheduling engines."""

from __future__ import annotations

import numpy as np
import pytest

from app.algorithms.cpsat_solver import CPSATScheduler, FacultySpec, ScheduledAssignment
from app.algorithms.ga_optimizer import GAOptimizationConfig, SessionGene, TimetableGAOptimizer
from app.algorithms.ml_demand_predictor import RoomDemandPredictor
from app.algorithms.rescheduler import (
    AffectedScope,
    DynamicRescheduler,
    RescheduleTrigger,
    RescheduleTriggerType,
)
from app.algorithms.resource_allocator import (
    AllocatedSession,
    ResourceSpec,
    SmartResourceAllocator,
)
from app.algorithms.session_generator import (
    CourseToSessionGenerator,
    GeneratedSession,
    ParticipantGroupResolver,
    ParticipantGroupSpec,
)
from app.algorithms.timeslot_grid import ScheduleGrid
from app.models.academic import ResourceType, SessionType


@pytest.fixture
def grid() -> ScheduleGrid:
    return ScheduleGrid.create_standard_piet_grid(
        days=5, periods_per_day=7, period_duration_minutes=60, lunch_period_index=4
    )


@pytest.fixture
def group() -> ParticipantGroupSpec:
    return ParticipantGroupSpec(10, 1, "Section A", [1], 20)


@pytest.fixture
def faculty() -> dict[int, FacultySpec]:
    return {101: FacultySpec(101, "Faculty A", max_weekly_hours=16)}


@pytest.fixture
def resources() -> list[ResourceSpec]:
    return [
        ResourceSpec(1, "CR-1", "Classroom 1", ResourceType.CLASSROOM, 40, department_id=1),
        ResourceSpec(2, "CR-2", "Classroom 2", ResourceType.CLASSROOM, 40, department_id=1),
        ResourceSpec(3, "LAB-1", "Lab 1", ResourceType.LABORATORY, 30, department_id=1, equipment={"pc": 1}),
        ResourceSpec(5, "AUD-1", "Auditorium", ResourceType.AUDITORIUM, 300, department_id=None),
    ]


def _course_config(session_type: SessionType, *, duration: int = 60, count: int = 1) -> dict:
    return {
        "course_session_type_id": 1,
        "session_type": session_type,
        "sessions_per_week": count,
        "duration_minutes": duration,
    }


def _assignment(
    *,
    label: str = "S1",
    slot: int = 1,
    faculty_ids: list[int] | None = None,
    subbatch_ids: list[int] | None = None,
    resource_id: int = 1,
    required_equipment: dict[str, int] | None = None,
) -> ScheduledAssignment:
    return ScheduledAssignment(
        session_id=1,
        course_id=1,
        label=label,
        session_type=SessionType.LECTURE.value,
        day=((slot - 1) // 7) + 1,
        start_slot_id=slot,
        start_time="09:00",
        end_time="10:00",
        duration_minutes=60,
        occupied_slot_ids=[slot],
        faculty_ids=faculty_ids or [101],
        participant_group_id=10,
        subbatch_ids=subbatch_ids or [1],
        department_id=1,
        required_resource_type=ResourceType.LABORATORY if required_equipment else ResourceType.CLASSROOM,
        required_capacity=20,
        required_equipment=required_equipment or {},
    )


def _allocated(
    *,
    label: str = "S1",
    course_id: int = 1,
    slot: int = 1,
    faculty_ids: list[int] | None = None,
    subbatch_ids: list[int] | None = None,
    resource_id: int = 1,
    resource_code: str = "CR-1",
    session_type: str = SessionType.LECTURE.value,
    equipment: dict[str, int] | None = None,
) -> AllocatedSession:
    resource_type = ResourceType.LABORATORY if resource_id == 3 else (
        ResourceType.AUDITORIUM if resource_id == 5 else ResourceType.CLASSROOM
    )
    return AllocatedSession(
        session_id=slot,
        course_id=course_id,
        label=label,
        session_type=session_type,
        day=((slot - 1) // 7) + 1,
        start_slot_id=slot,
        start_time="09:00",
        end_time="10:00",
        duration_minutes=60,
        occupied_slot_ids=[slot],
        faculty_ids=faculty_ids or [101],
        participant_group_id=10,
        subbatch_ids=subbatch_ids or [1],
        department_id=1,
        required_resource_type=resource_type,
        required_capacity=20,
        resource_id=resource_id,
        resource_code=resource_code,
        resource_name=resource_code,
        resource_type=resource_type,
        resource_capacity=300 if resource_id == 5 else (30 if resource_id == 3 else 40),
        resource_score=0.8,
        required_equipment=equipment or {},
    )


def _gene(
    *,
    idx: int = 0,
    course_id: int = 1,
    slot: int = 1,
    resource_id: int = 1,
    subbatch_ids: list[int] | None = None,
    faculty_ids: list[int] | None = None,
) -> SessionGene:
    return SessionGene(
        session_idx=idx,
        session_id=idx + 1,
        course_id=course_id,
        label=f"S{idx + 1}",
        session_type=SessionType.LECTURE.value,
        duration_minutes=60,
        start_slot_id=slot,
        occupied_slot_ids=[slot],
        day=1,
        resource_id=resource_id,
        faculty_ids=faculty_ids or [101],
        participant_group_id=10,
        subbatch_ids=subbatch_ids or [1],
        department_id=1,
        required_capacity=20,
        required_resource_type=ResourceType.CLASSROOM,
    )


# Session generator guards

@pytest.mark.parametrize(
    ("duration", "count"),
    [( -1, 1), (60, -1)],
)
def test_session_generator_rejects_negative_duration_or_weekly_count(duration, count, group):
    with pytest.raises(ValueError):
        CourseToSessionGenerator.generate_sessions_for_course(
            1, "CS101", 1, [_course_config(SessionType.LECTURE, duration=duration, count=count)],
            {"lecture": group}, {"lecture": [101]},
        )


def test_session_generator_rejects_missing_participant_groups():
    with pytest.raises(ValueError, match="participant group"):
        CourseToSessionGenerator.generate_sessions_for_course(
            1, "CS101", 1, [_course_config(SessionType.LECTURE)], {}, {"lecture": [101]},
        )


@pytest.mark.parametrize("session_type", [SessionType.SEMINAR, SessionType.EVENT])
def test_seminar_and_event_default_to_seminar_hall(session_type, group):
    generated = CourseToSessionGenerator.generate_sessions_for_course(
        1, "CS101", 1, [_course_config(session_type)], {"main": group}, {"main": [101]},
    )
    assert generated[0].required_resource_type == ResourceType.SEMINAR_HALL


# CP-SAT edge cases

def test_cpsat_empty_sessions_returns_feasible(grid):
    result = CPSATScheduler(grid, [], {}, {}).solve()
    assert result.is_feasible is True
    assert result.status_label == "FEASIBLE"
    assert result.total_sessions_scheduled == 0


def test_cpsat_prechecks_report_unknown_participant_group_and_faculty(grid):
    session = GeneratedSession(
        session_id=1, course_id=1, course_session_type_id=1, department_id=1,
        session_type=SessionType.LECTURE, duration_minutes=60,
        required_resource_type=ResourceType.CLASSROOM, required_capacity=20,
        participant_group_id=999, faculty_ids=[404], label="Invalid references",
    )
    diagnostics = CPSATScheduler(grid, [session], {}, {}).run_prechecks()
    combined = "\n".join(diagnostics)
    assert "HC-13" in combined and "999" in combined
    assert "HC-01/05" in combined and "404" in combined


def test_cpsat_rejects_nonpositive_time_limit(grid, group, faculty):
    session = GeneratedSession(
        session_id=1, course_id=1, course_session_type_id=1, department_id=1,
        session_type=SessionType.LECTURE, duration_minutes=60,
        required_resource_type=ResourceType.CLASSROOM, required_capacity=20,
        participant_group_id=10, faculty_ids=[101], label="S1",
    )
    result = CPSATScheduler(grid, [session], {10: group}, faculty).solve(-1)
    assert result.is_feasible is False
    assert result.status_label == "INVALID_CONFIGURATION"


# Resource allocator edge cases

@pytest.mark.parametrize(
    "weights",
    [{"unknown": 1.0}, {"capacity": -1.0}, {key: 0.0 for key in SmartResourceAllocator.DEFAULT_WEIGHTS}],
)
def test_allocator_rejects_invalid_scoring_weights(resources, weights):
    with pytest.raises(ValueError):
        SmartResourceAllocator(resources, weights=weights)


def test_allocator_enforces_equipment_from_session_metadata(resources):
    assignment = _assignment(required_equipment={"pc": 2})
    result = SmartResourceAllocator([resources[2]]).allocate([assignment])
    assert result.is_feasible is False
    assert result.total_allocated == 0
    assert result.unallocated[0].candidate_count == 0


def test_allocator_rejects_negative_revalidation_attempts(resources):
    allocator = SmartResourceAllocator(resources)
    with pytest.raises(ValueError, match="non-negative"):
        allocator.allocate_and_validate([], max_revalidation_attempts=-1)


# GA edge cases and soft-constraint evaluators

def test_ga_empty_allocations_returns_success(grid, resources):
    result = TimetableGAOptimizer(grid, resources).optimize([])
    assert result.is_optimized is True
    assert result.status_label == "OPTIMIZED"
    assert result.optimized_allocations == []
    assert result.metrics is None


def test_ga_halts_on_existing_hard_constraint_clash(grid, resources, faculty):
    optimizer = TimetableGAOptimizer(grid, resources, faculty)
    allocations = [
        _allocated(label="S1", slot=1, faculty_ids=[101], subbatch_ids=[1], resource_id=1),
        _allocated(label="S2", slot=1, faculty_ids=[101], subbatch_ids=[2], resource_id=2),
    ]
    result = optimizer.optimize(allocations)
    assert result.status_label == "SAFETY_VIOLATION"
    assert result.is_optimized is False
    assert result.metrics is None  # No population or generations were run.


def test_ga_seed_produces_deterministic_schedule(grid, resources, faculty):
    allocations = [
        _allocated(label="S1", slot=1, faculty_ids=[101], subbatch_ids=[1], resource_id=1),
        _allocated(label="S2", slot=8, faculty_ids=[101], subbatch_ids=[2], resource_id=2),
    ]
    config = GAOptimizationConfig(population_size=8, num_generations=3, random_seed=123)
    results = [
        TimetableGAOptimizer(grid, resources, faculty, config).optimize(allocations, max_time_seconds=2)
        for _ in range(2)
    ]
    placements = [
        [(a.session_id, a.day, a.start_slot_id, a.resource_id) for a in result.optimized_allocations]
        for result in results
    ]
    assert placements[0] == placements[1]
    assert results[0].metrics.final_fitness == results[1].metrics.final_fitness


def test_ga_sc05_faculty_preference_expected_score(grid, resources):
    faculty = {101: FacultySpec(101, "Faculty A", preferred_slot_ids={1})}
    optimizer = TimetableGAOptimizer(grid, resources, faculty)
    assert optimizer.evaluate_sc05_faculty_preference([_gene(slot=1)]) == 1.0
    assert optimizer.evaluate_sc05_faculty_preference([_gene(slot=2)]) == 0.0


def test_ga_sc07_room_switching_expected_score(grid, resources):
    optimizer = TimetableGAOptimizer(grid, resources)
    same_room = [_gene(idx=0, resource_id=1), _gene(idx=1, resource_id=1, slot=2)]
    switched_room = [_gene(idx=0, resource_id=1), _gene(idx=1, resource_id=2, slot=2)]
    assert optimizer.evaluate_sc07_room_switching(same_room) == 1.0
    assert optimizer.evaluate_sc07_room_switching(switched_room) == 0.0


def test_ga_sc11_grouping_efficiency_expected_score(grid, resources):
    optimizer = TimetableGAOptimizer(grid, resources)
    genes = [_gene(idx=0, subbatch_ids=[1, 2]), _gene(idx=1, subbatch_ids=[3], slot=2)]
    assert optimizer.evaluate_sc11_grouping_efficiency(genes) == pytest.approx(0.75)


# Dynamic rescheduler edge cases

@pytest.mark.parametrize("room_id", [99, 5])
def test_event_replacement_missing_or_inactive_room_returns_none(grid, resources, faculty, room_id):
    if room_id == 5:
        resources[3].is_active = False
    rescheduler = DynamicRescheduler(grid, resources, faculty)
    trigger = RescheduleTrigger(
        RescheduleTriggerType.ACADEMIC_EVENT, day=1, slot_ids=[1], resource_id=room_id,
        event_details={"title": "Guest Talk", "subbatch_ids": [1]},
    )
    scope = rescheduler.compute_affected_scope([_allocated()], trigger)
    assert rescheduler._try_event_replacement_strategy(scope) is None


def test_time_shift_prioritizes_faculty_preferred_slots(grid, resources, faculty):
    faculty[101].preferred_slot_ids = {8}
    rescheduler = DynamicRescheduler(grid, resources, faculty)
    old = _allocated()
    trigger = RescheduleTrigger(RescheduleTriggerType.FACULTY_UNAVAILABLE, day=1, slot_ids=[1], faculty_id=101)
    scope = rescheduler.compute_affected_scope([old], trigger)
    resolution = rescheduler._try_time_slot_shift_strategy(scope, {}, {}, {})
    assert resolution is not None
    assert resolution.resolved_allocations[-1].start_slot_id == 8


def test_session_cancellation_has_explicit_resolution(grid, resources, faculty, group):
    schedule = [_allocated()]
    rescheduler = DynamicRescheduler(grid, resources, faculty, {10: group})
    trigger = RescheduleTrigger(RescheduleTriggerType.SESSION_CANCELLATION, day=1, slot_ids=[1])
    result = rescheduler.resolve_rescheduling(schedule, trigger)
    cancellation = next(r for r in result.ranked_resolutions if r.strategy_type == "SESSION_CANCELLATION")
    assert result.is_successful is True
    assert cancellation.resolved_allocations == []
    assert cancellation.changed_sessions_count == 1


# ML validation and persistence edge cases

@pytest.mark.parametrize(
    ("X", "y", "test_size"),
    [
        (np.ones((4, 10)), np.ones(3), 0.2),
        (np.full((4, 10), np.nan), np.ones(4), 0.2),
        (np.ones((4, 10)), np.array([1.0, 1.0, np.inf, 1.0]), 0.2),
        (np.ones((4, 10)), np.ones(4), 0.0),
        (np.ones((4, 10)), np.ones(4), 1.0),
    ],
)
def test_ml_training_rejects_invalid_data(X, y, test_size):
    predictor = RoomDemandPredictor()
    with pytest.raises(ValueError):
        predictor.train_and_evaluate(X=X, y=y, test_size=test_size)


def test_ml_load_model_missing_path_raises(tmp_path):
    predictor = RoomDemandPredictor()
    with pytest.raises(FileNotFoundError):
        predictor.load_model(str(tmp_path / "missing-model.pkl"))
