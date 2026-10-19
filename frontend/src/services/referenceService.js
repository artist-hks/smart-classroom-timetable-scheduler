import { api, USE_MOCK } from "./api";
import { mockReference } from "./mockApi";

// Lookup data the timetable UI needs to turn ids into names.
export async function fetchReferenceData() {
  if (USE_MOCK) return mockReference();
  const page = { params: { limit: 500 } };
  const [departments, academicYears, semesters, sections, subBatches, faculty] = await Promise.all([
    api.get("/api/v1/departments", page),
    api.get("/api/v1/academic-years", page),
    api.get("/api/v1/semesters", page),
    api.get("/api/v1/sections", page),
    api.get("/api/v1/sub-batches", page),
    api.get("/api/v1/faculty", page),
  ]);
  return { departments, academicYears, semesters, sections, subBatches, faculty };
}
