"""
Unit tests for CourseToSessionGenerator and ParticipantGroupResolver (SB2/US8).
"""

import pytest
from app.algorithms.session_generator import (
    CourseToSessionGenerator,
    ParticipantGroupResolver,
    ParticipantGroupSpec,
)
from app.models.academic import ResourceType, SessionStatus, SessionType


def test_participant_group_resolver_section():
    # Section D with D1(20), D2(20), D3(20)
    subbatches = [(1, 20), (2, 20), (3, 20)]
    group = ParticipantGroupResolver.resolve_section_group(
        department_id=1,
        section_name="D",
        subbatches=subbatches,
        group_id=10,
    )
    assert group.label == "Section-D"
    assert group.combined_strength == 60
    assert group.subbatch_ids == [1, 2, 3]


def test_participant_group_resolver_arbitrary_combo():
    # Arbitrary combination D1 + D2 (FR-3.3.1)
    subbatches = [(1, 20), (2, 20)]
    group = ParticipantGroupResolver.resolve_combination_group(
        department_id=1,
        label="Group-D1-D2",
        subbatches=subbatches,
        group_id=11,
    )
    assert group.label == "Group-D1-D2"
    assert group.combined_strength == 40
    assert group.subbatch_ids == [1, 2]


def test_course_to_session_generator_lecture_and_lab():
    # Course: DBMS (3 Lectures of 60 min + 1 Practical of 120 min)
    configs = [
        {
            "course_session_type_id": 101,
            "session_type": SessionType.LECTURE,
            "sessions_per_week": 3,
            "duration_minutes": 60,
            "required_resource_type": ResourceType.CLASSROOM,
        },
        {
            "course_session_type_id": 102,
            "session_type": SessionType.PRACTICAL,
            "sessions_per_week": 1,
            "duration_minutes": 120,
            "required_resource_type": ResourceType.LABORATORY,
        },
    ]

    sec_d = ParticipantGroupResolver.resolve_section_group(1, "D", [(1, 20), (2, 20), (3, 20)], group_id=10)
    d1 = ParticipantGroupResolver.resolve_subbatch_group(1, 1, "D1", 20, group_id=11)
    d2 = ParticipantGroupResolver.resolve_subbatch_group(1, 2, "D2", 20, group_id=12)
    d3 = ParticipantGroupResolver.resolve_subbatch_group(1, 3, "D3", 20, group_id=13)

    section_groups = {
        "lecture": sec_d,
        "lab_D1": d1,
        "lab_D2": d2,
        "lab_D3": d3,
    }

    faculty_mapping = {
        "lecture": [501],
        "lab_D1": [501, 502],  # Multi-faculty lab session (FR-3.3.4)
        "lab_D2": [501, 503],
        "lab_D3": [502, 503],
    }

    sessions = CourseToSessionGenerator.generate_sessions_for_course(
        course_id=1,
        course_code="CS501_DBMS",
        department_id=1,
        configs=configs,
        section_groups=section_groups,
        faculty_mapping=faculty_mapping,
    )

    # 3 lectures + 3 lab sessions (1 for each sub-batch) = 6 sessions total
    assert len(sessions) == 6

    # Verify Lectures
    lectures = [s for s in sessions if s.session_type == SessionType.LECTURE]
    assert len(lectures) == 3
    for l in lectures:
        assert l.duration_minutes == 60
        assert l.required_capacity == 60
        assert l.faculty_ids == [501]
        assert l.required_resource_type == ResourceType.CLASSROOM

    # Verify Labs
    labs = [s for s in sessions if s.session_type == SessionType.PRACTICAL]
    assert len(labs) == 3
    for lab in labs:
        assert lab.duration_minutes == 120
        assert lab.required_capacity == 20
        assert len(lab.faculty_ids) == 2  # Multi-faculty
        assert lab.required_resource_type == ResourceType.LABORATORY
