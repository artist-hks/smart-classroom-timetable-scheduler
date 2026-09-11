from fastapi import FastAPI

app = FastAPI(
    title="Smart Classroom & Timetable Scheduler",
    version="0.1.0",
)

@app.get("/")
def root():
    return {"message": "Smart Classroom & Timetable Scheduler API"}

@app.get("/health")
def health():
    return {"status": "healthy"}
