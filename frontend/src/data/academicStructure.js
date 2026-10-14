// Mock data representing the academic hierarchy: Department -> Semester -> Section -> Sub-Batch
// Modelled on the PIET CSE scheduling scenarios described in the SRS (Section 10.1).

export const departments = [
  { id: "cse", name: "Computer Science & Engineering", shortName: "CSE", sections: 4, faculty: 22 },
  { id: "it", name: "Information Technology", shortName: "IT", sections: 2, faculty: 12 },
  { id: "ece", name: "Electronics & Communication", shortName: "ECE", sections: 3, faculty: 16 },
  { id: "me", name: "Mechanical Engineering", shortName: "ME", sections: 2, faculty: 10 },
];

export const academicYear = "2026-27";

export const sections = [
  {
    id: "sec-cse-7d",
    name: "Section D",
    department: "cse",
    semester: 7,
    academicYear,
    strength: 88,
    subBatchCount: 3,
  },
  {
    id: "sec-cse-7c",
    name: "Section C",
    department: "cse",
    semester: 7,
    academicYear,
    strength: 84,
    subBatchCount: 3,
  },
  {
    id: "sec-cse-5a",
    name: "Section A",
    department: "cse",
    semester: 5,
    academicYear,
    strength: 90,
    subBatchCount: 3,
  },
  {
    id: "sec-cse-5b",
    name: "Section B",
    department: "cse",
    semester: 5,
    academicYear,
    strength: 86,
    subBatchCount: 3,
  },
  {
    id: "sec-it-5a",
    name: "Section A",
    department: "it",
    semester: 5,
    academicYear,
    strength: 78,
    subBatchCount: 2,
  },
];

export const subBatches = [
  { id: "d1", name: "D1", parentSection: "sec-cse-7d", strength: 30 },
  { id: "d2", name: "D2", parentSection: "sec-cse-7d", strength: 29 },
  { id: "d3", name: "D3", parentSection: "sec-cse-7d", strength: 29 },
  { id: "c1", name: "C1", parentSection: "sec-cse-7c", strength: 28 },
  { id: "c2", name: "C2", parentSection: "sec-cse-7c", strength: 28 },
  { id: "c3", name: "C3", parentSection: "sec-cse-7c", strength: 28 },
  { id: "a1", name: "A1", parentSection: "sec-cse-5a", strength: 30 },
  { id: "a2", name: "A2", parentSection: "sec-cse-5a", strength: 30 },
  { id: "a3", name: "A3", parentSection: "sec-cse-5a", strength: 30 },
  { id: "b1", name: "B1", parentSection: "sec-cse-5b", strength: 29 },
  { id: "b2", name: "B2", parentSection: "sec-cse-5b", strength: 29 },
  { id: "b3", name: "B3", parentSection: "sec-cse-5b", strength: 28 },
  { id: "it-a1", name: "A1", parentSection: "sec-it-5a", strength: 39 },
  { id: "it-a2", name: "A2", parentSection: "sec-it-5a", strength: 39 },
];

export const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

// Configurable slot grid used for display purposes. Individual sessions may still
// occupy multi-hour continuous spans (HC-14) that cross these boundaries.
export const timeSlots = [
  { id: "ts1", label: "9:00 – 10:00", start: "09:00", end: "10:00" },
  { id: "ts2", label: "10:00 – 11:00", start: "10:00", end: "11:00" },
  { id: "ts3", label: "11:00 – 12:00", start: "11:00", end: "12:00" },
  { id: "brk1", label: "12:00 – 12:40", start: "12:00", end: "12:40", type: "break", label2: "Lunch" },
  { id: "ts4", label: "12:40 – 1:40", start: "12:40", end: "13:40" },
  { id: "ts5", label: "1:40 – 2:40", start: "13:40", end: "14:40" },
  { id: "ts6", label: "2:40 – 3:40", start: "14:40", end: "15:40" },
  { id: "ts7", label: "3:40 – 4:40", start: "15:40", end: "16:40" },
];

export const breaks = [
  { id: "b-lunch", type: "Lunch", start: "12:00", end: "12:40", applicableGroups: "All" },
  { id: "b-event-fri", type: "Event", start: "15:40", end: "16:40", applicableGroups: "CSE Section D", day: "Friday" },
];
