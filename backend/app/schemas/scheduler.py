"""Pydantic schemas for timetable generation and dynamic rescheduling."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SchedulerSchema(BaseModel):
    """Shared schema configuration for scheduler API models."""

    model_config = ConfigDict(from_attributes=True)


class GenerateTimetableRequest(SchedulerSchema):
    """Options used to generate a timetable for an academic department."""

    academic_year_id: int = Field(ge=1, description="ID of the academic year.")
    semester: int = Field(ge=1, description="Semester number within the academic year.")
    department_id: int = Field(ge=1, description="ID of the department to schedule.")
    time_limit_seconds: float = Field(
        default=15.0,
        ge=1.0,
        le=120.0,
        allow_inf_nan=False,
        description="Maximum solver time in seconds (1 to 120).",
    )
    enable_ga_optimization: bool = Field(
        default=True, description="Whether to run genetic algorithm optimization."
    )
    enable_ml_demand_prediction: bool = Field(
        default=True, description="Whether to use ML demand prediction."
    )
    preferred_building: str | None = Field(
        default=None, min_length=1, description="Optional preferred building name or code."
    )
    scoring_weights: dict[str, float] | None = Field(
        default=None,
        description="Optional non-negative scoring weights keyed by scoring criterion.",
    )

    @field_validator("scoring_weights")
    @classmethod
    def validate_scoring_weights(
        cls, weights: dict[str, float] | None
    ) -> dict[str, float] | None:
        if weights is None:
            return None
        if not weights:
            raise ValueError("scoring_weights must contain at least one weight")
        if any(not math.isfinite(weight) or weight < 0 for weight in weights.values()):
            raise ValueError("scoring_weights values must be finite and non-negative")
        if not any(weight > 0 for weight in weights.values()):
            raise ValueError("at least one scoring weight must be greater than zero")
        return weights


class AllocatedSessionResponse(SchedulerSchema):
    """A scheduled session together with its assigned room and participants."""

    session_id: int = Field(ge=1, description="ID of the scheduled session.")
    label: str = Field(min_length=1, description="Human-readable session label.")
    day: int = Field(ge=1, le=7, description="Day of week, where 1 is Monday and 7 Sunday.")
    period: int = Field(ge=1, description="Period number within the day.")
    start_time: str = Field(min_length=1, description="Session start time as a display string.")
    end_time: str = Field(min_length=1, description="Session end time as a display string.")
    duration_minutes: int = Field(gt=0, description="Session duration in minutes.")
    course_code: str = Field(min_length=1, description="Code of the associated course.")
    session_type: str = Field(min_length=1, description="Session type, such as lecture or lab.")
    resource_id: int = Field(ge=1, description="ID of the assigned room or other resource.")
    resource_code: str = Field(min_length=1, description="Code of the assigned resource.")
    resource_name: str = Field(min_length=1, description="Name of the assigned resource.")
    resource_type: str = Field(min_length=1, description="Type of the assigned resource.")
    resource_capacity: int = Field(ge=0, description="Capacity of the assigned resource.")
    faculty_ids: list[int] = Field(
        description="IDs of faculty members assigned to the session."
    )
    participant_group_id: int = Field(ge=1, description="ID of the participant group.")
    subbatch_ids: list[int] = Field(description="IDs of sub-batches participating in the session.")
    required_equipment: dict[str, int] = Field(
        description="Required equipment types and quantities for the session."
    )

    @field_validator("faculty_ids", "subbatch_ids")
    @classmethod
    def validate_positive_ids(cls, ids: list[int]) -> list[int]:
        if any(item_id < 1 for item_id in ids):
            raise ValueError("IDs must be positive integers")
        return ids

    @field_validator("required_equipment")
    @classmethod
    def validate_equipment_quantities(cls, equipment: dict[str, int]) -> dict[str, int]:
        if any(not key.strip() or quantity < 0 for key, quantity in equipment.items()):
            raise ValueError("equipment names must be non-empty and quantities non-negative")
        return equipment


class TimetableGenerationResponse(SchedulerSchema):
    """Solver result and the allocations produced for a timetable request."""

    is_feasible: bool = Field(description="Whether a feasible timetable was found.")
    status_label: str = Field(min_length=1, description="Human-readable solver status.")
    solve_time_seconds: float = Field(
        ge=0, allow_inf_nan=False, description="Elapsed solver time in seconds."
    )
    total_sessions_scheduled: int = Field(
        ge=0, description="Number of sessions successfully scheduled."
    )
    ga_initial_fitness: float | None = Field(
        default=None, allow_inf_nan=False, description="Fitness before GA optimization."
    )
    ga_final_fitness: float | None = Field(
        default=None, allow_inf_nan=False, description="Fitness after GA optimization."
    )
    initial_utilization: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="Resource utilization before optimization, as a percentage.",
    )
    final_utilization: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="Resource utilization after optimization, as a percentage.",
    )
    allocations: list[AllocatedSessionResponse] = Field(
        default_factory=list, description="Scheduled session allocations."
    )
    diagnostics: list[str] = Field(
        default_factory=list, description="Solver diagnostics and constraint explanations."
    )


class RescheduleRequest(SchedulerSchema):
    """Details describing an event that requires timetable rescheduling."""

    trigger_type: Literal[
        "FACULTY_LEAVE", "ROOM_OUTAGE", "EVENT_INSERTION", "EMERGENCY_ROOM_CHANGE"
    ] = Field(description="Event type that triggered the rescheduling request.")
    faculty_id: int | None = Field(
        default=None, ge=1, description="Faculty member affected by the trigger, if applicable."
    )
    resource_id: int | None = Field(
        default=None, ge=1, description="Resource affected by the trigger, if applicable."
    )
    slot_ids: list[int] = Field(
        default_factory=list, description="Time slot IDs affected by the trigger."
    )
    event_details: dict[str, Any] | None = Field(
        default=None, description="Additional details for an inserted event, if applicable."
    )
    current_timetable_id: int | None = Field(
        default=None, ge=1, description="ID of the timetable to update, if specified."
    )

    @field_validator("slot_ids")
    @classmethod
    def validate_slot_ids(cls, slot_ids: list[int]) -> list[int]:
        if any(slot_id < 1 for slot_id in slot_ids):
            raise ValueError("slot IDs must be positive integers")
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("slot IDs must be unique")
        return slot_ids


class RescheduleResolutionResponse(SchedulerSchema):
    """One candidate strategy and its resulting timetable changes."""

    resolution_id: str = Field(min_length=1, description="Unique identifier for this resolution.")
    title: str = Field(min_length=1, description="Short title for the resolution.")
    strategy_type: str = Field(min_length=1, description="Strategy used to create the resolution.")
    changed_sessions_count: int = Field(
        ge=0, description="Number of sessions changed by this resolution."
    )
    stability_percentage: float = Field(
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="Percentage of the timetable left unchanged.",
    )
    disruption_score: float = Field(
        ge=0, allow_inf_nan=False, description="Non-negative measure of timetable disruption."
    )
    audit_summary: list[str] = Field(description="Audit notes explaining the resolution.")
    resolved_allocations: list[AllocatedSessionResponse] = Field(
        description="Session allocations after applying this resolution."
    )


class DynamicReschedulingResponse(SchedulerSchema):
    """Outcome and candidate resolutions for a dynamic rescheduling request."""

    is_resolved: bool = Field(description="Whether the trigger was successfully resolved.")
    trigger_type: str = Field(min_length=1, description="Trigger type handled by the scheduler.")
    affected_sessions_count: int = Field(
        ge=0, description="Number of sessions affected by the trigger."
    )
    affected_subbatch_ids: list[int] = Field(
        description="IDs of affected sub-batches."
    )
    affected_faculty_ids: list[int] = Field(
        description="IDs of affected faculty members."
    )
    chosen_resolution: RescheduleResolutionResponse | None = Field(
        default=None, description="Selected resolution, if the trigger was resolved."
    )
    alternative_resolutions: list[RescheduleResolutionResponse] = Field(
        default_factory=list, description="Other feasible resolutions considered."
    )
    diagnostics: list[str] = Field(
        default_factory=list, description="Diagnostics explaining the rescheduling outcome."
    )

    @field_validator("affected_subbatch_ids", "affected_faculty_ids")
    @classmethod
    def validate_affected_ids(cls, ids: list[int]) -> list[int]:
        if any(item_id < 1 for item_id in ids):
            raise ValueError("IDs must be positive integers")
        return ids
