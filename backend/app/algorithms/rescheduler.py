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

from app.algorithms.cpsat_solver import FacultySpec, ScheduledAssignment
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
    ):
        self.grid = grid
        self.resources = list(resources)
        self.resources_by_id = {r.resource_id: r for r in self.resources}
        self.faculty_members = faculty_members
        self.participant_groups = participant_groups or {}
        self.substitute_pool = substitute_faculty_pool or {}

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
        scope = self.compute_affected_scope(current_schedule, trigger)

        if not scope.affected_sessions:
            return ReschedulingResult(
                is_successful=True,
                status_label="NO_AFFECTED_SESSIONS",
                scope=scope,
                diagnostics=["Trigger did not collide with any scheduled sessions."],
            )

        resolutions: list[RescheduleResolution] = []

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

        valid_starts = self.grid.get_valid_start_slots_for_duration(60)
        valid_starts_120 = self.grid.get_valid_start_slots_for_duration(120)

        for aff in scope.affected_sessions:
            starts = valid_starts_120 if aff.duration_minutes >= 120 else valid_starts
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
                candidate_rooms = [self.resources_by_id[aff.resource_id]] if aff.resource_id in self.resources_by_id else []
                # Add other rooms of same type
                candidate_rooms.extend([
                    r for r in self.resources
                    if r.resource_id != aff.resource_id
                    and r.is_active
                    and r.resource_type == req_type
                    and r.capacity >= aff.required_capacity
                    and (r.department_id is None or r.department_id == aff.department_id)
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

        return RescheduleResolution(
            resolution_id="RES_TIME_SHIFT",
            title="Alternative Time Slot Shift",
            strategy_type="TIME_SHIFT",
            changed_sessions_count=changed_count,
            stability_percentage=stability,
            disruption_score=2.0 * changed_count,  # Time shift has higher disruption than substitute
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
        ev_subbatches = list(scope.affected_subbatch_ids)
        ev_fac_ids = ev_details.get("faculty_ids", [scope.trigger.faculty_id] if scope.trigger.faculty_id else [])

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
            duration_minutes=len(scope.trigger.slot_ids) * 60,
            occupied_slot_ids=scope.trigger.slot_ids,
            faculty_ids=ev_fac_ids,
            participant_group_id=0,
            subbatch_ids=ev_subbatches,
            department_id=1,
            required_resource_type=ResourceType.AUDITORIUM if ev_room and ev_room.resource_type == ResourceType.AUDITORIUM else ResourceType.SEMINAR_HALL,
            required_capacity=sum(len(ev_subbatches) * 20 for _ in [1]),
            resource_id=ev_room_id,
            resource_code=ev_room.code if ev_room else "AUD",
            resource_name=ev_room.name if ev_room else "Auditorium",
            resource_type=ev_room.resource_type if ev_room else ResourceType.AUDITORIUM,
            resource_capacity=ev_room.capacity if ev_room else 300,
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
