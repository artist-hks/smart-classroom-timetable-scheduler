import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Smart Classroom & Timetable Scheduler",
    version="0.1.0",
)

# The Vite dev server (http://localhost:5173) calls this API from the browser,
# so it must be allowed. Override with CORS_ORIGINS="https://a.com,https://b.com".
_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Smart Classroom & Timetable Scheduler API"}

@app.get("/health")
def health():
    return {"status": "healthy"}

from app.api.auth import router as auth_router
from app.api.v1 import api_router as v1_router
app.include_router(auth_router)
app.include_router(v1_router)
