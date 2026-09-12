"""
Auth / RBAC models — SB2/US7/T1.

Implements the `User` / `Role` conceptual entities from the SRS's data
requirements (§6.1), scoped to exactly what NFR-3 and §2.4 (User Classes)
require: password hashing, role-based authorization, and department-level
access isolation.

Design decisions (mirrors the pattern set in SB2/US2/T1's academic models):

1. `role` is a native Postgres ENUM (`user_role_enum`), not a separate
   `roles` table. The SRS's §2.4 defines exactly four fixed user classes
   (System Administrator, Timetable Coordinator, Faculty, Student) with no
   indication this set is meant to be admin-configurable — the same
   reasoning already applied to `session_type_enum` / `resource_type_enum`
   in the academic hierarchy schema.

2. `department_id` is nullable. System Administrators are explicitly
   global (§2.4: "System-level configuration"), so they have no department.
   Coordinator/Faculty/Student rows must have one — enforced by
   `ck_users_department_scope` below, not just application logic, so a bad
   INSERT from anywhere (migration, admin script, future endpoint) can't
   silently create an unscoped Coordinator.

3. `hashed_password` — bcrypt via passlib. Never store or log plaintext;
   NFR-3 explicitly calls out "Password hashing."

4. `is_active` — supports FR from §2.4: "Activate/deactivate accounts."
   A deactivated user can authenticate-fail without deleting their row
   (preserves audit history, matches how the rest of this schema treats
   soft state via enums like `session_status_enum` rather than deletes).
"""

from __future__ import annotations

import datetime
import enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(str, enum.Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    COORDINATOR = "COORDINATOR"
    FACULTY = "FACULTY"
    STUDENT = "STUDENT"


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role_enum"), nullable=False
    )
    # Nullable: SYSTEM_ADMIN has no department. Everyone else must have one
    # (see ck_users_department_scope). No FK to `resources`/`faculty`-style
    # deferral needed here — `departments` already exists (SB2/US2/T2).
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.department_id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "(role = 'SYSTEM_ADMIN' AND department_id IS NULL) "
            "OR (role != 'SYSTEM_ADMIN' AND department_id IS NOT NULL)",
            name="ck_users_department_scope",
        ),
    )
