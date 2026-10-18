"""SB2/US4/T1 — Faculty CRUD, subject assignment, availability, workload."""

from app.models.academic import Session, SessionFaculty, SessionStatus, SessionType


def _faculty(seed, **over):
    body = {
        "department_id": seed["cse"],
        "employee_code": "FAC-CSE-01",
        "full_name": "Dr. Rakesh Sharma",
        "email": "rakesh@piet.ac.in",
        "designation": "Professor",
        "max_weekly_hours": 18,
        "course_ids": [seed["course"]],
        "availability": [{"day_of_week": 1, "start_time": "09:00:00", "end_time": "16:00:00"}],
    }
    body.update(over)
    return body


def test_create_and_get_faculty(client, seed):
    r = client.post("/api/v1/faculty", json=_faculty(seed), headers=seed["coord_cse"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["course_ids"] == [seed["course"]]
    assert body["availability"][0]["day_of_week"] == 1
    assert body["max_weekly_hours"] == 18.0

    got = client.get(f"/api/v1/faculty/{body['faculty_id']}", headers=seed["faculty_user"])
    assert got.status_code == 200


def test_faculty_validation(client, seed):
    h = seed["coord_cse"]
    assert client.post("/api/v1/faculty", json=_faculty(seed, max_weekly_hours=0), headers=h).status_code == 422
    assert client.post("/api/v1/faculty", json=_faculty(seed, email="not-an-email"), headers=h).status_code == 422
    assert client.post("/api/v1/faculty", json=_faculty(seed, course_ids=[999]), headers=h).status_code == 422
    overlapping = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "11:00:00"},
        {"day_of_week": 2, "start_time": "10:00:00", "end_time": "12:00:00"},
    ]
    assert client.post("/api/v1/faculty", json=_faculty(seed, availability=overlapping), headers=h).status_code == 422
    inverted = [{"day_of_week": 2, "start_time": "12:00:00", "end_time": "11:00:00"}]
    assert client.post("/api/v1/faculty", json=_faculty(seed, availability=inverted), headers=h).status_code == 422

    assert client.post("/api/v1/faculty", json=_faculty(seed), headers=h).status_code == 201
    # same employee_code / email -> 409
    assert client.post("/api/v1/faculty", json=_faculty(seed), headers=h).status_code == 409


def test_faculty_department_isolation(client, seed):
    fid = client.post("/api/v1/faculty", json=_faculty(seed), headers=seed["coord_cse"]).json()["faculty_id"]

    assert client.get(f"/api/v1/faculty/{fid}", headers=seed["coord_it"]).status_code == 403
    assert client.patch(f"/api/v1/faculty/{fid}", json={"designation": "X"}, headers=seed["coord_it"]).status_code == 403
    assert client.delete(f"/api/v1/faculty/{fid}", headers=seed["coord_it"]).status_code == 403
    assert client.put(
        f"/api/v1/faculty/{fid}/subjects", json={"course_ids": []}, headers=seed["coord_it"]
    ).status_code == 403
    assert client.get(f"/api/v1/faculty/{fid}/workload", headers=seed["coord_it"]).status_code == 403
    # creating into another department is blocked
    assert client.post(
        "/api/v1/faculty", json=_faculty(seed, employee_code="Z", email="z@x.in"), headers=seed["coord_it"]
    ).status_code == 403

    assert client.get("/api/v1/faculty", headers=seed["coord_it"]).json() == []
    assert len(client.get("/api/v1/faculty", headers=seed["coord_cse"]).json()) == 1
    assert len(client.get("/api/v1/faculty", headers=seed["admin"]).json()) == 1
    # FACULTY role is read-only
    assert client.post(
        "/api/v1/faculty", json=_faculty(seed, employee_code="Y", email="y@x.in"), headers=seed["faculty_user"]
    ).status_code == 403


def test_update_and_filters(client, seed):
    h = seed["coord_cse"]
    fid = client.post("/api/v1/faculty", json=_faculty(seed), headers=h).json()["faculty_id"]
    up = client.patch(f"/api/v1/faculty/{fid}", json={"max_weekly_hours": 20, "is_active": False}, headers=h)
    assert up.status_code == 200 and up.json()["max_weekly_hours"] == 20.0 and up.json()["is_active"] is False
    assert client.patch(f"/api/v1/faculty/{fid}", json={"full_name": None}, headers=h).status_code == 422

    assert client.get("/api/v1/faculty?is_active=true", headers=h).json() == []
    assert len(client.get("/api/v1/faculty?is_active=false", headers=h).json()) == 1
    assert len(client.get("/api/v1/faculty?q=rakesh", headers=h).json()) == 1
    assert client.get("/api/v1/faculty?q=nobody", headers=h).json() == []
    assert len(client.get(f"/api/v1/faculty?course_id={seed['course']}", headers=h).json()) == 1


def test_replace_subjects_and_availability(client, seed):
    h = seed["coord_cse"]
    fid = client.post("/api/v1/faculty", json=_faculty(seed), headers=h).json()["faculty_id"]

    # Re-sending the same course must not trip the unique constraint
    same = client.put(f"/api/v1/faculty/{fid}/subjects", json={"course_ids": [seed["course"]]}, headers=h)
    assert same.status_code == 200 and same.json()["course_ids"] == [seed["course"]]
    cleared = client.put(f"/api/v1/faculty/{fid}/subjects", json={"course_ids": []}, headers=h)
    assert cleared.json()["course_ids"] == []
    assert client.put(
        f"/api/v1/faculty/{fid}/subjects", json={"course_ids": [12345]}, headers=h
    ).status_code == 422

    windows = [
        {"day_of_week": 1, "start_time": "09:00:00", "end_time": "12:00:00"},
        {"day_of_week": 3, "start_time": "10:00:00", "end_time": "15:00:00"},
    ]
    r = client.put(f"/api/v1/faculty/{fid}/availability", json={"windows": windows}, headers=h)
    assert r.status_code == 200 and len(r.json()["availability"]) == 2
    assert client.put(f"/api/v1/faculty/{fid}/availability", json={"windows": []}, headers=h).json()["availability"] == []


def test_workload_and_delete_guard(client, seed, session_factory):
    h = seed["coord_cse"]
    fid = client.post("/api/v1/faculty", json=_faculty(seed, max_weekly_hours=2), headers=h).json()["faculty_id"]

    w = client.get(f"/api/v1/faculty/{fid}/workload", headers=h).json()
    assert w["assigned_hours"] == 0 and w["remaining_hours"] == 2 and w["over_limit"] is False

    db = session_factory()
    def mk(minutes, status):
        s = Session(
            course_id=seed["course"], course_session_type_id=1, department_id=seed["cse"],
            session_type=SessionType.LECTURE, duration_minutes=minutes, status=status,
        )
        db.add(s); db.flush()
        db.add(SessionFaculty(session_id=s.session_id, faculty_id=fid))
    # course_session_type FK: create the config row first
    from app.models.academic import CourseSessionTypeConfig
    db.add(CourseSessionTypeConfig(
        course_id=seed["course"], session_type=SessionType.LECTURE, sessions_per_week=3, duration_minutes=60
    ))
    db.flush()
    mk(60, SessionStatus.DRAFT)
    mk(90, SessionStatus.VALIDATED)
    mk(300, SessionStatus.CANCELLED)       # must not count
    db.commit(); db.close()

    w = client.get(f"/api/v1/faculty/{fid}/workload", headers=h).json()
    assert w["assigned_hours"] == 2.5
    assert w["session_count"] == 2
    assert w["over_limit"] is True and w["remaining_hours"] == -0.5

    # assigned to sessions -> hard delete refused
    assert client.delete(f"/api/v1/faculty/{fid}", headers=h).status_code == 409


def test_delete_unassigned_faculty(client, seed):
    h = seed["coord_cse"]
    fid = client.post("/api/v1/faculty", json=_faculty(seed), headers=h).json()["faculty_id"]
    assert client.delete(f"/api/v1/faculty/{fid}", headers=h).status_code == 204
    assert client.get(f"/api/v1/faculty/{fid}", headers=h).status_code == 404


def test_link_user_account(client, seed):
    h = seed["coord_cse"]
    ok = client.post("/api/v1/faculty", json=_faculty(seed, user_id=seed["faculty_user_id"]), headers=h)
    assert ok.status_code == 201 and ok.json()["user_id"] == seed["faculty_user_id"]
    # same user can't be linked twice
    again = client.post(
        "/api/v1/faculty",
        json=_faculty(seed, employee_code="B", email="b@x.in", user_id=seed["faculty_user_id"]),
        headers=h,
    )
    assert again.status_code == 409
    assert client.post(
        "/api/v1/faculty", json=_faculty(seed, employee_code="C", email="c@x.in", user_id=9999), headers=h
    ).status_code == 422
