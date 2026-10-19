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
import { sessions as publishedSessions } from "../data/timetable";
import { getCourse, getResource, formatFacultyNames, formatParticipants } from "../utils/scheduling";
import { sectionLabel } from "../utils/timetableAdapter";
import { useAuth, ROLES } from "../context/AuthContext";
import { useTimetable } from "../context/TimetableContext";
import useReferenceData from "../hooks/useReferenceData";

const VIEW_TABS = ["Section", "Faculty", "Resource"];

const publishedOptions = {
  Section: sections.map((s) => ({ value: s.id, label: `${s.name} · ${s.department.toUpperCase()} Sem ${s.semester}` })),
  Faculty: faculty.map((f) => ({ value: f.id, label: f.name })),
  Resource: resources.map((r) => ({ value: r.id, label: `${r.code} · ${r.type}` })),
};

export default function Timetable() {
  const { role } = useAuth();
  const { generated } = useTimetable();
  const restrictedRole = role === ROLES.FACULTY || role === ROLES.STUDENT;

  // Faculty/Student only ever see the Approved/Published timetable (FR-3.12.2).
  const canSeeDraft = !restrictedRole && !!generated;
  const [source, setSource] = useState(generated && !restrictedRole ? "generated" : "published");
  const activeSource = canSeeDraft ? source : "published";
  const isGenerated = activeSource === "generated";

  const { data: reference } = useReferenceData({ enabled: canSeeDraft });

  const [viewBy, setViewBy] = useState("Section");
  const [selection, setSelection] = useState({ published: {}, generated: {} });
  const [dayFilter, setDayFilter] = useState("All week");
  const [selectedSession, setSelectedSession] = useState(null);

  const options = useMemo(() => {
    if (!isGenerated) return publishedOptions;
    const rows = generated?.sessions || [];
    const sectionIds = new Set(rows.flatMap((s) => s.sectionIds));
    const facultyIds = new Set(rows.flatMap((s) => s.facultyIds));
    const resourceMap = new Map(rows.map((s) => [s.resourceId, s.display.resource]));
    return {
      Section: (reference?.sections || [])
        .filter((s) => sectionIds.has(s.section_id))
        .map((s) => ({ value: String(s.section_id), label: sectionLabel(s, reference) })),
      Faculty: (reference?.faculty || [])
        .filter((f) => facultyIds.has(f.faculty_id))
        .map((f) => ({ value: String(f.faculty_id), label: f.full_name })),
      Resource: [...resourceMap].map(([id, code]) => ({ value: String(id), label: code })),
    };
  }, [isGenerated, generated, reference]);

  const currentOptions = options[viewBy];
  const stored = selection[activeSource][viewBy];
  const selectedId = currentOptions.some((o) => o.value === stored) ? stored : currentOptions[0]?.value ?? "";
  const setSelectedId = (value) =>
    setSelection((prev) => ({ ...prev, [activeSource]: { ...prev[activeSource], [viewBy]: value } }));

  const baseSessions = isGenerated ? generated.sessions : publishedSessions;
  const weekDays = baseSessions.some((s) => s.day === "Sunday") ? [...days, "Sunday"] : days;

  const filteredSessions = useMemo(() => {
    let base = baseSessions;
    if (restrictedRole) {
      if (role === ROLES.FACULTY) base = base.filter((s) => s.faculty.includes("f-sharma-r"));
      if (role === ROLES.STUDENT) base = base.filter((s) => s.participants.some((p) => p.section === "sec-cse-7d"));
    } else if (selectedId !== "") {
      base = base.filter((s) => {
        if (s.api) {
          const id = Number(selectedId);
          if (viewBy === "Section") return s.sectionIds.includes(id);
          if (viewBy === "Faculty") return s.facultyIds.includes(id);
          return s.resourceId === id;
        }
        if (viewBy === "Section") return s.participants.some((p) => p.section === selectedId);
        if (viewBy === "Faculty") return s.faculty.includes(selectedId);
        return s.resource === selectedId;
      });
    } else {
      base = [];
    }
    if (dayFilter !== "All week") base = base.filter((s) => s.day === dayFilter);
    return base;
  }, [baseSessions, restrictedRole, role, viewBy, selectedId, dayFilter]);

  const activeDays = dayFilter === "All week" ? weekDays : [dayFilter];

  const emptyTitle =
    isGenerated && generated.sessions.length === 0
      ? "The last generation produced no timetable."
      : "No timetable has been generated for this selection yet.";
  const emptyDescription =
    isGenerated && generated.sessions.length === 0
      ? "The solver reported the inputs as infeasible. See the diagnostics on the Generate & Optimize screen."
      : "Try a different section, faculty member, or resource, or generate a fresh timetable from the Generate & Optimize screen.";

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Scheduling"
        title="Timetable"
        description={
          isGenerated
            ? `Latest generated draft (${generated.generatedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}) — not visible to Faculty or Students until approved.`
            : "Published (Approved) timetable — Version V2, effective from 14 Aug 2026."
        }
        actions={
          <>
            <Button variant="secondary" icon={Printer}>Print</Button>
            <Button variant="secondary" icon={Download}>Export</Button>
          </>
        }
      />

      <Card padded={false} className="p-4">
        <div className="flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-4">
          {canSeeDraft && (
            <div className="flex rounded border border-line overflow-hidden shrink-0 w-fit">
              {[
                ["published", "Published"],
                ["generated", "Latest generated"],
              ].map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setSource(key)}
                  className={`px-3.5 py-1.5 text-xs font-medium transition-colors ${
                    activeSource === key ? "bg-gold text-white" : "bg-surface text-slate-500 hover:bg-ink-50"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}

          {!restrictedRole && (
            <>
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

              <Select value={selectedId} onChange={(e) => setSelectedId(e.target.value)} className="lg:w-64" disabled={currentOptions.length === 0}>
                {currentOptions.length === 0 && <option value="">No {viewBy.toLowerCase()} in this timetable</option>}
                {currentOptions.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </Select>
            </>
          )}

          <Select value={dayFilter} onChange={(e) => setDayFilter(e.target.value)} className="lg:w-44">
            <option>All week</option>
            {weekDays.map((d) => (
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
          <EmptyState icon={CalendarX2} title={emptyTitle} description={emptyDescription} />
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
  const view = session.api
    ? {
        course: `${session.display.courseCode} · ${session.display.course}`,
        participants: session.display.participants,
        faculty: session.display.faculty,
        resource: session.display.resourceDetail,
      }
    : (() => {
        const course = getCourse(session.courseId);
        const resource = getResource(session.resource);
        return {
          course: `${course.code} · ${course.name}`,
          participants: formatParticipants(session.participants),
          faculty: formatFacultyNames(session.faculty),
          resource: `${resource?.code} · ${resource?.type} · Cap. ${resource?.capacity}`,
        };
      })();

  return (
    <div className="space-y-3 text-sm">
      <div>
        <p className="text-xs text-slate-400">Course</p>
        <p className="font-medium text-ink">{view.course}</p>
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
        <p className="font-medium text-ink">{view.participants}</p>
      </div>
      <div>
        <p className="text-xs text-slate-400">Faculty</p>
        <p className="font-medium text-ink">{view.faculty}</p>
      </div>
      <div>
        <p className="text-xs text-slate-400">Resource</p>
        <p className="font-medium text-ink">{view.resource}</p>
      </div>
      {session.status === "flagged" && <Badge tone="danger" dot>Flagged in Conflicts</Badge>}
    </div>
  );
}
