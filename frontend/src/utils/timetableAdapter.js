// Converts backend AllocatedSessionResponse rows into the session shape WeeklyGrid renders.
export const API_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

// Backend start_time/end_time are "display strings": accept "09:00", "09:00:00" and "9:00 AM".
export function normalizeTime(value) {
  const match = /^(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?$/.exec(String(value).trim());
  if (!match) return null;
  let hours = Number(match[1]);
  const minutes = match[2];
  const period = match[3]?.toUpperCase();
  if (period === "PM" && hours < 12) hours += 12;
  if (period === "AM" && hours === 12) hours = 0;
  return `${String(hours).padStart(2, "0")}:${minutes}`;
}

export function adaptAllocations(allocations = [], reference) {
  const facultyById = new Map((reference?.faculty || []).map((f) => [f.faculty_id, f.full_name]));
  const subBatchById = new Map((reference?.subBatches || []).map((b) => [b.subbatch_id, b]));

  return allocations
    .map((a) => {
      const start = normalizeTime(a.start_time);
      const end = normalizeTime(a.end_time);
      if (!start || !end || !API_DAY_NAMES[a.day - 1]) return null; // skip rows the grid can't place

      const subBatches = a.subbatch_ids.map((id) => subBatchById.get(id));
      return {
        id: `api-${a.session_id}`,
        api: true,
        type: String(a.session_type).toUpperCase(),
        day: API_DAY_NAMES[a.day - 1],
        start,
        end,
        status: "confirmed",
        facultyIds: a.faculty_ids,
        resourceId: a.resource_id,
        sectionIds: [...new Set(subBatches.filter(Boolean).map((b) => b.section_id))],
        display: {
          course: a.label,
          courseCode: a.course_code,
          faculty: a.faculty_ids.map((id) => facultyById.get(id) || `Faculty #${id}`).join(", "),
          participants: a.subbatch_ids.map((id, i) => subBatches[i]?.name || `SB-${id}`).join("+"),
          resource: a.resource_code,
          resourceDetail: `${a.resource_code} · ${a.resource_type} · Cap. ${a.resource_capacity}`,
        },
      };
    })
    .filter(Boolean);
}

export function sectionLabel(section, reference) {
  const dept = reference?.departments?.find((d) => d.department_id === section.department_id);
  const sem = reference?.semesters?.find((s) => s.semester_id === section.semester_id);
  return `${section.name} · ${dept?.code ?? "?"} Sem ${sem?.semester_number ?? "?"}`;
}
