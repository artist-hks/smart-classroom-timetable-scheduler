"""
Resource CRUD — SB2/US5/T1.

    /api/v1/resources   (rooms, labs, seminar halls, auditoriums + equipment list)

Visibility / write rules:
  * Department-owned resource (department_id set): same rules as faculty —
    read scoped to own department; write = SYSTEM_ADMIN or that department's COORDINATOR.
  * Shared resource (department_id NULL, e.g. main auditorium): readable by every
    logged-in user, writable by SYSTEM_ADMIN only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import selectinload

from app.api.deps import department_scope, enforce_department_scope, get_current_user
from app.api.v1.common import (
    Pagination,
    admin_or_coordinator,
    apply_updates,
    commit_or_409,
    require_exists,
)
from app.db.session import get_db
from app.models.academic import Department, ResourceType
from app.models.auth import User, UserRole
from app.models.resource import Resource, ResourceEquipment
from app.schemas.resource import EquipmentItem, ResourceCreate, ResourceOut, ResourceUpdate

router = APIRouter(prefix="/resources", tags=["resources"])

_CONFLICT = "A resource with this code already exists"


def _check_write_access(user: User, resource_department_id: int | None) -> None:
    if resource_department_id is None:
        if user.role != UserRole.SYSTEM_ADMIN:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Only a SYSTEM_ADMIN can manage institute-wide shared resources",
            )
        return
    enforce_department_scope(user, resource_department_id)


def _validate_equipment(items: list[EquipmentItem]) -> None:
    seen: set[str] = set()
    for item in items:
        key = item.name.strip().lower()
        if key in seen:
            raise HTTPException(422, detail=f"Duplicate equipment entry: '{item.name}'")
        seen.add(key)


def _equipment_rows(items: list[EquipmentItem]) -> list[ResourceEquipment]:
    _validate_equipment(items)
    return [ResourceEquipment(name=i.name.strip(), quantity=i.quantity) for i in items]


def _load(db: DBSession, resource_id: int) -> Resource:
    r = db.scalars(
        select(Resource)
        .options(selectinload(Resource.equipment))
        .where(Resource.resource_id == resource_id)
    ).first()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return r


def _load_for_read(db: DBSession, resource_id: int, user: User) -> Resource:
    r = _load(db, resource_id)
    if r.department_id is not None:  # shared resources are visible to everyone
        enforce_department_scope(user, r.department_id)
    return r


@router.get("", response_model=list[ResourceOut])
def list_resources(
    department_id: int | None = Query(None),
    resource_type: ResourceType | None = Query(None),
    is_active: bool | None = Query(None),
    min_capacity: int | None = Query(None, ge=1),
    q: str | None = Query(None, description="Search code, name or building"),
    scope: int | None = Depends(department_scope),
    page: Pagination = Depends(),
    db: DBSession = Depends(get_db),
):
    query = select(Resource).options(selectinload(Resource.equipment))
    if scope is not None:
        if department_id is not None and department_id != scope:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="You do not have access to this department's data"
            )
        # own department's resources + institute-wide shared ones
        query = query.where(
            or_(Resource.department_id == scope, Resource.department_id.is_(None))
        )
    elif department_id is not None:
        query = query.where(Resource.department_id == department_id)
    if resource_type is not None:
        query = query.where(Resource.resource_type == resource_type)
    if is_active is not None:
        query = query.where(Resource.is_active == is_active)
    if min_capacity is not None:
        query = query.where(Resource.capacity >= min_capacity)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(Resource.code.ilike(like), Resource.name.ilike(like), Resource.building.ilike(like))
        )
    query = query.order_by(Resource.code).limit(page.limit).offset(page.offset)
    return db.scalars(query).all()


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    return _load_for_read(db, resource_id, current_user)


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def create_resource(
    payload: ResourceCreate,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    _check_write_access(current_user, payload.department_id)
    if payload.department_id is not None:
        require_exists(db, Department, payload.department_id, "department_id")
    resource = Resource(
        department_id=payload.department_id,
        code=payload.code,
        name=payload.name,
        resource_type=payload.resource_type,
        capacity=payload.capacity,
        building=payload.building,
        floor=payload.floor,
        is_active=payload.is_active,
        equipment=_equipment_rows(payload.equipment),
    )
    db.add(resource)
    commit_or_409(db, _CONFLICT)
    return _load(db, resource.resource_id)


@router.patch("/{resource_id}", response_model=ResourceOut)
@router.put("/{resource_id}", response_model=ResourceOut)
def update_resource(
    resource_id: int,
    payload: ResourceUpdate,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    resource = _load(db, resource_id)
    _check_write_access(current_user, resource.department_id)
    data = payload.model_dump(exclude_unset=True)

    if "equipment" in data:
        if payload.equipment is None:
            raise HTTPException(
                422, detail="'equipment' cannot be null"
            )
        new_items = {i.name.strip().lower(): i for i in payload.equipment}
        _validate_equipment(payload.equipment)
        # Diff by name (see faculty.replace_subjects for why not delete-all/insert-all).
        existing = {e.name.lower(): e for e in resource.equipment}
        for key, row in existing.items():
            if key not in new_items:
                resource.equipment.remove(row)
        for key, item in new_items.items():
            if key in existing:
                existing[key].quantity = item.quantity
            else:
                resource.equipment.append(
                    ResourceEquipment(name=item.name.strip(), quantity=item.quantity)
                )
        del data["equipment"]

    apply_updates(resource, data, nullable={"building", "floor"})
    commit_or_409(db, _CONFLICT)
    return _load(db, resource_id)


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(
    resource_id: int,
    current_user: User = Depends(admin_or_coordinator),
    db: DBSession = Depends(get_db),
):
    resource = _load(db, resource_id)
    _check_write_access(current_user, resource.department_id)
    db.delete(resource)
    commit_or_409(
        db, "Resource is assigned to sessions; mark it inactive (is_active=false) instead"
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
