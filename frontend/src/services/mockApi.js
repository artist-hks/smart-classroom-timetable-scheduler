// Returns data in the SAME shape as the FastAPI backend (snake_case, numeric ids),
// so pages and adapters never branch on mock vs. real.
import { departments, sections, subBatches, days, timeSlots } from "../data/academicStructure";
import { faculty } from "../data/faculty";
import { resources, coursesById } from "../data/courses";
import { sessions } from "../data/timetable";
import { optimizationReport } from "../data/operations";

const delay = (ms) => new Promise((r) => setTimeout(r, ms));
const deptNumeric = (id) => departments.findIndex((d) => d.id === id) + 1;
const sectionNumeric = (id) => sections.findIndex((s) => s.id === id) + 1;
const subBatchNumeric = (id) => subBatches.findIndex((b) => b.id === id) + 1;
const facultyNumeric = (id) => faculty.findIndex((f) => f.id === id) + 1;
const resourceNumeric = (id) => resources.findIndex((r) => r.id === id) + 1;

export async function mockReference() {
  await delay(250);
  return {
    departments: departments.map((d, i) => ({ department_id: i + 1, code: d.shortName, name: d.name })),
    academicYears: [{ academic_year_id: 1, label: "2026-27", is_active: true }],
    semesters: [1, 2, 3, 4, 5, 6, 7, 8].map((n) => ({ semester_id: n, semester_number: n, name: `Semester ${n}` })),
    sections: sections.map((s, i) => ({
      section_id: i + 1,
      department_id: deptNumeric(s.department),
      academic_year_id: 1,
      semester_id: s.semester,
      name: s.name,
      student_strength: s.strength,
    })),
    subBatches: subBatches.map((b, i) => ({
      subbatch_id: i + 1,
      section_id: sectionNumeric(b.parentSection),
      name: b.name,
      student_strength: b.strength,
    })),
    faculty: faculty.map((f, i) => ({
      faculty_id: i + 1,
      department_id: deptNumeric(f.department),
      employee_code: f.code,
      full_name: f.name,
    })),
  };
}

function toMinutes(t) {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

export async function mockGenerate(payload) {
  await delay(1400);

  // Only CSE has seeded data; other departments exercise the infeasible/diagnostics UI.
  if (payload.department_id !== 1) {
    return {
      is_feasible: false,
      status_label: "INFEASIBLE",
      solve_time_seconds: 0.4,
      total_sessions_scheduled: 0,
      ga_initial_fitness: null,
      ga_final_fitness: null,
      initial_utilization: null,
      final_utilization: null,
      allocations: [],
      diagnostics: [
        "No courses with session configurations were found for the selected department and semester.",
        "Add course session configurations (weekly hours, session types) before generating.",
      ],
    };
  }

  const allocations = sessions.map((s, i) => {
    const course = coursesById[s.courseId];
    const resource = resources.find((r) => r.id === s.resource);
    const ids = s.participants.flatMap((p) =>
      p.subBatches
        ? p.subBatches.map(subBatchNumeric)
        : subBatches.filter((b) => b.parentSection === p.section).map((b) => subBatchNumeric(b.id))
    );
    const period = timeSlots.filter((t) => t.type !== "break").findIndex((t) => t.start === s.start) + 1;
    return {
      session_id: i + 1,
      label: `${course.name} (${s.type.replace("_", " ")})`,
      day: days.indexOf(s.day) + 1,
      period: Math.max(period, 1),
      start_time: s.start,
      end_time: s.end,
      duration_minutes: toMinutes(s.end) - toMinutes(s.start),
      course_code: course.code,
      session_type: s.type,
      resource_id: resourceNumeric(s.resource),
      resource_code: resource.code,
      resource_name: resource.code,
      resource_type: resource.type.toUpperCase().replace(" ", "_"),
      resource_capacity: resource.capacity,
      faculty_ids: s.faculty.map(facultyNumeric),
      participant_group_id: i + 1,
      subbatch_ids: ids,
      required_equipment: {},
    };
  });

  return {
    is_feasible: true,
    status_label: "OPTIMAL",
    solve_time_seconds: 3.2,
    total_sessions_scheduled: allocations.length,
    ga_initial_fitness: payload.enable_ga_optimization ? optimizationReport.initialFitness : null,
    ga_final_fitness: payload.enable_ga_optimization ? optimizationReport.finalFitness : null,
    initial_utilization: payload.enable_ga_optimization ? 72 : null,
    final_utilization: payload.enable_ga_optimization ? Math.round(optimizationReport.utilization * 100) : null,
    allocations,
    diagnostics: [],
  };
}
