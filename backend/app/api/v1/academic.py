"""
Academic hierarchy CRUD — SB2/US3/T1.

    /api/v1/departments
    /api/v1/academic-years
    /api/v1/semesters
    /api/v1/sections
    /api/v1/sub-batches        (+ GET /api/v1/sections/{id}/sub-batches)

Access rules (NFR-3 department-level isolation, see app/api/deps.py):
  * Every endpoint needs a valid access token.
  * departments / academic-years / semesters : read = any user (departments are
    scoped to the caller's own department unless SYSTEM_ADMIN);
    write = SYSTEM_ADMIN only.
  * sections / sub-batches : read = any user, scoped to own department;
    write = SYSTEM_ADMIN, or COORDINATOR within their own department.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.api.deps import department_scope, enforce_department_scope, get_current_user
from app.api.v1.common import (
    Pagination,
    admin_only,
    admin_or_coordinator,
    apply_updates,
    commit_or_409,
    get_or_404,
    require_exists,
)
from app.db.session import get_db
from app.models.academic import AcademicYear, Department, Section, Semester, SubBatch
from app.models.auth import User
from app.schemas.academic import (
    AcademicYearCreate,
    AcademicYearOut,
    AcademicYearUpdate,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    SectionCreate,
    SectionOut,
    SectionUpdate,
    SemesterCreate,
    SemesterOut,
    SemesterUpdate,
    SubBatchCreate,
    SubBatchOut,
    SubBatchUpdate,
)

# ===========================================================================
# Departments
# ===========================================================================
departments_router = APIRouter(prefix="/departments", tags=["departments"])


@departments_router.get("", response_model=list[DepartmentOut])
def list_departments(
    scope: int | None = Depends(department_scope),
    page: Pagination = Depends(),
    db: DBSession = Depends(get_db),
):
    query = select(Department).order_by(Department.code)
    if scope is not None:
        query = query.where(Department.department_id == scope)
    return db.scalars(query.limit(page.limit).offset(page.offset)).all()


@departments_router.get("/{department_id}", response_model=DepartmentOut)
def get_department(
    department_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    dept = get_or_404(db, Department, department_id, "Department")
    enforce_department_scope(current_user, dept.department_id)
    return dept


@departments_router.post(
    "",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_only)],
)
def create_department(payload: DepartmentCreate, db: DBSession = Depends(get_db)):
    dept = Department(**payload.model_dump())
    db.add(dept)
    commit_or_409(db, "A department with this code already exists")
    db.refresh(dept)
    return dept


@departments_router.patch(
    "/{department_id}",
    response_model=DepartmentOut,
    dependencies=[Depends(admin_only)],
)
@departments_router.put(
    "/{department_id}",
    response_model=DepartmentOut,
    dependencies=[Depends(admin_only)],
)
def update_department(
    department_id: int, payload: DepartmentUpdate, db: DBSession = Depends(get_db)
):
    dept = get_or_404(db, Department, department_id, "Department")
    apply_updates(dept, payload.model_dump(exclude_unset=True))
    commit_or_409(db, "A department with this code already exists")
    db.refresh(dept)
    return dept


@departments_router.delete(
    "/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(admin_only)],
)
def delete_department(department_id: int, db: DBSession = Depends(get_db)):
    dept = get_or_404(db, Department, department_id, "Department")
    db.delete(dept)
    commit_or_409(db, "Department is still referenced by sections, courses, faculty, resources or users")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ===========================================================================
# Academic years
# ===========================================================================
academic_years_router = APIRouter(
    prefix="/academic-years", tags=["academic-years"], dependencies=[Depends(get_current_user)]
)


@academic_years_router.get("", response_model=list[AcademicYearOut])
def list_academic_years(
    is_active: bool | None = None,
    page: Pagination = Depends(),
    db: DBSession = Depends(get_db),
):
    query = select(AcademicYear).order_by(AcademicYear.start_date.desc())
    if is_active is not None:
        query = query.where(AcademicYear.is_active == is_active)
    return db.scalars(query.limit(page.limit).offset(page.offset)).all()


@academic_years_router.get("/{academic_year_id}", response_model=AcademicYearOut)
def get_academic_year(academic_year_id: int, db: DBSession = Depends(get_db)):
    return get_or_404(db, AcademicYear, academic_year_id, "Academic year")


@academic_years_router.post(
    "",
    response_model=AcademicYearOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_only)],
)
def create_academic_year(payload: AcademicYearCreate, db: DBSession = Depends(get_db)):
    year = AcademicYear(**payload.model_dump())
    db.add(year)
    commit_or_409(db, "An academic year with this label already exists")
    db.refresh(year)
    return year


@academic_years_router.patch(
    "/{academic_year_id}",
    response_model=AcademicYearOut,
    dependencies=[Depends(admin_only)],
)
@academic_years_router.put(
    "/{academic_year_id}",
    response_model=AcademicYearOut,
    dependencies=[Depends(admin_only)],
)
def update_academic_year(
    academic_year_id: int, payload: AcademicYearUpdate, db: DBSession = Depends(get_db)
):
    year = get_or_404(db, AcademicYear, academic_year_id, "Academic year")
    apply_updates(year, payload.model_dump(exclude_unset=True))
    # Partial updates can invert the date range; re-check the merged result.
    if year.end_date <= year.start_date:
        raise HTTPException(
            422, detail="end_date must be after start_date"
        )
    commit_or_409(db, "An academic year with this label already exists")
    db.refresh(year)
    return year


@academic_years_router.delete(
    "/{academic_year_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(admin_only)],
)
def delete_academic_year(academic_year_id: int, db: DBSession = Depends(get_db)):
    year = get_or_404(db, AcademicYear, academic_year_id, "Academic year")
    db.delete(year)
    commit_or_409(db, "Academic year is still referenced by sections")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ===========================================================================
# Semesters (shared lookup, numbers 1-8)
# ===========================================================================
semesters_router = APIRouter(
    prefix="/semesters", tags=["semesters"], dependencies=[Depends(get_current_user)]
)


@semesters_router.get("", response_model=list[SemesterOut])
def list_semesters(page: Pagination = Depends(), db: DBSession = Depends(get_db)):
    query = select(Semester).order_by(Semester.semester_number)
    return db.scalars(query.limit(page.limit).offset(page.offset)).all()


@semesters_router.get("/{semester_id}", response_model=SemesterOut)
def get_semester(semester_id: int, db: DBSession = Depends(get_db)):
    return get_or_404(db, Semester, semester_id, "Semester")


@semesters_router.post(
    "",
    response_model=SemesterOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_only)],
)
def create_semester(payload: SemesterCreate, db: DBSession = Depends(get_db)):
    sem = Semester(**payload.model_dump())
    db.add(sem)
    commit_or_409(db, "A semester with this number already exists")
    db.refresh(sem)
    return sem


@semesters_router.patch(
    "/{semester_id}",
    response_model=SemesterOut,
    dependencies=[Depends(admin_only)],
)
@semesters_router.put(
    "/{semester_id}",
    response_model=SemesterOut,
    dependencies=[Depends(admin_only)],
)
def update_semester(semester_id: int, payload: SemesterUpdate, db: DBSession = Depends(get_db)):
    sem = get_or_404(db, Semester, semester_id, "Semester")
    apply_updates(sem, payload.model_dump(exclude_unset=True))
    commit_or_409(db, "A semester with this number already exists")
    db.refresh(sem)
    return sem


@semesters_router.delete(
    "/{semester_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(admin_only)],
)
def delete_semester(semester_id: int, db: DBSession = Depends(get_db)):
    sem = get_or_404(db, Semester, semester_id, "Semester")
    db.delete(sem)
    commit_or_409(db, "Semester is still referenced by sections or courses")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ===========================================================================
# Sections
# ===========================================================================
sections_router = APIRouter(prefix="/sections", tags=["sections"])


@sections_router.get("", response_model=list[SectionOut])
def list_sections(
    department_id: int | None = Query(None),
    semester_id: int | None = Query(None),
    academic_year_id: int | None = Query(None),
    scope: int | None = Depends(department_scope),
    page: Pagination = Depends(),
    db: DBSession = Depends(get_db),
):
    query = select(Section).order_by(Section.department_id, Section.semester_id, Section.name)
    if scope is not None:
        # Non-admins: explicitly asking for another department is a 403, not an empty list.
        if department_id is not None and department_id != scope:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="You do not have access to this department's data"
            )
        query = query.where(Section.department_id == scope)
    elif department_id is not None:
        query = query.where(Section.department_id == department_id)
    if semester_id is not None:
        query = query.where(Section.semester_id == semester_id)
    if academic_year_id is not None:
        query = query.where(Section.academic_year_id == academic_year_id)
    return db.scalars(query.limit(page.limit).offset(page.offset)).all()


@sections_router.get("/{section_id}", response_model=SectionOut)
def get_section(
    section_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    section = get_or_404(db, Section, section_id, "Section")
    enforce_department_scope(current_user, section.department_id)
    return section


@sections_router.get("/{section_id}/sub-batches", response_model=list[SubBatchOut])
def list_section_sub_batches(
    section_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    section = get_or_404(db, Section, section_id, "Section")
    enforce_department_scope(current_user, section.department_id)
    return db.scalars(
        select(SubBatch).where(SubBatch.section_id == section_id).order_by(SubBatch.name)
    ).all()


@sections_router.post("", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
def create_section(
    payload: SectionCreate,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    enforce_department_scope(current_user, payload.department_id)
    require_exists(db, Department, payload.department_id, "department_id")
    require_exists(db, AcademicYear, payload.academic_year_id, "academic_year_id")
    require_exists(db, Semester, payload.semester_id, "semester_id")

    section = Section(**payload.model_dump())
    db.add(section)
    commit_or_409(
        db, "A section with this name already exists for this department, year and semester"
    )
    db.refresh(section)
    return section


@sections_router.patch("/{section_id}", response_model=SectionOut)
@sections_router.put("/{section_id}", response_model=SectionOut)
def update_section(
    section_id: int,
    payload: SectionUpdate,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    section = get_or_404(db, Section, section_id, "Section")
    enforce_department_scope(current_user, section.department_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("academic_year_id") is not None:
        require_exists(db, AcademicYear, data["academic_year_id"], "academic_year_id")
    if data.get("semester_id") is not None:
        require_exists(db, Semester, data["semester_id"], "semester_id")
    apply_updates(section, data)
    commit_or_409(
        db, "A section with this name already exists for this department, year and semester"
    )
    db.refresh(section)
    return section


@sections_router.delete("/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_section(
    section_id: int,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    section = get_or_404(db, Section, section_id, "Section")
    enforce_department_scope(current_user, section.department_id)
    db.delete(section)
    commit_or_409(db, "Section still has sub-batches; delete them first")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ===========================================================================
# Sub-batches  (department is inherited from the parent section)
# ===========================================================================
sub_batches_router = APIRouter(prefix="/sub-batches", tags=["sub-batches"])


@sub_batches_router.get("", response_model=list[SubBatchOut])
def list_sub_batches(
    section_id: int | None = Query(None),
    scope: int | None = Depends(department_scope),
    page: Pagination = Depends(),
    db: DBSession = Depends(get_db),
):
    query = select(SubBatch).join(Section, Section.section_id == SubBatch.section_id)
    if scope is not None:
        query = query.where(Section.department_id == scope)
    if section_id is not None:
        query = query.where(SubBatch.section_id == section_id)
    query = query.order_by(SubBatch.section_id, SubBatch.name)
    return db.scalars(query.limit(page.limit).offset(page.offset)).all()


def _load_sub_batch_checked(
    db: DBSession, subbatch_id: int, current_user: User
) -> SubBatch:
    sub = get_or_404(db, SubBatch, subbatch_id, "Sub-batch")
    parent = get_or_404(db, Section, sub.section_id, "Section")
    enforce_department_scope(current_user, parent.department_id)
    return sub


@sub_batches_router.get("/{subbatch_id}", response_model=SubBatchOut)
def get_sub_batch(
    subbatch_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    return _load_sub_batch_checked(db, subbatch_id, current_user)


@sub_batches_router.post("", response_model=SubBatchOut, status_code=status.HTTP_201_CREATED)
def create_sub_batch(
    payload: SubBatchCreate,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    section = require_exists(db, Section, payload.section_id, "section_id")
    enforce_department_scope(current_user, section.department_id)
    sub = SubBatch(**payload.model_dump())
    db.add(sub)
    commit_or_409(db, "This section already has a sub-batch with that name")
    db.refresh(sub)
    return sub


@sub_batches_router.patch(
    "/{subbatch_id}", response_model=SubBatchOut
)
@sub_batches_router.put(
    "/{subbatch_id}", response_model=SubBatchOut
)
def update_sub_batch(
    subbatch_id: int,
    payload: SubBatchUpdate,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    sub = _load_sub_batch_checked(db, subbatch_id, current_user)
    apply_updates(sub, payload.model_dump(exclude_unset=True), nullable={"practical_group_info"})
    commit_or_409(db, "This section already has a sub-batch with that name")
    db.refresh(sub)
    return sub


@sub_batches_router.delete("/{subbatch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sub_batch(
    subbatch_id: int,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    sub = _load_sub_batch_checked(db, subbatch_id, current_user)
    db.delete(sub)
    commit_or_409(db, "Sub-batch is still referenced by a participant group")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
