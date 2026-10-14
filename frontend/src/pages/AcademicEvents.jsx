import { useState } from "react";
import { Plus, PartyPopper, AlertTriangle } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import EmptyState from "../components/ui/EmptyState";
import { Field, Input, Select } from "../components/ui/Field";
import { academicEvents } from "../data/operations";
import { faculty } from "../data/faculty";
import { resources } from "../data/courses";
import { sessions } from "../data/timetable";
import { getCourse, formatParticipants } from "../utils/scheduling";
import { useToast } from "../context/ToastContext";

export default function AcademicEvents() {
  const { showToast } = useToast();
  const [openNew, setOpenNew] = useState(false);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scheduling"
        title="Academic events"
        description="Non-routine activities — seminars, alumni sessions, guest lectures, workshops — that may replace regular sessions for their participants."
        actions={<Button icon={Plus} onClick={() => setOpenNew(true)}>Create event</Button>}
      />

      {academicEvents.length === 0 ? (
        <Card>
          <EmptyState icon={PartyPopper} title="No academic events scheduled" description="Create an event to see any overlapping regular sessions flagged automatically." />
        </Card>
      ) : (
        <div className="grid lg:grid-cols-2 gap-4">
          {academicEvents.map((ev) => (
            <Card key={ev.id}>
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <p className="text-sm font-semibold text-ink">{ev.title}</p>
                  <p className="text-xs text-slate-400">{ev.type} · {ev.date} · {ev.start}–{ev.end}</p>
                </div>
                <Badge tone="info">{ev.status}</Badge>
              </div>
              <dl className="space-y-2 text-sm mb-3">
                <Row label="Participants" value={formatParticipants(ev.participants)} />
                <Row label="Faculty" value={ev.faculty.map((f) => faculty.find((x) => x.id === f)?.name).join(", ")} />
                <Row label="Resource" value={`${resources.find((r) => r.id === ev.resource)?.code} (${ev.resourceType})`} />
              </dl>
              {ev.replacesSessions.length > 0 && (
                <div className="rounded border border-warning/25 bg-warning-50 px-3 py-2.5">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-warning mb-1.5">
                    <AlertTriangle size={13} /> Overlapping sessions flagged and replaced
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {ev.replacesSessions.map((sid) => {
                      const s = sessions.find((x) => x.id === sid);
                      const course = s && getCourse(s.courseId);
                      return course ? <Badge key={sid} tone="neutral">{course.code}</Badge> : null;
                    })}
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={openNew}
        onClose={() => setOpenNew(false)}
        title="Create academic event"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpenNew(false)}>Cancel</Button>
            <Button onClick={() => { showToast("Event created. Overlapping sessions have been flagged for review.", "success"); setOpenNew(false); }}>
              Create event
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Event title" required><Input placeholder="e.g. Guest Lecture — Cloud Architecture" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Event type" required>
              <Select defaultValue="Seminar">
                {["Seminar", "Alumni Session", "Guest Lecture", "Workshop", "Project Presentation"].map((t) => <option key={t}>{t}</option>)}
              </Select>
            </Field>
            <Field label="Required resource type" required>
              <Select defaultValue="Seminar Hall">
                {["Seminar Hall", "Auditorium", "Classroom"].map((t) => <option key={t}>{t}</option>)}
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Date" required><Input type="date" /></Field>
            <Field label="Start – End time" required>
              <div className="flex gap-2">
                <Input type="time" />
                <Input type="time" />
              </div>
            </Field>
          </div>
          <Field label="Faculty" required>
            <Select defaultValue="">
              <option value="" disabled>Select faculty…</option>
              {faculty.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </Select>
          </Field>
          <p className="text-xs text-slate-400">
            After creation, the system automatically identifies regular sessions that overlap this event for the same participants and time period, so they can be replaced for the affected participants only.
          </p>
        </div>
      </Modal>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-slate-400 shrink-0">{label}</dt>
      <dd className="font-medium text-ink text-right">{value}</dd>
    </div>
  );
}
