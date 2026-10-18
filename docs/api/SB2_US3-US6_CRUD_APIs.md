# CRUD REST APIs — SB2/US3/T1, US4/T1, US5/T1, US6/T1

Base URL (local): `http://localhost:8000` · Interactive docs: `/docs` (Swagger) · All routes live under **`/api/v1`**.
Owner: Kushagra Gupta · Consumer: frontend (Jangid) — replaces the mock data in `frontend/src/data/*`.

## Conventions

| Topic | Rule |
|---|---|
| Auth | `Authorization: Bearer <access_token>` from `POST /api/auth/login`. Missing/invalid token → `401`. |
| Roles | `SYSTEM_ADMIN` (global), `COORDINATOR` (own department), `FACULTY` / `STUDENT` (read-only, own department). |
| Department isolation (NFR-3) | Non-admins only see/modify rows of their own `department_id`. Single-row access to another department → `403`. List endpoints are silently filtered; explicitly passing another `?department_id=` → `403`. |
| Update | `PATCH` or `PUT` — both do a **partial** update (only send fields you want to change). Explicit `null` on a required field → `422`. |
| Pagination | `?limit=` (1–500, default 100) and `?offset=` (default 0) on every list endpoint. |
| Errors | `404` not found · `403` forbidden · `409` duplicate / still referenced by other rows · `422` validation (incl. unknown foreign keys). Body: `{"detail": "..."}`. |
| Days | `day_of_week`: 1 = Monday … 7 = Sunday. Times: `"HH:MM"` or `"HH:MM:SS"`. |
| Deletes | `204 No Content`. Rows that other tables still reference return `409` instead of deleting. |

## Task 1 — Academic hierarchy (SB2/US3/T1)

| Endpoint | Read | Write |
|---|---|---|
| `/api/v1/departments` (+ `/{id}`) | any user (non-admin sees only own dept) | SYSTEM_ADMIN |
| `/api/v1/academic-years` (+ `/{id}`) | any user | SYSTEM_ADMIN |
| `/api/v1/semesters` (+ `/{id}`) | any user | SYSTEM_ADMIN |
| `/api/v1/sections` (+ `/{id}`) | any user, own dept | SYSTEM_ADMIN, COORDINATOR (own dept) |
| `/api/v1/sub-batches` (+ `/{id}`) | any user, own dept (via parent section) | SYSTEM_ADMIN, COORDINATOR (own dept) |
| `GET /api/v1/sections/{id}/sub-batches` | convenience list of a section's sub-batches | — |

Filters: sections `?department_id&semester_id&academic_year_id`, sub-batches `?section_id`, academic-years `?is_active`.
`department_id` of a section and `section_id` of a sub-batch cannot be changed after creation.

```jsonc
// POST /api/v1/sections
{ "department_id": 1, "academic_year_id": 1, "semester_id": 7, "name": "D", "student_strength": 88 }
// POST /api/v1/sub-batches
{ "section_id": 1, "name": "D1", "student_strength": 30, "practical_group_info": "Lab group A" }
```

## Task 2 — Faculty & workload (SB2/US4/T1)

| Endpoint | Purpose |
|---|---|
| `GET/POST /api/v1/faculty`, `GET/PATCH/PUT/DELETE /api/v1/faculty/{id}` | CRUD. Filters: `?department_id&is_active&course_id&q=` |
| `PUT /api/v1/faculty/{id}/subjects` | Replace subject assignment: `{"course_ids": [1,2]}` |
| `PUT /api/v1/faculty/{id}/availability` | Replace weekly windows: `{"windows": [{"day_of_week":1,"start_time":"09:00","end_time":"16:40"}]}` (`[]` clears) |
| `GET /api/v1/faculty/{id}/workload` | `max_weekly_hours`, `assigned_hours`, `remaining_hours`, `utilization_pct`, `session_count`, `over_limit` |

Read: any user (own dept). Write: SYSTEM_ADMIN or COORDINATOR (own dept).
Create accepts `course_ids` and `availability` inline. `max_weekly_hours` must be > 0 and ≤ 60.
**Workload** is computed from `session_faculty` → `sessions` (sum of `duration_minutes`, excluding `CANCELLED` / `REPLACED_BY_EVENT`); it is never stored.
A faculty member who is assigned to sessions cannot be hard-deleted (`409`) — set `is_active=false` instead.
`user_id` optionally links the faculty row to a login account (must be in the same department, one account per faculty).

## Task 3 — Resources (SB2/US5/T1)

`GET/POST /api/v1/resources`, `GET/PATCH/PUT/DELETE /api/v1/resources/{id}`
Filters: `?department_id&resource_type&is_active&min_capacity&q=` · `resource_type` ∈ `CLASSROOM | LABORATORY | SEMINAR_HALL | AUDITORIUM`.

```jsonc
{ "department_id": 1, "code": "LAB-DBMS-1", "name": "DBMS Lab 1", "resource_type": "LABORATORY",
  "capacity": 40, "building": "Block A", "floor": 2, "is_active": true,
  "equipment": [ {"name": "Desktop PC", "quantity": 40}, {"name": "Projector"} ] }
```

* `department_id: null` = **institute-wide shared** resource (e.g. main auditorium): visible to everyone, writable by SYSTEM_ADMIN only.
* On update, `equipment` (when present) **replaces** the whole list; omit it to leave equipment unchanged.
* `is_active=false` models "under maintenance". Resources already assigned to sessions can't be deleted (`409`).

## Task 4 — TimeSlots & Breaks (SB2/US6/T1)

Institute-wide config. Read: any logged-in user. Write: SYSTEM_ADMIN.

| Endpoint | Notes |
|---|---|
| `GET/POST /api/v1/timeslots`, `GET/PATCH/PUT/DELETE /api/v1/timeslots/{id}` | Filters `?day_of_week&is_active`. Unique `(day_of_week, period)`; slots on the same day must not overlap (`409`). |
| `POST /api/v1/timeslots/bulk` | `{"slots": [...]}` — create a whole grid, all-or-nothing. |
| `GET/POST /api/v1/breaks`, `GET/PATCH/PUT/DELETE /api/v1/breaks/{id}` | `day_of_week: null` = every day. `?day_of_week=` returns breaks that apply on that day (including every-day ones). Overlapping breaks → `409`. |

Breaks are **not** cross-checked against time slots (the solver consumes both).

## Database changes

Migration `b7e2c4a91d05` (after `9fa0565135f6`) adds: `faculty`, `faculty_subjects`, `faculty_availability`, `resources`, `resource_equipment`, `time_slots`, `breaks`,
and the two FK constraints SB2/US2/T2 deferred: `sessions.resource_id → resources` and `session_faculty.faculty_id → faculty`.
Run: `cd backend && alembic upgrade head`.
(If a DB already has `sessions`/`session_faculty` rows pointing at ids that don't exist yet, clean those first or the FK creation fails.)

## Other changes

* `app/main.py`: registers the v1 router and enables CORS for the Vite dev server (`http://localhost:5173`); override with env `CORS_ORIGINS="https://a.com,https://b.com"`.
* Tests: `cd backend && python -m pytest tests` — the new API tests run on in-memory SQLite, no Postgres needed. Added `httpx` to `requirements.txt` (needed by FastAPI's `TestClient`).
* Not included (belongs to later tasks): sum-of-sub-batch-strength ≤ section-strength validation (deferred to SB3/US4/T1 per ERD decision 14), `ResourceAvailability` (SB2/US5/T2), `Course` CRUD.
