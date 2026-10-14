# PIET Smart Classroom & Timetable Scheduler — Frontend

A frontend-only, production-styled implementation of the Smart Classroom & Timetable
Scheduler described in SRS `PIET/CS/2023-27/17` (Team Code Storm). Built with
React + Vite + Tailwind CSS + React Router + Lucide icons, using realistic mock data
modelled on the SRS's own PIET CSE scheduling scenarios (Appendix 10.1, Scenarios A-H).

## 1. Setup & running the project

```bash
cd smart-scheduler
npm install
npm run dev       # starts Vite dev server, prints a local URL (default http://localhost:5173)
```

Other scripts:
```bash
npm run build      # production build to dist/
npm run preview    # preview the production build locally
npm run lint        # oxlint static analysis
```

No environment variables or backend are required - all data is in `src/data/*.js`.

## 2. Signing in

The login screen is a demo role selector (no real backend auth exists yet - see
Section 8). Enter any email/password and pick one of:

- **Timetable Coordinator** - full scheduling workflow (Session Builder, Generate &
  Optimize, Conflicts, Rescheduling, Academic Events, Approvals, Constraints)
- **Faculty** - personal timetable and profile/availability
- **Student** - personal/section timetable, read-only
- **System Administrator** - academic data (sections, faculty, courses, resources)
  and reports, without scheduling-execution screens

You can switch roles anytime from **Settings -> Demo role**.

## 3. Feature / module map (SRS -> page)

| SRS section | Requirement area | Page / component |
|---|---|---|
| 2.4, 3.13 | Role-based dashboards | `Dashboard.jsx` (3 role-specific views) |
| 3.1 | Academic structure (Dept -> Semester -> Section -> Sub-Batch) | `Sections.jsx` |
| 3.2 | Faculty / course / resource / time-slot input data | `Faculty.jsx`, `Courses.jsx`, `Resources.jsx` |
| 3.3, 5.1.1 | Session & participant management (Session Builder) | `SessionBuilder.jsx` - 6-step wizard with live FR-3.3.2 validation |
| 3.4-3.6 | CP-SAT feasibility -> Smart Resource Allocation -> GA optimization pipeline | `GenerateOptimize.jsx` - animated pipeline + generation/optimization reports |
| 3.7, 7.5 | ML room-demand prediction | `Reports.jsx` (ML Prediction card) |
| 3.8, 3.8.1 | Smart Resource Allocation & revalidation | Reflected in `SessionBuilder` resource-type step + `Resources.jsx` utilization |
| 3.9, 5.1.2 | Dynamic rescheduling (triggers, affected participants, ranked alternatives) | `Rescheduling.jsx` |
| 3.10 | Academic events & overlap flagging | `AcademicEvents.jsx` |
| 3.11 | Timetable validation / conflict diagnostics | `Conflicts.jsx` |
| 3.12 | Approval & versioning lifecycle | `Approvals.jsx` |
| 3.14 | Reporting & analytics (generation, optimization, utilization, workload, ML, rescheduling) | `Reports.jsx` |
| 3.15 | Export (Should-Have) | Print/Export buttons on `Timetable.jsx` / `Reports.jsx` (UI only - see assumptions) |
| 5.1 | Setup / scheduling / dynamic / governance / analytics screens | Full sidebar navigation |
| Section-, Faculty-, Resource-wise views | `Timetable.jsx` - custom minute-precision `WeeklyGrid` |
| Notifications (FR-3.9.8) | `Notifications.jsx` |

## 4. Technology stack & rationale

- **React 19 + Vite** - required by the brief; Vite gives fast dev/build.
- **Tailwind CSS v3** - utility-first styling; a custom design system (`ink` navy,
  `paper` background, `gold` accent) is defined in `tailwind.config.js` so the whole
  app shares one visual language instead of ad hoc classes.
- **React Router v7** - client-side routing with role-gated routes.
- **lucide-react** - icon set matching the sidebar/navbar/status iconography.

No state-management library, CSS-in-JS, or UI kit was added - React Context
(`AuthContext`, `ToastContext`) is sufficient for a frontend-only demo of this size,
per the brief's "don't use unnecessary technologies" instruction.

## 5. Project structure

```
src/
|- components/
|   |- layout/      AppShell, Sidebar, Topbar, navConfig (role-aware nav)
|   |- ui/           Button, Card, Badge, Modal, Field/Input/Select, EmptyState,
|   |                 StatCard, PageHeader
|   |- tables/       DataTable, TableToolbar (search + filter)
|   `- timetable/    WeeklyGrid (minute-precision grid), Legend
|- pages/            One file per route (18 pages, see table above)
|- data/              Mock data: academicStructure, faculty, courses, timetable,
|                      operations (conflicts/events/versions/notifications/reports)
|- context/          AuthContext (mock RBAC), ToastContext (form feedback)
|- utils/            scheduling.js - participant/strength/time-overlap helpers
`- App.jsx / main.jsx
```

## 6. Assumptions made (per brief Section 29 / SRS Section 9)

1. **Authentication is mocked.** The SRS specifies JWT-based REST auth (NFR-3); this
   frontend uses a local role-selector at login since no backend exists yet. The
   login form is structured (email/password fields, error states) so a real
   `POST /api/auth/login` call can replace `login(role)` in `AuthContext.jsx`
   without touching any page.
2. **CP-SAT / GA / ML are simulated.** `GenerateOptimize.jsx` animates through the
   pipeline stages and then displays static report data from `data/operations.js`.
   A real backend would replace the `runPipeline` timer with actual API polling.
3. **One department's data (CSE) is fully populated**; IT/ECE/ME appear in
   dropdowns and stat counts per SRS 2.4 department scoping, but detailed session
   data is only seeded for CSE, Sections C/D (Sem 7) and A/B (Sem 5), directly
   reflecting the SRS's own Scenario A-H examples.
4. **A single published timetable version (V2) is shown in the Timetable page**,
   with V3 shown as "In Review" in Approvals - reflecting FR-3.12.2 (only
   Approved/Published versions are visible to Faculty/Student), while still letting
   the Coordinator see the review-stage version in the Approvals page.
5. **Dynamic Rescheduling's "ranked alternatives"** (Section 5.1.2) are illustrative
   fixed options triggered by any selected faculty member, rather than a live
   solver - this matches the brief's "do not create fake functionality that can't
   realistically connect to an API" instruction: the UI/data shape is real, the
   computation is mocked.
6. **Export buttons (PDF/Excel/print)** are present as UI affordances (SRS 3.15 is
   a Should-Have) but do not generate real files, since that requires a backend
   rendering service or a heavier client-side PDF library not requested in the brief.
7. **Attendance management is out of scope**, per SRS Section 1.2 explicitly
   excluding it from this system's deliverables.

## 7. What requires real backend/API integration

Per SRS Section 5.2/10.5, the following are stubbed with mock data and are designed
to be swapped for real REST calls without restructuring the UI:

- Authentication (`POST /api/auth/login`, JWT storage/refresh)
- All CRUD on Sections/Sub-Batches, Faculty, Courses, Resources, Constraints
- `POST /api/sessions/schedule` (Session Builder save)
- CP-SAT feasibility run, Smart Resource Allocation, GA optimization endpoints
- ML prediction service (room demand)
- Dynamic rescheduling compute + apply endpoints
- Academic Events CRUD + overlap detection
- Approval/versioning state transitions
- Notification delivery (currently local mock list)
- Real PDF/Excel export generation

## 8. Testing checklist (brief Section 30)

- [x] `npm install` completes without errors
- [x] `npm run build` completes without errors (verified - see build log)
- [x] `npm run dev` serves the app (Vite dev server)
- [x] No compilation errors; all imports resolve
- [x] `npx oxlint src` - 0 errors (3 benign "fast refresh" advisories on context
      files that intentionally export both a provider and a hook - a standard,
      harmless pattern)
- [x] All sidebar routes render without runtime errors during code review
- [x] Buttons, modals, and forms wired to local state (add/edit dialogs give toast
      feedback via `ToastContext`)
- [x] Filters (department, semester, resource type, day) actually filter the
      rendered mock data in Sections/Faculty/Courses/Resources/Timetable
- [x] Search inputs filter table rows client-side
- [x] Empty states implemented for: no timetable for a filter combination, no
      conflicts open, no academic events, no faculty/courses/resources matching
      search, no notifications
- [x] Responsive layout: sidebar collapses to an icon rail on desktop and becomes
      an off-canvas drawer with backdrop on mobile; tables scroll horizontally on
      narrow screens; the weekly timetable grid scrolls horizontally below ~760px
- [x] Role-based route guards (`RequireRole`) redirect non-Coordinator/Admin users
      away from management and scheduling-execution screens

## 9. Known limitations (frontend-only demo)

- Data resets on page reload (no persistence layer).
- The Session Builder's "Save session" appends nothing to the visible timetable
  (no shared state store wired to `data/timetable.js` at runtime) - it validates
  and shows a success toast, consistent with "structure the frontend so a real
  backend can be integrated later" rather than faking a write to static data.
- Conflict "Mark resolved" and Notification "read" states are local to the
  component's React state and reset on reload.
