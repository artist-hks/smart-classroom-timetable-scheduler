export const conflicts = [
  {
    id: "cf-001",
    severity: "error",
    type: "Resource Clash (HC-02)",
    description: "CR-204 is booked for two overlapping sessions on Saturday, 11:00–12:00.",
    sessions: ["s-022"],
    detectedAt: "2026-09-10T08:12:00",
    status: "open",
  },
  {
    id: "cf-002",
    severity: "warning",
    type: "Faculty Workload (HC-10)",
    description: "Mr. Kushagra Gupta is at 20/20 weekly load — any new assignment will breach the configured maximum.",
    sessions: ["s-010", "s-015"],
    detectedAt: "2026-09-09T14:20:00",
    status: "open",
  },
  {
    id: "cf-003",
    severity: "warning",
    type: "Resource Suitability (HC-08)",
    description: "LAB-DBMS-1 is under maintenance; the DBMS practical for Section D currently points to an unavailable resource.",
    sessions: ["s-014"],
    detectedAt: "2026-09-08T09:00:00",
    status: "open",
  },
  {
    id: "cf-004",
    severity: "resolved",
    type: "Faculty Clash (HC-01)",
    description: "Ms. Smita Bisht was double-booked on Tuesday 11:00–12:00; resolved by reassigning the CN lecture.",
    sessions: ["s-009"],
    detectedAt: "2026-09-04T10:00:00",
    status: "resolved",
  },
];

export const academicEvents = [
  {
    id: "ev-001",
    title: "Alumni Interaction Session",
    type: "Seminar",
    participants: [{ section: "sec-cse-7d", subBatches: ["d1", "d2", "d3"] }],
    faculty: ["f-sharma-r"],
    resourceType: "Auditorium",
    resource: "aud-1",
    date: "2026-09-18",
    start: "10:00",
    end: "12:00",
    replacesSessions: ["s-004", "s-005", "s-006"],
    status: "scheduled",
  },
  {
    id: "ev-002",
    title: "Industry Guest Lecture — Cloud Architecture",
    type: "Guest Lecture",
    participants: [{ section: "sec-cse-7d", subBatches: null }, { section: "sec-cse-7c", subBatches: null }],
    faculty: ["f-verma-p"],
    resourceType: "Seminar Hall",
    resource: "sh-1",
    date: "2026-09-25",
    start: "14:40",
    end: "15:40",
    replacesSessions: [],
    status: "scheduled",
  },
];

export const timetableVersions = [
  {
    version: "V1",
    label: "Original",
    createdAt: "2026-07-20T09:00:00",
    createdBy: "Ms. Smita Bisht",
    reason: "Initial generation for Odd Semester 2026-27",
    changedSessions: 0,
    stage: "Published",
  },
  {
    version: "V2",
    label: "Faculty Leave Adjustment",
    createdAt: "2026-08-14T11:30:00",
    createdBy: "Ms. Smita Bisht",
    reason: "Mr. Hemant Jangid on leave — D2 OOPS practical reassigned",
    changedSessions: 1,
    stage: "Published",
  },
  {
    version: "V3",
    label: "Room Unavailability Adjustment",
    createdAt: "2026-09-08T16:00:00",
    createdBy: "Ms. Smita Bisht",
    reason: "LAB-DBMS-1 flagged for maintenance",
    changedSessions: 1,
    stage: "In Review",
  },
];

export const notifications = [
  {
    id: "n-001",
    title: "Resource conflict detected",
    body: "CR-204 has an overlapping booking on Saturday 11:00–12:00.",
    time: "2 hours ago",
    read: false,
    type: "error",
  },
  {
    id: "n-002",
    title: "Faculty unavailability reported",
    body: "Mr. Hemant Jangid marked unavailable, Monday 12:40–14:40.",
    time: "5 hours ago",
    read: false,
    type: "warning",
  },
  {
    id: "n-003",
    title: "Timetable V2 published",
    body: "Faculty Leave Adjustment is now visible to Faculty and Students.",
    time: "Yesterday",
    read: true,
    type: "success",
  },
  {
    id: "n-004",
    title: "Academic event created",
    body: "Alumni Interaction Session scheduled for 18 Sep, replacing 3 practical sessions.",
    time: "2 days ago",
    read: true,
    type: "info",
  },
];

export const generationReport = {
  generationTime: "38.4s",
  totalSessions: 214,
  hardConstraintViolations: 0,
  feasibility: "Feasible",
  lastRun: "2026-09-08T16:02:00",
};

export const optimizationReport = {
  initialFitness: 0.61,
  finalFitness: 0.89,
  utilization: 0.84,
  workloadVariance: 1.8,
  studentGapCount: 9,
  lastRun: "2026-09-08T16:04:00",
};

export const reschedulingReport = {
  trigger: "Room Unavailability — LAB-DBMS-1",
  affectedSessions: 1,
  affectedParticipants: "Section D (whole section)",
  changedAssignments: 1,
  reschedulingTime: "1.2s",
  preservedAssignments: "99.5%",
};

export const resourceUtilization = [
  { resource: "CR-201", utilization: 92 },
  { resource: "CR-204", utilization: 68 },
  { resource: "CR-305", utilization: 54 },
  { resource: "LAB-OOPS-1", utilization: 81 },
  { resource: "LAB-DSA-1", utilization: 76 },
  { resource: "LAB-DBMS-1", utilization: 0 },
  { resource: "LAB-NET-1", utilization: 63 },
  { resource: "SH-101", utilization: 40 },
];

export const facultyWorkload = [
  { faculty: "Dr. Rakesh Sharma", assigned: 16, max: 18 },
  { faculty: "Ms. Smita Bisht", assigned: 19, max: 20 },
  { faculty: "Mr. Kushagra Gupta", assigned: 20, max: 20 },
  { faculty: "Mr. Hemant Jangid", assigned: 14, max: 18 },
  { faculty: "Mr. Hemant Sharma", assigned: 17, max: 20 },
  { faculty: "Dr. Priya Verma", assigned: 15, max: 16 },
  { faculty: "Dr. Leela Nair", assigned: 12, max: 16 },
];

export const mlPrediction = {
  modelVersion: "room-demand-v3",
  dataSource: "Simulated (institutional data pending approval)",
  trainedOn: "2026-09-01",
  metrics: { MAE: 2.1, RMSE: 3.4, R2: 0.87 },
  predictedPeakSlots: ["Mon 9:00–10:00", "Wed 12:40–14:40", "Thu 9:00–11:00"],
};
