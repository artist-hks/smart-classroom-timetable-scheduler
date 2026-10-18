"""SB2/US6/T1 — TimeSlot & Break configuration."""


def _slot(day=1, period=1, start="09:00:00", end="10:00:00", **extra):
    return {"day_of_week": day, "period": period, "start_time": start, "end_time": end, **extra}


def test_read_for_all_write_admin_only(client, seed):
    assert client.get("/api/v1/timeslots").status_code == 401
    assert client.post("/api/v1/timeslots", json=_slot(), headers=seed["coord_cse"]).status_code == 403
    assert client.post("/api/v1/timeslots", json=_slot(), headers=seed["admin"]).status_code == 201
    assert len(client.get("/api/v1/timeslots", headers=seed["faculty_user"]).json()) == 1
    assert client.post("/api/v1/breaks", json={"label": "x", "start_time": "12:00:00", "end_time": "13:00:00"},
                       headers=seed["coord_cse"]).status_code == 403


def test_timeslot_validation(client, seed):
    h = seed["admin"]
    assert client.post("/api/v1/timeslots", json=_slot(day=8), headers=h).status_code == 422
    assert client.post("/api/v1/timeslots", json=_slot(period=0), headers=h).status_code == 422
    assert client.post("/api/v1/timeslots", json=_slot(start="10:00:00", end="09:00:00"), headers=h).status_code == 422

    assert client.post("/api/v1/timeslots", json=_slot(), headers=h).status_code == 201
    # same (day, period) -> 409 ; overlapping time on same day -> 409 ; other day is fine
    assert client.post("/api/v1/timeslots", json=_slot(start="13:00:00", end="14:00:00"), headers=h).status_code == 409
    assert client.post("/api/v1/timeslots", json=_slot(period=2, start="09:30:00", end="10:30:00"), headers=h).status_code == 409
    assert client.post("/api/v1/timeslots", json=_slot(day=2), headers=h).status_code == 201


def test_timeslot_update_delete_filters(client, seed):
    h = seed["admin"]
    a = client.post("/api/v1/timeslots", json=_slot(label="P1"), headers=h).json()
    b = client.post("/api/v1/timeslots", json=_slot(period=2, start="10:00:00", end="11:00:00"), headers=h).json()

    up = client.patch(f"/api/v1/timeslots/{a['time_slot_id']}", json={"label": "Period One", "is_active": False}, headers=h)
    assert up.status_code == 200 and up.json()["label"] == "Period One"
    # moving slot A so it collides with B
    assert client.patch(f"/api/v1/timeslots/{a['time_slot_id']}", json={"end_time": "10:30:00"}, headers=h).status_code == 409
    # partial update that inverts the range
    assert client.patch(f"/api/v1/timeslots/{b['time_slot_id']}", json={"start_time": "12:00:00"}, headers=h).status_code == 422
    # clearing the optional label is allowed
    assert client.patch(f"/api/v1/timeslots/{a['time_slot_id']}", json={"label": None}, headers=h).json()["label"] is None

    assert len(client.get("/api/v1/timeslots?is_active=true", headers=h).json()) == 1
    assert len(client.get("/api/v1/timeslots?day_of_week=1", headers=h).json()) == 2
    assert client.get("/api/v1/timeslots?day_of_week=2", headers=h).json() == []
    assert client.delete(f"/api/v1/timeslots/{a['time_slot_id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/timeslots/{a['time_slot_id']}", headers=h).status_code == 404


def test_bulk_create_grid_is_atomic(client, seed):
    h = seed["admin"]
    grid = [_slot(day=d, period=p, start=f"{8 + p:02d}:00:00", end=f"{9 + p:02d}:00:00")
            for d in range(1, 6) for p in range(1, 4)]
    r = client.post("/api/v1/timeslots/bulk", json={"slots": grid}, headers=h)
    assert r.status_code == 201 and len(r.json()) == 15

    # one conflicting slot in the batch -> nothing is created
    batch = [_slot(day=6, period=1), _slot(day=1, period=1)]
    assert client.post("/api/v1/timeslots/bulk", json={"slots": batch}, headers=h).status_code == 409
    assert client.get("/api/v1/timeslots?day_of_week=6", headers=h).json() == []
    # clash inside the request itself
    twin = [_slot(day=7, period=1), _slot(day=7, period=1)]
    assert client.post("/api/v1/timeslots/bulk", json={"slots": twin}, headers=h).status_code == 422
    assert client.post("/api/v1/timeslots/bulk", json={"slots": []}, headers=h).status_code == 422


def test_break_crud_and_overlap(client, seed):
    h = seed["admin"]
    lunch = client.post(
        "/api/v1/breaks", json={"label": "Lunch", "start_time": "12:00:00", "end_time": "13:00:00"}, headers=h
    )
    assert lunch.status_code == 201 and lunch.json()["day_of_week"] is None
    bid = lunch.json()["break_id"]

    # overlaps the every-day lunch on any day -> 409
    assert client.post("/api/v1/breaks", json={"label": "Tea", "day_of_week": 2, "start_time": "12:30:00",
                       "end_time": "13:30:00"}, headers=h).status_code == 409
    # a non-overlapping day-specific break is fine and is listed for that day only
    tea = client.post("/api/v1/breaks", json={"label": "Tea", "day_of_week": 2, "start_time": "15:00:00",
                      "end_time": "15:15:00"}, headers=h)
    assert tea.status_code == 201
    assert len(client.get("/api/v1/breaks?day_of_week=2", headers=h).json()) == 2
    assert len(client.get("/api/v1/breaks?day_of_week=3", headers=h).json()) == 1

    assert client.post("/api/v1/breaks", json={"label": "Bad", "start_time": "14:00:00", "end_time": "13:00:00"},
                       headers=h).status_code == 422
    assert client.patch(f"/api/v1/breaks/{bid}", json={"end_time": "11:00:00"}, headers=h).status_code == 422
    up = client.patch(f"/api/v1/breaks/{bid}", json={"label": "Lunch Break"}, headers=h)
    assert up.status_code == 200 and up.json()["label"] == "Lunch Break"
    assert client.patch(f"/api/v1/breaks/{tea.json()['break_id']}", json={"day_of_week": None}, headers=h).status_code == 200

    assert client.delete(f"/api/v1/breaks/{bid}", headers=h).status_code == 204
    assert client.get(f"/api/v1/breaks/{bid}", headers=h).status_code == 404
