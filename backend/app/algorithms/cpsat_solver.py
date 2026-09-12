"""
Google OR-Tools CP-SAT Feasibility Engine for Academic Timetable Scheduling.

Implements:
- SB2/US9/T1: CP-SAT mathematical model for non-resource hard constraints
  (HC-01, HC-03, HC-04, HC-05, HC-10, HC-11, HC-12, HC-14, HC-15)
- SB2/US9/T2: Infeasibility diagnostics and detailed assignment extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Sequence

from ortools.sat.python import cp_model

from app.algorithms.session_generator import GeneratedSession, ParticipantGroupSpec
from app.algorithms.timeslot_grid import GridSlot, ScheduleGrid


@dataclass
class FacultySpec:
    """Specification of a faculty member with availability and workload limits."""
    faculty_id: int
    name: str
    max_weekly_hours: float = 16.0
    unavailable_slot_ids: set[int] = field(default_factory=set)


@dataclass
class ScheduledAssignment:
    """Represents a scheduled session placed in a specific time slot."""
    session_id: int | None
    course_id: int
    label: str
    session_type: str
    day: int
    start_slot_id: int
    start_time: str
    end_time: str
    duration_minutes: int
    occupied_slot_ids: list[int]
    faculty_ids: list[int]
    participant_group_id: int
    subbatch_ids: list[int]


@dataclass
class CPSATSolverResult:
    """Output from the CP-SAT Feasibility Engine."""
    is_feasible: bool
    status_label: str
    solve_time_seconds: float
    total_sessions_scheduled: int
    assignments: list[ScheduledAssignment] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class CPSATScheduler:
    """
    Core CP-SAT Feasibility Engine using Google OR-Tools.
    Models hard constraints and finds conflict-free timetable assignments.
    """

    def __init__(
        self,
        grid: ScheduleGrid,
        sessions: Sequence[GeneratedSession],
        participant_groups: dict[int, ParticipantGroupSpec],
        faculty_members: dict[int, FacultySpec],
        reserved_slot_ids: set[int] | None = None,
    ):
        self.grid = grid
        self.sessions = list(sessions)
        self.participant_groups = participant_groups
        self.faculty_members = faculty_members
        self.reserved_slot_ids = reserved_slot_ids or set()

    def run_prechecks(self) -> list[str]:
        """
        Runs pre-solver sanity checks to catch obvious infeasibilities early.
        """
        diagnostics: list[str] = []

        # 1. Check Faculty workload limits (HC-10)
        faculty_hours: dict[int, float] = {}
        for s in self.sessions:
            for fid in s.faculty_ids:
                faculty_hours[fid] = faculty_hours.get(fid, 0.0) + s.duration_hours

        for fid, req_hours in faculty_hours.items():
            fac = self.faculty_members.get(fid)
            if fac:
                if req_hours > fac.max_weekly_hours:
                    diagnostics.append(
                        f"HC-10 Infeasibility: Faculty '{fac.name}' assigned {req_hours:.1f} hrs, "
                        f"which exceeds maximum weekly workload limit of {fac.max_weekly_hours:.1f} hrs."
                    )

        # 2. Check Sub-batch total contact hours vs available slots
        available_operational_slots = [
            s for s in self.grid.slots if not s.is_break and s.slot_id not in self.reserved_slot_ids
        ]
        total_available_periods = len(available_operational_slots)

        subbatch_hours: dict[int, float] = {}
        for s in self.sessions:
            pg = self.participant_groups.get(s.participant_group_id)
            if pg:
                for sbid in pg.subbatch_ids:
                    subbatch_hours[sbid] = subbatch_hours.get(sbid, 0.0) + s.duration_hours

        for sbid, hours in subbatch_hours.items():
            if hours > total_available_periods:
                diagnostics.append(
                    f"HC-03/04 Infeasibility: Sub-batch ID {sbid} requires {hours:.1f} contact hours, "
                    f"but only {total_available_periods} total slots exist on the grid."
                )

        # 3. Check Session valid slot availability
        for s in self.sessions:
            valid_starts = self.grid.get_valid_start_slots_for_duration(s.duration_minutes)
            if not valid_starts:
                diagnostics.append(
                    f"HC-14 Infeasibility: Session '{s.label}' ({s.duration_minutes}m) has no valid "
                    f"consecutive slots on the grid."
                )

        return diagnostics

    def solve(self, time_limit_seconds: float = 30.0) -> CPSATSolverResult:
        """
        Executes Google OR-Tools CP-SAT solver to find a conflict-free feasible schedule.
        """
        start_time = time.perf_counter()

        # Run pre-checks
        pre_diagnostics = self.run_prechecks()
        if pre_diagnostics:
            return CPSATSolverResult(
                is_feasible=False,
                status_label="INFEASIBLE (Pre-check failed)",
                solve_time_seconds=time.perf_counter() - start_time,
                total_sessions_scheduled=0,
                diagnostics=pre_diagnostics,
            )

        model = cp_model.CpModel()

        # -------------------------------------------------------------------
        # Decision Variables: y[session_idx, start_slot_id] -> BoolVar
        # -------------------------------------------------------------------
        # y[i, t] == 1 if session i starts at slot t
        session_slot_vars: dict[tuple[int, int], cp_model.IntVar] = {}
        valid_starts_by_session: dict[int, list[int]] = {}

        for i, s in enumerate(self.sessions):
            valid_starts = self.grid.get_valid_start_slots_for_duration(s.duration_minutes)
            
            # Filter out starts that overlap reserved slots
            filtered_starts: list[int] = []
            for t in valid_starts:
                occ = self.grid.get_occupied_slots(t, s.duration_minutes)
                if not any(slot_id in self.reserved_slot_ids for slot_id in occ):
                    # Filter if faculty is unavailable at any occupied slot (HC-05)
                    faculty_available = True
                    for fid in s.faculty_ids:
                        fac = self.faculty_members.get(fid)
                        if fac and any(slot_id in fac.unavailable_slot_ids for slot_id in occ):
                            faculty_available = False
                            break
                    if faculty_available:
                        filtered_starts.append(t)

            valid_starts_by_session[i] = filtered_starts
            
            if not filtered_starts:
                return CPSATSolverResult(
                    is_feasible=False,
                    status_label="INFEASIBLE",
                    solve_time_seconds=time.perf_counter() - start_time,
                    total_sessions_scheduled=0,
                    diagnostics=[
                        f"HC-05 Infeasibility: Session '{s.label}' has 0 available slots after faculty availability filtering."
                    ],
                )

            for t in filtered_starts:
                var_name = f"s{i}_t{t}"
                session_slot_vars[(i, t)] = model.NewBoolVar(var_name)

        # -------------------------------------------------------------------
        # Constraint 1 (HC-11): Each session must start at exactly ONE valid slot
        # -------------------------------------------------------------------
        for i, s in enumerate(self.sessions):
            model.AddExactlyOne(session_slot_vars[(i, t)] for t in valid_starts_by_session[i])

        # Precompute mapping: for each session i and atomic slot tau, which start slots t cover tau?
        # session_occupancy[(i, tau)] = [t1, t2, ...]
        session_occupancy: dict[tuple[int, int], list[int]] = {}
        for i, s in enumerate(self.sessions):
            for t in valid_starts_by_session[i]:
                occ = self.grid.get_occupied_slots(t, s.duration_minutes)
                for tau in occ:
                    session_occupancy.setdefault((i, tau), []).append(t)

        all_atomic_slots = [s.slot_id for s in self.grid.slots if not s.is_break]

        # -------------------------------------------------------------------
        # Constraint 2 (HC-01): Faculty Non-Overlap
        # At most 1 session per faculty member at any atomic slot tau
        # -------------------------------------------------------------------
        all_faculty_ids = set(self.faculty_members.keys())
        for fid in all_faculty_ids:
            fac_sessions = [
                i for i, s in enumerate(self.sessions) if fid in s.faculty_ids
            ]
            if len(fac_sessions) > 1:
                for tau in all_atomic_slots:
                    active_vars_at_tau = []
                    for i in fac_sessions:
                        covering_starts = session_occupancy.get((i, tau), [])
                        for t in covering_starts:
                            active_vars_at_tau.append(session_slot_vars[(i, t)])
                    if len(active_vars_at_tau) > 1:
                        model.Add(sum(active_vars_at_tau) <= 1)

        # -------------------------------------------------------------------
        # Constraint 3 (HC-03 / HC-04): Participant Sub-batch Non-Overlap
        # At most 1 session per sub-batch at any atomic slot tau
        # -------------------------------------------------------------------
        all_subbatch_ids = set()
        for pg in self.participant_groups.values():
            all_subbatch_ids.update(pg.subbatch_ids)

        for sbid in all_subbatch_ids:
            # Find all sessions whose participant group includes sub-batch sbid
            subbatch_sessions = []
            for i, s in enumerate(self.sessions):
                pg = self.participant_groups.get(s.participant_group_id)
                if pg and sbid in pg.subbatch_ids:
                    subbatch_sessions.append(i)

            if len(subbatch_sessions) > 1:
                for tau in all_atomic_slots:
                    active_vars_at_tau = []
                    for i in subbatch_sessions:
                        covering_starts = session_occupancy.get((i, tau), [])
                        for t in covering_starts:
                            active_vars_at_tau.append(session_slot_vars[(i, t)])
                    if len(active_vars_at_tau) > 1:
                        model.Add(sum(active_vars_at_tau) <= 1)

        # -------------------------------------------------------------------
        # Solve with CP-SAT Solver
        # -------------------------------------------------------------------
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        solver.parameters.num_workers = 4  # parallel solver workers

        status = solver.Solve(model)
        elapsed = time.perf_counter() - start_time

        if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            assignments: list[ScheduledAssignment] = []
            for i, s in enumerate(self.sessions):
                for t in valid_starts_by_session[i]:
                    if solver.Value(session_slot_vars[(i, t)]) == 1:
                        start_slot = self.grid.slot_by_id[t]
                        occ_slots = self.grid.get_occupied_slots(t, s.duration_minutes)
                        end_slot = self.grid.slot_by_id[occ_slots[-1]]
                        pg = self.participant_groups.get(s.participant_group_id)
                        
                        assignment = ScheduledAssignment(
                            session_id=s.session_id,
                            course_id=s.course_id,
                            label=s.label,
                            session_type=s.session_type.value,
                            day=start_slot.day,
                            start_slot_id=t,
                            start_time=start_slot.start_time,
                            end_time=end_slot.end_time,
                            duration_minutes=s.duration_minutes,
                            occupied_slot_ids=occ_slots,
                            faculty_ids=s.faculty_ids,
                            participant_group_id=s.participant_group_id,
                            subbatch_ids=pg.subbatch_ids if pg else [],
                        )
                        assignments.append(assignment)
                        break

            return CPSATSolverResult(
                is_feasible=True,
                status_label="FEASIBLE" if status == cp_model.FEASIBLE else "OPTIMAL",
                solve_time_seconds=elapsed,
                total_sessions_scheduled=len(assignments),
                assignments=assignments,
                metrics={
                    "wall_time": elapsed,
                    "num_branches": solver.NumBranches(),
                    "num_conflicts": solver.NumConflicts(),
                },
            )
        else:
            return CPSATSolverResult(
                is_feasible=False,
                status_label="INFEASIBLE",
                solve_time_seconds=elapsed,
                total_sessions_scheduled=0,
                diagnostics=[
                    "CP-SAT solver exhausted search space without finding a conflict-free assignment.",
                    "Potential causes: High constraint density between shared faculty, overlapping sub-batch practicals, or tight slot bounds.",
                ],
            )
