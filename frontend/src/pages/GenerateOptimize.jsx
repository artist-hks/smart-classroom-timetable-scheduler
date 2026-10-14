import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { PlayCircle, CheckCircle2, Loader2, ArrowRight } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { generationReport, optimizationReport } from "../data/operations";
import { useToast } from "../context/ToastContext";

const STAGES = [
  "Input data",
  "Session generation",
  "CP-SAT feasibility",
  "Smart Resource Allocation",
  "Resource allocation validation",
  "GA optimization",
  "Final validation",
];

export default function GenerateOptimize() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [running, setRunning] = useState(false);
  const [activeStage, setActiveStage] = useState(-1);
  const [completed, setCompleted] = useState(false);
  const timer = useRef(null);

  const runPipeline = () => {
    setRunning(true);
    setCompleted(false);
    setActiveStage(0);
    let i = 0;
    timer.current = setInterval(() => {
      i += 1;
      if (i >= STAGES.length) {
        clearInterval(timer.current);
        setRunning(false);
        setCompleted(true);
        showToast("Timetable generated and optimized — 0 hard-constraint violations.", "success");
      } else {
        setActiveStage(i);
      }
    }, 550);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scheduling"
        title="Generate & optimize"
        description="Runs the four-engine pipeline: CP-SAT determines feasibility, Smart Resource Allocation assigns rooms, and the Genetic Algorithm optimizes against soft constraints."
        actions={
          <Button icon={running ? Loader2 : PlayCircle} onClick={runPipeline} disabled={running}>
            {running ? "Running…" : "Run generation"}
          </Button>
        }
      />

      <Card>
        <CardHeader title="Pipeline" subtitle="Fixed, non-overlapping division of responsibility between the four engines." />
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 overflow-x-auto pb-1">
          {STAGES.map((stage, i) => {
            const state = !running && !completed ? "idle" : i < activeStage || completed ? "done" : i === activeStage ? "active" : "idle";
            return (
              <div key={stage} className="flex items-center gap-2 shrink-0">
                <div
                  className={`flex items-center gap-2 rounded border px-3 py-2 text-xs font-medium whitespace-nowrap ${
                    state === "done"
                      ? "border-success/30 bg-success-50 text-success"
                      : state === "active"
                      ? "border-ink-600 bg-ink-50 text-ink"
                      : "border-line text-slate-400"
                  }`}
                >
                  {state === "done" && <CheckCircle2 size={13} />}
                  {state === "active" && <Loader2 size={13} className="animate-spin" />}
                  {stage}
                </div>
                {i < STAGES.length - 1 && <ArrowRight size={13} className="text-slate-300 hidden sm:block" />}
              </div>
            );
          })}
        </div>
      </Card>

      {completed && (
        <div className="grid lg:grid-cols-2 gap-4">
          <Card>
            <CardHeader title="Generation report" subtitle="CP-SAT feasibility pass" />
            <dl className="space-y-3 text-sm">
              <Row label="Feasibility" value={<Badge tone="success" dot>{generationReport.feasibility}</Badge>} />
              <Row label="Total sessions" value={generationReport.totalSessions} />
              <Row label="Hard-constraint violations" value={generationReport.hardConstraintViolations} />
              <Row label="Generation time" value={generationReport.generationTime} />
            </dl>
          </Card>
          <Card>
            <CardHeader title="Optimization report" subtitle="Genetic Algorithm (soft constraints)" />
            <dl className="space-y-3 text-sm">
              <Row label="Initial fitness" value={optimizationReport.initialFitness} />
              <Row label="Final fitness" value={optimizationReport.finalFitness} />
              <Row label="Resource utilization" value={`${Math.round(optimizationReport.utilization * 100)}%`} />
              <Row label="Workload variance" value={optimizationReport.workloadVariance} />
              <Row label="Student gap count" value={optimizationReport.studentGapCount} />
            </dl>
          </Card>
        </div>
      )}

      {completed && (
        <Card className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-ink">Ready for review</p>
            <p className="text-xs text-slate-400">This timetable has 0 hard-constraint violations and can proceed to Coordinator review.</p>
          </div>
          <Button onClick={() => navigate("/approvals")}>Send to review</Button>
        </Card>
      )}

      {!completed && !running && (
        <Card>
          <p className="text-sm text-slate-400 text-center py-6">
            No generation has been run in this session yet. Click "Run generation" to execute the scheduling pipeline against the current academic data, faculty, resources, and constraint configuration.
          </p>
        </Card>
      )}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-ink">{value}</dd>
    </div>
  );
}
