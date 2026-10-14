import { useMemo, useState } from "react";
import { CalendarX2, Download, Printer } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import EmptyState from "../components/ui/EmptyState";
import Modal from "../components/ui/Modal";
import { Select } from "../components/ui/Field";
import WeeklyGrid from "../components/timetable/WeeklyGrid";
import Legend from "../components/timetable/Legend";
import { sections, days } from "../data/academicStructure";
import { faculty } from "../data/faculty";
import { resources } from "../data/courses";
import { sessions } from "../data/timetable";
import { getCourse, getResource, formatFacultyNames, formatParticipants } from "../utils/scheduling";
import { useAuth, ROLES } from "../context/AuthContext";

const VIEW_TABS = ["Section", "Faculty", "Resource"];

export default function Timetable() {
  const { role } = useAuth();
  const [viewBy, setViewBy] = useState("Section");
  const [sectionId, setSectionId] = useState("sec-cse-7d");
  const [facultyId, setFacultyId] = useState(faculty[0].id);
  const [resourceId, setResourceId] = useState(resources[0].id);
  const [dayFilter, setDayFilter] = useState("All week");
  const [selectedSession, setSelectedSession] = useState(null);

  const restrictedRole = role === ROLES.FACULTY || role === ROLES.STUDENT;

  const filteredSessions = useMemo(() => {
    let base = sessions;
    if (restrictedRole) {
      if (role === ROLES.FACULTY) base = sessions.filter((s) => s.faculty.includes("f-sharma-r"));
      if (role === ROLES.STUDENT) base = sessions.filter((s) => s.participants.some((p) => p.section === "sec-cse-7d"));
    } else if (viewBy === "Section") {
      base = sessions.filter((s) => s.participants.some((p) => p.section === sectionId));
    } else if (viewBy === "Faculty") {
      base = sessions.filter((s) => s.faculty.includes(facultyId));
    } else if (viewBy === "Resource") {
      base = sessions.filter((s) => s.resource === resourceId);
    }
    if (dayFilter !== "All week") base = base.filter((s) => s.day === dayFilter);
    return base;
  }, [viewBy, sectionId, facultyId, resourceId, dayFilter, restrictedRole, role]);

  const activeDays = dayFilter === "All week" ? days : [dayFilter];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Scheduling"
        title="Timetable"
        description="Published (Approved) timetable — Version V2, effective from 14 Aug 2026."
        actions={
          <>
            <Button variant="secondary" icon={Printer}>Print</Button>
            <Button variant="secondary" icon={Download}>Export</Button>
          </>
        }
      />

      <Card padded={false} className="p-4">
        <div className="flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-4">
          {!restrictedRole && (
            <div className="flex rounded border border-line overflow-hidden shrink-0 w-fit">
              {VIEW_TABS.map((tab) => (
                <button
                  key={tab}
                  onClick={() => setViewBy(tab)}
                  className={`px-3.5 py-1.5 text-xs font-medium transition-colors ${
                    viewBy === tab ? "bg-ink text-white" : "bg-surface text-slate-500 hover:bg-ink-50"
                  }`}
                >
                  {tab}-wise
                </button>
              ))}
            </div>
          )}

          {!restrictedRole && viewBy === "Section" && (
            <Select value={sectionId} onChange={(e) => setSectionId(e.target.value)} className="lg:w-64">
              {sections.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.department.toUpperCase()} Sem {s.semester}
                </option>
              ))}
            </Select>
          )}
          {!restrictedRole && viewBy === "Faculty" && (
            <Select value={facultyId} onChange={(e) => setFacultyId(e.target.value)} className="lg:w-64">
              {faculty.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </Select>
          )}
          {!restrictedRole && viewBy === "Resource" && (
            <Select value={resourceId} onChange={(e) => setResourceId(e.target.value)} className="lg:w-64">
              {resources.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.code} · {r.type}
                </option>
              ))}
            </Select>
          )}

          <Select value={dayFilter} onChange={(e) => setDayFilter(e.target.value)} className="lg:w-44">
            <option>All week</option>
            {days.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </Select>

          <div className="lg:ml-auto">
            <Legend />
          </div>
        </div>
      </Card>

      <Card padded={false} className="p-4">
        {filteredSessions.length === 0 ? (
          <EmptyState
            icon={CalendarX2}
            title="No timetable has been generated for this selection yet."
            description="Try a different section, faculty member, or resource, or generate a fresh timetable from the Generate & Optimize screen."
          />
        ) : (
          <WeeklyGrid sessions={filteredSessions} activeDays={activeDays} onSelectSession={setSelectedSession} />
        )}
      </Card>

      <Modal open={!!selectedSession} onClose={() => setSelectedSession(null)} title="Session details" size="sm">
        {selectedSession && <SessionDetails session={selectedSession} />}
      </Modal>
    </div>
  );
}

function SessionDetails({ session }) {
  const course = getCourse(session.courseId);
  const resource = getResource(session.resource);
  return (
    <div className="space-y-3 text-sm">
      <div>
        <p className="text-xs text-slate-400">Course</p>
        <p className="font-medium text-ink">{course.code} · {course.name}</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs text-slate-400">Day & time</p>
          <p className="font-medium text-ink">{session.day}, {session.start}–{session.end}</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Session type</p>
          <Badge tone="neutral">{session.type.replace("_", " ")}</Badge>
        </div>
      </div>
      <div>
        <p className="text-xs text-slate-400">Participants</p>
        <p className="font-medium text-ink">{formatParticipants(session.participants)}</p>
      </div>
      <div>
        <p className="text-xs text-slate-400">Faculty</p>
        <p className="font-medium text-ink">{formatFacultyNames(session.faculty)}</p>
      </div>
      <div>
        <p className="text-xs text-slate-400">Resource</p>
        <p className="font-medium text-ink">{resource?.code} · {resource?.type} · Cap. {resource?.capacity}</p>
      </div>
      {session.status === "flagged" && (
        <Badge tone="danger" dot>Flagged in Conflicts</Badge>
      )}
    </div>
  );
}
