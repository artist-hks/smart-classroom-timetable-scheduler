"""SB2/US3/T1 — Department, AcademicYear, Semester, Section, SubBatch CRUD."""


def _section_payload(seed, **over):
    body = {
        "department_id": seed["cse"],
        "academic_year_id": seed["year"],
        "semester_id": seed["sem"],
        "name": "D",
        "student_strength": 60,
    }
    body.update(over)
    return body


def test_requires_authentication(client):
    assert client.get("/api/v1/sections").status_code == 401
    assert client.get("/api/v1/departments").status_code == 401


def test_department_crud_admin_only_writes(client, seed):
    r = client.post("/api/v1/departments", json={"code": "ECE", "name": "Electronics"}, headers=seed["admin"])
    assert r.status_code == 201
    dept_id = r.json()["department_id"]

    # duplicate code -> 409
    dup = client.post("/api/v1/departments", json={"code": "ECE", "name": "x"}, headers=seed["admin"])
    assert dup.status_code == 409

    # coordinator cannot write
    assert client.post(
        "/api/v1/departments", json={"code": "ME", "name": "Mech"}, headers=seed["coord_cse"]
    ).status_code == 403

    up = client.patch(f"/api/v1/departments/{dept_id}", json={"name": "ECE Dept"}, headers=seed["admin"])
    assert up.status_code == 200 and up.json()["name"] == "ECE Dept"
    # explicit null on NOT NULL column -> 422 not 500
    assert client.patch(
        f"/api/v1/departments/{dept_id}", json={"name": None}, headers=seed["admin"]
    ).status_code == 422

    assert client.delete(f"/api/v1/departments/{dept_id}", headers=seed["admin"]).status_code == 204
    assert client.get(f"/api/v1/departments/{dept_id}", headers=seed["admin"]).status_code == 404


def test_department_isolation(client, seed):
    admin_list = client.get("/api/v1/departments", headers=seed["admin"]).json()
    assert len(admin_list) == 2
    coord_list = client.get("/api/v1/departments", headers=seed["coord_cse"]).json()
    assert [d["code"] for d in coord_list] == ["CSE"]
    assert client.get(f"/api/v1/departments/{seed['it']}", headers=seed["coord_cse"]).status_code == 403


def test_department_delete_blocked_when_referenced(client, seed):
    r = client.delete(f"/api/v1/departments/{seed['cse']}", headers=seed["admin"])
    assert r.status_code == 409  # users/courses point at it


def test_academic_year_validation(client, seed):
    bad = client.post(
        "/api/v1/academic-years",
        json={"label": "2030-31", "start_date": "2030-07-01", "end_date": "2030-01-01"},
        headers=seed["admin"],
    )
    assert bad.status_code == 422
    ok = client.post(
        "/api/v1/academic-years",
        json={"label": "2027-28", "start_date": "2027-07-01", "end_date": "2028-06-30"},
        headers=seed["admin"],
    )
    assert ok.status_code == 201
    yid = ok.json()["academic_year_id"]
    # partial update that inverts the range is rejected
    assert client.patch(
        f"/api/v1/academic-years/{yid}", json={"end_date": "2027-01-01"}, headers=seed["admin"]
    ).status_code == 422


def test_semester_crud(client, seed):
    r = client.post("/api/v1/semesters", json={"semester_number": 8, "name": "Semester 8"}, headers=seed["admin"])
    assert r.status_code == 201
    assert client.post(
        "/api/v1/semesters", json={"semester_number": 8, "name": "again"}, headers=seed["admin"]
    ).status_code == 409
    assert client.post(
        "/api/v1/semesters", json={"semester_number": 9, "name": "bad"}, headers=seed["admin"]
    ).status_code == 422
    assert len(client.get("/api/v1/semesters", headers=seed["faculty_user"]).json()) == 2


def test_section_crud_and_validation(client, seed):
    r = client.post("/api/v1/sections", json=_section_payload(seed), headers=seed["coord_cse"])
    assert r.status_code == 201
    sid = r.json()["section_id"]

    # duplicate (dept, year, sem, name) -> 409
    assert client.post("/api/v1/sections", json=_section_payload(seed), headers=seed["coord_cse"]).status_code == 409
    # strength must be > 0
    assert client.post(
        "/api/v1/sections", json=_section_payload(seed, name="E", student_strength=0), headers=seed["coord_cse"]
    ).status_code == 422
    # unknown FK -> 422
    assert client.post(
        "/api/v1/sections", json=_section_payload(seed, name="F", semester_id=999), headers=seed["coord_cse"]
    ).status_code == 422

    up = client.put(f"/api/v1/sections/{sid}", json={"student_strength": 75}, headers=seed["coord_cse"])
    assert up.status_code == 200 and up.json()["student_strength"] == 75

    assert client.delete(f"/api/v1/sections/{sid}", headers=seed["coord_cse"]).status_code == 204


def test_section_department_isolation(client, seed):
    sid = client.post(
        "/api/v1/sections", json=_section_payload(seed), headers=seed["coord_cse"]
    ).json()["section_id"]

    # IT coordinator: cannot read, edit or delete a CSE section, nor create in CSE
    assert client.get(f"/api/v1/sections/{sid}", headers=seed["coord_it"]).status_code == 403
    assert client.patch(f"/api/v1/sections/{sid}", json={"name": "Z"}, headers=seed["coord_it"]).status_code == 403
    assert client.delete(f"/api/v1/sections/{sid}", headers=seed["coord_it"]).status_code == 403
    assert client.post(
        "/api/v1/sections", json=_section_payload(seed, name="Q"), headers=seed["coord_it"]
    ).status_code == 403

    # list is silently scoped; explicitly asking for another dept is 403
    assert client.get("/api/v1/sections", headers=seed["coord_it"]).json() == []
    assert client.get(
        f"/api/v1/sections?department_id={seed['cse']}", headers=seed["coord_it"]
    ).status_code == 403
    # admin sees it, can filter
    assert len(client.get(f"/api/v1/sections?department_id={seed['cse']}", headers=seed["admin"]).json()) == 1

    # FACULTY role may read own department but not write
    assert client.get(f"/api/v1/sections/{sid}", headers=seed["faculty_user"]).status_code == 200
    assert client.patch(f"/api/v1/sections/{sid}", json={"name": "Z"}, headers=seed["faculty_user"]).status_code == 403


def test_sub_batch_crud_and_isolation(client, seed):
    sid = client.post(
        "/api/v1/sections", json=_section_payload(seed), headers=seed["coord_cse"]
    ).json()["section_id"]

    r = client.post(
        "/api/v1/sub-batches",
        json={"section_id": sid, "name": "D1", "student_strength": 20, "practical_group_info": "Lab group A"},
        headers=seed["coord_cse"],
    )
    assert r.status_code == 201
    bid = r.json()["subbatch_id"]
    assert client.post(
        "/api/v1/sub-batches", json={"section_id": sid, "name": "D1", "student_strength": 20},
        headers=seed["coord_cse"],
    ).status_code == 409

    # IT coordinator is locked out via the parent section's department
    assert client.get(f"/api/v1/sub-batches/{bid}", headers=seed["coord_it"]).status_code == 403
    assert client.post(
        "/api/v1/sub-batches", json={"section_id": sid, "name": "D2", "student_strength": 20},
        headers=seed["coord_it"],
    ).status_code == 403
    assert client.get("/api/v1/sub-batches", headers=seed["coord_it"]).json() == []

    assert len(client.get(f"/api/v1/sections/{sid}/sub-batches", headers=seed["coord_cse"]).json()) == 1
    up = client.patch(
        f"/api/v1/sub-batches/{bid}", json={"practical_group_info": None}, headers=seed["coord_cse"]
    )
    assert up.status_code == 200 and up.json()["practical_group_info"] is None

    # parent section can't be deleted while it still has sub-batches
    assert client.delete(f"/api/v1/sections/{sid}", headers=seed["coord_cse"]).status_code == 409
    assert client.delete(f"/api/v1/sub-batches/{bid}", headers=seed["coord_cse"]).status_code == 204
    assert client.delete(f"/api/v1/sections/{sid}", headers=seed["coord_cse"]).status_code == 204


def test_pagination(client, seed):
    for n in "ABC":
        client.post("/api/v1/sections", json=_section_payload(seed, name=n), headers=seed["admin"])
    page = client.get("/api/v1/sections?limit=2&offset=0", headers=seed["admin"]).json()
    assert len(page) == 2
    rest = client.get("/api/v1/sections?limit=2&offset=2", headers=seed["admin"]).json()
    assert len(rest) == 1
    assert client.get("/api/v1/sections?limit=0", headers=seed["admin"]).status_code == 422
