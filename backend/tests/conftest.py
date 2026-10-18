"""
Shared fixtures for the /api/v1 CRUD tests.

Runs against in-memory SQLite (no Postgres needed). DATABASE_URL is pointed at
SQLite *before* the app is imported so app.db.session doesn't try to load psycopg2.
Foreign keys are switched on explicitly because SQLite ignores them by default.
"""

import os

os.environ["DATABASE_URL"] = "sqlite://"

import datetime  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.security import create_token  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.academic import AcademicYear, Course, Department, Semester  # noqa: E402
from app.models.auth import User, UserRole  # noqa: E402


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False)
    engine.dispose()


@pytest.fixture()
def client(session_factory):
    def _override():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _headers(user: User) -> dict[str, str]:
    token = create_token(
        subject=str(user.user_id), token_type="access", extra_claims={"role": user.role.value}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def seed(session_factory):
    """Two departments, one of every role in CSE, a coordinator in IT, plus
    a semester, an academic year and a course."""
    db = session_factory()
    cse = Department(code="CSE", name="Computer Science")
    it = Department(code="IT", name="Information Technology")
    db.add_all([cse, it])
    db.flush()

    def mk(email, role, dept):
        u = User(
            email=email, hashed_password="x", full_name=email.split("@")[0],
            role=role, department_id=dept.department_id if dept else None,
        )
        db.add(u)
        return u

    admin = mk("admin@x.in", UserRole.SYSTEM_ADMIN, None)
    coord_cse = mk("coord.cse@x.in", UserRole.COORDINATOR, cse)
    coord_it = mk("coord.it@x.in", UserRole.COORDINATOR, it)
    fac_user = mk("fac.cse@x.in", UserRole.FACULTY, cse)
    sem = Semester(semester_number=7, name="Semester 7")
    year = AcademicYear(
        label="2026-27", start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30)
    )
    db.add_all([sem, year])
    db.flush()
    course = Course(
        code="CS701", name="DBMS", department_id=cse.department_id,
        semester_id=sem.semester_id, required_weekly_hours=4,
    )
    db.add(course)
    db.commit()

    data = {
        "cse": cse.department_id,
        "it": it.department_id,
        "sem": sem.semester_id,
        "year": year.academic_year_id,
        "course": course.course_id,
        "admin": _headers(admin),
        "coord_cse": _headers(coord_cse),
        "coord_it": _headers(coord_it),
        "faculty_user": _headers(fac_user),
        "faculty_user_id": fac_user.user_id,
    }
    db.close()
    return data
