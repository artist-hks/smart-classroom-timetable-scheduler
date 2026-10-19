"""
Smart Resource Allocation & Mandatory Resource Validation Engine.

Implements:
- SB3/US1/T1: Filter candidate resources by required type, capacity, availability (FR-3.8.1).
- SB3/US1/T2: Compute resource score (capacity fit, availability, equipment, participant strength,
              location, predicted demand, stability) and assign best-suitable match (FR-3.8.2, FR-3.8.3).
- SB3/US2/T1: Revalidate resource capacity, type suitability, availability, and clashes across all sessions (FR-3.8.4).
- SB3/US2/T2: Handle revalidation failure: re-scoring against remaining candidate resources, or report infeasibility (FR-3.8.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Sequence

from app.algorithms.cpsat_solver import ScheduledAssignment
from app.models.academic import ResourceType, SessionType

DEFAULT_RESOURCE_REVALIDATION_ATTEMPTS = 3


@dataclass
class ResourceSpec:
    """
    Specification of an academic resource (Classroom, Lab, Seminar Hall, Auditorium).
    Can be instantiated from in-memory tests or directly from SQLAlchemy Resource models.
    """
    resource_id: int
    code: str
    name: str
    resource_type: ResourceType
    capacity: int
    department_id: int | None = None  # None indicates an institute-wide shared resource
    building: str | None = None
    floor: int | None = None
    is_active: bool = True
    equipment: dict[str, int] = field(default_factory=dict)  # equipment_name -> quantity
    unavailable_slot_ids: set[int] = field(default_factory=set)  # slot_ids when resource is unavailable

    @classmethod
    def from_db(cls, resource_obj: Any) -> ResourceSpec:
        """Constructs a ResourceSpec from a SQLAlchemy Resource model instance."""
        eq_map: dict[str, int] = {}
        if hasattr(resource_obj, "equipment") and resource_obj.equipment:
            for eq in resource_obj.equipment:
                eq_map[eq.name.strip().lower()] = eq.quantity

        return cls(
            resource_id=resource_obj.resource_id,
            code=resource_obj.code,
            name=resource_obj.name,
            resource_type=resource_obj.resource_type,
            capacity=resource_obj.capacity,
            department_id=resource_obj.department_id,
            building=resource_obj.building,
            floor=resource_obj.floor,
            is_active=resource_obj.is_active,
            equipment=eq_map,
        )


@dataclass
class AllocatedSession:
    """
    Represents a CP-SAT scheduled session enriched with concrete assigned resource and scoring details.
    """
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
    department_id: int
    required_resource_type: ResourceType | None
    required_capacity: int
    # Assigned Resource Information
    resource_id: int
    resource_code: str
    resource_name: str
    resource_type: ResourceType
    resource_capacity: int
    resource_score: float
    score_breakdown: dict[str, float] = field(default_factory=dict)
    required_equipment: dict[str, int] = field(default_factory=dict)


@dataclass
class AllocationDiagnostic:
    """Diagnostics recorded when a session cannot be allocated or fails validation."""
    session_label: str
    session_type: str
    day: int
    start_time: str
    end_time: str
    occupied_slot_ids: list[int]
    required_capacity: int
    required_resource_type: ResourceType | None
    department_id: int
    candidate_count: int
    reason: str
    violating_constraints: list[str] = field(default_factory=list)


@dataclass
class ResourceAllocationResult:
    """
    Final output of the Smart Resource Allocation and Mandatory Validation Engine.
    """
    is_feasible: bool
    status_label: str  # "FEASIBLE", "INFEASIBLE", "RESOURCE_VALIDATED"
    total_sessions: int
    total_allocated: int
    allocations: list[AllocatedSession] = field(default_factory=list)
    unallocated: list[AllocationDiagnostic] = field(default_factory=list)
    validation_passed: bool = False
    validation_errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class SmartResourceAllocator:
    """
    Engine 2 in the 4-engine scheduling pipeline.
    
    Operates on the feasible (session, faculty, participant-group, timeslot) output
    from CP-SAT Feasibility Engine (Engine 1) and acts as the sole assigner of physical resources.
    """

    DEFAULT_WEIGHTS = {
        "capacity": 0.35,      # Efficient room utilization vs oversized waste
        "department": 0.25,    # Prefer department's own rooms over institute shared
        "equipment": 0.15,     # Equipment adequacy and enrichment
        "location": 0.10,      # Proximity to home building / floor
        "ml_demand": 0.05,     # ML predicted room demand preservation
        "stability": 0.10,     # Room continuity across sessions of the same course (SC-10)
    }

    def __init__(
        self,
        resources: Sequence[ResourceSpec],
        predicted_demand: dict[tuple[int, int, int], float] | None = None,
        weights: dict[str, float] | None = None,
    ):
        """
        Initialize the Smart Resource Allocator.

        Args:
            resources: Available candidate physical resources.
            predicted_demand: Optional mapping of (resource_id, day, slot_id) -> demand score [0.0 - 1.0].
            weights: Optional custom weight overrides for scoring components.
        """
        self.resources = list(resources)
        self.resources_by_id = {r.resource_id: r for r in self.resources}
        self.predicted_demand = predicted_demand or {}

        # Normalize weights
        raw_weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        unknown = set(raw_weights) - set(self.DEFAULT_WEIGHTS)
        if unknown:
            raise ValueError(f"Unknown resource scoring weights: {sorted(unknown)}")
        if any(not math.isfinite(float(v)) or float(v) < 0 for v in raw_weights.values()):
            raise ValueError("Resource scoring weights must be finite and non-negative.")
        total_w = sum(raw_weights.values())
        if total_w <= 0:
            raise ValueError("At least one resource scoring weight must be positive.")
        self.weights = {k: v / total_w for k, v in raw_weights.items()}

    def filter_candidate_resources(
        self,
        session: ScheduledAssignment,
        current_bookings: dict[tuple[int, int], int],  # (resource_id, slot_id) -> session_id
        excluded_resource_ids: set[int] | None = None,
        required_equipment: dict[str, int] | None = None,
    ) -> tuple[list[ResourceSpec], list[str]]:
        """
        Filter resources for a given scheduled session (FR-3.8.1).
        
        Criteria enforced:
        1. Active status: resource.is_active is True
        2. Exclusions: resource_id not in excluded_resource_ids (used during backtracking/re-scoring)
        3. Resource Type suitability: resource.resource_type == session.required_resource_type (HC-08, HC-09)
        4. Department Isolation / Shared Access: resource belongs to department or is shared
        5. Capacity constraint: resource.capacity >= session.required_capacity (HC-07, HC-16)
        6. Equipment sufficiency: resource equipment matches or exceeds required (HC-09)
        7. Resource availability: resource not in maintenance/unavailability for session slots (HC-06)
        8. Resource clash: resource not already booked by another session in occupied slots (HC-02)

        Returns:
            Tuple of (valid_candidates, rejection_reasons)
        """
        candidates: list[ResourceSpec] = []
        rejection_reasons: list[str] = []
        excluded = excluded_resource_ids or set()
        req_eq = {k.strip().lower(): v for k, v in (required_equipment or session.required_equipment or {}).items()}

        for r in self.resources:
            # 1. Active status check
            if not r.is_active:
                continue

            # 2. Excluded set check
            if r.resource_id in excluded:
                continue

            # 3. Resource Type matching (FR-3.8.1, HC-08, HC-09)
            if session.required_resource_type is not None and r.resource_type != session.required_resource_type:
                rejection_reasons.append(
                    f"Resource '{r.code}' ({r.resource_type.value}) does not match required type '{session.required_resource_type.value}'"
                )
                continue

            # 4. Department Isolation & Shared Access
            # department_id is nullable: NULL means institute-wide shared resource
            if r.department_id is not None and r.department_id != session.department_id:
                rejection_reasons.append(
                    f"Resource '{r.code}' belongs to department {r.department_id}, cannot be accessed by department {session.department_id}"
                )
                continue

            # 5. Capacity constraint (HC-07, HC-16)
            if r.capacity < session.required_capacity:
                rejection_reasons.append(
                    f"Resource '{r.code}' capacity ({r.capacity}) insufficient for required strength ({session.required_capacity})"
                )
                continue

            # 6. Equipment sufficiency (HC-09)
            if req_eq:
                missing_or_insufficient = False
                for eq_name, min_qty in req_eq.items():
                    r_qty = r.equipment.get(eq_name, 0)
                    if r_qty < min_qty:
                        missing_or_insufficient = True
                        rejection_reasons.append(
                            f"Resource '{r.code}' lacks equipment '{eq_name}' (has {r_qty}, requires {min_qty})"
                        )
                        break
                if missing_or_insufficient:
                    continue

            # 7. Resource Availability (HC-06)
            is_unavailable = any(slot_id in r.unavailable_slot_ids for slot_id in session.occupied_slot_ids)
            if is_unavailable:
                rejection_reasons.append(
                    f"Resource '{r.code}' is marked unavailable in one of the session slots {session.occupied_slot_ids}"
                )
                continue

            # 8. Resource Clash (HC-02)
            has_clash = any(
                (r.resource_id, slot_id) in current_bookings for slot_id in session.occupied_slot_ids
            )
            if has_clash:
                clashing_sessions = [
                    current_bookings[(r.resource_id, slot_id)]
                    for slot_id in session.occupied_slot_ids
                    if (r.resource_id, slot_id) in current_bookings
                ]
                rejection_reasons.append(
                    f"Resource '{r.code}' has scheduling clash at slots {session.occupied_slot_ids} (with session {clashing_sessions})"
                )
                continue

            # Passed all filters
            candidates.append(r)

        return candidates, rejection_reasons

    def compute_candidate_score(
        self,
        resource: ResourceSpec,
        session: ScheduledAssignment,
        prior_course_allocations: dict[int, int] | None = None,
        required_equipment: dict[str, int] | None = None,
        preferred_building: str | None = None,
    ) -> tuple[float, dict[str, float]]:
        """
        Compute multi-criteria resource suitability score (FR-3.8.2).
        
        Scoring Factors:
        1. Capacity Fit (utilization): required_capacity / resource.capacity (higher is better, avoids wasting big halls)
        2. Department Affinity: 1.0 for department's own resource, 0.6 for institute-wide shared
        3. Equipment Match: 1.0 for meeting requirements, with bonus for rich audiovisual aids
        4. Location Proximity: 1.0 if matching preferred building/floor, 0.7 otherwise
        5. ML Demand: 1.0 - predicted_external_demand (preserves high-demand rooms when possible)
        6. Resource Stability (SC-10): 1.0 if course already used this room earlier in week, 0.5 otherwise
        """
        scores: dict[str, float] = {}

        # 1. Capacity Fit Score (SC-01, SC-06)
        # Avoid assigning a 200-capacity auditorium to a 20-student lab
        if resource.capacity > 0 and session.required_capacity > 0:
            utilization = session.required_capacity / resource.capacity
            # Cap at 1.0; slight non-linear curve to penalize severe oversized rooms
            scores["capacity"] = max(0.0, min(1.0, math.sqrt(utilization)))
        else:
            scores["capacity"] = 0.5

        # 2. Department Affinity Score
        if resource.department_id == session.department_id:
            scores["department"] = 1.0
        elif resource.department_id is None:
            # Institute shared resource
            scores["department"] = 0.6
        else:
            scores["department"] = 0.0

        # 3. Equipment Match Score
        req_eq = {k.strip().lower(): v for k, v in (required_equipment or {}).items()}
        if req_eq:
            eq_satisfaction = 1.0
            # Bonus if projector or smart board present for lectures
            if "projector" in resource.equipment or "smart board" in resource.equipment:
                eq_satisfaction = min(1.0, eq_satisfaction + 0.1)
            scores["equipment"] = eq_satisfaction
        else:
            # Bonus for standard teaching aids
            has_aid = any(k in resource.equipment for k in ("projector", "smart board", "display"))
            scores["equipment"] = 0.9 if has_aid else 0.7

        # 4. Location Proximity Score
        if preferred_building and resource.building:
            scores["location"] = 1.0 if resource.building.lower() == preferred_building.lower() else 0.6
        else:
            scores["location"] = 0.8

        # 5. ML Predicted Demand Score (FR-3.7.1 - 3.7.3)
        # High external demand -> lower score, preserving resource for other needs
        slot_demands = [
            self.predicted_demand.get((resource.resource_id, session.day, slot_id), 0.0)
            for slot_id in session.occupied_slot_ids
        ]
        avg_demand = sum(slot_demands) / len(slot_demands) if slot_demands else 0.0
        scores["ml_demand"] = max(0.0, 1.0 - avg_demand)

        # 6. Resource Stability Score (SC-10)
        # Check if this course was previously scheduled in this resource
        prior_room = (prior_course_allocations or {}).get(session.course_id)
        if prior_room is not None:
            scores["stability"] = 1.0 if prior_room == resource.resource_id else 0.4
        else:
            scores["stability"] = 0.7

        # Weighted composite score
        total_score = sum(scores[factor] * self.weights[factor] for factor in scores)

        return round(total_score, 4), scores

    def allocate(
        self,
        assignments: Sequence[ScheduledAssignment],
        session_equipment: dict[int, dict[str, int]] | None = None,
        preferred_building: str | None = None,
    ) -> ResourceAllocationResult:
        """
        Execute Smart Resource Allocation on CP-SAT scheduled assignments (FR-3.8.3).
        
        Sorting Heuristic (Most Constrained First):
        1. Lab / Practical sessions first (labs are scarcer and require specific equipment)
        2. Longest duration sessions first
        3. Highest capacity required first
        """
        session_eq = session_equipment or {}
        current_bookings: dict[tuple[int, int], int] = {}  # (resource_id, slot_id) -> session_idx
        allocated_sessions: list[AllocatedSession] = []
        unallocated_diagnostics: list[AllocationDiagnostic] = []
        prior_course_allocations: dict[int, int] = {}  # course_id -> resource_id

        # Sort assignments to place hardest/most constrained sessions first
        def session_priority_key(a: ScheduledAssignment) -> tuple[int, int, int]:
            # Priority 0 for Labs, 1 for Seminars, 2 for Lectures
            stype_prio = 0 if a.session_type == SessionType.PRACTICAL.value else (
                1 if a.session_type == SessionType.SEMINAR.value else 2
            )
            # Descending duration, descending capacity
            return (stype_prio, -a.duration_minutes, -a.required_capacity)

        sorted_assignments = sorted(assignments, key=session_priority_key)

        for session in sorted_assignments:
            req_eq = session_eq.get(session.session_id or 0, session.required_equipment)
            candidates, rejection_reasons = self.filter_candidate_resources(
                session=session,
                current_bookings=current_bookings,
                required_equipment=req_eq,
            )

            if not candidates:
                # No suitable resource available
                diag = AllocationDiagnostic(
                    session_label=session.label,
                    session_type=session.session_type,
                    day=session.day,
                    start_time=session.start_time,
                    end_time=session.end_time,
                    occupied_slot_ids=session.occupied_slot_ids,
                    required_capacity=session.required_capacity,
                    required_resource_type=session.required_resource_type,
                    department_id=session.department_id,
                    candidate_count=0,
                    reason=f"No eligible resource available for session '{session.label}' (requires {session.required_capacity} seats, {session.required_resource_type}).",
                    violating_constraints=rejection_reasons[:5],
                )
                unallocated_diagnostics.append(diag)
                continue

            # Score each candidate and select the highest scoring match (FR-3.8.3)
            scored_candidates: list[tuple[float, dict[str, float], ResourceSpec]] = []
            for cand in candidates:
                score, breakdown = self.compute_candidate_score(
                    resource=cand,
                    session=session,
                    prior_course_allocations=prior_course_allocations,
                    required_equipment=req_eq,
                    preferred_building=preferred_building,
                )
                scored_candidates.append((score, breakdown, cand))

            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_breakdown, best_resource = scored_candidates[0]

            # Assign resource and record bookings (HC-02)
            for slot_id in session.occupied_slot_ids:
                current_bookings[(best_resource.resource_id, slot_id)] = session.course_id

            prior_course_allocations[session.course_id] = best_resource.resource_id

            allocated = AllocatedSession(
                session_id=session.session_id,
                course_id=session.course_id,
                label=session.label,
                session_type=session.session_type,
                day=session.day,
                start_slot_id=session.start_slot_id,
                start_time=session.start_time,
                end_time=session.end_time,
                duration_minutes=session.duration_minutes,
                occupied_slot_ids=session.occupied_slot_ids,
                faculty_ids=session.faculty_ids,
                participant_group_id=session.participant_group_id,
                subbatch_ids=session.subbatch_ids,
                department_id=session.department_id,
                required_resource_type=session.required_resource_type,
                required_capacity=session.required_capacity,
                resource_id=best_resource.resource_id,
                resource_code=best_resource.code,
                resource_name=best_resource.name,
                resource_type=best_resource.resource_type,
                resource_capacity=best_resource.capacity,
                resource_score=best_score,
                score_breakdown=best_breakdown,
                required_equipment=dict(req_eq or {}),
            )
            allocated_sessions.append(allocated)

        is_feasible = (len(unallocated_diagnostics) == 0)

        # Compute summary metrics
        metrics = self._compute_allocation_metrics(allocated_sessions)

        return ResourceAllocationResult(
            is_feasible=is_feasible,
            status_label="FEASIBLE" if is_feasible else "INFEASIBLE",
            total_sessions=len(assignments),
            total_allocated=len(allocated_sessions),
            allocations=allocated_sessions,
            unallocated=unallocated_diagnostics,
            validation_passed=False,
            validation_errors=[],
            metrics=metrics,
        )

    def validate_allocation(
        self,
        allocations: Sequence[AllocatedSession],
        session_equipment: dict[int, dict[str, int]] | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Mandatory Resource Allocation Validation (FR-3.8.4).
        
        Independently revalidates every allocated session against all hard resource constraints:
        1. HC-02 (Resource Clash): No resource hosts two overlapping sessions
        2. HC-06 (Resource Availability): Resource is active and not on scheduled maintenance
        3. HC-07 / HC-16 (Resource Capacity): resource.capacity >= session.required_capacity
        4. HC-08 (Resource Suitability): resource.resource_type == session.required_resource_type
        5. HC-09 (Lab Requirement): Required equipment present in sufficient quantity
        6. Department Access: Resource belongs to session department or is shared institute resource
        """
        errors: list[str] = []
        session_eq = session_equipment or {}

        # 1. Check HC-02 (No Resource Clashes)
        resource_slot_map: dict[tuple[int, int], str] = {}
        for a in allocations:
            for slot_id in a.occupied_slot_ids:
                key = (a.resource_id, slot_id)
                if key in resource_slot_map:
                    errors.append(
                        f"HC-02 Violation: Resource '{a.resource_code}' (ID {a.resource_id}) has double booking "
                        f"between '{resource_slot_map[key]}' and '{a.label}' at slot {slot_id}."
                    )
                else:
                    resource_slot_map[key] = a.label

        # 2. Check each allocation independently
        for a in allocations:
            res = self.resources_by_id.get(a.resource_id)
            if not res:
                errors.append(f"Invalid Resource: Session '{a.label}' assigned non-existent resource ID {a.resource_id}.")
                continue

            # Active status
            if not res.is_active:
                errors.append(f"HC-06 Violation: Resource '{res.code}' is inactive/under maintenance for session '{a.label}'.")

            # Availability check (HC-06)
            for slot_id in a.occupied_slot_ids:
                if slot_id in res.unavailable_slot_ids:
                    errors.append(
                        f"HC-06 Violation: Resource '{res.code}' is unavailable at slot {slot_id} assigned to '{a.label}'."
                    )

            # Capacity check (HC-07, HC-16)
            if res.capacity < a.required_capacity:
                errors.append(
                    f"HC-07 Violation: Resource '{res.code}' capacity ({res.capacity}) is less than "
                    f"session '{a.label}' required strength ({a.required_capacity})."
                )

            # Resource Type Suitability (HC-08, HC-09)
            if a.required_resource_type is not None and res.resource_type != a.required_resource_type:
                errors.append(
                    f"HC-08 Violation: Resource '{res.code}' type ({res.resource_type.value}) does not match "
                    f"session '{a.label}' required type ({a.required_resource_type.value})."
                )

            # Department Isolation & Access
            if res.department_id is not None and res.department_id != a.department_id:
                errors.append(
                    f"Department Access Violation: Resource '{res.code}' belongs to dept {res.department_id}, "
                    f"cannot be used by session '{a.label}' of dept {a.department_id}."
                )

            # Equipment Check (HC-09)
            req_eq = session_eq.get(a.session_id or 0, a.required_equipment)
            for eq_name, min_qty in req_eq.items():
                r_qty = res.equipment.get(eq_name.strip().lower(), 0)
                if r_qty < min_qty:
                    errors.append(
                        f"HC-09 Violation: Resource '{res.code}' lacks equipment '{eq_name}' "
                        f"(requires {min_qty}, has {r_qty}) for session '{a.label}'."
                    )

        is_valid = (len(errors) == 0)
        return is_valid, errors

    def allocate_and_validate(
        self,
        assignments: Sequence[ScheduledAssignment],
        session_equipment: dict[int, dict[str, int]] | None = None,
        preferred_building: str | None = None,
        max_revalidation_attempts: int = DEFAULT_RESOURCE_REVALIDATION_ATTEMPTS,
    ) -> ResourceAllocationResult:
        """
        Executes end-to-end Smart Resource Allocation and Mandatory Validation (FR-3.8.1 - FR-3.8.5).
        
        If revalidation detects conflicts, it initiates backtracking and re-scoring against
        remaining candidates (FR-3.8.5) up to max_revalidation_attempts before reporting infeasibility.
        """
        if max_revalidation_attempts < 0:
            raise ValueError("max_revalidation_attempts must be non-negative.")
        result = self.allocate(
            assignments=assignments,
            session_equipment=session_equipment,
            preferred_building=preferred_building,
        )

        if not result.is_feasible:
            result.validation_passed = False
            result.validation_errors = ["Allocation was infeasible: one or more sessions could not be placed."]
            return result

        # Run Mandatory Revalidation (FR-3.8.4)
        is_valid, errors = self.validate_allocation(
            allocations=result.allocations,
            session_equipment=session_equipment,
        )

        if is_valid:
            result.validation_passed = True
            result.status_label = "RESOURCE_VALIDATED"
            return result

        # Handle Revalidation Failure (FR-3.8.5)
        # Attempt candidate rejection & re-scoring
        attempt = 1
        current_allocations = list(result.allocations)
        excluded_pairs: set[tuple[str, int]] = set()  # (session_label, resource_id)

        while not is_valid and attempt <= max_revalidation_attempts:
            # Parse error to identify failing session and resource
            for err in errors:
                for alloc in current_allocations:
                    if alloc.label in err:
                        excluded_pairs.add((alloc.label, alloc.resource_id))

            # Re-run allocation with exclusions
            # Reset bookings and re-allocate with failing resources excluded
            re_result = self._allocate_with_exclusions(
                assignments=assignments,
                session_equipment=session_equipment,
                excluded_pairs=excluded_pairs,
                preferred_building=preferred_building,
            )

            if not re_result.is_feasible:
                # Infeasibility confirmed per FR-3.8.5
                re_result.validation_passed = False
                re_result.validation_errors = errors
                re_result.status_label = "INFEASIBLE (Revalidation failed, no alternative candidate)"
                return re_result

            is_valid, errors = self.validate_allocation(
                allocations=re_result.allocations,
                session_equipment=session_equipment,
            )
            if is_valid:
                re_result.validation_passed = True
                re_result.status_label = "RESOURCE_VALIDATED"
                return re_result

            current_allocations = list(re_result.allocations)
            attempt += 1

        result.validation_passed = False
        result.validation_errors = errors
        result.status_label = "INFEASIBLE (Revalidation failed after maximum repair attempts)"
        return result

    def _allocate_with_exclusions(
        self,
        assignments: Sequence[ScheduledAssignment],
        session_equipment: dict[int, dict[str, int]] | None,
        excluded_pairs: set[tuple[str, int]],
        preferred_building: str | None,
    ) -> ResourceAllocationResult:
        """Internal helper to re-allocate sessions with specific rejected candidates excluded."""
        session_eq = session_equipment or {}
        current_bookings: dict[tuple[int, int], int] = {}
        allocated_sessions: list[AllocatedSession] = []
        unallocated_diagnostics: list[AllocationDiagnostic] = []
        prior_course_allocations: dict[int, int] = {}

        def session_priority_key(a: ScheduledAssignment) -> tuple[int, int, int]:
            stype_prio = 0 if a.session_type == SessionType.PRACTICAL.value else (
                1 if a.session_type == SessionType.SEMINAR.value else 2
            )
            return (stype_prio, -a.duration_minutes, -a.required_capacity)

        sorted_assignments = sorted(assignments, key=session_priority_key)

        for session in sorted_assignments:
            req_eq = session_eq.get(session.session_id or 0)
            excluded_res_ids = {r_id for (lbl, r_id) in excluded_pairs if lbl == session.label}
            candidates, rejection_reasons = self.filter_candidate_resources(
                session=session,
                current_bookings=current_bookings,
                excluded_resource_ids=excluded_res_ids,
                required_equipment=req_eq,
            )

            if not candidates:
                diag = AllocationDiagnostic(
                    session_label=session.label,
                    session_type=session.session_type,
                    day=session.day,
                    start_time=session.start_time,
                    end_time=session.end_time,
                    occupied_slot_ids=session.occupied_slot_ids,
                    required_capacity=session.required_capacity,
                    required_resource_type=session.required_resource_type,
                    department_id=session.department_id,
                    candidate_count=0,
                    reason=f"No alternative candidate resource available for session '{session.label}' after revalidation rejection.",
                    violating_constraints=rejection_reasons[:5],
                )
                unallocated_diagnostics.append(diag)
                continue

            scored_candidates: list[tuple[float, dict[str, float], ResourceSpec]] = []
            for cand in candidates:
                score, breakdown = self.compute_candidate_score(
                    resource=cand,
                    session=session,
                    prior_course_allocations=prior_course_allocations,
                    required_equipment=req_eq,
                    preferred_building=preferred_building,
                )
                scored_candidates.append((score, breakdown, cand))

            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_breakdown, best_resource = scored_candidates[0]

            for slot_id in session.occupied_slot_ids:
                current_bookings[(best_resource.resource_id, slot_id)] = session.course_id

            prior_course_allocations[session.course_id] = best_resource.resource_id

            allocated = AllocatedSession(
                session_id=session.session_id,
                course_id=session.course_id,
                label=session.label,
                session_type=session.session_type,
                day=session.day,
                start_slot_id=session.start_slot_id,
                start_time=session.start_time,
                end_time=session.end_time,
                duration_minutes=session.duration_minutes,
                occupied_slot_ids=session.occupied_slot_ids,
                faculty_ids=session.faculty_ids,
                participant_group_id=session.participant_group_id,
                subbatch_ids=session.subbatch_ids,
                department_id=session.department_id,
                required_resource_type=session.required_resource_type,
                required_capacity=session.required_capacity,
                resource_id=best_resource.resource_id,
                resource_code=best_resource.code,
                resource_name=best_resource.name,
                resource_type=best_resource.resource_type,
                resource_capacity=best_resource.capacity,
                resource_score=best_score,
                score_breakdown=best_breakdown,
            )
            allocated_sessions.append(allocated)

        is_feasible = (len(unallocated_diagnostics) == 0)
        metrics = self._compute_allocation_metrics(allocated_sessions)

        return ResourceAllocationResult(
            is_feasible=is_feasible,
            status_label="FEASIBLE" if is_feasible else "INFEASIBLE",
            total_sessions=len(assignments),
            total_allocated=len(allocated_sessions),
            allocations=allocated_sessions,
            unallocated=unallocated_diagnostics,
            validation_passed=False,
            validation_errors=[],
            metrics=metrics,
        )

    def _compute_allocation_metrics(self, allocations: Sequence[AllocatedSession]) -> dict[str, Any]:
        """Compute summary statistics for resource utilization, scores, and room usage."""
        if not allocations:
            return {
                "average_utilization": 0.0,
                "average_score": 0.0,
                "rooms_used_count": 0,
                "shared_resources_used": 0,
                "department_match_ratio": 0.0,
            }

        utilizations = [
            (a.required_capacity / a.resource_capacity) for a in allocations if a.resource_capacity > 0
        ]
        scores = [a.resource_score for a in allocations]
        unique_rooms = {a.resource_id for a in allocations}

        dept_matches = sum(
            1 for a in allocations
            if self.resources_by_id.get(a.resource_id) and self.resources_by_id[a.resource_id].department_id == a.department_id
        )
        shared_count = sum(
            1 for a in allocations
            if self.resources_by_id.get(a.resource_id) and self.resources_by_id[a.resource_id].department_id is None
        )

        return {
            "average_utilization": round(sum(utilizations) / len(utilizations), 4) if utilizations else 0.0,
            "average_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "rooms_used_count": len(unique_rooms),
            "shared_resources_used": shared_count,
            "department_match_ratio": round(dept_matches / len(allocations), 4) if allocations else 0.0,
        }
