"""
TimeSlot & Break configuration — SB2/US6/T1.

    /api/v1/timeslots      (+ POST /timeslots/bulk)
    /api/v1/breaks

Institute-wide configuration (no department owner): any logged-in user can
read it, only SYSTEM_ADMIN can change it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user
from app.api.v1.common import (
    Pagination,
    admin_only,
    apply_updates,
    commit_or_409,
    get_or_404,
    times_overlap,
)
from app.db.session import get_db
from app.models.timeslot import Break, TimeSlot
from app.schemas.timeslot import (
    BreakCreate,
    BreakOut,
    BreakUpdate,
    TimeSlotBulkCreate,
    TimeSlotCreate,
    TimeSlotOut,
    TimeSlotUpdate,
)

# ===========================================================================
# Time slots
# ===========================================================================
timeslots_router = APIRouter(
    prefix="/timeslots", tags=["timeslots"], dependencies=[Depends(get_current_user)]
)

_SLOT_DUP = "A time slot with this day and period already exists"


def _assert_slot_free(
    db: DBSession, day: int, start, end, exclude_id: int | None = None
) -> None:
    rows = db.scalars(select(TimeSlot).where(TimeSlot.day_of_week == day)).all()
    for s in rows:
        if s.time_slot_id == exclude_id:
            continue
        if times_overlap(start, end, s.start_time, s.end_time):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Overlaps existing slot (period {s.period}, {s.start_time:%H:%M}-{s.end_time:%H:%M}) on day {day}",
            )


@timeslots_router.get("", response_model=list[TimeSlotOut])
def list_timeslots(
    day_of_week: int | None = Query(None, ge=1, le=7),
    is_active: bool | None = Query(None),
    page: Pagination = Depends(),
    db: DBSession = Depends(get_db),
):
    query = select(TimeSlot).order_by(TimeSlot.day_of_week, TimeSlot.period)
    if day_of_week is not None:
        query = query.where(TimeSlot.day_of_week == day_of_week)
    if is_active is not None:
        query = query.where(TimeSlot.is_active == is_active)
    return db.scalars(query.limit(page.limit).offset(page.offset)).all()


@timeslots_router.get("/{time_slot_id}", response_model=TimeSlotOut)
def get_timeslot(time_slot_id: int, db: DBSession = Depends(get_db)):
    return get_or_404(db, TimeSlot, time_slot_id, "Time slot")


@timeslots_router.post(
    "", response_model=TimeSlotOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(admin_only)]
)
def create_timeslot(payload: TimeSlotCreate, db: DBSession = Depends(get_db)):
    _assert_slot_free(db, payload.day_of_week, payload.start_time, payload.end_time)
    slot = TimeSlot(**payload.model_dump())
    db.add(slot)
    commit_or_409(db, _SLOT_DUP)
    db.refresh(slot)
    return slot


@timeslots_router.post(
    "/bulk",
    response_model=list[TimeSlotOut],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_only)],
)
def bulk_create_timeslots(payload: TimeSlotBulkCreate, db: DBSession = Depends(get_db)):
    """Create a whole grid in one call. All-or-nothing: any conflict creates nothing."""
    seen: list[TimeSlotCreate] = []
    for s in payload.slots:
        for prev in seen:
            if prev.day_of_week != s.day_of_week:
                continue
            if prev.period == s.period or times_overlap(
                s.start_time, s.end_time, prev.start_time, prev.end_time
            ):
                raise HTTPException(
                    422,
                    detail=f"Slots in the request clash on day {s.day_of_week} (period {s.period})",
                )
        seen.append(s)
        _assert_slot_free(db, s.day_of_week, s.start_time, s.end_time)
    rows = [TimeSlot(**s.model_dump()) for s in payload.slots]
    db.add_all(rows)
    commit_or_409(db, _SLOT_DUP)
    for r in rows:
        db.refresh(r)
    return rows


@timeslots_router.patch(
    "/{time_slot_id}",
    response_model=TimeSlotOut,
    dependencies=[Depends(admin_only)],
)
@timeslots_router.put(
    "/{time_slot_id}",
    response_model=TimeSlotOut,
    dependencies=[Depends(admin_only)],
)
def update_timeslot(time_slot_id: int, payload: TimeSlotUpdate, db: DBSession = Depends(get_db)):
    slot = get_or_404(db, TimeSlot, time_slot_id, "Time slot")
    apply_updates(slot, payload.model_dump(exclude_unset=True), nullable={"label"})
    if slot.end_time <= slot.start_time:
        raise HTTPException(
            422, detail="end_time must be after start_time"
        )
    _assert_slot_free(db, slot.day_of_week, slot.start_time, slot.end_time, exclude_id=slot.time_slot_id)
    commit_or_409(db, _SLOT_DUP)
    db.refresh(slot)
    return slot


@timeslots_router.delete(
    "/{time_slot_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(admin_only)]
)
def delete_timeslot(time_slot_id: int, db: DBSession = Depends(get_db)):
    slot = get_or_404(db, TimeSlot, time_slot_id, "Time slot")
    db.delete(slot)
    commit_or_409(db, "Time slot is still in use")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ===========================================================================
# Breaks
# ===========================================================================
breaks_router = APIRouter(
    prefix="/breaks", tags=["breaks"], dependencies=[Depends(get_current_user)]
)


def _assert_break_free(
    db: DBSession, day: int | None, start, end, exclude_id: int | None = None
) -> None:
    """A break clashes with another break that applies on the same day
    (same day, or either one being 'every day' = NULL)."""
    query = select(Break)
    if day is not None:
        query = query.where(or_(Break.day_of_week == day, Break.day_of_week.is_(None)))
    for b in db.scalars(query).all():
        if b.break_id == exclude_id:
            continue
        if times_overlap(start, end, b.start_time, b.end_time):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Overlaps existing break '{b.label}' ({b.start_time:%H:%M}-{b.end_time:%H:%M})",
            )


@breaks_router.get("", response_model=list[BreakOut])
def list_breaks(
    day_of_week: int | None = Query(
        None, ge=1, le=7, description="Breaks that apply on this day (incl. every-day breaks)"
    ),
    page: Pagination = Depends(),
    db: DBSession = Depends(get_db),
):
    query = select(Break).order_by(Break.day_of_week.nulls_first(), Break.start_time)
    if day_of_week is not None:
        query = query.where(or_(Break.day_of_week == day_of_week, Break.day_of_week.is_(None)))
    return db.scalars(query.limit(page.limit).offset(page.offset)).all()


@breaks_router.get("/{break_id}", response_model=BreakOut)
def get_break(break_id: int, db: DBSession = Depends(get_db)):
    return get_or_404(db, Break, break_id, "Break")


@breaks_router.post(
    "", response_model=BreakOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(admin_only)]
)
def create_break(payload: BreakCreate, db: DBSession = Depends(get_db)):
    _assert_break_free(db, payload.day_of_week, payload.start_time, payload.end_time)
    brk = Break(**payload.model_dump())
    db.add(brk)
    commit_or_409(db, "Could not create break")
    db.refresh(brk)
    return brk


@breaks_router.patch(
    "/{break_id}",
    response_model=BreakOut,
    dependencies=[Depends(admin_only)],
)
@breaks_router.put(
    "/{break_id}",
    response_model=BreakOut,
    dependencies=[Depends(admin_only)],
)
def update_break(break_id: int, payload: BreakUpdate, db: DBSession = Depends(get_db)):
    brk = get_or_404(db, Break, break_id, "Break")
    apply_updates(brk, payload.model_dump(exclude_unset=True), nullable={"day_of_week"})
    if brk.end_time <= brk.start_time:
        raise HTTPException(
            422, detail="end_time must be after start_time"
        )
    _assert_break_free(db, brk.day_of_week, brk.start_time, brk.end_time, exclude_id=brk.break_id)
    commit_or_409(db, "Could not update break")
    db.refresh(brk)
    return brk


@breaks_router.delete(
    "/{break_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(admin_only)]
)
def delete_break(break_id: int, db: DBSession = Depends(get_db)):
    brk = get_or_404(db, Break, break_id, "Break")
    db.delete(brk)
    commit_or_409(db, "Could not delete break")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
