"""SB2/US5/T1 — Resource CRUD (rooms, labs, capacity, equipment)."""


def _resource(seed, **over):
    body = {
        "department_id": seed["cse"],
        "code": "LAB-DBMS-1",
        "name": "DBMS Lab 1",
        "resource_type": "LABORATORY",
        "capacity": 40,
        "building": "Block A",
        "floor": 2,
        "equipment": [{"name": "Desktop PC", "quantity": 40}, {"name": "Projector"}],
    }
    body.update(over)
    return body


def test_create_get_resource(client, seed):
    r = client.post("/api/v1/resources", json=_resource(seed), headers=seed["coord_cse"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["resource_type"] == "LABORATORY"
    assert {e["name"]: e["quantity"] for e in body["equipment"]} == {"Desktop PC": 40, "Projector": 1}
    assert client.get(f"/api/v1/resources/{body['resource_id']}", headers=seed["faculty_user"]).status_code == 200


def test_resource_validation(client, seed):
    h = seed["coord_cse"]
    assert client.post("/api/v1/resources", json=_resource(seed, capacity=0), headers=h).status_code == 422
    assert client.post("/api/v1/resources", json=_resource(seed, resource_type="GARAGE"), headers=h).status_code == 422
    dup_eq = [{"name": "Projector"}, {"name": "projector"}]
    assert client.post("/api/v1/resources", json=_resource(seed, equipment=dup_eq), headers=h).status_code == 422
    assert client.post("/api/v1/resources", json=_resource(seed, department_id=999), headers=seed["admin"]).status_code == 422
    assert client.post("/api/v1/resources", json=_resource(seed), headers=h).status_code == 201
    assert client.post("/api/v1/resources", json=_resource(seed), headers=h).status_code == 409


def test_resource_department_isolation(client, seed):
    rid = client.post("/api/v1/resources", json=_resource(seed), headers=seed["coord_cse"]).json()["resource_id"]
    assert client.get(f"/api/v1/resources/{rid}", headers=seed["coord_it"]).status_code == 403
    assert client.patch(f"/api/v1/resources/{rid}", json={"capacity": 10}, headers=seed["coord_it"]).status_code == 403
    assert client.delete(f"/api/v1/resources/{rid}", headers=seed["coord_it"]).status_code == 403
    assert client.post(
        "/api/v1/resources", json=_resource(seed, code="X"), headers=seed["coord_it"]
    ).status_code == 403
    assert client.get("/api/v1/resources", headers=seed["coord_it"]).json() == []
    assert client.get(
        f"/api/v1/resources?department_id={seed['cse']}", headers=seed["coord_it"]
    ).status_code == 403


def test_shared_resources(client, seed):
    shared = _resource(seed, department_id=None, code="AUD-1", name="Main Auditorium",
                       resource_type="AUDITORIUM", capacity=500, equipment=[])
    # coordinators can't create institute-wide resources; admin can
    assert client.post("/api/v1/resources", json=shared, headers=seed["coord_cse"]).status_code == 403
    r = client.post("/api/v1/resources", json=shared, headers=seed["admin"])
    assert r.status_code == 201 and r.json()["department_id"] is None
    rid = r.json()["resource_id"]

    # every department can see it, none can modify it
    for who in ("coord_cse", "coord_it", "faculty_user"):
        assert client.get(f"/api/v1/resources/{rid}", headers=seed[who]).status_code == 200
        assert len(client.get("/api/v1/resources", headers=seed[who]).json()) == 1
    assert client.patch(f"/api/v1/resources/{rid}", json={"capacity": 1}, headers=seed["coord_it"]).status_code == 403
    assert client.delete(f"/api/v1/resources/{rid}", headers=seed["coord_cse"]).status_code == 403
    assert client.patch(f"/api/v1/resources/{rid}", json={"capacity": 450}, headers=seed["admin"]).status_code == 200


def test_update_equipment_and_fields(client, seed):
    h = seed["coord_cse"]
    rid = client.post("/api/v1/resources", json=_resource(seed), headers=h).json()["resource_id"]

    up = client.patch(
        f"/api/v1/resources/{rid}",
        json={
            "capacity": 45, "is_active": False,
            "equipment": [{"name": "Desktop PC", "quantity": 45}, {"name": "Whiteboard"}],
        },
        headers=h,
    )
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["capacity"] == 45 and body["is_active"] is False
    assert {e["name"]: e["quantity"] for e in body["equipment"]} == {"Desktop PC": 45, "Whiteboard": 1}

    # omitting equipment leaves it untouched; null is rejected; [] clears it
    assert len(client.patch(f"/api/v1/resources/{rid}", json={"floor": 3}, headers=h).json()["equipment"]) == 2
    assert client.patch(f"/api/v1/resources/{rid}", json={"equipment": None}, headers=h).status_code == 422
    assert client.patch(f"/api/v1/resources/{rid}", json={"equipment": []}, headers=h).json()["equipment"] == []
    assert client.patch(f"/api/v1/resources/{rid}", json={"capacity": None}, headers=h).status_code == 422


def test_filters_and_delete(client, seed):
    h = seed["coord_cse"]
    client.post("/api/v1/resources", json=_resource(seed), headers=h)
    client.post("/api/v1/resources", json=_resource(
        seed, code="CR-204", name="Room 204", resource_type="CLASSROOM", capacity=90, equipment=[]), headers=h)

    assert len(client.get("/api/v1/resources?resource_type=CLASSROOM", headers=h).json()) == 1
    assert len(client.get("/api/v1/resources?min_capacity=60", headers=h).json()) == 1
    assert len(client.get("/api/v1/resources?q=dbms", headers=h).json()) == 1
    assert len(client.get("/api/v1/resources?is_active=true", headers=h).json()) == 2

    rid = client.get("/api/v1/resources?q=CR-204", headers=h).json()[0]["resource_id"]
    assert client.delete(f"/api/v1/resources/{rid}", headers=h).status_code == 204
    assert client.get(f"/api/v1/resources/{rid}", headers=h).status_code == 404
