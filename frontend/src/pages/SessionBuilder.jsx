import { useMemo, useState } from "react";
import { Check, ChevronRight, ChevronLeft, AlertTriangle, CheckCircle2 } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { Field, Select, Checkbox } from "../components/ui/Field";
import { sections, subBatches, days, timeSlots } from "../data/academicStructure";
import { courses } from "../data/courses";
import { faculty } from "../data/faculty";
import { resources } from "../data/courses";
import { sessions } from "../data/timetable";
import { participantStrength, overlaps } from "../utils/scheduling";
import { useToast } from "../context/ToastContext";

const STEPS = [
  "Section & sub-batches",
  "Subject & type",
  "Faculty",
  "Duration & resource type",
  "Day & time",
  "Review",
];

export default function SessionBuilder() {
  const { showToast } = useToast();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    sectionIds: ["sec-cse-7d"],
    subBatchIds: [],
    wholeSection: true,
    courseId: "",
    sessionType: "LECTURE",
    facultyIds: [],
    duration: 1,
    resourceType: "Classroom",
    day: "Monday",
    startSlot: "ts1",
    requiredCapacity: 0,
  });

  const update = (patch) => setForm((f) => ({ ...f, ...patch }));

  const availableSubBatches = subBatches.filter((b) => form.sectionIds.includes(b.parentSection));
  const selectedCourse = courses.find((c) => c.id === form.courseId);

  const participants = form.wholeSection
    ? form.sectionIds.map((s) => ({ section: s, subBatches: null }))
    : form.sectionIds.map((s) => ({
        section: s,
        subBatches: availableSubBatches.filter((b) => b.parentSection === s && form.subBatchIds.includes(b.id)).map((b) => b.id),
      }));

  const strength = participantStrength(participants);

  // Validation logic per FR-3.3.2: strength, faculty availability, conflicts, candidate resource existence
  const validation = useMemo(() => {
    const issues = [];
    if (form.facultyIds.length === 0) issues.push({ level: "error", text: "At least one faculty member must be assigned." });

    // Faculty conflict check against existing published sessions
    const startMinutes = timeSlots.find((t) => t.id === form.startSlot);
    if (startMinutes) {
      const startTime = startMinutes.start;
      const endTime = addHours(startTime, form.duration);
      form.facultyIds.forEach((fid) => {
        const clash = sessions.find(
          (s) => s.day === form.day && s.faculty.includes(fid) && overlaps(s.start, s.end, startTime, endTime)
        );
        if (clash) {
          const f = faculty.find((x) => x.id === fid);
          issues.push({ level: "error", text: `${f?.name} already has a session scheduled during this time slot.` });
        }
      });
    }

    // Candidate resource existence
    const candidateResources = resources.filter(
      (r) => r.type === form.resourceType || r.labType === form.resourceType
    );
    const suitable = candidateResources.filter((r) => r.capacity >= strength && r.status === "available");
    if (candidateResources.length === 0) {
      issues.push({ level: "error", text: `No resources of type "${form.resourceType}" exist in the system.` });
    } else if (suitable.length === 0) {
      issues.push({
        level: "warning",
        text: `No available ${form.resourceType} currently has capacity ≥ ${strength}. Resource identity will be finalized by Smart Resource Allocation.`,
      });
    }

    if (strength === 0) issues.push({ level: "error", text: "Select at least one section or sub-batch." });

    return issues;
  }, [form, strength]);

  const hasBlockingError = validation.some((v) => v.level === "error");

  const handlePublish = () => {
    showToast("Session created and sent for feasibility validation.", "success");
    setStep(0);
    setForm({
      sectionIds: ["sec-cse-7d"],
      subBatchIds: [],
      wholeSection: true,
      courseId: "",
      sessionType: "LECTURE",
      facultyIds: [],
      duration: 1,
      resourceType: "Classroom",
      day: "Monday",
      startSlot: "ts1",
      requiredCapacity: 0,
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scheduling"
        title="Session Builder"
        description="Compose a scheduling session from a course/activity. A course may generate several sessions; each is scheduled independently."
      />

      <div className="grid lg:grid-cols-[220px_1fr] gap-6">
        {/* Stepper */}
        <div className="space-y-1">
          {STEPS.map((label, i) => (
            <button
              key={label}
              onClick={() => i < step && setStep(i)}
              className={`w-full flex items-center gap-2.5 rounded px-3 py-2.5 text-left text-sm transition-colors ${
                i === step ? "bg-ink text-white" : i < step ? "text-ink hover:bg-ink-50" : "text-slate-400"
              }`}
            >
              <span
                className={`h-5 w-5 rounded-full flex items-center justify-center text-[10px] shrink-0 ${
                  i === step ? "bg-white text-ink" : i < step ? "bg-ink text-white" : "bg-ink-50 text-slate-400"
                }`}
              >
                {i < step ? <Check size={12} /> : i + 1}
              </span>
              {label}
            </button>
          ))}
        </div>

        <Card>
          {step === 0 && (
            <StepSections form={form} update={update} availableSubBatches={availableSubBatches} strength={strength} />
          )}
          {step === 1 && <StepSubject form={form} update={update} />}
          {step === 2 && <StepFaculty form={form} update={update} selectedCourse={selectedCourse} />}
          {step === 3 && <StepResourceType form={form} update={update} strength={strength} />}
          {step === 4 && <StepDayTime form={form} update={update} />}
          {step === 5 && (
            <StepReview form={form} participants={participants} strength={strength} validation={validation} />
          )}

          <div className="flex items-center justify-between mt-6 pt-4 border-t border-line">
            <Button variant="ghost" icon={ChevronLeft} disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
              Back
            </Button>
            {step < STEPS.length - 1 ? (
              <Button onClick={() => setStep((s) => s + 1)} disabled={!canProceed(step, form)}>
                Continue <ChevronRight size={16} className="ml-1" />
              </Button>
            ) : (
              <Button onClick={handlePublish} disabled={hasBlockingError} variant={hasBlockingError ? "secondary" : "primary"}>
                Save session
              </Button>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function canProceed(step, form) {
  if (step === 0) return form.sectionIds.length > 0 && (form.wholeSection || form.subBatchIds.length > 0);
  if (step === 1) return !!form.courseId;
  if (step === 2) return form.facultyIds.length > 0;
  return true;
}

function addHours(time, hours) {
  const [h, m] = time.split(":").map(Number);
  const total = h * 60 + m + hours * 60;
  const nh = Math.floor(total / 60) % 24;
  const nm = total % 60;
  return `${String(nh).padStart(2, "0")}:${String(nm).padStart(2, "0")}`;
}

function StepSections({ form, update, availableSubBatches, strength }) {
  const toggleSection = (id) => {
    const exists = form.sectionIds.includes(id);
    update({ sectionIds: exists ? form.sectionIds.filter((s) => s !== id) : [...form.sectionIds, id] });
  };
  const toggleSubBatch = (id) => {
    const exists = form.subBatchIds.includes(id);
    update({ subBatchIds: exists ? form.subBatchIds.filter((s) => s !== id) : [...form.subBatchIds, id] });
  };

  return (
    <div className="space-y-5">
      <CardHeader
        title="Select sections"
        subtitle="A session may span multiple sections for combined activities such as project reviews or seminars."
      />
      <div className="grid sm:grid-cols-2 gap-2">
        {sections.map((s) => (
          <label
            key={s.id}
            className={`flex items-center gap-2.5 rounded border px-3 py-2.5 cursor-pointer ${
              form.sectionIds.includes(s.id) ? "border-ink-600 bg-ink-50" : "border-line"
            }`}
          >
            <input
              type="checkbox"
              checked={form.sectionIds.includes(s.id)}
              onChange={() => toggleSection(s.id)}
              className="accent-ink-600"
            />
            <div>
              <p className="text-sm font-medium text-ink">{s.name} · {s.department.toUpperCase()}</p>
              <p className="text-xs text-slate-400">Sem {s.semester} · {s.strength} students</p>
            </div>
          </label>
        ))}
      </div>

      <div className="pt-2 border-t border-line">
        <Checkbox
          label="Include whole section(s) rather than specific sub-batches"
          checked={form.wholeSection}
          onChange={(e) => update({ wholeSection: e.target.checked })}
        />
      </div>

      {!form.wholeSection && (
        <div>
          <p className="text-xs font-medium text-ink mb-2">Select sub-batches (any valid combination)</p>
          <div className="grid sm:grid-cols-3 gap-2">
            {availableSubBatches.map((b) => (
              <label
                key={b.id}
                className={`flex items-center gap-2 rounded border px-3 py-2 cursor-pointer text-sm ${
                  form.subBatchIds.includes(b.id) ? "border-ink-600 bg-ink-50" : "border-line"
                }`}
              >
                <input
                  type="checkbox"
                  checked={form.subBatchIds.includes(b.id)}
                  onChange={() => toggleSubBatch(b.id)}
                  className="accent-ink-600"
                />
                {b.name} <span className="text-slate-400">({b.strength})</span>
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="rounded bg-ink-50 px-3 py-2.5 text-sm text-ink flex items-center justify-between">
        <span>Combined participant strength</span>
        <span className="font-semibold">{strength} students</span>
      </div>
    </div>
  );
}

function StepSubject({ form, update }) {
  const relevantCourses = courses;
  return (
    <div className="space-y-5">
      <CardHeader title="Course / activity and session type" />
      <Field label="Course / activity" required>
        <Select value={form.courseId} onChange={(e) => update({ courseId: e.target.value, resourceType: courses.find(c=>c.id===e.target.value)?.resourceType || form.resourceType })}>
          <option value="">Select a course…</option>
          {relevantCourses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.code} — {c.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Session type" required hint="Session types are LECTURE, PRACTICAL, TUTE_ASSIGNMENT, PROJECT, SEMINAR, or EVENT.">
        <Select value={form.sessionType} onChange={(e) => update({ sessionType: e.target.value })}>
          {["LECTURE", "PRACTICAL", "TUTE_ASSIGNMENT", "PROJECT", "SEMINAR", "EVENT"].map((t) => (
            <option key={t} value={t}>{t.replace("_", " ")}</option>
          ))}
        </Select>
      </Field>
    </div>
  );
}

function StepFaculty({ form, update, selectedCourse }) {
  const suggested = faculty.filter((f) => selectedCourse?.department === f.department);
  const toggle = (id) => {
    const exists = form.facultyIds.includes(id);
    update({ facultyIds: exists ? form.facultyIds.filter((f) => f !== id) : [...form.facultyIds, id] });
  };
  return (
    <div className="space-y-5">
      <CardHeader
        title="Assign faculty"
        subtitle="Multiple faculty members may be assigned for joint sessions (e.g. combined project guidance). Each is validated independently for availability."
      />
      <div className="space-y-2">
        {(suggested.length ? suggested : faculty).map((f) => (
          <label
            key={f.id}
            className={`flex items-center justify-between gap-3 rounded border px-3 py-2.5 cursor-pointer ${
              form.facultyIds.includes(f.id) ? "border-ink-600 bg-ink-50" : "border-line"
            }`}
          >
            <div className="flex items-center gap-2.5">
              <input type="checkbox" checked={form.facultyIds.includes(f.id)} onChange={() => toggle(f.id)} className="accent-ink-600" />
              <div>
                <p className="text-sm font-medium text-ink">{f.name}</p>
                <p className="text-xs text-slate-400">{f.designation} · Load {f.currentLoad}/{f.maxWeeklyLoad} hrs</p>
              </div>
            </div>
            {f.status === "on-leave" ? (
              <Badge tone="warning">On leave</Badge>
            ) : f.currentLoad >= f.maxWeeklyLoad ? (
              <Badge tone="danger">At max load</Badge>
            ) : (
              <Badge tone="success">Available</Badge>
            )}
          </label>
        ))}
      </div>
    </div>
  );
}

function StepResourceType({ form, update, strength }) {
  const resourceTypes = ["Classroom", "OOPS Lab", "DSA Lab", "DBMS Lab", "Networks Lab", "Seminar Hall", "Auditorium"];
  return (
    <div className="space-y-5">
      <CardHeader
        title="Duration & required resource type"
        subtitle="The specific room or lab is not chosen here — it is assigned later by Smart Resource Allocation based on capacity, equipment, and predicted demand."
      />
      <Field label="Duration (hours)" required hint="Supports multi-hour continuous sessions, e.g. 2-hour practicals.">
        <Select value={form.duration} onChange={(e) => update({ duration: Number(e.target.value) })}>
          {[1, 2, 3].map((h) => (
            <option key={h} value={h}>{h} hour{h > 1 ? "s" : ""}</option>
          ))}
        </Select>
      </Field>
      <Field label="Required resource type" required>
        <Select value={form.resourceType} onChange={(e) => update({ resourceType: e.target.value })}>
          {resourceTypes.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </Select>
      </Field>
      <div className="rounded bg-ink-50 px-3 py-2.5 text-sm text-ink flex items-center justify-between">
        <span>Required capacity (from participant strength)</span>
        <span className="font-semibold">{strength}</span>
      </div>
    </div>
  );
}

function StepDayTime({ form, update }) {
  return (
    <div className="space-y-5">
      <CardHeader title="Day & starting time slot" />
      <Field label="Day" required>
        <Select value={form.day} onChange={(e) => update({ day: e.target.value })}>
          {days.map((d) => (
            <option key={d}>{d}</option>
          ))}
        </Select>
      </Field>
      <Field label="Starting time slot" required>
        <Select value={form.startSlot} onChange={(e) => update({ startSlot: e.target.value })}>
          {timeSlots.filter((t) => t.type !== "break").map((t) => (
            <option key={t.id} value={t.id}>{t.label}</option>
          ))}
        </Select>
      </Field>
    </div>
  );
}

function StepReview({ form, participants, strength, validation }) {
  const course = courses.find((c) => c.id === form.courseId);
  const slot = timeSlots.find((t) => t.id === form.startSlot);
  const endTime = addHours(slot?.start || "09:00", form.duration);
  const facultyNames = form.facultyIds.map((id) => faculty.find((f) => f.id === id)?.name).join(", ");

  return (
    <div className="space-y-5">
      <CardHeader title="Review & validate" subtitle="The system checks strength, faculty availability, conflicts, and candidate resources before this session can be saved." />

      <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
        <ReviewRow label="Course" value={course ? `${course.code} — ${course.name}` : "—"} />
        <ReviewRow label="Session type" value={form.sessionType.replace("_", " ")} />
        <ReviewRow label="Participants" value={participants.map((p) => p.section).join(", ") || "—"} />
        <ReviewRow label="Combined strength" value={`${strength} students`} />
        <ReviewRow label="Faculty" value={facultyNames || "—"} />
        <ReviewRow label="Resource type" value={form.resourceType} />
        <ReviewRow label="Day" value={form.day} />
        <ReviewRow label="Time" value={`${slot?.start} – ${endTime}`} />
      </dl>

      <div className="space-y-2">
        {validation.length === 0 ? (
          <div className="flex items-center gap-2 rounded border border-success/25 bg-success-50 px-3 py-2.5 text-sm text-success">
            <CheckCircle2 size={16} /> All checks passed — this session is ready to save.
          </div>
        ) : (
          validation.map((v, i) => (
            <div
              key={i}
              className={`flex items-start gap-2 rounded border px-3 py-2.5 text-sm ${
                v.level === "error" ? "border-danger/25 bg-danger-50 text-danger" : "border-warning/25 bg-warning-50 text-warning"
              }`}
            >
              <AlertTriangle size={16} className="mt-0.5 shrink-0" /> {v.text}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function ReviewRow({ label, value }) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="font-medium text-ink">{value}</dd>
    </div>
  );
}
