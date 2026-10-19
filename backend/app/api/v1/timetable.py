"""
Timetable generation — SB3/US5/T1.

    POST /api/v1/timetable/generate

Runs the full scheduling pipeline through ``TimetableSchedulerService`` for one
department / academic year / semester and saves the result:

    DB inputs -> sessions -> CP-SAT (Engine 1) -> [ML demand] -> resource
    allocation (Engine 2) -> [GA optimisation (Engine 3)] -> persist

Only a *feasible, resource-validated* timetable is written. An infeasible run
returns ``is_feasible=false`` with diagnostics and leaves the database untouched.

Persistence rules
-----------------
* Rows go into ``sessions`` (+ ``session_faculty`` / ``session_participant_groups``)
  with status ``RESOURCE_ALLOCATED``; the approval step (a later task) promotes them
  to ``VALIDATED``.
* Re-running replaces the previous (not yet approved) timetable of the same
  department + semester in the same transaction. If any session of that scope is
  already ``VALIDATED`` the request is rejected with 409 instead of overwriting it.
* Access: SYSTEM_ADMIN, or COORDINATOR for their own department (NFR-3).
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import selectinload

from app.algorithms.cpsat_solver import FacultySpec
from app.algorithms.ga_optimizer import GAOptimizationConfig
from app.algorithms.resource_allocator import AllocatedSession, ResourceSpec, SmartResourceAllocator
from app.algorithms.session_generator import (
    GeneratedSession,
    ParticipantGroupResolver,
    ParticipantGroupSpec,
)
from app.algorithms.timeslot_grid import GridSlot, ScheduleGrid
from app.api.deps import enforce_department_scope
from app.api.v1.common import admin_or_coordinator, commit_or_409, require_exists
from app.db.session import get_db
from app.models.academic import (
    AcademicYear,
    Course,
    Department,
    ParticipantGroup,
    ParticipantGroupMember,
    Section,
    Semester,
    Session,
    SessionFaculty,
    SessionParticipantGroup,
    SessionStatus,
    SessionType,
)
from app.models.auth import User
from app.models.faculty import Faculty, FacultyAvailability, FacultySubject
from app.models.resource import Resource
from app.models.timeslot import Break, TimeSlot
from app.schemas.scheduler import (
    AllocatedSessionResponse,
    GenerateTimetableRequest,
    TimetableGenerationResponse,
)
from app.services.scheduler_service import TimetableSchedulerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/timetable", tags=["timetable"])


# ---------------------------------------------------------------------------
# Loaded inputs (plain data only, so the DB connection can be released while
# the solver runs for up to two minutes)
# ---------------------------------------------------------------------------
@dataclass
class _Inputs:
    grid: ScheduleGrid
    sessions: list[GeneratedSession]
    groups: dict[int, ParticipantGroupSpec]  # temporary id -> spec
    faculty: dict[int, FacultySpec]
    resources: list[ResourceSpec]
    course_codes: dict[int, str]
    course_ids: list[int]
    diagnostics: list[str] = field(default_factory=list)


def _hhmm(t: datetime.time) -> str:
    return f"{t:%H:%M}"


def _minutes(t: datetime.time) -> int:
    return t.hour * 60 + t.minute


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _build_grid(db: DBSession) -> ScheduleGrid:
    """Grid from the configured time slots + breaks; standard PIET grid if none exist."""
    slots = db.scalars(
        select(TimeSlot)
        .where(TimeSlot.is_active.is_(True))
        .order_by(TimeSlot.day_of_week, TimeSlot.period)
    ).all()
    if not slots:
        return TimetableSchedulerService.create_piet_standard_grid()

    breaks = db.scalars(select(Break)).all()
    grid_slots: list[GridSlot] = []
    for s in slots:
        on_break = any(
            (b.day_of_week is None or b.day_of_week == s.day_of_week)
            and s.start_time < b.end_time
            and b.start_time < s.end_time
            for b in breaks
        )
        grid_slots.append(
            GridSlot(
                slot_id=s.time_slot_id,
                day=s.day_of_week,
                period=s.period,
                start_time=_hhmm(s.start_time),
                end_time=_hhmm(s.end_time),
                duration_minutes=_minutes(s.end_time) - _minutes(s.start_time),
                is_break=on_break,
                label=s.label or f"Period {s.period}",
            )
        )
    return ScheduleGrid(grid_slots)


def _unavailable_slots(grid: ScheduleGrid, windows: list[FacultyAvailability]) -> set[int]:
    """A faculty member with availability windows can only teach inside them.
    No windows at all means "no restriction"."""
    if not windows:
        return set()
    blocked: set[int] = set()
    for slot in grid.slots:
        if slot.is_break:
            continue
        start = datetime.time.fromisoformat(slot.start_time)
        end = datetime.time.fromisoformat(slot.end_time)
        inside = any(
            w.day_of_week == slot.day and w.start_time <= start and end <= w.end_time
            for w in windows
        )
        if not inside:
            blocked.add(slot.slot_id)
    return blocked


def _load_inputs(db: DBSession, req: GenerateTimetableRequest) -> tuple[_Inputs, int]:
    """Read everything the pipeline needs. Returns (inputs, semester_number)."""
    require_exists(db, AcademicYear, req.academic_year_id, "Academic year")
    require_exists(db, Department, req.department_id, "Department")
    semester = db.scalars(select(Semester).where(Semester.semester_number == req.semester)).first()
    if semester is None:
        raise HTTPException(422, detail=f"Semester {req.semester} does not exist")

    sections = db.scalars(
        select(Section)
        .options(selectinload(Section.sub_batches))
        .where(
            Section.department_id == req.department_id,
            Section.academic_year_id == req.academic_year_id,
            Section.semester_id == semester.semester_id,
        )
        .order_by(Section.name)
    ).all()
    if not sections:
        raise HTTPException(422, detail="No sections exist for this department, academic year and semester")

    courses = db.scalars(
        select(Course)
        .options(selectinload(Course.session_type_configs))
        .where(Course.department_id == req.department_id, Course.semester_id == semester.semester_id)
        .order_by(Course.code)
    ).all()
    if not courses:
        raise HTTPException(422, detail="No courses exist for this department and semester")
    course_ids = [c.course_id for c in courses]

    approved = db.scalar(
        select(Session.session_id)
        .where(
            Session.department_id == req.department_id,
            Session.course_id.in_(course_ids),
            Session.status == SessionStatus.VALIDATED,
        )
        .limit(1)
    )
    if approved is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="An approved timetable already exists for this department and semester",
        )

    diagnostics: list[str] = []
    grid = _build_grid(db)

    # ---- faculty qualified for each course (active only; may be cross-department)
    qualified: dict[int, list[Faculty]] = {}
    for course_id, fac in db.execute(
        select(FacultySubject.course_id, Faculty)
        .join(Faculty, Faculty.faculty_id == FacultySubject.faculty_id)
        .where(FacultySubject.course_id.in_(course_ids), Faculty.is_active.is_(True))
        .order_by(Faculty.faculty_id)
    ).all():
        qualified.setdefault(course_id, []).append(fac)
    faculty_rows = {f.faculty_id: f for facs in qualified.values() for f in facs}
    windows: dict[int, list[FacultyAvailability]] = {}
    if faculty_rows:
        for w in db.scalars(
            select(FacultyAvailability).where(FacultyAvailability.faculty_id.in_(faculty_rows))
        ):
            windows.setdefault(w.faculty_id, []).append(w)
    faculty_specs = {
        fid: FacultySpec(
            faculty_id=fid,
            name=f.full_name,
            max_weekly_hours=float(f.max_weekly_hours),
            unavailable_slot_ids=_unavailable_slots(grid, windows.get(fid, [])),
        )
        for fid, f in faculty_rows.items()
    }

    # ---- resources: this department's rooms + institute-wide shared ones
    resources = [
        ResourceSpec.from_db(r)
        for r in db.scalars(
            select(Resource)
            .options(selectinload(Resource.equipment))
            .where(
                Resource.is_active.is_(True),
                (Resource.department_id == req.department_id) | Resource.department_id.is_(None),
            )
            .order_by(Resource.resource_id)
        )
    ]

    # ---- participant groups (temporary ids; real rows are created on success)
    groups: dict[int, ParticipantGroupSpec] = {}
    group_by_members: dict[frozenset[int], int] = {}

    def register(spec: ParticipantGroupSpec) -> ParticipantGroupSpec:
        key = frozenset(spec.subbatch_ids)
        if key not in group_by_members:
            temp_id = len(groups) + 1
            spec.participant_group_id = temp_id
            groups[temp_id] = spec
            group_by_members[key] = temp_id
        return groups[group_by_members[key]]

    # ---- sessions: every course x every schedulable section
    sessions: list[GeneratedSession] = []
    planned_hours: dict[int, float] = {}
    for section in sections:
        if not section.sub_batches:
            diagnostics.append(f"Section '{section.name}' has no sub-batches and was skipped.")
            continue
        sub_batches = sorted(section.sub_batches, key=lambda sb: sb.name)
        section_groups = {
            "lecture": register(
                ParticipantGroupResolver.resolve_section_group(
                    req.department_id,
                    section.name,
                    [(sb.subbatch_id, sb.student_strength) for sb in sub_batches],
                )
            )
        }
        for sb in sub_batches:
            section_groups[f"lab_{sb.name}"] = register(
                ParticipantGroupResolver.resolve_subbatch_group(
                    req.department_id, sb.subbatch_id, sb.name, sb.student_strength
                )
            )

        for course in courses:
            if not course.session_type_configs:
                continue
            candidates = qualified.get(course.course_id, [])
            if candidates:
                # One teacher per course; spread courses over the least-loaded qualified faculty.
                teacher = min(candidates, key=lambda f: (planned_hours.get(f.faculty_id, 0.0), f.faculty_id))
                assignments = {course.code: {"main": [teacher.faculty_id]}}
            else:
                teacher = None
                assignments = {}
                msg = f"No active faculty is assigned to course {course.code}; it was scheduled without a teacher."
                if msg not in diagnostics:
                    diagnostics.append(msg)

            try:
                generated = TimetableSchedulerService.generate_sessions(
                    courses_data=[
                        {
                            "course_id": course.course_id,
                            "code": course.code,
                            "department_id": course.department_id,
                            "configs": [
                                {
                                    "course_session_type_id": cfg.course_session_type_id,
                                    "session_type": cfg.session_type,
                                    "sessions_per_week": cfg.sessions_per_week,
                                    "duration_minutes": cfg.duration_minutes,
                                    "required_resource_type": cfg.required_resource_type,
                                }
                                for cfg in course.session_type_configs
                            ],
                        }
                    ],
                    section_groups=section_groups,
                    faculty_assignments=assignments,
                )
            except ValueError as exc:
                raise HTTPException(422, detail=f"Cannot generate sessions for course {course.code}: {exc}")

            for s in generated:
                s.label = f"{section.name}_{s.label}"  # keep labels unique across sections
            if teacher is not None:
                planned_hours[teacher.faculty_id] = planned_hours.get(teacher.faculty_id, 0.0) + sum(
                    s.duration_hours for s in generated
                )
            sessions.extend(generated)

    if not sessions:
        raise HTTPException(422, detail="No sessions to schedule: the courses have no session configuration")
    # Temporary ids let us match results back to their sessions (labels stay for humans).
    for index, s in enumerate(sessions, start=1):
        s.session_id = index

    return (
        _Inputs(
            grid=grid,
            sessions=sessions,
            groups=groups,
            faculty=faculty_specs,
            resources=resources,
            course_codes={c.course_id: c.code for c in courses},
            course_ids=course_ids,
            diagnostics=diagnostics,
        ),
        semester.semester_number,
    )


# ---------------------------------------------------------------------------
# Scoring weights: allocator keys and GA keys share one request field
# ---------------------------------------------------------------------------
def _split_weights(
    weights: dict[str, float] | None,
) -> tuple[dict[str, float] | None, dict[str, float] | None]:
    if not weights:
        return None, None
    allocator_keys = set(SmartResourceAllocator.DEFAULT_WEIGHTS)
    ga_keys = set(GAOptimizationConfig().weights)
    unknown = sorted(set(weights) - allocator_keys - ga_keys)
    if unknown:
        raise HTTPException(
            422,
            detail=(
                f"Unknown scoring weights: {unknown}. "
                f"Allowed: {sorted(allocator_keys)} (room allocation) or {sorted(ga_keys)} (optimisation)"
            ),
        )
    return (
        {k: v for k, v in weights.items() if k in allocator_keys} or None,
        {k: v for k, v in weights.items() if k in ga_keys} or None,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _replace_previous_timetable(db: DBSession, department_id: int, course_ids: list[int]) -> None:
    old = select(Session.session_id).where(
        Session.department_id == department_id, Session.course_id.in_(course_ids)
    )
    db.execute(delete(SessionFaculty).where(SessionFaculty.session_id.in_(old)))
    db.execute(delete(SessionParticipantGroup).where(SessionParticipantGroup.session_id.in_(old)))
    db.execute(
        delete(Session).where(Session.department_id == department_id, Session.course_id.in_(course_ids))
    )


def _real_group_ids(
    db: DBSession, department_id: int, groups: dict[int, ParticipantGroupSpec], used: set[int]
) -> dict[int, int]:
    """Map temporary group ids to ParticipantGroup rows, reusing identical groups."""
    members: dict[int, set[int]] = {}
    for gid, sbid in db.execute(
        select(ParticipantGroupMember.participant_group_id, ParticipantGroupMember.subbatch_id)
        .join(
            ParticipantGroup,
            ParticipantGroup.participant_group_id == ParticipantGroupMember.participant_group_id,
        )
        .where(ParticipantGroup.department_id == department_id)
    ):
        members.setdefault(gid, set()).add(sbid)
    existing = {frozenset(ids): gid for gid, ids in sorted(members.items(), reverse=True)}

    mapping: dict[int, int] = {}
    for temp_id in sorted(used):
        spec = groups[temp_id]
        key = frozenset(spec.subbatch_ids)
        if key not in existing:
            row = ParticipantGroup(
                department_id=department_id, label=spec.label, combined_strength=spec.combined_strength
            )
            db.add(row)
            db.flush()
            db.add_all(
                ParticipantGroupMember(participant_group_id=row.participant_group_id, subbatch_id=sbid)
                for sbid in spec.subbatch_ids
            )
            existing[key] = row.participant_group_id
        mapping[temp_id] = existing[key]
    return mapping


def _persist(
    db: DBSession, req: GenerateTimetableRequest, inputs: _Inputs, allocations: list[AllocatedSession]
) -> list[AllocatedSessionResponse]:
    by_temp_id = {s.session_id: s for s in inputs.sessions}
    ordered = sorted(allocations, key=lambda a: (a.day, a.start_slot_id, a.label))

    _replace_previous_timetable(db, req.department_id, inputs.course_ids)
    group_map = _real_group_ids(db, req.department_id, inputs.groups, {a.participant_group_id for a in ordered})

    rows: list[Session] = []
    for a in ordered:
        source = by_temp_id[a.session_id]
        rows.append(
            Session(
                course_id=a.course_id,
                course_session_type_id=source.course_session_type_id,
                department_id=a.department_id,
                session_type=SessionType(a.session_type),
                duration_minutes=a.duration_minutes,
                required_resource_type=a.required_resource_type,
                required_capacity=a.required_capacity,
                scheduled_day=a.day,
                start_time=datetime.time.fromisoformat(a.start_time),
                end_time=datetime.time.fromisoformat(a.end_time),
                resource_id=a.resource_id,
                status=SessionStatus.RESOURCE_ALLOCATED,
            )
        )
    db.add_all(rows)
    db.flush()  # assigns session_id

    for row, a in zip(rows, ordered):
        db.add_all(SessionFaculty(session_id=row.session_id, faculty_id=fid) for fid in sorted(set(a.faculty_ids)))
        db.add(
            SessionParticipantGroup(
                session_id=row.session_id, participant_group_id=group_map[a.participant_group_id]
            )
        )
    commit_or_409(db, "Could not save the timetable: a referenced row was changed concurrently")

    return [
        AllocatedSessionResponse(
            session_id=row.session_id,
            label=a.label,
            day=a.day,
            period=inputs.grid.slot_by_id[a.start_slot_id].period,
            start_time=a.start_time,
            end_time=a.end_time,
            duration_minutes=a.duration_minutes,
            course_code=inputs.course_codes[a.course_id],
            session_type=a.session_type,
            resource_id=a.resource_id,
            resource_code=a.resource_code,
            resource_name=a.resource_name,
            resource_type=a.resource_type.value,
            resource_capacity=a.resource_capacity,
            faculty_ids=sorted(set(a.faculty_ids)),
            participant_group_id=group_map[a.participant_group_id],
            subbatch_ids=list(a.subbatch_ids),
            required_equipment=dict(a.required_equipment),
        )
        for row, a in zip(rows, ordered)
    ]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post(
    "/generate",
    response_model=TimetableGenerationResponse,
    summary="Generate a timetable and save it as sessions",
)
def generate_timetable(
    payload: GenerateTimetableRequest,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
) -> TimetableGenerationResponse:
    """Always answers 200 with the solver outcome. When ``is_feasible`` is false nothing
    is saved and ``diagnostics`` explains why. 403 = other department, 409 = an approved
    timetable already exists, 422 = missing/invalid inputs or unknown scoring weights."""
    enforce_department_scope(current_user, payload.department_id)
    allocator_weights, ga_weights = _split_weights(payload.scoring_weights)

    inputs, semester_number = _load_inputs(db, payload)
    db.rollback()  # end the read transaction; the solver below can run for minutes

    service = TimetableSchedulerService
    diagnostics = list(inputs.diagnostics)

    # Engine 1: CP-SAT feasibility
    solved = service.solve_timetable(
        grid=inputs.grid,
        sessions=inputs.sessions,
        participant_groups=inputs.groups,
        faculty_members=inputs.faculty,
        time_limit_seconds=payload.time_limit_seconds,
    )
    diagnostics.extend(solved.diagnostics)
    if not solved.is_feasible:
        return TimetableGenerationResponse(
            is_feasible=False,
            status_label=solved.status_label,
            solve_time_seconds=solved.solve_time_seconds,
            total_sessions_scheduled=0,
            diagnostics=diagnostics,
        )

    # Optional ML room-demand matrix feeding the allocator's score
    predicted_demand = None
    if payload.enable_ml_demand_prediction:
        try:
            predicted_demand, _ = service.predict_room_demand_matrix(
                grid=inputs.grid,
                resources=inputs.resources,
                department_id=payload.department_id,
                semester=semester_number,
            )
        except Exception:  # the prediction only refines scores; never block generation on it
            logger.exception("ML demand prediction failed; continuing without it")
            diagnostics.append("ML demand prediction was skipped because it failed.")

    # Engine 2: rooms + mandatory revalidation
    try:
        allocated = service.allocate_resources(
            assignments=solved.assignments,
            resources=inputs.resources,
            predicted_demand=predicted_demand,
            preferred_building=payload.preferred_building,
            weights=allocator_weights,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc))
    if not (allocated.is_feasible and allocated.validation_passed):
        diagnostics.extend(d.reason for d in allocated.unallocated)
        diagnostics.extend(allocated.validation_errors)
        return TimetableGenerationResponse(
            is_feasible=False,
            status_label=allocated.status_label,
            solve_time_seconds=solved.solve_time_seconds,
            total_sessions_scheduled=0,
            diagnostics=diagnostics,
        )
    final_allocations = allocated.allocations

    # Engine 3 (optional): GA improves soft constraints without breaking hard ones
    average_utilization = min(100.0, float(allocated.metrics.get("average_utilization", 0.0)) * 100.0)
    initial_utilization = final_utilization = average_utilization
    ga_initial = ga_final = None
    if payload.enable_ga_optimization:
        config = GAOptimizationConfig(weights=ga_weights) if ga_weights else None
        try:
            optimized = service.optimize_timetable(
                grid=inputs.grid,
                allocations=allocated.allocations,
                resources=inputs.resources,
                faculty_members=inputs.faculty,
                config=config,
                max_time_seconds=payload.time_limit_seconds,
                participant_groups=inputs.groups,
            )
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc))
        diagnostics.extend(optimized.diagnostics)
        if optimized.is_optimized and optimized.metrics is not None:
            final_allocations = optimized.optimized_allocations
            ga_initial = optimized.metrics.initial_fitness
            ga_final = optimized.metrics.final_fitness
            initial_utilization = min(100.0, optimized.metrics.initial_utilization * 100.0)
            final_utilization = min(100.0, optimized.metrics.final_utilization * 100.0)
        else:
            diagnostics.append("Optimisation was not applied; the resource-validated timetable was saved instead.")
    elif ga_weights:
        diagnostics.append("Optimisation weights were ignored because enable_ga_optimization is false.")

    saved = _persist(db, payload, inputs, final_allocations)
    return TimetableGenerationResponse(
        is_feasible=True,
        status_label=solved.status_label,
        solve_time_seconds=solved.solve_time_seconds,
        total_sessions_scheduled=len(saved),
        ga_initial_fitness=ga_initial,
        ga_final_fitness=ga_final,
        initial_utilization=initial_utilization,
        final_utilization=final_utilization,
        allocations=saved,
        diagnostics=diagnostics,
    )
