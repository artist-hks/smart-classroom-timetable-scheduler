import { Link } from "react-router-dom";
import {
  CalendarDays,
  Users,
  DoorOpen,
  ShieldAlert,
  ArrowUpRight,
  Clock,
  CheckCircle2,
  BellRing,
} from "lucide-react";
import { useAuth, ROLES } from "../context/AuthContext";
import PageHeader from "../components/ui/PageHeader";
import StatCard from "../components/ui/StatCard";
import { Card, CardHeader } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import { sections } from "../data/academicStructure";
import { faculty } from "../data/faculty";
import { resources } from "../data/courses";
import { sessions, sessionTypeMeta } from "../data/timetable";
import { conflicts, notifications, generationReport } from "../data/operations";
import { getCourse, getResource, formatFacultyNames, formatParticipants } from "../utils/scheduling";

const TODAY = "Monday"; // fixed for demo consistency

export default function Dashboard() {
  const { role } = useAuth();

  if (role === ROLES.FACULTY) return <FacultyDashboard />;
  if (role === ROLES.STUDENT) return <StudentDashboard />;
  return <CoordinatorDashboard />;
}

function CoordinatorDashboard() {
  const openConflicts = conflicts.filter((c) => c.status === "open");
  const todaySessions = sessions.filter((s) => s.day === TODAY);
  const roomsInUse = new Set(todaySessions.map((s) => s.resource)).size;
  const utilization = Math.round((roomsInUse / resources.length) * 100);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Overview"
        title="Coordinator dashboard"
        description="Computer Science & Engineering · Odd Semester 2026-27"
        actions={
          <>
            <Button as={Link} to="/session-builder" variant="secondary" size="md">
              New session
            </Button>
            <Button as={Link} to="/generate" size="md">
              Generate timetable
            </Button>
          </>
        }
      />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Sections managed" value={sections.filter((s) => s.department === "cse").length} icon={CalendarDays} />
        <StatCard label="Faculty (CSE)" value={faculty.filter((f) => f.department === "cse").length} icon={Users} />
        <StatCard label="Rooms & labs" value={resources.length} icon={DoorOpen} suffix={`${utilization}% in use today`} />
        <StatCard
          label="Open conflicts"
          value={openConflicts.length}
          icon={ShieldAlert}
          tone={openConflicts.length > 0 ? "danger" : "success"}
          trend={openConflicts.length > 0 ? "Needs review before publishing" : "All clear"}
        />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Today's sessions — Monday"
            subtitle="Section D, CSE Semester 7"
            action={
              <Link to="/timetable" className="text-xs font-medium text-ink-600 flex items-center gap-1 hover:underline">
                Full timetable <ArrowUpRight size={12} />
              </Link>
            }
          />
          <div className="space-y-2">
            {todaySessions.slice(0, 6).map((s) => {
              const course = getCourse(s.courseId);
              const resource = getResource(s.resource);
              const meta = sessionTypeMeta[s.type];
              return (
                <div key={s.id} className="flex items-center gap-3 rounded border border-line px-3 py-2.5">
                  <span className="h-8 w-1 rounded-full shrink-0" style={{ backgroundColor: meta.color }} />
                  <div className="w-24 shrink-0 text-xs text-slate-500 flex items-center gap-1">
                    <Clock size={12} /> {s.start}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-ink truncate">{course.name}</p>
                    <p className="text-xs text-slate-400 truncate">
                      {formatParticipants(s.participants)} · {formatFacultyNames(s.faculty)}
                    </p>
                  </div>
                  <Badge tone="neutral">{resource?.code}</Badge>
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <CardHeader title="Generation status" subtitle="Latest CP-SAT + GA run" />
          <div className="space-y-3 text-sm">
            <Row label="Feasibility" value={<Badge tone="success" dot>Feasible</Badge>} />
            <Row label="Total sessions" value={generationReport.totalSessions} />
            <Row label="Hard-constraint violations" value={generationReport.hardConstraintViolations} />
            <Row label="Generation time" value={generationReport.generationTime} />
          </div>
          <Button as={Link} to="/reports" variant="secondary" className="w-full mt-4">
            View full report
          </Button>
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Open conflicts"
            subtitle="Requires coordinator attention before publishing"
            action={
              <Link to="/conflicts" className="text-xs font-medium text-ink-600 flex items-center gap-1 hover:underline">
                Resolve all <ArrowUpRight size={12} />
              </Link>
            }
          />
          {openConflicts.length === 0 ? (
            <p className="text-sm text-slate-400 py-6 text-center">No open conflicts. The timetable is ready to publish.</p>
          ) : (
            <div className="space-y-2">
              {openConflicts.map((c) => (
                <div key={c.id} className="flex items-start gap-3 rounded border border-line px-3 py-2.5">
                  <Badge tone={c.severity === "error" ? "danger" : "warning"} dot className="mt-0.5 shrink-0">
                    {c.severity === "error" ? "Error" : "Warning"}
                  </Badge>
                  <div className="min-w-0">
                    <p className="text-sm text-ink font-medium">{c.type}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{c.description}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Recent activity" />
          <div className="space-y-3.5">
            {notifications.slice(0, 4).map((n) => (
              <div key={n.id} className="flex gap-2.5 text-sm">
                <BellRing size={14} className="text-ink-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-ink leading-snug">{n.title}</p>
                  <p className="text-xs text-slate-400">{n.time}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function FacultyDashboard() {
  const { user } = useAuth();
  const facultyId = "f-sharma-r";
  const mySessions = sessions.filter((s) => s.faculty.includes(facultyId));
  const todaySessions = mySessions.filter((s) => s.day === TODAY);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Faculty"
        title={`Welcome back, ${user.name}`}
        description="Department of Computer Science & Engineering"
        actions={
          <Button as={Link} to="/settings" variant="secondary">
            Submit availability
          </Button>
        }
      />
      <div className="grid sm:grid-cols-3 gap-4">
        <StatCard label="Sessions this week" value={mySessions.length} icon={CalendarDays} />
        <StatCard label="Today's sessions" value={todaySessions.length} icon={Clock} />
        <StatCard label="Weekly load" value="16 / 18 hrs" icon={CheckCircle2} tone="success" />
      </div>

      <Card>
        <CardHeader title="Today's schedule — Monday" action={
          <Link to="/timetable" className="text-xs font-medium text-ink-600 flex items-center gap-1 hover:underline">
            My full timetable <ArrowUpRight size={12} />
          </Link>
        } />
        {todaySessions.length === 0 ? (
          <p className="text-sm text-slate-400 py-6 text-center">No sessions scheduled for you today.</p>
        ) : (
          <div className="space-y-2">
            {todaySessions.map((s) => {
              const course = getCourse(s.courseId);
              const resource = getResource(s.resource);
              const meta = sessionTypeMeta[s.type];
              return (
                <div key={s.id} className="flex items-center gap-3 rounded border border-line px-3 py-2.5">
                  <span className="h-8 w-1 rounded-full shrink-0" style={{ backgroundColor: meta.color }} />
                  <div className="w-28 shrink-0 text-xs text-slate-500">{s.start} – {s.end}</div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-ink">{course.name}</p>
                    <p className="text-xs text-slate-400">{formatParticipants(s.participants)}</p>
                  </div>
                  <Badge tone="neutral">{resource?.code}</Badge>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}

function StudentDashboard() {
  const { user } = useAuth();
  const sectionId = "sec-cse-7d";
  const todaySessions = sessions.filter(
    (s) => s.day === TODAY && s.participants.some((p) => p.section === sectionId)
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Student"
        title={`Hi ${user.name.split(" ")[0]}, here's today's plan`}
        description="Section D · CSE · Semester 7"
      />
      <Card>
        <CardHeader title="Today — Monday" action={
          <Link to="/timetable" className="text-xs font-medium text-ink-600 flex items-center gap-1 hover:underline">
            Weekly timetable <ArrowUpRight size={12} />
          </Link>
        } />
        <div className="space-y-2">
          {todaySessions.map((s) => {
            const course = getCourse(s.courseId);
            const resource = getResource(s.resource);
            const meta = sessionTypeMeta[s.type];
            return (
              <div key={s.id} className="flex items-center gap-3 rounded border border-line px-3 py-2.5">
                <span className="h-8 w-1 rounded-full shrink-0" style={{ backgroundColor: meta.color }} />
                <div className="w-28 shrink-0 text-xs text-slate-500">{s.start} – {s.end}</div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-ink">{course.name}</p>
                  <p className="text-xs text-slate-400">{formatFacultyNames(s.faculty)} · {formatParticipants(s.participants)}</p>
                </div>
                <Badge tone="neutral">{resource?.code}</Badge>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-ink">{value}</span>
    </div>
  );
}
