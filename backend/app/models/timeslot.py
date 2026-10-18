"""
TimeSlot & Break configuration models — SB2/US6/T1.

Institute-wide scheduling grid configuration (not department-owned):
  time_slots — the teaching periods per day (period 1 = 09:00-10:00, ...).
  breaks     — lunch / tea breaks during which nothing may be scheduled
               (HC-12 / HC-14 / HC-15 consume this in the solver).

`day_of_week` follows the same convention as sessions.scheduled_day:
1 = Monday ... 7 = Sunday. For `breaks`, NULL means "every operating day".
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimeSlot(Base):
    __tablename__ = "time_slots"

    time_slot_id: Mapped[int] = mapped_column(primary_key=True)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    period: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    __table_args__ = (
        UniqueConstraint("day_of_week", "period", name="uq_time_slots_day_period"),
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_time_slots_day_range"),
        CheckConstraint("period >= 1", name="ck_time_slots_period_positive"),
        CheckConstraint("end_time > start_time", name="ck_time_slots_time_order"),
    )


class Break(Base):
    __tablename__ = "breaks"

    break_id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    # NULL = applies to every day.
    day_of_week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    start_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "day_of_week IS NULL OR day_of_week BETWEEN 1 AND 7",
            name="ck_breaks_day_range",
        ),
        CheckConstraint("end_time > start_time", name="ck_breaks_time_order"),
    )
