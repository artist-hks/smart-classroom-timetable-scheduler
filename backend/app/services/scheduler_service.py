"""
Scheduler Service Layer.

Provides high-level methods to:
1. Generate sessions from courses and configs
2. Run CP-SAT feasibility engine
3. Provide diagnostics and formatted schedule representation
"""

from __future__ import annotations

from typing import Any, Sequence

from app.algorithms.cpsat_solver import CPSATScheduler, CPSATSolverResult, FacultySpec, ScheduledAssignment
from app.algorithms.ga_optimizer import (
    GAOptimizationConfig,
    GAOptimizationResult,
    TimetableGAOptimizer,
)
from app.algorithms.ml_demand_predictor import (
    MLDemandDatasetGenerator,
    MLModelMetadata,
    RoomDemandPredictor,
)
from app.algorithms.rescheduler import (
    DynamicRescheduler,
    RescheduleTrigger,
    RescheduleTriggerType,
    ReschedulingResult,
)
from app.algorithms.resource_allocator import (
    AllocatedSession,
    ResourceAllocationResult,
    ResourceSpec,
    SmartResourceAllocator,
)
from app.algorithms.session_generator import (
    CourseToSessionGenerator,
    GeneratedSession,
    ParticipantGroupResolver,
    ParticipantGroupSpec,
)
from app.algorithms.timeslot_grid import GridSlot, ScheduleGrid
from app.models.academic import ResourceType, SessionType

DEFAULT_GRID_DAYS = 5
DEFAULT_PERIODS_PER_DAY = 7
DEFAULT_PERIOD_DURATION_MINUTES = 60
DEFAULT_LUNCH_PERIOD_INDEX = 4
DEFAULT_SOLVER_TIME_LIMIT_SECONDS = 15.0
DEFAULT_GA_TIME_LIMIT_SECONDS = 15.0
DEFAULT_DEMAND_DEPARTMENT_ID = 1
DEFAULT_DEMAND_SEMESTER = 5
DEFAULT_DEMAND_STRENGTH = 60


class TimetableSchedulerService:
    """
    Service facade orchestrating Course-to-Session generation and CP-SAT solving.
    """

    @staticmethod
    def create_piet_standard_grid(
        days: int = DEFAULT_GRID_DAYS,
        periods_per_day: int = DEFAULT_PERIODS_PER_DAY,
        lunch_period_index: int = DEFAULT_LUNCH_PERIOD_INDEX,
    ) -> ScheduleGrid:
        """Create standard PIET college weekly schedule grid."""
        return ScheduleGrid.create_standard_piet_grid(
            days=days,
            periods_per_day=periods_per_day,
            period_duration_minutes=DEFAULT_PERIOD_DURATION_MINUTES,
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
        time_limit_seconds: float = DEFAULT_SOLVER_TIME_LIMIT_SECONDS,
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

    @staticmethod
    def allocate_resources(
        assignments: Sequence[ScheduledAssignment],
        resources: Sequence[ResourceSpec],
        predicted_demand: dict[tuple[int, int, int], float] | None = None,
        session_equipment: dict[int, dict[str, int]] | None = None,
        preferred_building: str | None = None,
        weights: dict[str, float] | None = None,
        max_revalidation_attempts: int = 3,
    ) -> ResourceAllocationResult:
        """
        Runs Smart Resource Allocation & Mandatory Validation (Engine 2).
        Scores candidates and assigns conflict-free rooms matching capacity,
        type, equipment, and availability.
        """
        allocator = SmartResourceAllocator(
            resources=resources,
            predicted_demand=predicted_demand,
            weights=weights,
        )
        return allocator.allocate_and_validate(
            assignments=assignments,
            session_equipment=session_equipment,
            preferred_building=preferred_building,
            max_revalidation_attempts=max_revalidation_attempts,
        )

    @staticmethod
    def optimize_timetable(
        grid: ScheduleGrid,
        allocations: Sequence[AllocatedSession],
        resources: Sequence[ResourceSpec],
        faculty_members: dict[int, FacultySpec] | None = None,
        config: GAOptimizationConfig | None = None,
        max_time_seconds: float = DEFAULT_GA_TIME_LIMIT_SECONDS,
        participant_groups: dict[int, ParticipantGroupSpec] | None = None,
        reserved_slot_ids: set[int] | None = None,
    ) -> GAOptimizationResult:
        """
        Runs Genetic Algorithm (GA) Optimization (Engine 3).
        Evolves soft-constraint objectives (SC-01 to SC-11) while strictly preserving
        zero hard-constraint violations (HC-01 to HC-16).
        """
        optimizer = TimetableGAOptimizer(
            grid=grid,
            resources=resources,
            faculty_members=faculty_members,
            config=config,
            participant_groups=participant_groups,
            reserved_slot_ids=reserved_slot_ids,
        )
        return optimizer.optimize(allocations=allocations, max_time_seconds=max_time_seconds)

    @staticmethod
    def reschedule_timetable(
        grid: ScheduleGrid,
        current_schedule: Sequence[AllocatedSession],
        trigger: RescheduleTrigger,
        resources: Sequence[ResourceSpec],
        faculty_members: dict[int, FacultySpec],
        substitute_faculty_pool: dict[int, list[int]] | None = None,
        participant_groups: dict[int, ParticipantGroupSpec] | None = None,
        reserved_slot_ids: set[int] | None = None,
    ) -> ReschedulingResult:
        """
        Runs Dynamic Rescheduling Engine (Engine 4).
        Scopes impact to affected sub-batches/faculty/rooms, isolates the subproblem,
        preserves unaffected sessions (EV-8 >= 85%), and generates ranked alternative resolutions.
        """
        rescheduler = DynamicRescheduler(
            grid=grid,
            resources=resources,
            faculty_members=faculty_members,
            substitute_faculty_pool=substitute_faculty_pool,
            participant_groups=participant_groups,
            reserved_slot_ids=reserved_slot_ids,
        )
        return rescheduler.resolve_rescheduling(
            current_schedule=current_schedule,
            trigger=trigger,
        )

    @staticmethod
    def predict_room_demand_matrix(
        grid: ScheduleGrid,
        resources: Sequence[ResourceSpec],
        department_id: int = DEFAULT_DEMAND_DEPARTMENT_ID,
        semester: int = DEFAULT_DEMAND_SEMESTER,
        model_version: str = "v1.0.0-piet-simulated",
        X: Any | None = None,
        y: Any | None = None,
    ) -> tuple[dict[tuple[int, int, int], float], MLModelMetadata]:
        """
        Runs ML Room Demand Prediction Engine.
        Trains/evaluates the regression model (FR-3.7.1 - FR-3.7.3) and generates
        the (resource_id, day, slot_id) -> demand_score matrix for Smart Resource Allocation.
        """
        predictor = RoomDemandPredictor(model_version=model_version)
        metadata = predictor.train_and_evaluate(X=X, y=y)
        matrix = predictor.generate_demand_matrix(
            grid=grid,
            resources=resources,
            department_id=department_id,
            semester=semester,
            default_strength=DEFAULT_DEMAND_STRENGTH,
        )
        return matrix, metadata




