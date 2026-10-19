# Timetable Generate API — SB3/US5/T1

`POST /api/v1/timetable/generate` — runs the scheduling pipeline for one department / academic year / semester and saves the result as sessions.

Request/response models: `backend/app/schemas/scheduler.py` (`GenerateTimetableRequest` → `TimetableGenerationResponse`).
Code: `backend/app/api/v1/timetable.py` · Tests: `backend/tests/test_api_timetable.py`.

## Access

| Caller | Result |
|---|---|
| `SYSTEM_ADMIN` | any department |
| `COORDINATOR` | own department only (`403` for another department) |
| `FACULTY` / `STUDENT` | `403` |
| no/invalid token | `401` |

## Pipeline

1. **Load** (read-only): sections + sub-batches, courses + session configs, qualified active faculty (`faculty_subjects`, `faculty_availability`), active resources of the department + institute-wide ones, time slots/breaks.
   * Grid = active `time_slots`, slots overlapping a `breaks` row are marked as breaks. No time slots configured → `create_piet_standard_grid()`.
   * One session set per **course × section**; lectures use the whole section, practicals one session per sub-batch. Labels are prefixed with the section name (`D_CS701_PRACTICAL_SubBatch-D1_S1`).
   * One teacher per course (the least-loaded qualified faculty). A course with no qualified faculty is still scheduled, with a diagnostic.
   * A faculty member with availability windows can only be placed inside them; none = unrestricted.
2. **CP-SAT** (`solve_timetable`) — `time_limit_seconds`.
3. **ML demand** (`predict_room_demand_matrix`) if `enable_ml_demand_prediction`. A failure here is logged and reported in `diagnostics`; it never blocks generation.
4. **Resource allocation + revalidation** (`allocate_resources`) with `preferred_building` and the allocator weights.
5. **GA** (`optimize_timetable`) if `enable_ga_optimization`. If it cannot guarantee zero hard-constraint violations the resource-validated timetable is saved instead (see `diagnostics`).
6. **Persist** in one transaction (only when 2–4 succeeded).

## `scoring_weights`

One field for both engines; keys are routed by name and unknown keys give `422`.

* Room allocation: `capacity`, `department`, `equipment`, `location`, `ml_demand`, `stability`
* GA (soft constraints): `sc01_utilization` … `sc11_grouping_efficiency`

## What is saved

* `sessions` — `scheduled_day`, `start_time`, `end_time`, `resource_id`, `required_capacity`, status **`RESOURCE_ALLOCATED`** (approval later promotes to `VALIDATED`).
* `session_faculty`, `session_participant_groups`; `participant_groups` / `participant_group_members` are created on demand and **reused** when the same set of sub-batches already has a group.
* Re-running **replaces** the previous timetable of that department + semester (sessions of the semester's courses). If any of those sessions is already `VALIDATED` the call fails with `409` and nothing is changed.
* An infeasible run saves nothing and leaves any earlier timetable untouched.

## Responses

| Status | When |
|---|---|
| `200` | Pipeline ran. `is_feasible=true` → timetable saved, `allocations[].session_id` are the saved rows. `is_feasible=false` → nothing saved, see `diagnostics`. |
| `401` / `403` | not logged in / role or department not allowed |
| `409` | an approved (`VALIDATED`) timetable already exists for this department + semester |
| `422` | unknown academic year / department / semester, no sections, no courses/session configs, unknown `scoring_weights` key, or a schema violation |

`utilization` values in the response are percentages (0–100). Without GA, `initial_utilization == final_utilization` (the allocator's average) and the `ga_*_fitness` fields are `null`.

```jsonc
// POST /api/v1/timetable/generate
{ "academic_year_id": 1, "semester": 7, "department_id": 1,
  "time_limit_seconds": 15, "enable_ga_optimization": true,
  "enable_ml_demand_prediction": true, "preferred_building": "Block A" }
```

## Known limitation (engine behaviour, not the endpoint)

CP-SAT (Engine 1) does not know how many rooms exist. If too few rooms of a type exist for sessions that CP-SAT places at the same time, Engine 2 reports the run infeasible (e.g. two lab sub-batches with no shared teacher and a single lab). The response says which session could not be placed.
