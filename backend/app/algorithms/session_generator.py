"""
Course-to-Session Generator and Participant Group Resolver.

Implements:
- SB2/US8/T1: Course-to-Session generation (session types, weekly hours, duration per FR-3.3.6)
- SB2/US8/T2: Participant Group resolution (section, sub-batch, valid multi-section/multi-sub-batch combinations per FR-3.3.1-3.3.3)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence
import math

from app.models.academic import ResourceType, SessionStatus, SessionType


@dataclass
class ParticipantGroupSpec:
    """Specification of a participant group (e.g., single sub-batch, section, or multi-batch combo)."""
    participant_group_id: int | None
    department_id: int
    label: str
    subbatch_ids: list[int]
    combined_strength: int


@dataclass
class GeneratedSession:
    """Atomic scheduling unit to be scheduled by CP-SAT."""
    session_id: int | None
    course_id: int
    course_session_type_id: int
    department_id: int
    session_type: SessionType
    duration_minutes: int
    required_resource_type: ResourceType | None
    required_capacity: int
    participant_group_id: int
    faculty_ids: list[int] = field(default_factory=list)
    status: SessionStatus = SessionStatus.DRAFT
    label: str = ""

    @property
    def duration_hours(self) -> float:
        return self.duration_minutes / 60.0


class ParticipantGroupResolver:
    """
    Resolves and validates participant groups per FR-3.3.1, FR-3.3.2, FR-3.3.3.
    Supports single sub-batches, full sections, arbitrary combinations (e.g. D1+D2),
    and multi-section groups (e.g. A+B+C+D).
    """

    @staticmethod
    def resolve_subbatch_group(
        department_id: int,
        subbatch_id: int,
        subbatch_name: str,
        student_strength: int,
        group_id: int | None = None,
    ) -> ParticipantGroupSpec:
        """Resolve a single sub-batch participant group (e.g., D1 for a lab)."""
        if student_strength <= 0:
            raise ValueError(f"Sub-batch {subbatch_name} must have positive student strength.")
        return ParticipantGroupSpec(
            participant_group_id=group_id,
            department_id=department_id,
            label=f"SubBatch-{subbatch_name}",
            subbatch_ids=[subbatch_id],
            combined_strength=student_strength,
        )

    @staticmethod
    def resolve_section_group(
        department_id: int,
        section_name: str,
        subbatches: Sequence[tuple[int, int]],  # list of (subbatch_id, strength)
        group_id: int | None = None,
    ) -> ParticipantGroupSpec:
        """Resolve a full section participant group from its component sub-batches."""
        if not subbatches:
            raise ValueError(f"Section {section_name} has no sub-batches.")
        subbatch_ids = [sb[0] for sb in subbatches]
        total_strength = sum(sb[1] for sb in subbatches)
        if total_strength <= 0:
            raise ValueError(f"Section {section_name} total strength must be positive.")
        return ParticipantGroupSpec(
            participant_group_id=group_id,
            department_id=department_id,
            label=f"Section-{section_name}",
            subbatch_ids=subbatch_ids,
            combined_strength=total_strength,
        )

    @staticmethod
    def resolve_combination_group(
        department_id: int,
        label: str,
        subbatches: Sequence[tuple[int, int]],  # list of (subbatch_id, strength)
        group_id: int | None = None,
    ) -> ParticipantGroupSpec:
        """
        Resolve an arbitrary combination of sub-batches (e.g. D1 + D2 or cross-section).
        Implements FR-3.3.1 (Arbitrary Sub-Batch Grouping).
        """
        if not subbatches:
            raise ValueError(f"Participant group {label} must contain at least one sub-batch.")
        subbatch_ids = [sb[0] for sb in subbatches]
        total_strength = sum(sb[1] for sb in subbatches)
        return ParticipantGroupSpec(
            participant_group_id=group_id,
            department_id=department_id,
            label=label,
            subbatch_ids=subbatch_ids,
            combined_strength=total_strength,
        )


class CourseToSessionGenerator:
    """
    Generates atomic Session instances from Course and CourseSessionTypeConfig configurations.
    Implements SB2/US8/T1 (FR-3.3.6).
    """

    @staticmethod
    def generate_sessions_for_course(
        course_id: int,
        course_code: str,
        department_id: int,
        configs: Sequence[dict[str, Any]],
        section_groups: dict[str, ParticipantGroupSpec],  # e.g. {"lecture": group, "lab_D1": group1, ...}
        faculty_mapping: dict[str, list[int]],            # e.g. {"lecture": [101], "lab_D1": [101, 102]}
    ) -> list[GeneratedSession]:
        """
        Generate atomic scheduling sessions for a given course configuration.

        Args:
            course_id: ID of the course
            course_code: Code of the course (e.g., 'CS501')
            department_id: ID of the department
            configs: List of dicts representing CourseSessionTypeConfig:
                     [{'course_session_type_id': 1, 'session_type': SessionType.LECTURE,
                       'sessions_per_week': 3, 'duration_minutes': 60,
                       'required_resource_type': ResourceType.CLASSROOM}]
            section_groups: Mapping of config roles to participant groups.
            faculty_mapping: Mapping of config roles to list of assigned faculty IDs.

        Returns:
            List of GeneratedSession instances ready for CP-SAT scheduling.
        """
        generated_sessions: list[GeneratedSession] = []

        for cfg in configs:
            stype: SessionType = cfg["session_type"]
            cst_id: int = cfg["course_session_type_id"]
            sessions_per_week: int = cfg["sessions_per_week"]
            duration_minutes: int = cfg["duration_minutes"]
            res_type: ResourceType | None = cfg.get("required_resource_type")

            if stype == SessionType.LECTURE or stype == SessionType.TUTE_ASSIGNMENT or stype == SessionType.SEMINAR:
                # Typically whole-section or designated group
                pgroup = section_groups.get("lecture") or section_groups.get("main")
                if not pgroup:
                    # Fallback to the first available group
                    pgroup = next(iter(section_groups.values()))
                
                faculty_ids = faculty_mapping.get("lecture") or faculty_mapping.get("main") or []

                for i in range(1, sessions_per_week + 1):
                    session = GeneratedSession(
                        session_id=None,
                        course_id=course_id,
                        course_session_type_id=cst_id,
                        department_id=department_id,
                        session_type=stype,
                        duration_minutes=duration_minutes,
                        required_resource_type=res_type or ResourceType.CLASSROOM,
                        required_capacity=pgroup.combined_strength,
                        participant_group_id=pgroup.participant_group_id or 0,
                        faculty_ids=faculty_ids,
                        status=SessionStatus.DRAFT,
                        label=f"{course_code}_{stype.value}_S{i}",
                    )
                    generated_sessions.append(session)

            elif stype == SessionType.PRACTICAL or stype == SessionType.PROJECT:
                # Typically per sub-batch (D1, D2, D3) or grouped sub-batches
                # Find all sub-batch groups matching practical keys
                lab_groups = {k: v for k, v in section_groups.items() if k.startswith("lab_") or k.startswith("subbatch_")}
                if not lab_groups:
                    # If no specific lab groups given, use all available non-main groups
                    lab_groups = {k: v for k, v in section_groups.items() if k not in ("lecture", "main")}
                
                if not lab_groups:
                    # Fallback: single group
                    lab_groups = {"default_lab": next(iter(section_groups.values()))}

                for group_key, pgroup in lab_groups.items():
                    faculty_ids = faculty_mapping.get(group_key) or faculty_mapping.get("lab") or faculty_mapping.get("main") or []
                    for i in range(1, sessions_per_week + 1):
                        session = GeneratedSession(
                            session_id=None,
                            course_id=course_id,
                            course_session_type_id=cst_id,
                            department_id=department_id,
                            session_type=stype,
                            duration_minutes=duration_minutes,
                            required_resource_type=res_type or ResourceType.LABORATORY,
                            required_capacity=pgroup.combined_strength,
                            participant_group_id=pgroup.participant_group_id or 0,
                            faculty_ids=faculty_ids,
                            status=SessionStatus.DRAFT,
                            label=f"{course_code}_{stype.value}_{pgroup.label}_S{i}",
                        )
                        generated_sessions.append(session)

        return generated_sessions
