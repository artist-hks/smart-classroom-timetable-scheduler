"""
Faculty CRUD & workload — SB2/US4/T1.

    /api/v1/faculty
    /api/v1/faculty/{id}/subjects      PUT  (replace subject assignment)
    /api/v1/faculty/{id}/availability  PUT  (replace weekly availability windows)
    /api/v1/faculty/{id}/workload      GET  (assigned vs max weekly hours)

Read = any user, scoped to own department. Write = SYSTEM_ADMIN, or
COORDINATOR within their own department.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import selectinload

from app.api.deps import department_scope, enforce_department_scope, get_current_user
from app.api.v1.common import (
    Pagination,
    admin_or_coordinator,
    apply_updates,
    commit_or_409,
    get_or_404,
    require_exists,
    times_overlap,
)
from app.db.session import get_db
from app.models.academic import Course, Department, Session, SessionFaculty, SessionStatus
from app.models.auth import User
from app.models.faculty import Faculty, FacultyAvailability, FacultySubject
from app.schemas.faculty import (
    AvailabilityReplace,
    AvailabilityWindow,
    FacultyCreate,
    FacultyOut,
    FacultyUpdate,
    SubjectAssignment,
    WorkloadOut,
)

router = APIRouter(prefix="/faculty", tags=["faculty"])

# Sessions in these states no longer consume a faculty member's weekly hours.
_NON_LOADING_STATUSES = (SessionStatus.CANCELLED, SessionStatus.REPLACED_BY_EVENT)
_CONFLICT = "Employee code, email or linked user is already used by another faculty member"


def to_out(f: Faculty) -> FacultyOut:
    return FacultyOut(
        faculty_id=f.faculty_id,
        department_id=f.department_id,
        user_id=f.user_id,
        employee_code=f.employee_code,
        full_name=f.full_name,
        email=f.email,
        designation=f.designation,
        max_weekly_hours=float(f.max_weekly_hours),
        is_active=f.is_active,
        course_ids=sorted(s.course_id for s in f.subjects),
        availability=[AvailabilityWindow.model_validate(a) for a in f.availability],
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


def _validate_no_overlap(windows: list[AvailabilityWindow]) -> None:
    by_day: dict[int, list[AvailabilityWindow]] = {}
    for w in windows:
        by_day.setdefault(w.day_of_week, []).append(w)
    for day, items in by_day.items():
        items.sort(key=lambda w: w.start_time)
        for prev, cur in zip(items, items[1:]):
            if times_overlap(prev.start_time, prev.end_time, cur.start_time, cur.end_time):
                raise HTTPException(
                    422,
                    detail=f"Availability windows overlap on day {day}",
                )


def _validate_courses(db: DBSession, course_ids: list[int]) -> list[int]:
    unique_ids = sorted(set(course_ids))
    if unique_ids:
        found = set(
            db.scalars(select(Course.course_id).where(Course.course_id.in_(unique_ids))).all()
        )
        missing = [c for c in unique_ids if c not in found]
        if missing:
            raise HTTPException(
                422,
                detail=f"Unknown course_ids: {missing}",
            )
    return unique_ids


def _validate_user_link(db: DBSession, user_id: int | None, faculty_dept: int) -> None:
    if user_id is None:
        return
    user = require_exists(db, User, user_id, "user_id")
    if user.department_id is not None and user.department_id != faculty_dept:
        raise HTTPException(
            422,
            detail="Linked user belongs to a different department",
        )


def _load(db: DBSession, faculty_id: int, current_user: User) -> Faculty:
    f = db.scalars(
        select(Faculty)
        .options(selectinload(Faculty.subjects), selectinload(Faculty.availability))
        .where(Faculty.faculty_id == faculty_id)
    ).first()
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Faculty not found")
    enforce_department_scope(current_user, f.department_id)
    return f


def compute_workload(db: DBSession, faculty: Faculty) -> WorkloadOut:
    """Weekly load = total duration of this faculty's non-cancelled sessions."""
    minutes, count = db.execute(
        select(func.coalesce(func.sum(Session.duration_minutes), 0), func.count(Session.session_id))
        .select_from(SessionFaculty)
        .join(Session, Session.session_id == SessionFaculty.session_id)
        .where(
            SessionFaculty.faculty_id == faculty.faculty_id,
            Session.status.notin_(_NON_LOADING_STATUSES),
        )
    ).one()
    assigned = round(float(minutes) / 60.0, 2)
    maximum = float(faculty.max_weekly_hours)
    return WorkloadOut(
        faculty_id=faculty.faculty_id,
        max_weekly_hours=maximum,
        assigned_hours=assigned,
        remaining_hours=round(maximum - assigned, 2),
        utilization_pct=round(assigned / maximum * 100, 1) if maximum else 0.0,
        session_count=int(count),
        over_limit=assigned > maximum,
    )


# ---------------------------------------------------------------------------
@router.get("", response_model=list[FacultyOut])
def list_faculty(
    department_id: int | None = Query(None),
    is_active: bool | None = Query(None),
    course_id: int | None = Query(None, description="Only faculty assigned to this course"),
    q: str | None = Query(None, description="Search name, employee code or email"),
    scope: int | None = Depends(department_scope),
    page: Pagination = Depends(),
    db: DBSession = Depends(get_db),
):
    query = select(Faculty).options(
        selectinload(Faculty.subjects), selectinload(Faculty.availability)
    )
    if scope is not None:
        if department_id is not None and department_id != scope:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="You do not have access to this department's data"
            )
        query = query.where(Faculty.department_id == scope)
    elif department_id is not None:
        query = query.where(Faculty.department_id == department_id)
    if is_active is not None:
        query = query.where(Faculty.is_active == is_active)
    if course_id is not None:
        query = query.where(
            Faculty.faculty_id.in_(
                select(FacultySubject.faculty_id).where(FacultySubject.course_id == course_id)
            )
        )
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Faculty.full_name.ilike(like),
                Faculty.employee_code.ilike(like),
                Faculty.email.ilike(like),
            )
        )
    query = query.order_by(Faculty.full_name).limit(page.limit).offset(page.offset)
    return [to_out(f) for f in db.scalars(query).all()]


@router.get("/{faculty_id}", response_model=FacultyOut)
def get_faculty(
    faculty_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    return to_out(_load(db, faculty_id, current_user))


@router.post("", response_model=FacultyOut, status_code=status.HTTP_201_CREATED)
def create_faculty(
    payload: FacultyCreate,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    enforce_department_scope(current_user, payload.department_id)
    require_exists(db, Department, payload.department_id, "department_id")
    _validate_user_link(db, payload.user_id, payload.department_id)
    course_ids = _validate_courses(db, payload.course_ids)
    _validate_no_overlap(payload.availability)

    faculty = Faculty(
        department_id=payload.department_id,
        user_id=payload.user_id,
        employee_code=payload.employee_code,
        full_name=payload.full_name,
        email=str(payload.email),
        designation=payload.designation,
        max_weekly_hours=payload.max_weekly_hours,
        is_active=payload.is_active,
        subjects=[FacultySubject(course_id=c) for c in course_ids],
        availability=[
            FacultyAvailability(
                day_of_week=w.day_of_week, start_time=w.start_time, end_time=w.end_time
            )
            for w in payload.availability
        ],
    )
    db.add(faculty)
    commit_or_409(db, _CONFLICT)
    return to_out(_load(db, faculty.faculty_id, current_user))


@router.patch("/{faculty_id}", response_model=FacultyOut)
@router.put("/{faculty_id}", response_model=FacultyOut)
def update_faculty(
    faculty_id: int,
    payload: FacultyUpdate,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    faculty = _load(db, faculty_id, current_user)
    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"])
    if data.get("user_id") is not None:
        _validate_user_link(db, data["user_id"], faculty.department_id)
    apply_updates(faculty, data, nullable={"user_id", "designation"})
    commit_or_409(db, _CONFLICT)
    return to_out(_load(db, faculty_id, current_user))


@router.delete("/{faculty_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faculty(
    faculty_id: int,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    faculty = _load(db, faculty_id, current_user)
    db.delete(faculty)
    commit_or_409(
        db, "Faculty is assigned to sessions; deactivate (is_active=false) instead of deleting"
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
@router.put("/{faculty_id}/subjects", response_model=FacultyOut)
def replace_subjects(
    faculty_id: int,
    payload: SubjectAssignment,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    """Replace the full set of courses this faculty member can teach."""
    faculty = _load(db, faculty_id, current_user)
    wanted = set(_validate_courses(db, payload.course_ids))
    current = {s.course_id: s for s in faculty.subjects}
    # Diff instead of delete-all/insert-all: the unit of work would INSERT before
    # DELETE and trip uq_faculty_subjects_pair for ids that stay assigned.
    for course_id, row in current.items():
        if course_id not in wanted:
            faculty.subjects.remove(row)
    for course_id in wanted - current.keys():
        faculty.subjects.append(FacultySubject(course_id=course_id))
    commit_or_409(db, "Could not update subject assignment")
    return to_out(_load(db, faculty_id, current_user))


@router.put("/{faculty_id}/availability", response_model=FacultyOut)
def replace_availability(
    faculty_id: int,
    payload: AvailabilityReplace,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    """Replace all weekly availability windows (send [] to clear)."""
    faculty = _load(db, faculty_id, current_user)
    _validate_no_overlap(payload.windows)
    faculty.availability = [
        FacultyAvailability(day_of_week=w.day_of_week, start_time=w.start_time, end_time=w.end_time)
        for w in payload.windows
    ]
    commit_or_409(db, "Could not update availability")
    return to_out(_load(db, faculty_id, current_user))


@router.get("/{faculty_id}/workload", response_model=WorkloadOut)
def get_workload(
    faculty_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    return compute_workload(db, _load(db, faculty_id, current_user))
