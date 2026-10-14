import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { Field, Input } from "../components/ui/Field";
import { breaks } from "../data/academicStructure";
import { useToast } from "../context/ToastContext";

const HARD_CONSTRAINTS = [
  { id: "HC-01", label: "Faculty Clash", desc: "A faculty member cannot conduct two overlapping sessions." },
  { id: "HC-02", label: "Resource Clash", desc: "A resource cannot host overlapping sessions." },
  { id: "HC-03", label: "Section Clash", desc: "A section cannot attend two overlapping sessions." },
  { id: "HC-04", label: "Sub-Batch Clash", desc: "A sub-batch cannot attend two overlapping sessions." },
  { id: "HC-07", label: "Resource Capacity", desc: "Assigned resource capacity must be ≥ combined participant strength." },
  { id: "HC-10", label: "Faculty Workload", desc: "Faculty workload shall not exceed the configured mandatory maximum." },
  { id: "HC-14", label: "Multi-hour Continuity", desc: "A multi-hour session occupies one continuous, uninterrupted interval." },
];

const SOFT_CONSTRAINTS = [
  { id: "SC-01", label: "Resource utilization", defaultWeight: 70 },
  { id: "SC-02", label: "Faculty workload balance", defaultWeight: 65 },
  { id: "SC-03", label: "Student idle gaps", defaultWeight: 80 },
  { id: "SC-04", label: "Daily distribution", defaultWeight: 50 },
  { id: "SC-05", label: "Faculty slot preference", defaultWeight: 40 },
  { id: "SC-07", label: "Room switching", defaultWeight: 55 },
  { id: "SC-11", label: "Grouping efficiency", defaultWeight: 45 },
];

export default function Constraints() {
  const { showToast } = useToast();
  const [weights, setWeights] = useState(Object.fromEntries(SOFT_CONSTRAINTS.map((c) => [c.id, c.defaultWeight])));
  const [maxWorkload, setMaxWorkload] = useState(20);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scheduling"
        title="Constraints & breaks"
        description="Hard constraints are always enforced by CP-SAT and cannot be disabled. Soft constraint weights tune the Genetic Algorithm's fitness function."
        actions={<Button onClick={() => showToast("Constraint configuration saved.", "success")}>Save configuration</Button>}
      />

      <Card>
        <CardHeader title="Hard constraints" subtitle="Zero violations are permitted in any generated timetable (Constraint 2.6)." />
        <div className="space-y-2">
          {HARD_CONSTRAINTS.map((c) => (
            <div key={c.id} className="flex items-start gap-3 rounded border border-line px-3 py-2.5">
              <Badge tone="neutral" className="mt-0.5 shrink-0">{c.id}</Badge>
              <div className="flex-1">
                <p className="text-sm font-medium text-ink">{c.label}</p>
                <p className="text-xs text-slate-400">{c.desc}</p>
              </div>
              <Badge tone="success" dot>Enforced</Badge>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-4 border-t border-line grid sm:grid-cols-2 gap-4">
          <Field label="Mandatory maximum faculty workload (hrs/week)" hint="If no feasible timetable exists under this limit, generation reports infeasibility rather than exceeding it (HC-10).">
            <Input type="number" value={maxWorkload} onChange={(e) => setMaxWorkload(e.target.value)} />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader title="Soft constraint weights" subtitle="Used by the Genetic Algorithm to optimize the resource-validated timetable (SC-01 – SC-11)." />
        <div className="space-y-4">
          {SOFT_CONSTRAINTS.map((c) => (
            <div key={c.id} className="flex items-center gap-4">
              <span className="w-48 text-sm text-ink shrink-0">{c.label}</span>
              <input
                type="range"
                min="0"
                max="100"
                value={weights[c.id]}
                onChange={(e) => setWeights((w) => ({ ...w, [c.id]: Number(e.target.value) }))}
                className="flex-1 accent-ink-600"
              />
              <span className="w-10 text-sm text-slate-500 text-right">{weights[c.id]}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Breaks & reserved slots"
          subtitle="Lunch, event, and maintenance blocks that the scheduler treats as unavailable."
          action={<Button variant="secondary" size="sm" icon={Plus}>Add break</Button>}
        />
        <div className="space-y-2">
          {breaks.map((b) => (
            <div key={b.id} className="flex items-center gap-3 rounded border border-line px-3 py-2.5">
              <Badge tone="gold">{b.type}</Badge>
              <span className="text-sm text-ink">{b.start} – {b.end}</span>
              {b.day && <span className="text-xs text-slate-400">{b.day}</span>}
              <span className="text-xs text-slate-400 ml-auto">{b.applicableGroups}</span>
              <button className="text-slate-400 hover:text-danger">
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
