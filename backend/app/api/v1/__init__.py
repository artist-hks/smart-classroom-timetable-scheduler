"""Aggregates every /api/v1 router (SB2/US3-US6 CRUD APIs)."""

from fastapi import APIRouter

from app.api.v1.academic import (
    academic_years_router,
    departments_router,
    sections_router,
    semesters_router,
    sub_batches_router,
)
from app.api.v1.faculty import router as faculty_router
from app.api.v1.resources import router as resources_router
from app.api.v1.scheduling_config import breaks_router, timeslots_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(departments_router)
api_router.include_router(academic_years_router)
api_router.include_router(semesters_router)
api_router.include_router(sections_router)
api_router.include_router(sub_batches_router)
api_router.include_router(faculty_router)
api_router.include_router(resources_router)
api_router.include_router(timeslots_router)
api_router.include_router(breaks_router)
