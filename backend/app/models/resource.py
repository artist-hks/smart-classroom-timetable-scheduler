"""
Resource models — SB2/US5/T1 (Resource CRUD APIs).

Tables:
  resources            — rooms, labs, seminar halls, auditoriums.
  resource_equipment   — equipment list per resource (projector, 40 PCs, ...).

`department_id` is nullable on purpose: a NULL department means an
institute-wide shared resource (e.g. the main auditorium). Anyone logged in can
read shared resources, but only a SYSTEM_ADMIN may create/modify them.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.academic import ResourceType


class Resource(Base):
    __tablename__ = "resources"

    resource_id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.department_id"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Reuses the existing native PG enum `resource_type_enum` (created in SB2/US2/T2).
    resource_type: Mapped[ResourceType] = mapped_column(
        SAEnum(ResourceType, name="resource_type_enum"), nullable=False
    )
    capacity: Mapped[int] = mapped_column(nullable=False)
    building: Mapped[str | None] = mapped_column(String(100), nullable=True)
    floor: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # False = under maintenance / not schedulable (see frontend "LAB under maintenance").
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    equipment: Mapped[list["ResourceEquipment"]] = relationship(
        back_populates="resource",
        cascade="all, delete-orphan",
        order_by="ResourceEquipment.name",
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_resources_code"),
        CheckConstraint("capacity > 0", name="ck_resources_capacity_positive"),
        Index("ix_resources_department_id", "department_id"),
        Index("ix_resources_type", "resource_type"),
    )


class ResourceEquipment(Base):
    __tablename__ = "resource_equipment"

    equipment_id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.resource_id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False, server_default="1")

    resource: Mapped["Resource"] = relationship(back_populates="equipment")

    __table_args__ = (
        UniqueConstraint("resource_id", "name", name="uq_resource_equipment_name"),
        CheckConstraint("quantity > 0", name="ck_resource_equipment_qty_positive"),
    )
