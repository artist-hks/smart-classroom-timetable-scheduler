import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PlayCircle, CheckCircle2, Loader2, ArrowRight, XCircle, AlertTriangle, CalendarDays } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { Field, Select, Input, Checkbox } from "../components/ui/Field";
import useReferenceData from "../hooks/useReferenceData";
import { generateTimetable } from "../services/timetableService";
import { useTimetable } from "../context/TimetableContext";
import { useToast } from "../context/ToastContext";

// Stages are derived from what the response actually proves, not from a timer.
function deriveStages(response) {
  const ran = !!response;
  const feasible = ran && response.is_feasible;
  return [
    { label: "CP-SAT feasibility", state: !ran ? "idle" : feasible ? "done" : "failed" },
    { label: "Smart Resource Allocation", state: !ran ? "idle" : feasible && response.allocations.length > 0 ? "done" : "failed" },
    { label: "GA optimization", state: !ran ? "idle" : response.ga_final_fitness != null ? "done" : "skipped" },
    { label: "Final validation", state: !ran ? "idle" : feasible ? "done" : "failed" },
  ];
}

const fmt = (n, digits = 2) => (n == null ? "—" : Number(n).toFixed(digits));

export default function GenerateOptimize() {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const { generated, saveGeneration } = useTimetable();
  const { data: reference, loading: refLoading, error: refError, reload } = useReferenceData();

  const [form, setForm] = useState({
    academic_year_id: "",
    semester: "",
    department_id: "",
    time_limit_seconds: 15,
    enable_ga_optimization: true,
    enable_ml_demand_prediction: true,
  });
  const [errors, setErrors] = useState({});
  const [running, setRunning] = useState(false);
  const [requestError, setRequestError] = useState(null);
  const abortRef = useRef(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  // Until the user chooses, default to the active academic year and the first department.
  const defaultYear = (reference?.academicYears.find((y) => y.is_active) || reference?.academicYears[0])?.academic_year_id ?? "";
  const defaultDept = reference?.departments[0]?.department_id ?? "";
  const yearValue = form.academic_year_id !== "" ? form.academic_year_id : defaultYear;
  const deptValue = form.department_id !== "" ? form.department_id : defaultDept;

  const update = (patch) => setForm((f) => ({ ...f, ...patch }));
  const response = generated?.response;
  const stages = useMemo(() => deriveStages(response), [response]);

  const validate = () => {
    const e = {};
    if (!yearValue) e.academic_year_id = "Select an academic year.";
    if (!form.semester) e.semester = "Select a semester.";
    if (!deptValue) e.department_id = "Select a department.";
    const t = Number(form.time_limit_seconds);
    if (!(t >= 1 && t <= 120)) e.time_limit_seconds = "Enter a value between 1 and 120 seconds.";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const run = async () => {
    if (!validate()) return;
    const payload = {
      academic_year_id: Number(yearValue),
      semester: Number(form.semester),
      department_id: Number(deptValue),
      time_limit_seconds: Number(form.time_limit_seconds),
      enable_ga_optimization: form.enable_ga_optimization,
      enable_ml_demand_prediction: form.enable_ml_demand_prediction,
    };

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setRunning(true);
    setRequestError(null);
    try {
      const result = await generateTimetable(payload, { signal: abortRef.current.signal });
      saveGeneration(payload, result, reference);
      if (result.is_feasible) {
        showToast(`Timetable generated — ${result.total_sessions_scheduled} sessions scheduled.`, "success");
      } else {
        showToast("No feasible timetable exists for these inputs. See diagnostics below.", "warning");
      }
    } catch (err) {
      if (err.name === "AbortError") return;
      setRequestError(err);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scheduling"
        title="Generate & optimize"
        description="CP-SAT determines feasibility, Smart Resource Allocation assigns rooms, and the Genetic Algorithm optimizes against soft constraints."
        actions={
          <Button icon={running ? Loader2 : PlayCircle} onClick={run} disabled={running || refLoading || !reference}>
            {running ? "Running…" : "Run generation"}
          </Button>
        }
      />

      <Card>
        <CardHeader title="Generation options" subtitle="Sent to the scheduler as a GenerateTimetableRequest." />
        {refError ? (
          <div className="flex items-center justify-between gap-3 rounded border border-danger/25 bg-danger-50 px-3 py-2.5 text-sm text-danger">
            <span>Could not load academic data: {refError}</span>
            <Button size="sm" variant="secondary" onClick={reload}>Retry</Button>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Field label="Academic year" required error={errors.academic_year_id}>
              <Select value={yearValue} onChange={(e) => update({ academic_year_id: e.target.value })} disabled={refLoading} error={errors.academic_year_id}>
                <option value="">{refLoading ? "Loading…" : "Select year…"}</option>
                {reference?.academicYears.map((y) => <option key={y.academic_year_id} value={y.academic_year_id}>{y.label}</option>)}
              </Select>
            </Field>
            <Field label="Semester" required error={errors.semester}>
              <Select value={form.semester} onChange={(e) => update({ semester: e.target.value })} disabled={refLoading} error={errors.semester}>
                <option value="">{refLoading ? "Loading…" : "Select semester…"}</option>
                {reference?.semesters.map((s) => <option key={s.semester_id} value={s.semester_number}>{s.name}</option>)}
              </Select>
            </Field>
            <Field label="Department" required error={errors.department_id}>
              <Select value={deptValue} onChange={(e) => update({ department_id: e.target.value })} disabled={refLoading} error={errors.department_id}>
                <option value="">{refLoading ? "Loading…" : "Select department…"}</option>
                {reference?.departments.map((d) => <option key={d.department_id} value={d.department_id}>{d.code} — {d.name}</option>)}
              </Select>
            </Field>
            <Field label="Solver time limit (s)" required error={errors.time_limit_seconds} hint="1 to 120 seconds.">
              <Input type="number" min="1" max="120" value={form.time_limit_seconds} onChange={(e) => update({ time_limit_seconds: e.target.value })} error={errors.time_limit_seconds} />
            </Field>
          </div>
        )}
        <div className="flex flex-wrap gap-x-6 gap-y-2 mt-4 pt-4 border-t border-line">
          <Checkbox label="Run GA optimization" checked={form.enable_ga_optimization} onChange={(e) => update({ enable_ga_optimization: e.target.checked })} />
          <Checkbox label="Use ML room-demand prediction" checked={form.enable_ml_demand_prediction} onChange={(e) => update({ enable_ml_demand_prediction: e.target.checked })} />
        </div>
      </Card>

      <Card>
        <CardHeader title="Pipeline" subtitle="Reflects the outcome of the last run." />
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 overflow-x-auto pb-1">
          {running ? (
            <div className="flex items-center gap-2 rounded border border-ink-600 bg-ink-50 px-3 py-2 text-xs font-medium text-ink">
              <Loader2 size={13} className="animate-spin" /> Running the scheduling pipeline… this can take up to {form.time_limit_seconds || 15}s per solver stage.
            </div>
          ) : (
            stages.map((stage, i) => (
              <div key={stage.label} className="flex items-center gap-2 shrink-0">
                <StageChip stage={stage} />
                {i < stages.length - 1 && <ArrowRight size={13} className="text-slate-300 hidden sm:block" />}
              </div>
            ))
          )}
        </div>
      </Card>

      {requestError && (
        <Card>
          <div className="flex items-start gap-3">
            <XCircle size={18} className="text-danger mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-ink">
                {requestError.status === 404 ? "Generation endpoint not found" : requestError.status === 403 ? "Not permitted" : "Generation failed"}
              </p>
              <p className="text-sm text-slate-500 mt-0.5">{requestError.message}</p>
              {requestError.status === 404 && (
                <p className="text-xs text-slate-400 mt-2">
                  The backend does not expose a generate route at this path yet. Set <code>VITE_GENERATE_PATH</code> once it does, or use mock mode (<code>VITE_USE_MOCK=true</code>).
                </p>
              )}
            </div>
            <Button size="sm" variant="secondary" onClick={run}>Retry</Button>
          </div>
        </Card>
      )}

      {response && !response.is_feasible && (
        <Card>
          <div className="flex items-start gap-3">
            <AlertTriangle size={18} className="text-warning mt-0.5 shrink-0" />
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-ink">No feasible timetable</p>
                <Badge tone="danger" dot>{response.status_label}</Badge>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">Solver stopped after {fmt(response.solve_time_seconds, 1)}s. No broken timetable was produced.</p>
              <ul className="mt-3 space-y-1.5 text-sm text-ink list-disc pl-5">
                {response.diagnostics.length === 0 ? <li>The solver returned no diagnostic details.</li> : response.diagnostics.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            </div>
          </div>
        </Card>
      )}

      {response?.is_feasible && (
        <>
          <div className="grid lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader title="Generation report" subtitle="CP-SAT feasibility + resource allocation" />
              <dl className="space-y-3 text-sm">
                <Row label="Feasibility" value={<Badge tone="success" dot>{response.status_label}</Badge>} />
                <Row label="Sessions scheduled" value={response.total_sessions_scheduled} />
                <Row label="Solve time" value={`${fmt(response.solve_time_seconds, 1)}s`} />
              </dl>
            </Card>
            <Card>
              <CardHeader title="Optimization report" subtitle="Genetic Algorithm (soft constraints)" />
              {response.ga_final_fitness == null ? (
                <p className="text-sm text-slate-400">GA optimization was not run for this generation.</p>
              ) : (
                <dl className="space-y-3 text-sm">
                  <Row label="Initial fitness" value={fmt(response.ga_initial_fitness)} />
                  <Row label="Final fitness" value={fmt(response.ga_final_fitness)} />
                  <Row label="Utilization before" value={response.initial_utilization == null ? "—" : `${fmt(response.initial_utilization, 0)}%`} />
                  <Row label="Utilization after" value={response.final_utilization == null ? "—" : `${fmt(response.final_utilization, 0)}%`} />
                </dl>
              )}
            </Card>
          </div>

          {generated.droppedCount > 0 && (
            <Card>
              <div className="flex items-start gap-3 text-sm text-warning">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                <p>
                  {generated.droppedCount} of {response.allocations.length} sessions could not be placed on the grid because their day or time was not in a recognised format. Check the API's start_time / end_time values.
                </p>
              </div>
            </Card>
          )}

          {response.diagnostics.length > 0 && (
            <Card>
              <CardHeader title="Solver notes" />
              <ul className="space-y-1.5 text-sm text-ink list-disc pl-5">
                {response.diagnostics.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            </Card>
          )}

          <Card className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-ink">Generated timetable is ready</p>
              <p className="text-xs text-slate-400">View it on the weekly grid, or send it for Coordinator review.</p>
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" icon={CalendarDays} onClick={() => navigate("/timetable")}>View timetable</Button>
              <Button onClick={() => navigate("/approvals")}>Send to review</Button>
            </div>
          </Card>
        </>
      )}

      {!response && !running && !requestError && (
        <Card>
          <p className="text-sm text-slate-400 text-center py-6">
            No generation has been run in this session yet. Choose a year, semester and department, then click "Run generation".
          </p>
        </Card>
      )}
    </div>
  );
}

function StageChip({ stage }) {
  const styles = {
    done: "border-success/30 bg-success-50 text-success",
    failed: "border-danger/30 bg-danger-50 text-danger",
    skipped: "border-line bg-paper text-slate-400",
    idle: "border-line text-slate-400",
  };
  return (
    <div className={`flex items-center gap-2 rounded border px-3 py-2 text-xs font-medium whitespace-nowrap ${styles[stage.state]}`}>
      {stage.state === "done" && <CheckCircle2 size={13} />}
      {stage.state === "failed" && <XCircle size={13} />}
      {stage.label}
      {stage.state === "skipped" && <span className="font-normal">(skipped)</span>}
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
