"""SB3/US5/T1 — POST /api/v1/timetable/generate."""

import datetime

import pytest
from sqlalchemy import func, select

from app.models.academic import (
    Course,
    CourseSessionTypeConfig,
    ParticipantGroup,
    ResourceType,
    Section,
    Session,
    SessionFaculty,
    SessionParticipantGroup,
    SessionStatus,
    SessionType,
    SubBatch,
)
from app.models.faculty import Faculty, FacultyAvailability, FacultySubject
from app.models.resource import Resource
from app.models.timeslot import Break, TimeSlot

URL = "/api/v1/timetable/generate"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture()
def world(seed, session_factory):
    """CSE sem-7 with one section (D1+D2), one course (2 lectures + 1 two-hour
    lab per sub-batch), one teacher and a classroom + a lab."""
    db = session_factory()
    section = Section(
        department_id=seed["cse"], academic_year_id=seed["year"], semester_id=seed["sem"],
        name="D", student_strength=60,
    )
    db.add(section)
    db.flush()
    db.add_all([
        SubBatch(section_id=section.section_id, name="D1", student_strength=30),
        SubBatch(section_id=section.section_id, name="D2", student_strength=30),
    ])
    db.add_all([
        CourseSessionTypeConfig(
            course_id=seed["course"], session_type=SessionType.LECTURE, sessions_per_week=2,
            duration_minutes=60, required_resource_type=ResourceType.CLASSROOM,
        ),
        CourseSessionTypeConfig(
            course_id=seed["course"], session_type=SessionType.PRACTICAL, sessions_per_week=1,
            duration_minutes=120, required_resource_type=ResourceType.LABORATORY,
        ),
    ])
    teacher = Faculty(
        department_id=seed["cse"], employee_code="E1", full_name="Dr. Rao", email="rao@x.in",
        max_weekly_hours=16, is_active=True,
    )
    db.add(teacher)
    db.flush()
    db.add(FacultySubject(faculty_id=teacher.faculty_id, course_id=seed["course"]))
    db.add_all([
        Resource(department_id=seed["cse"], code="R101", name="Room 101",
                 resource_type=ResourceType.CLASSROOM, capacity=70, is_active=True),
        Resource(department_id=seed["cse"], code="LAB1", name="Lab 1",
                 resource_type=ResourceType.LABORATORY, capacity=40, is_active=True),
    ])
    db.commit()
    data = {"section": section.section_id, "teacher": teacher.faculty_id}
    db.close()
    return {**seed, **data}


def _body(world, **over):
    body = {
        "academic_year_id": world["year"],
        "semester": 7,
        "department_id": world["cse"],
        "time_limit_seconds": 5,
        "enable_ga_optimization": False,
        "enable_ml_demand_prediction": False,
    }
    body.update(over)
    return body


def _count(session_factory, model):
    db = session_factory()
    try:
        return db.scalar(select(func.count()).select_from(model))
    finally:
        db.close()


def _overlap(a, b):
    return a["day"] == b["day"] and a["start_time"] < b["end_time"] and b["start_time"] < a["end_time"]


def _assert_conflict_free(allocations):
    for i, a in enumerate(allocations):
        for b in allocations[i + 1:]:
            if not _overlap(a, b):
                continue
            assert a["resource_id"] != b["resource_id"], f"room clash {a['label']} / {b['label']}"
            assert not set(a["faculty_ids"]) & set(b["faculty_ids"]), f"faculty clash {a['label']} / {b['label']}"
            assert not set(a["subbatch_ids"]) & set(b["subbatch_ids"]), f"batch clash {a['label']} / {b['label']}"


# ---------------------------------------------------------------------------
# Happy path + persistence
# ---------------------------------------------------------------------------
def test_generate_saves_conflict_free_timetable(client, world, session_factory):
    r = client.post(URL, json=_body(world), headers=world["coord_cse"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_feasible"] is True
    assert body["total_sessions_scheduled"] == 4  # 2 lectures + 1 lab per sub-batch (D1, D2)
    allocs = body["allocations"]
    assert len(allocs) == 4
    _assert_conflict_free(allocs)

    lectures = [a for a in allocs if a["session_type"] == "LECTURE"]
    labs = [a for a in allocs if a["session_type"] == "PRACTICAL"]
    assert len(lectures) == 2 and len(labs) == 2
    assert all(a["resource_code"] == "R101" and a["course_code"] == "CS701" for a in lectures)
    assert all(a["resource_code"] == "LAB1" and a["duration_minutes"] == 120 for a in labs)
    assert all(a["faculty_ids"] == [world["teacher"]] for a in allocs)
    assert len({a["label"] for a in allocs}) == 4  # labels are unique
    assert sorted(len(a["subbatch_ids"]) for a in allocs) == [1, 1, 2, 2]

    # Saved rows match the response one-to-one.
    db = session_factory()
    rows = {s.session_id: s for s in db.scalars(select(Session))}
    assert set(rows) == {a["session_id"] for a in allocs}
    for a in allocs:
        row = rows[a["session_id"]]
        assert row.status == SessionStatus.RESOURCE_ALLOCATED
        assert row.scheduled_day == a["day"]
        assert row.resource_id == a["resource_id"]
        assert f"{row.start_time:%H:%M}" == a["start_time"] and f"{row.end_time:%H:%M}" == a["end_time"]
        assert row.duration_minutes == a["duration_minutes"]
        assert row.required_capacity == (60 if a["session_type"] == "LECTURE" else 30)
        links = db.scalars(select(SessionParticipantGroup).where(SessionParticipantGroup.session_id == row.session_id)).all()
        assert [l.participant_group_id for l in links] == [a["participant_group_id"]]
        facs = db.scalars(select(SessionFaculty).where(SessionFaculty.session_id == row.session_id)).all()
        assert [f.faculty_id for f in facs] == [world["teacher"]]
    db.close()


def test_generate_with_ml_and_ga_enabled(client, world):
    r = client.post(
        URL,
        json=_body(world, enable_ga_optimization=True, enable_ml_demand_prediction=True),
        headers=world["admin"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_feasible"] is True and body["total_sessions_scheduled"] == 4
    assert body["ga_initial_fitness"] is not None
    assert body["ga_final_fitness"] >= body["ga_initial_fitness"]
    assert 0 < body["initial_utilization"] <= 100 and 0 < body["final_utilization"] <= 100
    _assert_conflict_free(body["allocations"])


def test_generate_without_ga_reports_plain_utilization(client, world):
    body = client.post(URL, json=_body(world), headers=world["coord_cse"]).json()
    assert body["ga_initial_fitness"] is None and body["ga_final_fitness"] is None
    assert body["initial_utilization"] == body["final_utilization"] > 0


def test_regenerate_replaces_previous_timetable(client, world, session_factory):
    assert client.post(URL, json=_body(world), headers=world["coord_cse"]).status_code == 200
    groups_after_first = _count(session_factory, ParticipantGroup)
    second = client.post(URL, json=_body(world), headers=world["coord_cse"])
    assert second.status_code == 200, second.text
    assert _count(session_factory, Session) == 4  # replaced, not appended
    assert _count(session_factory, SessionFaculty) == 4
    assert _count(session_factory, SessionParticipantGroup) == 4
    assert _count(session_factory, ParticipantGroup) == groups_after_first  # groups are reused

    db = session_factory()
    saved_ids = set(db.scalars(select(Session.session_id)))
    db.close()
    assert saved_ids == {a["session_id"] for a in second.json()["allocations"]}


def test_two_sections_are_scheduled_without_clashes(client, world, session_factory):
    db = session_factory()
    sec = Section(
        department_id=world["cse"], academic_year_id=world["year"], semester_id=world["sem"],
        name="E", student_strength=30,
    )
    db.add(sec)
    db.flush()
    db.add(SubBatch(section_id=sec.section_id, name="D1", student_strength=30))  # same name as section D's
    db.commit()
    db.close()

    r = client.post(URL, json=_body(world), headers=world["coord_cse"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_feasible"] is True
    assert body["total_sessions_scheduled"] == 7  # section D: 4, section E: 2 lectures + 1 lab
    assert len({a["label"] for a in body["allocations"]}) == 7
    _assert_conflict_free(body["allocations"])


# ---------------------------------------------------------------------------
# Grid, availability, weights
# ---------------------------------------------------------------------------
def test_uses_configured_time_slots_and_breaks(client, world, session_factory):
    db = session_factory()
    for day in range(1, 6):
        for period in range(1, 6):
            h = 8 + period
            db.add(TimeSlot(day_of_week=day, period=period, is_active=True,
                            start_time=datetime.time(h, 0), end_time=datetime.time(h + 1, 0)))
    db.add(Break(label="Lunch", day_of_week=None, start_time=datetime.time(12, 0), end_time=datetime.time(13, 0)))
    db.commit()
    db.close()

    r = client.post(URL, json=_body(world), headers=world["coord_cse"])
    assert r.status_code == 200, r.text
    allocs = r.json()["allocations"]
    assert allocs
    for a in allocs:
        assert a["period"] != 4  # period 4 (12:00-13:00) is the lunch break
        assert not (a["start_time"] < "13:00" and "12:00" < a["end_time"])
        assert a["day"] <= 5 and a["end_time"] <= "14:00"


def test_faculty_availability_windows_are_respected(client, world, session_factory):
    db = session_factory()
    db.add_all(
        FacultyAvailability(
            faculty_id=world["teacher"], day_of_week=day,
            start_time=datetime.time(9, 0), end_time=datetime.time(12, 0),
        )
        for day in (1, 2, 3)
    )
    db.commit()
    db.close()

    r = client.post(URL, json=_body(world), headers=world["coord_cse"])
    assert r.status_code == 200, r.text
    allocs = r.json()["allocations"]
    assert allocs
    assert all(a["day"] in (1, 2, 3) and a["start_time"] >= "09:00" and a["end_time"] <= "12:00" for a in allocs)


def test_scoring_weights_for_allocator_and_ga_are_accepted(client, world):
    r = client.post(
        URL,
        json=_body(world, enable_ga_optimization=True,
                   scoring_weights={"capacity": 1.0, "equipment": 0.5, "sc03_gaps": 0.6}),
        headers=world["coord_cse"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_feasible"] is True


def test_ga_weights_without_ga_are_reported_as_ignored(client, world):
    r = client.post(URL, json=_body(world, scoring_weights={"sc03_gaps": 1.0}), headers=world["coord_cse"])
    assert r.status_code == 200
    assert any("ignored" in d for d in r.json()["diagnostics"])


def test_unknown_scoring_weight_is_422(client, world, session_factory):
    r = client.post(URL, json=_body(world, scoring_weights={"vibes": 1.0}), headers=world["coord_cse"])
    assert r.status_code == 422
    assert "vibes" in r.json()["detail"]
    assert _count(session_factory, Session) == 0


def test_course_without_teacher_is_scheduled_with_a_warning(client, world, session_factory):
    db = session_factory()
    db.query(FacultySubject).delete()
    # Without a teacher nothing stops D1 and D2 labs from running at the same time
    # (CP-SAT doesn't model room counts), so a second lab is needed.
    db.add(Resource(department_id=world["cse"], code="LAB2", name="Lab 2",
                    resource_type=ResourceType.LABORATORY, capacity=40, is_active=True))
    db.commit()
    db.close()
    body = client.post(URL, json=_body(world), headers=world["coord_cse"]).json()
    assert body["is_feasible"] is True
    assert all(a["faculty_ids"] == [] for a in body["allocations"])
    assert any("CS701" in d and "without a teacher" in d for d in body["diagnostics"])


def test_section_without_sub_batches_is_skipped(client, world, session_factory):
    db = session_factory()
    db.add(Section(department_id=world["cse"], academic_year_id=world["year"],
                   semester_id=world["sem"], name="Z", student_strength=10))
    db.commit()
    db.close()
    body = client.post(URL, json=_body(world), headers=world["coord_cse"]).json()
    assert body["is_feasible"] is True and body["total_sessions_scheduled"] == 4
    assert any("Section 'Z'" in d for d in body["diagnostics"])


# ---------------------------------------------------------------------------
# Infeasible runs must not touch the database
# ---------------------------------------------------------------------------
def test_infeasible_workload_saves_nothing_and_keeps_previous_timetable(client, world, session_factory):
    assert client.post(URL, json=_body(world), headers=world["coord_cse"]).json()["is_feasible"] is True
    db = session_factory()
    db.get(Faculty, world["teacher"]).max_weekly_hours = 1  # needs 6 h/week
    db.commit()
    db.close()

    r = client.post(URL, json=_body(world), headers=world["coord_cse"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_feasible"] is False
    assert body["total_sessions_scheduled"] == 0 and body["allocations"] == []
    assert any("HC-10" in d for d in body["diagnostics"])
    assert _count(session_factory, Session) == 4  # the earlier timetable survives


def test_no_suitable_room_is_infeasible_and_saves_nothing(client, world, session_factory):
    db = session_factory()
    db.query(Resource).filter(Resource.code == "LAB1").delete()
    db.commit()
    db.close()
    r = client.post(URL, json=_body(world), headers=world["coord_cse"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_feasible"] is False and body["allocations"] == []
    assert body["diagnostics"]
    assert _count(session_factory, Session) == 0
    assert _count(session_factory, ParticipantGroup) == 0


def test_approved_timetable_is_never_overwritten(client, world, session_factory):
    client.post(URL, json=_body(world), headers=world["coord_cse"])
    db = session_factory()
    first = db.scalars(select(Session)).first()
    first.status = SessionStatus.VALIDATED
    db.commit()
    db.close()

    r = client.post(URL, json=_body(world), headers=world["coord_cse"])
    assert r.status_code == 409
    assert _count(session_factory, Session) == 4


# ---------------------------------------------------------------------------
# Access control and validation
# ---------------------------------------------------------------------------
def test_requires_authentication(client, world):
    assert client.post(URL, json=_body(world)).status_code == 401


def test_faculty_users_cannot_generate(client, world):
    assert client.post(URL, json=_body(world), headers=world["faculty_user"]).status_code == 403


def test_coordinator_cannot_generate_for_another_department(client, world, session_factory):
    r = client.post(URL, json=_body(world), headers=world["coord_it"])
    assert r.status_code == 403
    assert _count(session_factory, Session) == 0


def test_admin_can_generate_for_any_department(client, world):
    assert client.post(URL, json=_body(world), headers=world["admin"]).status_code == 200


@pytest.mark.parametrize(
    "override",
    [
        {"academic_year_id": 999},
        {"department_id": 999},
        {"semester": 8},  # no such semester row
        {"semester": 3},  # valid row would exist, but not here
    ],
)
def test_unknown_references_are_422(client, world, override):
    r = client.post(URL, json=_body(world, **override), headers=world["admin"])
    assert r.status_code == 422, r.text


def test_nothing_to_schedule_is_422(client, world, session_factory):
    db = session_factory()
    db.query(CourseSessionTypeConfig).delete()
    db.commit()
    db.close()
    assert client.post(URL, json=_body(world), headers=world["coord_cse"]).status_code == 422


def test_no_sections_is_422(client, world, session_factory):
    db = session_factory()
    db.query(SubBatch).delete()
    db.query(Section).delete()
    db.commit()
    db.close()
    r = client.post(URL, json=_body(world), headers=world["coord_cse"])
    assert r.status_code == 422 and "sections" in r.json()["detail"]


@pytest.mark.parametrize(
    "override",
    [
        {"time_limit_seconds": 0},
        {"time_limit_seconds": 500},
        {"scoring_weights": {}},
        {"scoring_weights": {"capacity": -1}},
        {"department_id": 0},
    ],
)
def test_request_schema_validation_is_422(client, world, override):
    assert client.post(URL, json=_body(world, **override), headers=world["admin"]).status_code == 422
