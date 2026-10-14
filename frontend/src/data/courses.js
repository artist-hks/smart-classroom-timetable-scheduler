export const courses = [
  {
    id: "dbms",
    code: "CS701",
    name: "Database Management Systems",
    department: "cse",
    semester: 7,
    weeklyHours: 5,
    sessionTypes: [
      { type: "LECTURE", count: 3, duration: 1 },
      { type: "PRACTICAL", count: 1, duration: 2 },
    ],
    labRequired: true,
    resourceType: "DBMS Lab",
  },
  {
    id: "oops",
    code: "CS702",
    name: "Object Oriented Programming",
    department: "cse",
    semester: 7,
    weeklyHours: 5,
    sessionTypes: [
      { type: "LECTURE", count: 3, duration: 1 },
      { type: "PRACTICAL", count: 1, duration: 2 },
    ],
    labRequired: true,
    resourceType: "OOPS Lab",
  },
  {
    id: "os",
    code: "CS703",
    name: "Operating Systems",
    department: "cse",
    semester: 7,
    weeklyHours: 4,
    sessionTypes: [
      { type: "LECTURE", count: 3, duration: 1 },
      { type: "TUTE_ASSIGNMENT", count: 1, duration: 1 },
    ],
    labRequired: false,
    resourceType: "Classroom",
  },
  {
    id: "cn",
    code: "CS704",
    name: "Computer Networks",
    department: "cse",
    semester: 7,
    weeklyHours: 4,
    sessionTypes: [
      { type: "LECTURE", count: 3, duration: 1 },
      { type: "PRACTICAL", count: 1, duration: 2 },
    ],
    labRequired: true,
    resourceType: "Networks Lab",
  },
  {
    id: "se",
    code: "CS705",
    name: "Software Engineering",
    department: "cse",
    semester: 7,
    weeklyHours: 3,
    sessionTypes: [
      { type: "LECTURE", count: 2, duration: 1 },
      { type: "TUTE_ASSIGNMENT", count: 1, duration: 1 },
    ],
    labRequired: false,
    resourceType: "Classroom",
  },
  {
    id: "dsa",
    code: "CS501",
    name: "Data Structures & Algorithms",
    department: "cse",
    semester: 5,
    weeklyHours: 5,
    sessionTypes: [
      { type: "LECTURE", count: 3, duration: 1 },
      { type: "PRACTICAL", count: 1, duration: 2 },
    ],
    labRequired: true,
    resourceType: "DSA Lab",
  },
  {
    id: "proj7",
    code: "CS799",
    name: "Major Project",
    department: "cse",
    semester: 7,
    weeklyHours: 2,
    sessionTypes: [{ type: "PROJECT", count: 1, duration: 2 }],
    labRequired: false,
    resourceType: "Classroom",
  },
];

export const coursesById = Object.fromEntries(courses.map((c) => [c.id, c]));

export const resources = [
  { id: "cr-201", code: "CR-201", type: "Classroom", block: "Block A", floor: 2, capacity: 90, equipment: ["Projector", "PA System"], status: "available" },
  { id: "cr-204", code: "CR-204", type: "Classroom", block: "Block A", floor: 2, capacity: 90, equipment: ["Projector"], status: "available" },
  { id: "cr-305", code: "CR-305", type: "Classroom", block: "Block A", floor: 3, capacity: 70, equipment: ["Projector"], status: "available" },
  { id: "lab-oops", code: "LAB-OOPS-1", type: "Laboratory", block: "Block B", floor: 1, capacity: 32, equipment: ["30 Workstations", "JDK/Eclipse"], status: "available", labType: "OOPS Lab" },
  { id: "lab-oops-2", code: "LAB-OOPS-2", type: "Laboratory", block: "Block B", floor: 1, capacity: 32, equipment: ["30 Workstations"], status: "available", labType: "OOPS Lab" },
  { id: "lab-dsa", code: "LAB-DSA-1", type: "Laboratory", block: "Block B", floor: 1, capacity: 32, equipment: ["30 Workstations"], status: "available", labType: "DSA Lab" },
  { id: "lab-dbms", code: "LAB-DBMS-1", type: "Laboratory", block: "Block B", floor: 2, capacity: 32, equipment: ["30 Workstations", "MySQL/Oracle"], status: "under-maintenance", labType: "DBMS Lab" },
  { id: "lab-net", code: "LAB-NET-1", type: "Laboratory", block: "Block B", floor: 2, capacity: 32, equipment: ["Cisco Packet Tracer", "Switches"], status: "available", labType: "Networks Lab" },
  { id: "sh-1", code: "SH-101", type: "Seminar Hall", block: "Block C", floor: 1, capacity: 120, equipment: ["Projector", "Mic"], status: "available" },
  { id: "aud-1", code: "AUD-MAIN", type: "Auditorium", block: "Block C", floor: 0, capacity: 400, equipment: ["Stage", "Full AV"], status: "available" },
];

export const resourcesById = Object.fromEntries(resources.map((r) => [r.id, r]));
