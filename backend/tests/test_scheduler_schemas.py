import pytest
from pydantic import ValidationError

from app.schemas.scheduler import RescheduleRequest


@pytest.mark.parametrize(
    ("trigger_type", "required_field"),
    [
        ("FACULTY_LEAVE", "faculty_id"),
        ("ROOM_OUTAGE", "resource_id"),
        ("EVENT_INSERTION", "event_details"),
    ],
)
def test_reschedule_request_requires_trigger_details(trigger_type, required_field):
    with pytest.raises(ValidationError, match=f"{required_field} is required"):
        RescheduleRequest(trigger_type=trigger_type)


@pytest.mark.parametrize(
    "request_data",
    [
        {"trigger_type": "FACULTY_LEAVE", "faculty_id": 1},
        {"trigger_type": "ROOM_OUTAGE", "resource_id": 1},
        {"trigger_type": "EVENT_INSERTION", "event_details": {}},
        {"trigger_type": "EMERGENCY_ROOM_CHANGE"},
    ],
)
def test_reschedule_request_accepts_valid_trigger_details(request_data):
    assert RescheduleRequest(**request_data)


def test_reschedule_request_preserves_slot_id_validation():
    with pytest.raises(ValidationError, match="slot IDs must be unique"):
        RescheduleRequest(
            trigger_type="FACULTY_LEAVE",
            faculty_id=1,
            slot_ids=[1, 1],
        )
