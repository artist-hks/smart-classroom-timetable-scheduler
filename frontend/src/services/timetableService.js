import { api, USE_MOCK } from "./api";
import { mockGenerate } from "./mockApi";

// The backend defines GenerateTimetableRequest / TimetableGenerationResponse
// (app/schemas/scheduler.py) but does not expose an HTTP route for them yet.
// Set VITE_GENERATE_PATH once the route exists.
const GENERATE_PATH = import.meta.env.VITE_GENERATE_PATH || "/api/v1/timetable/generate";

/** POST GenerateTimetableRequest -> TimetableGenerationResponse (synchronous). */
export async function generateTimetable(payload, { signal } = {}) {
  if (USE_MOCK) return mockGenerate(payload);
  return api.post(GENERATE_PATH, payload, { signal });
}
