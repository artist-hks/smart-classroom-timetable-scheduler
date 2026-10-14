import { Download } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import {
  generationReport,
  optimizationReport,
  reschedulingReport,
  resourceUtilization,
  facultyWorkload,
  mlPrediction,
} from "../data/operations";

export default function Reports() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Insights"
        title="Reports & analytics"
        description="Generation, optimization, utilization, workload, ML prediction, and rescheduling metrics."
        actions={<Button variant="secondary" icon={Download}>Export PDF</Button>}
      />

      <div className="grid lg:grid-cols-3 gap-4">
        <Card>
          <CardHeader title="Generation" subtitle={new Date(generationReport.lastRun).toLocaleString("en-IN", { dateStyle: "medium" })} />
          <dl className="space-y-2.5 text-sm">
            <Row label="Feasibility" value={<Badge tone="success" dot>{generationReport.feasibility}</Badge>} />
            <Row label="Total sessions" value={generationReport.totalSessions} />
            <Row label="Hard-constraint violations" value={generationReport.hardConstraintViolations} />
            <Row label="Generation time" value={generationReport.generationTime} />
          </dl>
        </Card>
        <Card>
          <CardHeader title="Optimization" subtitle="Genetic Algorithm" />
          <dl className="space-y-2.5 text-sm">
            <Row label="Initial fitness" value={optimizationReport.initialFitness} />
            <Row label="Final fitness" value={optimizationReport.finalFitness} />
            <Row label="Utilization" value={`${Math.round(optimizationReport.utilization * 100)}%`} />
            <Row label="Workload variance" value={optimizationReport.workloadVariance} />
            <Row label="Student gap count" value={optimizationReport.studentGapCount} />
          </dl>
        </Card>
        <Card>
          <CardHeader title="Rescheduling" subtitle="Most recent incremental run" />
          <dl className="space-y-2.5 text-sm">
            <Row label="Trigger" value={reschedulingReport.trigger} />
            <Row label="Changed assignments" value={reschedulingReport.changedAssignments} />
            <Row label="Rescheduling time" value={reschedulingReport.reschedulingTime} />
            <Row label="Preserved assignments" value={reschedulingReport.preservedAssignments} />
          </dl>
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Resource utilization" subtitle="Share of scheduled hours per resource, current week" />
          <div className="space-y-3">
            {resourceUtilization.map((r) => (
              <div key={r.resource} className="flex items-center gap-3">
                <span className="w-24 text-xs text-slate-500 shrink-0">{r.resource}</span>
                <div className="h-2 flex-1 rounded-full bg-ink-50 overflow-hidden">
                  <div
                    className={`h-full ${r.utilization === 0 ? "bg-danger" : "bg-ink-600"}`}
                    style={{ width: `${r.utilization}%` }}
                  />
                </div>
                <span className="w-10 text-xs text-slate-500 text-right">{r.utilization}%</span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader title="Faculty workload balance" subtitle="Assigned vs. maximum configured hours" />
          <div className="space-y-3">
            {facultyWorkload.map((f) => (
              <div key={f.faculty} className="flex items-center gap-3">
                <span className="w-36 text-xs text-slate-500 truncate shrink-0">{f.faculty}</span>
                <div className="h-2 flex-1 rounded-full bg-ink-50 overflow-hidden">
                  <div
                    className={`h-full ${f.assigned >= f.max ? "bg-warning" : "bg-ink-600"}`}
                    style={{ width: `${(f.assigned / f.max) * 100}%` }}
                  />
                </div>
                <span className="w-14 text-xs text-slate-500 text-right">{f.assigned}/{f.max}h</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="ML room demand prediction" subtitle={`Model ${mlPrediction.modelVersion} · trained ${mlPrediction.trainedOn}`} />
        <div className="grid sm:grid-cols-2 gap-6">
          <div>
            <p className="text-xs text-slate-400 mb-2">Data source</p>
            <p className="text-sm text-ink mb-4">{mlPrediction.dataSource}</p>
            <p className="text-xs text-slate-400 mb-2">Predicted peak-demand slots</p>
            <div className="flex flex-wrap gap-1.5">
              {mlPrediction.predictedPeakSlots.map((s) => <Badge key={s} tone="info">{s}</Badge>)}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <MetricBlock label="MAE" value={mlPrediction.metrics.MAE} />
            <MetricBlock label="RMSE" value={mlPrediction.metrics.RMSE} />
            <MetricBlock label="R²" value={mlPrediction.metrics.R2} />
          </div>
        </div>
        <p className="text-xs text-slate-400 mt-4 pt-4 border-t border-line">
          Scope is limited to per-slot room demand prediction — this model is never used to resolve faculty or resource clashes; that responsibility remains with CP-SAT.
        </p>
      </Card>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-slate-500 shrink-0">{label}</dt>
      <dd className="font-medium text-ink text-right truncate">{value}</dd>
    </div>
  );
}

function MetricBlock({ label, value }) {
  return (
    <div className="rounded border border-line px-3 py-3 text-center">
      <p className="text-lg font-semibold text-ink">{value}</p>
      <p className="text-xs text-slate-400">{label}</p>
    </div>
  );
}
