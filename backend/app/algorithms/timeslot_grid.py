"""
TimeSlot and Academic Schedule Grid Modeling.

Provides grid representation, slot lookup, break detection, and
multi-hour continuous slot interval validation per HC-12, HC-14, and HC-15.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Sequence


@dataclass(frozen=True)
class GridSlot:
    """Represents an atomic time slot on the schedule grid."""
    slot_id: int
    day: int            # 1 = Monday, 2 = Tuesday, ..., 5 = Friday, 6 = Saturday
    period: int         # 1-indexed period within the day (1, 2, 3, ...)
    start_time: str     # "09:00"
    end_time: str       # "10:00"
    duration_minutes: int = 60
    is_break: bool = False
    label: str = ""

    def __repr__(self) -> str:
        tag = " [BREAK]" if self.is_break else ""
        return f"Slot({self.slot_id}: D{self.day}P{self.period} {self.start_time}-{self.end_time}{tag})"


class ScheduleGrid:
    """
    Manages the academic scheduling grid across all operational days and periods.
    """

    def __init__(self, slots: Sequence[GridSlot]):
        self.slots = list(slots)
        self.slot_by_id: dict[int, GridSlot] = {s.slot_id: s for s in self.slots}
        
        # Organize slots by day: {day: [GridSlot, ... sorted by period]}
        self.slots_by_day: dict[int, list[GridSlot]] = {}
        for s in self.slots:
            self.slots_by_day.setdefault(s.day, []).append(s)
        for day in self.slots_by_day:
            self.slots_by_day[day].sort(key=lambda s: s.period)

    @classmethod
    def create_standard_piet_grid(
        cls,
        days: int = 5,                      # 5 operational days (Mon-Fri) or 6
        periods_per_day: int = 7,          # 7 periods per day (e.g. 09:00 - 16:30)
        period_duration_minutes: int = 60, # 60 min slots (or 50 min)
        lunch_period_index: int = 4,       # Period 4 is lunch break (12:00 - 13:00)
    ) -> ScheduleGrid:
        """
        Factory helper to create standard PIET college weekly academic grid.
        """
        slots: list[GridSlot] = []
        slot_id = 1
        base_hour = 9

        for day in range(1, days + 1):
            for period in range(1, periods_per_day + 1):
                h_start = base_hour + (period - 1)
                h_end = h_start + 1
                start_str = f"{h_start:02d}:00"
                end_str = f"{h_end:02d}:00"
                is_break = (period == lunch_period_index)
                label = "Lunch Break" if is_break else f"Period {period}"

                slot = GridSlot(
                    slot_id=slot_id,
                    day=day,
                    period=period,
                    start_time=start_str,
                    end_time=end_str,
                    duration_minutes=period_duration_minutes,
                    is_break=is_break,
                    label=label,
                )
                slots.append(slot)
                slot_id += 1

        return cls(slots)

    def get_valid_start_slots_for_duration(self, duration_minutes: int) -> list[int]:
        """
        Returns all slot IDs where a session of `duration_minutes` can validly begin
        without overflowing the day or crossing a break slot (HC-14 Multi-hour continuity).
        """
        unit_duration = 60  # standard slot duration
        needed_periods = max(1, round(duration_minutes / unit_duration))
        valid_start_slots: list[int] = []

        for day, day_slots in self.slots_by_day.items():
            for i, slot in enumerate(day_slots):
                # Check if we have enough consecutive non-break slots starting at i
                if i + needed_periods <= len(day_slots):
                    consecutive_window = day_slots[i : i + needed_periods]
                    # Must not contain any break slot and must be strictly consecutive
                    if all(not s.is_break for s in consecutive_window):
                        # Verify consecutive period numbers
                        is_consecutive = all(
                            consecutive_window[k].period == consecutive_window[k - 1].period + 1
                            for k in range(1, len(consecutive_window))
                        )
                        if is_consecutive:
                            valid_start_slots.append(slot.slot_id)

        return valid_start_slots

    def get_occupied_slots(self, start_slot_id: int, duration_minutes: int) -> list[int]:
        """
        Returns all atomic slot IDs occupied by a session starting at `start_slot_id`
        for the given `duration_minutes`.
        """
        start_slot = self.slot_by_id[start_slot_id]
        unit_duration = 60
        needed_periods = max(1, round(duration_minutes / unit_duration))
        
        day_slots = self.slots_by_day[start_slot.day]
        start_idx = next(i for i, s in enumerate(day_slots) if s.slot_id == start_slot_id)
        
        occupied = [s.slot_id for s in day_slots[start_idx : start_idx + needed_periods]]
        return occupied
