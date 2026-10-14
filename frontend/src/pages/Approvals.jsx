import { CheckCircle2, Clock, FileCheck2 } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { timetableVersions } from "../data/operations";
import { useToast } from "../context/ToastContext";

const LIFECYCLE = ["Generated", "Resource-Validated", "Optimized", "Final-Validated", "Reviewed", "Approved", "Published"];

export default function Approvals() {
  const { showToast } = useToast();

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scheduling"
        title="Approval & versioning"
        description="Students and faculty only ever see the Approved/Published version — never intermediate drafts."
      />

      <Card>
        <CardHeader title="Approval lifecycle" subtitle="Current version — V3, Room Unavailability Adjustment" />
        <div className="flex flex-wrap items-center gap-2">
          {LIFECYCLE.map((stage, i) => (
            <div key={stage} className="flex items-center gap-2">
              <div
                className={`rounded border px-3 py-1.5 text-xs font-medium ${
                  i <= 3 ? "border-success/30 bg-success-50 text-success" : i === 4 ? "border-ink-600 bg-ink-50 text-ink" : "border-line text-slate-400"
                }`}
              >
                {stage}
              </div>
              {i < LIFECYCLE.length - 1 && <span className="text-slate-300">→</span>}
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-5">
          <Button variant="secondary" icon={FileCheck2}>Send back for revision</Button>
          <Button icon={CheckCircle2} onClick={() => showToast("Timetable V3 approved and published.", "success")}>
            Approve & publish
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader title="Version history" />
        <div className="space-y-3">
          {timetableVersions.map((v) => (
            <div key={v.version} className="flex items-start gap-4 rounded border border-line px-4 py-3.5">
              <div className="h-9 w-9 rounded bg-ink-50 flex items-center justify-center text-xs font-semibold text-ink shrink-0">
                {v.version}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-ink">{v.label}</p>
                  <Badge tone={v.stage === "Published" ? "success" : "warning"} dot>{v.stage}</Badge>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">{v.reason}</p>
                <div className="flex items-center gap-3 text-xs text-slate-400 mt-1.5">
                  <span className="flex items-center gap-1"><Clock size={11} /> {new Date(v.createdAt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</span>
                  <span>By {v.createdBy}</span>
                  <span>{v.changedSessions} session{v.changedSessions !== 1 ? "s" : ""} changed</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
