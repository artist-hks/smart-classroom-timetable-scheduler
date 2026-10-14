import { useState } from "react";
import { ShieldCheck, AlertTriangle, XCircle, ArrowRight } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import EmptyState from "../components/ui/EmptyState";
import { conflicts as initialConflicts } from "../data/operations";
import { sessions } from "../data/timetable";
import { getCourse } from "../utils/scheduling";
import { useToast } from "../context/ToastContext";

export default function Conflicts() {
  const { showToast } = useToast();
  const [conflicts, setConflicts] = useState(initialConflicts);
  const open = conflicts.filter((c) => c.status === "open");
  const resolved = conflicts.filter((c) => c.status === "resolved");

  const resolve = (id) => {
    setConflicts((cs) => cs.map((c) => (c.id === id ? { ...c, status: "resolved" } : c)));
    showToast("Conflict marked as resolved.", "success");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scheduling"
        title="Conflicts & validation"
        description="Hard-constraint violations and resource issues surfaced before a timetable can be approved."
      />

      <div className="grid sm:grid-cols-3 gap-4">
        <SummaryCard tone="danger" icon={XCircle} label="Errors" value={open.filter((c) => c.severity === "error").length} />
        <SummaryCard tone="warning" icon={AlertTriangle} label="Warnings" value={open.filter((c) => c.severity === "warning").length} />
        <SummaryCard tone="success" icon={ShieldCheck} label="Resolved" value={resolved.length} />
      </div>

      <Card>
        <CardHeader title="Open issues" subtitle="Must be addressed before the timetable can move to Approval." />
        {open.length === 0 ? (
          <EmptyState icon={ShieldCheck} title="No open conflicts" description="This timetable is clear of hard-constraint violations and resource issues." />
        ) : (
          <div className="space-y-3">
            {open.map((c) => (
              <div key={c.id} className="rounded border border-line px-4 py-3.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <Badge tone={c.severity === "error" ? "danger" : "warning"} dot className="mt-0.5 shrink-0">
                      {c.severity === "error" ? "Error" : "Warning"}
                    </Badge>
                    <div>
                      <p className="text-sm font-medium text-ink">{c.type}</p>
                      <p className="text-sm text-slate-500 mt-0.5">{c.description}</p>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {c.sessions.map((sid) => {
                          const s = sessions.find((x) => x.id === sid);
                          const course = s && getCourse(s.courseId);
                          return course ? (
                            <Badge key={sid} tone="neutral">{course.code} · {s.day} {s.start}</Badge>
                          ) : null;
                        })}
                      </div>
                    </div>
                  </div>
                  <Button size="sm" variant="secondary" onClick={() => resolve(c.id)} className="shrink-0">
                    Mark resolved
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Resolution history" />
        {resolved.length === 0 ? (
          <p className="text-sm text-slate-400 py-4 text-center">No conflicts have been resolved yet.</p>
        ) : (
          <div className="space-y-2">
            {resolved.map((c) => (
              <div key={c.id} className="flex items-center gap-3 rounded border border-line px-3 py-2.5 text-sm">
                <ShieldCheck size={15} className="text-success shrink-0" />
                <span className="text-ink font-medium">{c.type}</span>
                <ArrowRight size={12} className="text-slate-300" />
                <span className="text-slate-500 flex-1 truncate">{c.description}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function SummaryCard({ tone, icon: Icon, label, value }) {
  const toneMap = { danger: "text-danger bg-danger-50", warning: "text-warning bg-warning-50", success: "text-success bg-success-50" };
  return (
    <Card className="flex items-center gap-3">
      <div className={`h-9 w-9 rounded flex items-center justify-center shrink-0 ${toneMap[tone]}`}>
        <Icon size={17} />
      </div>
      <div>
        <p className="text-xl font-semibold text-ink">{value}</p>
        <p className="text-xs text-slate-400">{label}</p>
      </div>
    </Card>
  );
}
