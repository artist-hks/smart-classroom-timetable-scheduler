"""
Dynamic Rescheduling Engine with Affected-Participant Scoping & Alternative Ranking.

Implements:
- SB3/US6/T1: Trigger detection (faculty leave, room outage, event insertion) and
              precise affected entity scoping (sessions, sub-batches, faculty, resources)
              per FR-3.9.1, FR-3.9.2.
- SB3/US6/T2: Subproblem isolation, reduced solver re-run with preservation of unaffected
              assignments (EV-8 Rescheduling Stability >= 85%), ranked alternative resolutions,
              and change tracking per FR-3.9.3 - FR-3.9.7.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import datetime
import enum
from typing import Any, Sequence

from app.algorithms.cpsat_solver import CPSATScheduler, FacultySpec, ScheduledAssignment
from app.algorithms.resource_allocator import (
    AllocatedSession,
    ResourceSpec,
    SmartResourceAllocator,
)
from app.algorithms.session_generator import GeneratedSession, ParticipantGroupSpec
from app.algorithms.timeslot_grid import GridSlot, ScheduleGrid
from app.models.academic import ResourceType, SessionType


class RescheduleTriggerType(str, enum.Enum):
    """Supported constraint-change and dynamic rescheduling triggers (FR-3.9.1)."""
    FACULTY_UNAVAILABLE = "FACULTY_UNAVAILABLE"       # Faculty leave, illness, emergency
    FACULTY_EARLY_DEPARTURE = "FACULTY_EARLY_DEPARTURE" # Faculty leaves after period N
    ROOM_UNAVAILABLE = "ROOM_UNAVAILABLE"             # Maintenance, power/AC outage, repair
    EMERGENCY_ROOM_CHANGE = "EMERGENCY_ROOM_CHANGE"   # Shift session to another room immediately
    ACADEMIC_EVENT = "ACADEMIC_EVENT"                 # Workshop, alumni talk, campus seminar
    SESSION_CANCELLATION = "SESSION_CANCELLATION"     # Class cancelled for holiday/event
    ADDITIONAL_SESSION = "ADDITIONAL_SESSION"         # Extra makeup lecture inserted
    SECTION_REGROUPING = "SECTION_REGROUPING"
    RESOURCE_REASSIGNMENT = "RESOURCE_REASSIGNMENT"
    CONSTRAINT_MODIFICATION = "CONSTRAINT_MODIFICATION"


@dataclass
class RescheduleTrigger:
    """Specification of a schedule perturbation / dynamic event trigger."""
    trigger_type: RescheduleTriggerType
    day: int                                      # Day of the week (1 to 5)
    slot_ids: list[int]                           # Atomic slot IDs impacted
    faculty_id: int | None = None                 # Impacted faculty (if applicable)
    resource_id: int | None = None                # Impacted resource (if applicable)
    subbatch_id: int | None = None                # Specific affected sub-batch (if scoped)
    reason: str = ""                              # Human-readable justification
    event_details: dict[str, Any] | None = None   # Title, participants, required venue for events


@dataclass
class AffectedScope:
    """
    Result of affected-participant scoping (FR-3.9.2).
    Separates the timetable into affected subproblem and unaffected preserved schedules.
    """
    trigger: RescheduleTrigger
    affected_sessions: list[AllocatedSession]
    unaffected_sessions: list[AllocatedSession]
    affected_session_ids: set[int | None]
    affected_subbatch_ids: set[int]
    affected_faculty_ids: set[int]
    affected_resource_ids: set[int]
    preservation_percentage: float


@dataclass
class RescheduleAuditEntry:
    """Audit log entry for change tracking (FR-3.9.7)."""
    session_label: str
    trigger_type: str
    reason: str
    old_day: int
    old_slot_ids: list[int]
    old_start_time: str
    old_end_time: str
    old_resource_code: str
    old_faculty_ids: list[int]
    new_day: int
    new_slot_ids: list[int]
    new_start_time: str
    new_end_time: str
    new_resource_code: str
    new_faculty_ids: list[int]
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


@dataclass
class RescheduleResolution:
    """A validated candidate resolution option presented to the Coordinator (FR-3.9.6)."""
    resolution_id: str
    title: str
    strategy_type: str  # "TIME_SHIFT", "FACULTY_SUBSTITUTE", "ROOM_CHANGE", "EVENT_REPLACEMENT"
    changed_sessions_count: int
    stability_percentage: float
    disruption_score: float  # Lower is better (fewer changes, preferred slots)
    resolved_allocations: list[AllocatedSession]
    audit_entries: list[RescheduleAuditEntry] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class ReschedulingResult:
    """Final output of the Dynamic Rescheduling Engine."""
    is_successful: bool
    status_label: str
    scope: AffectedScope
    ranked_resolutions: list[RescheduleResolution] = field(default_factory=list)
    best_resolution: RescheduleResolution | None = None
    diagnostics: list[str] = field(default_factory=list)


class DynamicRescheduler:
    """
    Engine 4 in the 4-engine scheduling architecture.
    
    Handles runtime schedule perturbations by:
    1. Detecting trigger and computing precise affected scope (FR-3.9.1, FR-3.9.2)
    2. Isolating the affected subproblem while freezing unaffected sessions (FR-3.9.3, FR-3.9.4)
    3. Generating ranked alternative resolutions (FR-3.9.5, FR-3.9.6)
    4. Recording change-tracking audit logs (FR-3.9.7)
    """

    def __init__(
        self,
        grid: ScheduleGrid,
        resources: Sequence[ResourceSpec],
        faculty_members: dict[int, FacultySpec],
        participant_groups: dict[int, ParticipantGroupSpec] | None = None,
        substitute_faculty_pool: dict[int, list[int]] | None = None,  # course_id -> list[faculty_id]
        reserved_slot_ids: set[int] | None = None,
    ):
        self.grid = grid
        self.resources = list(resources)
        self.resources_by_id = {r.resource_id: r for r in self.resources}
        self.faculty_members = faculty_members
        self.participant_groups = participant_groups or {}
        self.substitute_pool = substitute_faculty_pool or {}
        self.reserved_slot_ids = reserved_slot_ids or set()

    # -----------------------------------------------------------------------
    # Step 1: Trigger Detection & Affected Scoping (FR-3.9.1, FR-3.9.2)
    # -----------------------------------------------------------------------

    def compute_affected_scope(
        self,
        current_schedule: Sequence[AllocatedSession],
        trigger: RescheduleTrigger,
    ) -> AffectedScope:
        """
        Scans current schedule and isolates the precise affected sessions.
        
        Affected-Participants Concept:
        - Scopes impact strictly to affected sub-batch, faculty, and room.
        - Does NOT unnecessarily drag unrelated sub-batches or sections into rescheduling.
        """
        affected: list[AllocatedSession] = []
        unaffected: list[AllocatedSession] = []
        trigger_slots = set(trigger.slot_ids)

        for session in current_schedule:
            is_affected = False

            # Check matching day
            if session.day == trigger.day:
                session_slots = set(session.occupied_slot_ids)
                has_time_overlap = bool(session_slots & trigger_slots)

                if has_time_overlap:
                    # 1. Faculty leave / departure
                    if trigger.trigger_type in (
                        RescheduleTriggerType.FACULTY_UNAVAILABLE,
                        RescheduleTriggerType.FACULTY_EARLY_DEPARTURE,
                    ):
                        if trigger.faculty_id in session.faculty_ids:
                            is_affected = True

                    # 2. Room / Lab outage
                    elif trigger.trigger_type in (
                        RescheduleTriggerType.ROOM_UNAVAILABLE,
                        RescheduleTriggerType.EMERGENCY_ROOM_CHANGE,
                    ):
                        if session.resource_id == trigger.resource_id:
                            is_affected = True

                    # 3. Academic Event Insertion
                    elif trigger.trigger_type == RescheduleTriggerType.ACADEMIC_EVENT:
                        # Event affects regular sessions if room, faculty, or subbatches overlap
                        ev_details = trigger.event_details or {}
                        ev_room = trigger.resource_id
                        ev_subbatches = set(ev_details.get("subbatch_ids", []))
                        ev_faculty = set(ev_details.get("faculty_ids", []))

                        if ev_room and session.resource_id == ev_room:
                            is_affected = True
                        elif ev_subbatches and bool(set(session.subbatch_ids) & ev_subbatches):
                            is_affected = True
                        elif ev_faculty and bool(set(session.faculty_ids) & ev_faculty):
                            is_affected = True

                    elif trigger.trigger_type == RescheduleTriggerType.SESSION_CANCELLATION:
                        is_affected = trigger.subbatch_id is None or trigger.subbatch_id in session.subbatch_ids

                    elif trigger.trigger_type == RescheduleTriggerType.SECTION_REGROUPING:
                        changed_subbatches = set((trigger.event_details or {}).get("subbatch_ids", []))
                        is_affected = trigger.subbatch_id in session.subbatch_ids if trigger.subbatch_id is not None else bool(set(session.subbatch_ids) & changed_subbatches)

                    elif trigger.trigger_type == RescheduleTriggerType.RESOURCE_REASSIGNMENT:
                        is_affected = trigger.resource_id is None or session.resource_id == trigger.resource_id

                    # 4. Specific Sub-batch target
                    elif trigger.subbatch_id is not None:
                        if trigger.subbatch_id in session.subbatch_ids:
                            is_affected = True

            if is_affected:
                affected.append(session)
            else:
                unaffected.append(session)

        total_sessions = len(current_schedule)
        preservation = round((len(unaffected) / total_sessions) * 100.0, 2) if total_sessions > 0 else 100.0

        affected_sids = {s.session_id for s in affected}
        affected_sb = {sb for s in affected for sb in s.subbatch_ids}
        affected_fac = {f for s in affected for f in s.faculty_ids}
        affected_res = {s.resource_id for s in affected}

        return AffectedScope(
            trigger=trigger,
            affected_sessions=affected,
            unaffected_sessions=unaffected,
            affected_session_ids=affected_sids,
            affected_subbatch_ids=affected_sb,
            affected_faculty_ids=affected_fac,
            affected_resource_ids=affected_res,
            preservation_percentage=preservation,
        )

    # -----------------------------------------------------------------------
    # Step 2: Alternative Candidate Resolutions Generation (FR-3.9.3 - FR-3.9.6)
    # -----------------------------------------------------------------------

    def resolve_rescheduling(
        self,
        current_schedule: Sequence[AllocatedSession],
        trigger: RescheduleTrigger,
    ) -> ReschedulingResult:
        """
        Executes dynamic rescheduling by exploring and ranking alternative resolutions.
        Enforces 100% hard constraint validation on all proposed resolutions.
        """
        if not trigger.slot_ids or any(slot_id not in self.grid.slot_by_id for slot_id in trigger.slot_ids):
            empty_scope = self.compute_affected_scope(current_schedule, trigger)
            return ReschedulingResult(False, "INVALID_TRIGGER", empty_scope, diagnostics=[
                "Rescheduling trigger must reference at least one valid schedule slot."
            ])
        scope = self.compute_affected_scope(current_schedule, trigger)

        if not scope.affected_sessions:
            if trigger.trigger_type == RescheduleTriggerType.ADDITIONAL_SESSION:
                return ReschedulingResult(False, "INFEASIBLE_MISSING_SESSION_SPEC", scope, diagnostics=[
                    "Additional-session rescheduling requires a complete session specification and candidate participant group."
                ])
            return ReschedulingResult(
                is_successful=True,
                status_label="NO_AFFECTED_SESSIONS",
                scope=scope,
                diagnostics=["Trigger did not collide with any scheduled sessions."],
            )

        resolutions: list[RescheduleResolution] = []

        reduced_opt = self._try_reduced_solver_strategy(scope)
        if reduced_opt:
            resolutions.append(reduced_opt)

        # Build occupancy map of the UNAFFECTED (frozen) sessions
        # (day, slot_id) -> booked entities
        frozen_fac_slots: dict[tuple[int, int], set[int]] = {}
        frozen_sb_slots: dict[tuple[int, int], set[int]] = {}
        frozen_res_slots: dict[tuple[int, int], int] = {}

        for u in scope.unaffected_sessions:
            for sid in u.occupied_slot_ids:
                key = (u.day, sid)
                frozen_fac_slots.setdefault(key, set()).update(u.faculty_ids)
                frozen_sb_slots.setdefault(key, set()).update(u.subbatch_ids)
                frozen_res_slots[key] = u.resource_id

        # Strategy 1: Room Reassignment (if ROOM_UNAVAILABLE or EMERGENCY_ROOM_CHANGE)
        if trigger.trigger_type in (
            RescheduleTriggerType.ROOM_UNAVAILABLE,
            RescheduleTriggerType.EMERGENCY_ROOM_CHANGE,
        ):
            res_opt = self._try_room_reassignment_strategy(
                scope=scope,
                frozen_res_slots=frozen_res_slots,
            )
            if res_opt:
                resolutions.append(res_opt)

        # Strategy 2: Faculty Substitution (if FACULTY_UNAVAILABLE)
        if trigger.trigger_type in (
            RescheduleTriggerType.FACULTY_UNAVAILABLE,
            RescheduleTriggerType.FACULTY_EARLY_DEPARTURE,
        ):
            sub_opt = self._try_faculty_substitution_strategy(
                scope=scope,
                frozen_fac_slots=frozen_fac_slots,
            )
            if sub_opt:
                resolutions.append(sub_opt)

        # Strategy 3: Time Slot Shift (Always applicable: move affected session to another conflict-free slot)
        shift_opt = self._try_time_slot_shift_strategy(
            scope=scope,
            frozen_fac_slots=frozen_fac_slots,
            frozen_sb_slots=frozen_sb_slots,
            frozen_res_slots=frozen_res_slots,
        )
        if shift_opt:
            resolutions.append(shift_opt)

        # Strategy 4: Academic Event Replacement (if ACADEMIC_EVENT)
        if trigger.trigger_type == RescheduleTriggerType.ACADEMIC_EVENT:
            event_opt = self._try_event_replacement_strategy(
                scope=scope,
            )
            if event_opt:
                resolutions.append(event_opt)

        if trigger.trigger_type == RescheduleTriggerType.SESSION_CANCELLATION:
            resolutions.append(self._build_cancellation_resolution(scope))

        validated_resolutions: list[RescheduleResolution] = []
        for resolution in resolutions:
            errors = self._validate_resolution(resolution.resolved_allocations)
            if errors:
                resolution.diagnostics.extend(errors)
            else:
                validated_resolutions.append(resolution)
        resolutions = validated_resolutions

        # Rank resolutions by disruption score (lower disruption = higher ranking)
        resolutions.sort(key=lambda r: (r.disruption_score, -r.stability_percentage))

        is_successful = len(resolutions) > 0
        best_res = resolutions[0] if resolutions else None

        return ReschedulingResult(
            is_successful=is_successful,
            status_label="RESOLVED" if is_successful else "INFEASIBLE_NO_ALTERNATIVE",
            scope=scope,
            ranked_resolutions=resolutions,
            best_resolution=best_res,
            diagnostics=[] if is_successful else ["No conflict-free alternative resolution found on schedule grid."],
        )

    def _build_cancellation_resolution(self, scope: AffectedScope) -> RescheduleResolution:
        preserved = list(scope.unaffected_sessions)
        changed = len(scope.affected_sessions)
        total = len(preserved) + changed
        stability = round(len(preserved) / total * 100.0, 2) if total else 100.0
        audit = [RescheduleAuditEntry(
            session_label=session.label,
            trigger_type=scope.trigger.trigger_type.value,
            reason=scope.trigger.reason or "Session cancelled",
            old_day=session.day,
            old_slot_ids=list(session.occupied_slot_ids),
            old_start_time=session.start_time,
            old_end_time=session.end_time,
            old_resource_code=session.resource_code,
            old_faculty_ids=list(session.faculty_ids),
            new_day=session.day,
            new_slot_ids=[],
            new_start_time="",
            new_end_time="",
            new_resource_code="",
            new_faculty_ids=[],
        ) for session in scope.affected_sessions]
        return RescheduleResolution(
            resolution_id="RES_CANCEL",
            title="Cancel Affected Sessions",
            strategy_type="SESSION_CANCELLATION",
            changed_sessions_count=changed,
            stability_percentage=stability,
            disruption_score=float(changed),
            resolved_allocations=preserved,
            audit_entries=audit,
        )

    def _try_reduced_solver_strategy(self, scope: AffectedScope) -> RescheduleResolution | None:
        """Re-solve only affected sessions, allocate around frozen sessions, then validate the full result."""
        group_specs: dict[int, ParticipantGroupSpec] = {}
        generated: list[GeneratedSession] = []
        try:
            for assignment in scope.affected_sessions:
                group = group_specs.get(assignment.participant_group_id)
                if group is None:
                    group_specs[assignment.participant_group_id] = ParticipantGroupSpec(
                        participant_group_id=assignment.participant_group_id,
                        department_id=assignment.department_id,
                        label=f"Reschedule group {assignment.participant_group_id}",
                        subbatch_ids=list(assignment.subbatch_ids),
                        combined_strength=assignment.required_capacity,
                    )
                elif set(group.subbatch_ids) != set(assignment.subbatch_ids):
                    return None
                generated.append(GeneratedSession(
                    session_id=assignment.session_id,
                    course_id=assignment.course_id,
                    course_session_type_id=0,
                    department_id=assignment.department_id,
                    session_type=SessionType(assignment.session_type),
                    duration_minutes=assignment.duration_minutes,
                    required_resource_type=assignment.required_resource_type,
                    required_capacity=assignment.required_capacity,
                    participant_group_id=assignment.participant_group_id,
                    faculty_ids=list(assignment.faculty_ids),
                    label=assignment.label,
                    required_equipment=dict(assignment.required_equipment),
                ))
        except (ValueError, TypeError):
            return None

        frozen_slot_ids = {
            sid for session in scope.unaffected_sessions for sid in session.occupied_slot_ids
        }
        reserved = set(self.reserved_slot_ids)
        if scope.trigger.trigger_type == RescheduleTriggerType.ACADEMIC_EVENT:
            reserved.update(scope.trigger.slot_ids)

        faculty_specs = copy.deepcopy(self.faculty_members)
        if scope.trigger.trigger_type in (RescheduleTriggerType.FACULTY_UNAVAILABLE, RescheduleTriggerType.FACULTY_EARLY_DEPARTURE):
            faculty = faculty_specs.get(scope.trigger.faculty_id)
            if faculty:
                faculty.unavailable_slot_ids.update(scope.trigger.slot_ids)

        solver_result = CPSATScheduler(
            grid=self.grid,
            sessions=generated,
            participant_groups=group_specs,
            faculty_members=faculty_specs,
            reserved_slot_ids=reserved,
        ).solve()
        if not solver_result.is_feasible or len(solver_result.assignments) != len(generated):
            return None

        resources = copy.deepcopy(self.resources)
        resources_by_id = {resource.resource_id: resource for resource in resources}
        for session in scope.unaffected_sessions:
            resource = resources_by_id.get(session.resource_id)
            if resource:
                resource.unavailable_slot_ids.update(session.occupied_slot_ids)
        if scope.trigger.trigger_type in (RescheduleTriggerType.ROOM_UNAVAILABLE, RescheduleTriggerType.EMERGENCY_ROOM_CHANGE):
            resource = resources_by_id.get(scope.trigger.resource_id)
            if resource:
                resource.unavailable_slot_ids.update(scope.trigger.slot_ids)

        allocation_result = SmartResourceAllocator(resources).allocate_and_validate(solver_result.assignments)
        if not allocation_result.is_feasible or not allocation_result.validation_passed:
            return None

        replacements = {allocation.label: allocation for allocation in allocation_result.allocations}
        if len(replacements) != len(scope.affected_sessions):
            return None
        resolved = list(scope.unaffected_sessions) + list(allocation_result.allocations)
        audit_entries: list[RescheduleAuditEntry] = []
        original_by_label = {assignment.label: assignment for assignment in scope.affected_sessions}
        for label, updated in replacements.items():
            original = original_by_label.get(label)
            if original is None:
                return None
            audit_entries.append(RescheduleAuditEntry(
                session_label=label,
                trigger_type=scope.trigger.trigger_type.value,
                reason=scope.trigger.reason or "Affected sessions re-solved by CP-SAT",
                old_day=original.day,
                old_slot_ids=list(original.occupied_slot_ids),
                old_start_time=original.start_time,
                old_end_time=original.end_time,
                old_resource_code=original.resource_code,
                old_faculty_ids=list(original.faculty_ids),
                new_day=updated.day,
                new_slot_ids=list(updated.occupied_slot_ids),
                new_start_time=updated.start_time,
                new_end_time=updated.end_time,
                new_resource_code=updated.resource_code,
                new_faculty_ids=list(updated.faculty_ids),
            ))

        changed_count = len(scope.affected_sessions)
        total = len(resolved)
        stability = round((len(scope.unaffected_sessions) / total) * 100.0, 2) if total else 100.0
        preference_penalty = sum(
            1.0 for updated in allocation_result.allocations for fid in updated.faculty_ids
            if faculty_specs.get(fid) and faculty_specs[fid].preferred_slot_ids
            and not all(sid in faculty_specs[fid].preferred_slot_ids for sid in updated.occupied_slot_ids)
        )
        room_change_penalty = sum(1.0 for entry in audit_entries if entry.old_resource_code != entry.new_resource_code)
        return RescheduleResolution(
            resolution_id="RES_REDUCED_CPSAT",
            title="Reduced CP-SAT Reschedule with Resource Reallocation",
            strategy_type="TIME_SHIFT",
            changed_sessions_count=changed_count,
            stability_percentage=stability,
            disruption_score=2.0 * changed_count + preference_penalty + room_change_penalty,
            resolved_allocations=resolved,
            audit_entries=audit_entries,
        )

    def _validate_resolution(self, allocations: Sequence[AllocatedSession]) -> list[str]:
        errors: list[str] = []
        faculty_slots: set[tuple[int, int, int]] = set()
        subbatch_slots: set[tuple[int, int, int]] = set()
        resource_slots: set[tuple[int, int, int]] = set()
        faculty_hours: dict[int, float] = {}
        for assignment in allocations:
            if assignment.start_slot_id not in self.grid.slot_by_id:
                errors.append(f"HC-12 Violation: '{assignment.label}' has an invalid start slot.")
                continue
            try:
                expected = self.grid.get_occupied_slots(assignment.start_slot_id, assignment.duration_minutes)
            except (KeyError, IndexError, StopIteration, ValueError):
                expected = []
            if expected != assignment.occupied_slot_ids or self.grid.slot_by_id[assignment.start_slot_id].day != assignment.day:
                errors.append(f"HC-12/14 Violation: '{assignment.label}' does not occupy a valid continuous interval.")
                continue
            if assignment.session_type != SessionType.EVENT.value and any(sid in self.reserved_slot_ids for sid in expected):
                errors.append(f"HC-15 Violation: '{assignment.label}' overlaps a reserved institutional event slot.")
            if not assignment.subbatch_ids or len(set(assignment.subbatch_ids)) != len(assignment.subbatch_ids):
                errors.append(f"HC-13 Violation: '{assignment.label}' has an invalid participant group.")
            group = self.participant_groups.get(assignment.participant_group_id)
            if self.participant_groups and (group is None or set(group.subbatch_ids) != set(assignment.subbatch_ids)):
                errors.append(f"HC-13 Violation: '{assignment.label}' participant group does not match its registered sub-batches.")
            resource = self.resources_by_id.get(assignment.resource_id)
            if not resource:
                errors.append(f"HC-02/06 Violation: '{assignment.label}' references missing resource {assignment.resource_id}.")
            else:
                if not resource.is_active or any(sid in resource.unavailable_slot_ids for sid in expected):
                    errors.append(f"HC-06 Violation: resource '{resource.code}' is inactive or unavailable for '{assignment.label}'.")
                if resource.capacity < assignment.required_capacity:
                    errors.append(f"HC-07/16 Violation: resource '{resource.code}' lacks capacity for '{assignment.label}'.")
                if assignment.required_resource_type is not None and resource.resource_type != assignment.required_resource_type:
                    errors.append(f"HC-08/09 Violation: resource '{resource.code}' has the wrong type for '{assignment.label}'.")
                if resource.department_id is not None and resource.department_id != assignment.department_id:
                    errors.append(f"Department Access Violation: resource '{resource.code}' is not accessible to '{assignment.label}'.")
                if any(resource.equipment.get(name.strip().lower(), 0) < qty for name, qty in assignment.required_equipment.items()):
                    errors.append(f"HC-09 Violation: resource '{resource.code}' lacks required equipment for '{assignment.label}'.")
            for sid in expected:
                for fid in assignment.faculty_ids:
                    if fid not in self.faculty_members:
                        errors.append(f"HC-01/05 Violation: '{assignment.label}' references unknown faculty {fid}.")
                    faculty = self.faculty_members.get(fid)
                    if faculty and sid in faculty.unavailable_slot_ids:
                        errors.append(f"HC-05 Violation: faculty {fid} unavailable for '{assignment.label}' at slot {sid}.")
                    fk = (assignment.day, sid, fid)
                    if fk in faculty_slots:
                        errors.append(f"HC-01 Violation: faculty {fid} has overlapping sessions at slot {sid}.")
                    faculty_slots.add(fk)
                    faculty_hours[fid] = faculty_hours.get(fid, 0.0) + assignment.duration_minutes / max(1, len(expected)) / 60.0
                for sbid in assignment.subbatch_ids:
                    sk = (assignment.day, sid, sbid)
                    if sk in subbatch_slots:
                        errors.append(f"HC-03/04 Violation: sub-batch {sbid} has overlapping sessions at slot {sid}.")
                    subbatch_slots.add(sk)
                rk = (assignment.day, sid, assignment.resource_id)
                if rk in resource_slots:
                    errors.append(f"HC-02 Violation: resource {assignment.resource_id} has overlapping sessions at slot {sid}.")
                resource_slots.add(rk)
        for fid, hours in faculty_hours.items():
            faculty = self.faculty_members.get(fid)
            if faculty and hours > faculty.max_weekly_hours:
                errors.append(f"HC-10 Violation: faculty {fid} exceeds maximum weekly workload.")
        return errors

    # -----------------------------------------------------------------------
    # Strategy Implementations
    # -----------------------------------------------------------------------

    def _try_room_reassignment_strategy(
        self,
        scope: AffectedScope,
        frozen_res_slots: dict[tuple[int, int], int],
    ) -> RescheduleResolution | None:
        """
        Attempts to resolve room outage by keeping exact time slot and faculty,
        and reallocating an alternative active room matching type and capacity.
        """
        resolved: list[AllocatedSession] = list(scope.unaffected_sessions)
        audit_entries: list[RescheduleAuditEntry] = []
        temp_bookings = copy.deepcopy(frozen_res_slots)

        for aff in scope.affected_sessions:
            req_type = aff.required_resource_type or ResourceType.CLASSROOM
            candidates = [
                r for r in self.resources
                if r.is_active
                and r.resource_id != scope.trigger.resource_id
                and r.resource_type == req_type
                and r.capacity >= aff.required_capacity
                and (r.department_id is None or r.department_id == aff.department_id)
                and all(r.equipment.get(name.strip().lower(), 0) >= qty for name, qty in aff.required_equipment.items())
            ]

            # Filter candidates free at aff.occupied_slot_ids
            free_cand = None
            for cand in candidates:
                # Check unavailable slots (HC-06)
                if any(sid in cand.unavailable_slot_ids for sid in aff.occupied_slot_ids):
                    continue
                # Check clashes with frozen bookings (HC-02)
                is_clashing = any(
                    temp_bookings.get((aff.day, sid)) == cand.resource_id
                    for sid in aff.occupied_slot_ids
                )
                if not is_clashing:
                    free_cand = cand
                    break

            if not free_cand:
                return None  # Room reassignment failed for at least one session

            # Record booking
            for sid in aff.occupied_slot_ids:
                temp_bookings[(aff.day, sid)] = free_cand.resource_id

            new_alloc = copy.deepcopy(aff)
            new_alloc.resource_id = free_cand.resource_id
            new_alloc.resource_code = free_cand.code
            new_alloc.resource_name = free_cand.name
            new_alloc.resource_capacity = free_cand.capacity
            new_alloc.resource_type = free_cand.resource_type
            resolved.append(new_alloc)

            audit_entries.append(
                RescheduleAuditEntry(
                    session_label=aff.label,
                    trigger_type=scope.trigger.trigger_type.value,
                    reason=scope.trigger.reason or "Emergency room reassignment",
                    old_day=aff.day,
                    old_slot_ids=aff.occupied_slot_ids,
                    old_start_time=aff.start_time,
                    old_end_time=aff.end_time,
                    old_resource_code=aff.resource_code,
                    old_faculty_ids=aff.faculty_ids,
                    new_day=new_alloc.day,
                    new_slot_ids=new_alloc.occupied_slot_ids,
                    new_start_time=new_alloc.start_time,
                    new_end_time=new_alloc.end_time,
                    new_resource_code=new_alloc.resource_code,
                    new_faculty_ids=new_alloc.faculty_ids,
                )
            )

        changed_count = len(scope.affected_sessions)
        stability = round((len(scope.unaffected_sessions) / (len(scope.unaffected_sessions) + changed_count)) * 100.0, 2)

        return RescheduleResolution(
            resolution_id="RES_ROOM_SWAP",
            title="Alternative Room Reassignment",
            strategy_type="ROOM_CHANGE",
            changed_sessions_count=changed_count,
            stability_percentage=stability,
            disruption_score=1.0 * changed_count,  # Minimal disruption: time and faculty unchanged
            resolved_allocations=resolved,
            audit_entries=audit_entries,
        )

    def _try_faculty_substitution_strategy(
        self,
        scope: AffectedScope,
        frozen_fac_slots: dict[tuple[int, int], set[int]],
    ) -> RescheduleResolution | None:
        """
        Attempts to resolve faculty leave by finding a qualified substitute faculty
        free at that exact time slot.
        """
        resolved: list[AllocatedSession] = list(scope.unaffected_sessions)
        audit_entries: list[RescheduleAuditEntry] = []
        temp_fac_slots = copy.deepcopy(frozen_fac_slots)

        for aff in scope.affected_sessions:
            subs = self.substitute_pool.get(aff.course_id, [])
            free_sub = None

            for sub_fid in subs:
                if sub_fid == scope.trigger.faculty_id:
                    continue
                sub_spec = self.faculty_members.get(sub_fid)
                if not sub_spec:
                    continue

                # Check sub availability (HC-05)
                if any(sid in sub_spec.unavailable_slot_ids for sid in aff.occupied_slot_ids):
                    continue

                # Check conflict with frozen sessions (HC-01)
                is_clashing = any(
                    sub_fid in temp_fac_slots.get((aff.day, sid), set())
                    for sid in aff.occupied_slot_ids
                )
                if not is_clashing:
                    free_sub = sub_fid
                    break

            if not free_sub:
                return None  # No substitute available

            # Record booking
            for sid in aff.occupied_slot_ids:
                temp_fac_slots.setdefault((aff.day, sid), set()).add(free_sub)

            new_alloc = copy.deepcopy(aff)
            # Replace unavailable faculty with substitute
            new_fac_list = [f if f != scope.trigger.faculty_id else free_sub for f in aff.faculty_ids]
            new_alloc.faculty_ids = new_fac_list
            resolved.append(new_alloc)

            sub_name = self.faculty_members[free_sub].name
            audit_entries.append(
                RescheduleAuditEntry(
                    session_label=aff.label,
                    trigger_type=scope.trigger.trigger_type.value,
                    reason=f"Substitute faculty assigned ({sub_name}) due to {scope.trigger.reason}",
                    old_day=aff.day,
                    old_slot_ids=aff.occupied_slot_ids,
                    old_start_time=aff.start_time,
                    old_end_time=aff.end_time,
                    old_resource_code=aff.resource_code,
                    old_faculty_ids=aff.faculty_ids,
                    new_day=new_alloc.day,
                    new_slot_ids=new_alloc.occupied_slot_ids,
                    new_start_time=new_alloc.start_time,
                    new_end_time=new_alloc.end_time,
                    new_resource_code=new_alloc.resource_code,
                    new_faculty_ids=new_alloc.faculty_ids,
                )
            )

        changed_count = len(scope.affected_sessions)
        stability = round((len(scope.unaffected_sessions) / (len(scope.unaffected_sessions) + changed_count)) * 100.0, 2)

        return RescheduleResolution(
            resolution_id="RES_FACULTY_SUB",
            title="Substitute Faculty Assignment",
            strategy_type="FACULTY_SUBSTITUTE",
            changed_sessions_count=changed_count,
            stability_percentage=stability,
            disruption_score=1.5 * changed_count,  # Slightly higher than room swap because faculty changes
            resolved_allocations=resolved,
            audit_entries=audit_entries,
        )

    def _try_time_slot_shift_strategy(
        self,
        scope: AffectedScope,
        frozen_fac_slots: dict[tuple[int, int], set[int]],
        frozen_sb_slots: dict[tuple[int, int], set[int]],
        frozen_res_slots: dict[tuple[int, int], int],
    ) -> RescheduleResolution | None:
        """
        Shifts affected sessions to other conflict-free time slots on the grid,
        preserving the session's faculty and room where possible (or assigning a free room).
        """
        resolved: list[AllocatedSession] = list(scope.unaffected_sessions)
        audit_entries: list[RescheduleAuditEntry] = []

        temp_fac = copy.deepcopy(frozen_fac_slots)
        temp_sb = copy.deepcopy(frozen_sb_slots)
        temp_res = copy.deepcopy(frozen_res_slots)

        for aff in scope.affected_sessions:
            starts = self.grid.get_valid_start_slots_for_duration(aff.duration_minutes)
            starts.sort(key=lambda start_id: (
                not all(
                    not self.faculty_members.get(fid)
                    or not self.faculty_members[fid].preferred_slot_ids
                    or all(sid in self.faculty_members[fid].preferred_slot_ids
                           for sid in self.grid.get_occupied_slots(start_id, aff.duration_minutes))
                    for fid in aff.faculty_ids
                ),
                start_id != aff.start_slot_id,
            ))
            placed = False

            # Search across all operational days for an open slot
            for start_id in starts:
                start_slot = self.grid.slot_by_id[start_id]
                occ_slots = self.grid.get_occupied_slots(start_id, aff.duration_minutes)
                day = start_slot.day

                # If trigger was room outage and room is same on trigger day/slots, skip
                if (
                    scope.trigger.trigger_type == RescheduleTriggerType.ROOM_UNAVAILABLE
                    and aff.resource_id == scope.trigger.resource_id
                    and day == scope.trigger.day
                    and any(sid in scope.trigger.slot_ids for sid in occ_slots)
                ):
                    continue

                # 1. Faculty Clash Check (HC-01) & Availability (HC-05)
                fac_conflict = False
                for fid in aff.faculty_ids:
                    # If this faculty is on leave at trigger.day / trigger.slot_ids, skip
                    if (
                        scope.trigger.trigger_type in (
                            RescheduleTriggerType.FACULTY_UNAVAILABLE,
                            RescheduleTriggerType.FACULTY_EARLY_DEPARTURE,
                        )
                        and fid == scope.trigger.faculty_id
                        and day == scope.trigger.day
                        and any(sid in scope.trigger.slot_ids for sid in occ_slots)
                    ):
                        fac_conflict = True
                        break

                    fac = self.faculty_members.get(fid)
                    if fac and any(sid in fac.unavailable_slot_ids for sid in occ_slots):
                        fac_conflict = True
                        break

                    if any(fid in temp_fac.get((day, sid), set()) for sid in occ_slots):
                        fac_conflict = True
                        break

                if fac_conflict:
                    continue

                # 2. Sub-batch Clash Check (HC-03, HC-04)
                sb_conflict = False
                for sbid in aff.subbatch_ids:
                    if any(sbid in temp_sb.get((day, sid), set()) for sid in occ_slots):
                        sb_conflict = True
                        break
                if sb_conflict:
                    continue

                # 3. Resource Check (HC-02)
                # First try original room; if occupied, search other compatible rooms
                req_type = aff.required_resource_type or ResourceType.CLASSROOM
                original_room = self.resources_by_id.get(aff.resource_id)
                candidate_rooms = [original_room] if original_room and original_room.is_active and original_room.resource_type == req_type and original_room.capacity >= aff.required_capacity and (original_room.department_id is None or original_room.department_id == aff.department_id) and all(original_room.equipment.get(name.strip().lower(), 0) >= qty for name, qty in aff.required_equipment.items()) else []
                # Add other rooms of same type
                candidate_rooms.extend([
                    r for r in self.resources
                    if r.resource_id != aff.resource_id
                    and r.is_active
                    and r.resource_type == req_type
                    and r.capacity >= aff.required_capacity
                    and (r.department_id is None or r.department_id == aff.department_id)
                    and all(r.equipment.get(name.strip().lower(), 0) >= qty for name, qty in aff.required_equipment.items())
                ])

                chosen_room = None
                for rm in candidate_rooms:
                    if any(sid in rm.unavailable_slot_ids for sid in occ_slots):
                        continue
                    if not any(temp_res.get((day, sid)) == rm.resource_id for sid in occ_slots):
                        chosen_room = rm
                        break

                if not chosen_room:
                    continue

                # Placed successfully!
                for sid in occ_slots:
                    temp_fac.setdefault((day, sid), set()).update(aff.faculty_ids)
                    temp_sb.setdefault((day, sid), set()).update(aff.subbatch_ids)
                    temp_res[(day, sid)] = chosen_room.resource_id

                end_slot = self.grid.slot_by_id[occ_slots[-1]]
                new_alloc = copy.deepcopy(aff)
                new_alloc.day = day
                new_alloc.start_slot_id = start_id
                new_alloc.start_time = start_slot.start_time
                new_alloc.end_time = end_slot.end_time
                new_alloc.occupied_slot_ids = occ_slots
                new_alloc.resource_id = chosen_room.resource_id
                new_alloc.resource_code = chosen_room.code
                new_alloc.resource_name = chosen_room.name
                new_alloc.resource_capacity = chosen_room.capacity
                new_alloc.resource_type = chosen_room.resource_type
                resolved.append(new_alloc)

                audit_entries.append(
                    RescheduleAuditEntry(
                        session_label=aff.label,
                        trigger_type=scope.trigger.trigger_type.value,
                        reason=f"Time slot shifted to Day {day} {new_alloc.start_time}-{new_alloc.end_time} due to {scope.trigger.reason}",
                        old_day=aff.day,
                        old_slot_ids=aff.occupied_slot_ids,
                        old_start_time=aff.start_time,
                        old_end_time=aff.end_time,
                        old_resource_code=aff.resource_code,
                        old_faculty_ids=aff.faculty_ids,
                        new_day=new_alloc.day,
                        new_slot_ids=new_alloc.occupied_slot_ids,
                        new_start_time=new_alloc.start_time,
                        new_end_time=new_alloc.end_time,
                        new_resource_code=new_alloc.resource_code,
                        new_faculty_ids=new_alloc.faculty_ids,
                    )
                )
                placed = True
                break

            if not placed:
                return None  # Infeasible to shift all affected sessions

        changed_count = len(scope.affected_sessions)
        stability = round((len(scope.unaffected_sessions) / (len(scope.unaffected_sessions) + changed_count)) * 100.0, 2)
        preference_penalty = sum(
            1.0 for assignment in scope.affected_sessions for fid in assignment.faculty_ids
            if self.faculty_members.get(fid)
            and self.faculty_members[fid].preferred_slot_ids
            and not all(sid in self.faculty_members[fid].preferred_slot_ids
                        for sid in next((entry.new_slot_ids for entry in audit_entries if entry.session_label == assignment.label), []))
        )
        room_change_penalty = sum(1.0 for entry in audit_entries if entry.old_resource_code != entry.new_resource_code)

        return RescheduleResolution(
            resolution_id="RES_TIME_SHIFT",
            title="Alternative Time Slot Shift",
            strategy_type="TIME_SHIFT",
            changed_sessions_count=changed_count,
            stability_percentage=stability,
            disruption_score=2.0 * changed_count + preference_penalty + room_change_penalty,
            resolved_allocations=resolved,
            audit_entries=audit_entries,
        )

    def _try_event_replacement_strategy(
        self,
        scope: AffectedScope,
    ) -> RescheduleResolution | None:
        """
        Replaces regular scheduled sessions with an Academic Event (e.g. Alumni Talk)
        for the designated participants and slots (FR-3.10.1 - FR-3.10.4).
        """
        resolved: list[AllocatedSession] = list(scope.unaffected_sessions)
        audit_entries: list[RescheduleAuditEntry] = []
        ev_details = scope.trigger.event_details or {}

        event_name = ev_details.get("title", "Campus Academic Event")
        ev_room_id = scope.trigger.resource_id or (scope.affected_sessions[0].resource_id if scope.affected_sessions else 1)
        ev_room = self.resources_by_id.get(ev_room_id)
        if ev_room is None or not ev_room.is_active:
            return None
        ev_subbatches = list(scope.affected_subbatch_ids)
        ev_fac_ids = ev_details.get("faculty_ids", [scope.trigger.faculty_id] if scope.trigger.faculty_id else [])

        if not scope.trigger.slot_ids or any(sid not in self.grid.slot_by_id for sid in scope.trigger.slot_ids):
            return None
        start_slot = self.grid.slot_by_id[scope.trigger.slot_ids[0]]
        end_slot = self.grid.slot_by_id[scope.trigger.slot_ids[-1]]

        event_session = AllocatedSession(
            session_id=None,
            course_id=0,
            label=f"EVENT_{event_name}",
            session_type=SessionType.EVENT.value,
            day=scope.trigger.day,
            start_slot_id=scope.trigger.slot_ids[0],
            start_time=start_slot.start_time,
            end_time=end_slot.end_time,
            duration_minutes=sum(self.grid.slot_by_id[sid].duration_minutes for sid in scope.trigger.slot_ids),
            occupied_slot_ids=scope.trigger.slot_ids,
            faculty_ids=ev_fac_ids,
            participant_group_id=0,
            subbatch_ids=ev_subbatches,
            department_id=(scope.affected_sessions[0].department_id if scope.affected_sessions and len({s.department_id for s in scope.affected_sessions}) == 1 else (ev_room.department_id or 0)),
            required_resource_type=ResourceType.AUDITORIUM if ev_room and ev_room.resource_type == ResourceType.AUDITORIUM else ResourceType.SEMINAR_HALL,
            required_capacity=int(ev_details.get("participant_strength", max((s.required_capacity for s in scope.affected_sessions), default=0))),
            resource_id=ev_room_id,
            resource_code=ev_room.code,
            resource_name=ev_room.name,
            resource_type=ev_room.resource_type,
            resource_capacity=ev_room.capacity,
            resource_score=1.0,
        )
        resolved.append(event_session)

        for aff in scope.affected_sessions:
            audit_entries.append(
                RescheduleAuditEntry(
                    session_label=aff.label,
                    trigger_type=scope.trigger.trigger_type.value,
                    reason=f"Session replaced by academic event '{event_name}'",
                    old_day=aff.day,
                    old_slot_ids=aff.occupied_slot_ids,
                    old_start_time=aff.start_time,
                    old_end_time=aff.end_time,
                    old_resource_code=aff.resource_code,
                    old_faculty_ids=aff.faculty_ids,
                    new_day=scope.trigger.day,
                    new_slot_ids=scope.trigger.slot_ids,
                    new_start_time=start_slot.start_time,
                    new_end_time=end_slot.end_time,
                    new_resource_code=event_session.resource_code,
                    new_faculty_ids=ev_fac_ids,
                )
            )

        changed_count = len(scope.affected_sessions)
        stability = round((len(scope.unaffected_sessions) / (len(scope.unaffected_sessions) + changed_count)) * 100.0, 2)

        return RescheduleResolution(
            resolution_id="RES_EVENT_REPLACE",
            title=f"Event Insertion & Session Replacement ({event_name})",
            strategy_type="EVENT_REPLACEMENT",
            changed_sessions_count=changed_count,
            stability_percentage=stability,
            disruption_score=1.0 * changed_count,
            resolved_allocations=resolved,
            audit_entries=audit_entries,
        )
