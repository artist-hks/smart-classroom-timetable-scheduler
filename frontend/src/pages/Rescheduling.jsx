import { useState } from "react";
import { RefreshCw, CheckCircle2 } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { Field, Select } from "../components/ui/Field";
import { faculty } from "../data/faculty";
import { reschedulingReport } from "../data/operations";
import { useToast } from "../context/ToastContext";

const TRIGGERS = [
  "Faculty leave / unavailability",
  "Faculty early departure",
  "Room / lab unavailability",
  "Section / sub-batch regrouping",
  "Resource reassignment",
  "Emergency room change",
  "Class / session cancellation",
  "Academic event insertion",
  "Additional lecture",
  "Constraint modification",
];

const ALTERNATIVES = [
  {
    id: "opt-1",
    title: "Merge D1 + D2 into LAB-OOPS-1",
    changes: 1,
    detail: "Combine the two affected sub-batches into a single practical session, validated against HC-13 and HC-07/HC-16 for capacity and grouping consistency.",
  },
  {
    id: "opt-2",
    title: "Move D2 session to 1:40 – 3:40 PM",
    changes: 1,
    detail: "Shift the affected sub-batch's session later in the day, preserving the same faculty and resource.",
  },
  {
    id: "opt-3",
    title: "Reassign to Faculty Y",
    changes: 1,
    detail: "Keep the original time and resource, substituting an available faculty member with matching subject expertise.",
  },
];

export default function Rescheduling() {
  const { showToast } = useToast();
  const [trigger, setTrigger] = useState(TRIGGERS[0]);
  const [facultyId, setFacultyId] = useState(faculty[0].id);
  const [computed, setComputed] = useState(false);
  const [selected, setSelected] = useState(null);
  const [approved, setApproved] = useState(false);

  const computeImpact = () => {
    setComputed(true);
    setApproved(false);
    setSelected(null);
  };

  const approve = () => {
    setApproved(true);
    showToast("Rescheduling alternative approved. Timetable V4 will be published as Resource-Validated.", "success");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scheduling"
        title="Dynamic rescheduling"
        description="Report a change and the system isolates only the affected sub-batch, faculty, and resource — unrelated sessions remain untouched."
      />

      <Card>
        <CardHeader title="Report a change" />
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Trigger" required>
            <Select value={trigger} onChange={(e) => setTrigger(e.target.value)}>
              {TRIGGERS.map((t) => <option key={t}>{t}</option>)}
            </Select>
          </Field>
          <Field label="Affected faculty" required>
            <Select value={facultyId} onChange={(e) => setFacultyId(e.target.value)}>
              {faculty.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </Select>
          </Field>
        </div>
        <Button className="mt-4" icon={RefreshCw} onClick={computeImpact}>
          Compute affected sessions
        </Button>
      </Card>

      {computed && (
        <>
          <Card>
            <CardHeader title="Affected participants" subtitle="Scoped to the sub-batch, faculty, and resource involved — not the entire section." />
            <div className="grid sm:grid-cols-3 gap-3">
              <ImpactBlock label="Trigger" value={trigger} />
              <ImpactBlock label="Affected session" value="D2 · OOPS Practical, Mon 12:40–14:40" />
              <ImpactBlock label="Affected faculty" value={faculty.find((f) => f.id === facultyId)?.name} />
            </div>
          </Card>

          <Card>
            <CardHeader title="Ranked alternative resolutions" subtitle="Each option is annotated with the number of sessions it changes. Sub-batch merges are proposed only — never applied automatically." />
            <div className="space-y-2.5">
              {ALTERNATIVES.map((opt, i) => (
                <label
                  key={opt.id}
                  className={`flex items-start gap-3 rounded border px-4 py-3 cursor-pointer ${
                    selected === opt.id ? "border-ink-600 bg-ink-50" : "border-line"
                  }`}
                >
                  <input
                    type="radio"
                    name="alt"
                    checked={selected === opt.id}
                    onChange={() => setSelected(opt.id)}
                    className="mt-1 accent-ink-600"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-400">Option {i + 1}</span>
                      <Badge tone="neutral">{opt.changes} change{opt.changes > 1 ? "s" : ""}</Badge>
                    </div>
                    <p className="text-sm font-medium text-ink mt-1">{opt.title}</p>
                    <p className="text-xs text-slate-500 mt-1">{opt.detail}</p>
                  </div>
                </label>
              ))}
            </div>
            <div className="flex justify-end mt-4">
              <Button disabled={!selected} onClick={approve}>
                Approve selected alternative
              </Button>
            </div>
          </Card>

          {approved && (
            <Card>
              <CardHeader title="Rescheduling report" />
              <dl className="grid sm:grid-cols-3 gap-4 text-sm">
                <Row label="Changed assignments" value={reschedulingReport.changedAssignments} />
                <Row label="Rescheduling time" value={reschedulingReport.reschedulingTime} />
                <Row label="Preserved assignments" value={reschedulingReport.preservedAssignments} />
              </dl>
              <div className="flex items-center gap-2 mt-4 text-sm text-success">
                <CheckCircle2 size={16} /> Notifications queued for affected faculty and students.
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function ImpactBlock({ label, value }) {
  return (
    <div className="rounded border border-line px-3 py-2.5">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-sm font-medium text-ink mt-0.5">{value}</p>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="text-base font-semibold text-ink">{value}</dd>
    </div>
  );
}
