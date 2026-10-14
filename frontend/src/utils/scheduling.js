import { coursesById, resourcesById } from "../data/courses";
import { facultyById } from "../data/faculty";
import { sections, subBatches } from "../data/academicStructure";

export const sectionsById = Object.fromEntries(sections.map((s) => [s.id, s]));
export const subBatchesById = Object.fromEntries(subBatches.map((b) => [b.id, b]));

export function getCourse(id) {
  return coursesById[id];
}

export function getFacultyMember(id) {
  return facultyById[id];
}

export function getResource(id) {
  return resourcesById[id];
}

export function formatFacultyNames(facultyIds = []) {
  return facultyIds.map((id) => facultyById[id]?.name || id).join(", ");
}

export function formatParticipants(participants = []) {
  return participants
    .map((p) => {
      const section = sectionsById[p.section];
      const sectionLabel = section ? `${section.name}` : p.section;
      if (!p.subBatches) return sectionLabel;
      const names = p.subBatches.map((b) => subBatchesById[b]?.name || b).join("+");
      return names;
    })
    .join(" + ");
}

export function participantStrength(participants = []) {
  return participants.reduce((total, p) => {
    if (!p.subBatches) {
      return total + (sectionsById[p.section]?.strength || 0);
    }
    return total + p.subBatches.reduce((sum, b) => sum + (subBatchesById[b]?.strength || 0), 0);
  }, 0);
}

export function timeToMinutes(t) {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

export function overlaps(aStart, aEnd, bStart, bEnd) {
  return timeToMinutes(aStart) < timeToMinutes(bEnd) && timeToMinutes(bStart) < timeToMinutes(aEnd);
}
