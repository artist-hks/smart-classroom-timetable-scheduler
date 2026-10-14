import { useState } from "react";
import { Plus, Users } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import EmptyState from "../components/ui/EmptyState";
import Modal from "../components/ui/Modal";
import { Field, Input, Select } from "../components/ui/Field";
import TableToolbar from "../components/tables/TableToolbar";
import DataTable from "../components/tables/DataTable";
import { faculty } from "../data/faculty";
import { departments } from "../data/academicStructure";
import { courses } from "../data/courses";
import { sessions, sessionTypeMeta } from "../data/timetable";
import { getCourse } from "../utils/scheduling";
import { useToast } from "../context/ToastContext";

const statusTone = { active: "success", "on-leave": "warning", inactive: "neutral" };
const statusLabel = { active: "Active", "on-leave": "On leave", inactive: "Inactive" };

export default function FacultyPage() {
  const { showToast } = useToast();
  const [search, setSearch] = useState("");
  const [dept, setDept] = useState("all");
  const [selected, setSelected] = useState(null);
  const [openNew, setOpenNew] = useState(false);

  const filtered = faculty.filter((f) => {
    const matchesDept = dept === "all" || f.department === dept;
    const matchesSearch = f.name.toLowerCase().includes(search.toLowerCase()) || f.code.toLowerCase().includes(search.toLowerCase());
    return matchesDept && matchesSearch;
  });

  const columns = [
    {
      key: "name",
      header: "Faculty",
      render: (r) => (
        <div>
          <p className="font-medium text-ink">{r.name}</p>
          <p className="text-xs text-slate-400">{r.code}</p>
        </div>
      ),
    },
    { key: "designation", header: "Designation" },
    { key: "department", header: "Dept.", render: (r) => departments.find((d) => d.id === r.department)?.shortName },
    {
      key: "subjects",
      header: "Subjects",
      render: (r) => r.subjects.map((s) => courses.find((c) => c.id === s)?.code).join(", "),
    },
    {
      key: "load",
      header: "Weekly load",
      render: (r) => (
        <span className={r.currentLoad >= r.maxWeeklyLoad ? "text-danger font-medium" : ""}>
          {r.currentLoad} / {r.maxWeeklyLoad} hrs
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (r) => <Badge tone={statusTone[r.status]} dot>{statusLabel[r.status]}</Badge>,
    },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Academic data"
        title="Faculty"
        description="Assigned subjects, weekly workload, availability, and preferred slots."
        actions={<Button icon={Plus} onClick={() => setOpenNew(true)}>Add faculty</Button>}
      />

      <Card>
        <TableToolbar
          search={search}
          onSearch={setSearch}
          placeholder="Search by name or code…"
          filters={
            <Select value={dept} onChange={(e) => setDept(e.target.value)} className="sm:w-52">
              <option value="all">All departments</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </Select>
          }
        />
        <DataTable
          columns={columns}
          rows={filtered}
          onRowClick={setSelected}
          emptyState={<EmptyState icon={Users} title="No faculty match your filters" description="Try a different department or search term." />}
        />
      </Card>

      <Modal open={!!selected} onClose={() => setSelected(null)} title="Faculty profile" size="lg">
        {selected && <FacultyProfile faculty={selected} />}
      </Modal>

      <Modal
        open={openNew}
        onClose={() => setOpenNew(false)}
        title="Add faculty"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpenNew(false)}>Cancel</Button>
            <Button onClick={() => { showToast("Faculty member added successfully.", "success"); setOpenNew(false); }}>
              Save faculty
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Full name" required><Input placeholder="e.g. Dr. Meera Iyer" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Department" required>
              <Select defaultValue="cse">
                {departments.map((d) => <option key={d.id} value={d.id}>{d.shortName}</option>)}
              </Select>
            </Field>
            <Field label="Designation" required>
              <Select defaultValue="Assistant Professor">
                {["Professor", "Associate Professor", "Assistant Professor"].map((d) => <option key={d}>{d}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Maximum weekly workload (hours)" required>
            <Input type="number" min="1" placeholder="e.g. 18" />
          </Field>
          <Field label="Institutional email" required>
            <Input type="email" placeholder="name@piet.ac.in" />
          </Field>
        </div>
      </Modal>
    </div>
  );
}

function FacultyProfile({ faculty: f }) {
  const facultySessions = sessions.filter((s) => s.faculty.includes(f.id));
  return (
    <div className="space-y-5">
      <div className="flex items-start gap-4">
        <div className="h-12 w-12 rounded-full bg-ink text-white flex items-center justify-center font-semibold shrink-0">
          {f.name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
        </div>
        <div>
          <p className="font-semibold text-ink">{f.name}</p>
          <p className="text-xs text-slate-400">{f.designation} · {departments.find((d) => d.id === f.department)?.name}</p>
          <p className="text-xs text-slate-400">{f.email}</p>
        </div>
        <Badge tone={statusTone[f.status]} dot className="ml-auto">{statusLabel[f.status]}</Badge>
      </div>

      <div className="grid sm:grid-cols-3 gap-3">
        <InfoBlock label="Weekly load" value={`${f.currentLoad} / ${f.maxWeeklyLoad} hrs`} />
        <InfoBlock label="Availability" value={f.availability} />
        <InfoBlock label="Preferred slots" value={f.preferredSlots.join(", ")} />
      </div>

      <div>
        <p className="text-xs font-medium text-ink mb-2">Assigned subjects</p>
        <div className="flex flex-wrap gap-1.5">
          {f.subjects.map((s) => {
            const c = courses.find((x) => x.id === s);
            return <Badge key={s} tone="neutral">{c?.code} — {c?.name}</Badge>;
          })}
        </div>
      </div>

      <div>
        <p className="text-xs font-medium text-ink mb-2">Assigned sessions this week ({facultySessions.length})</p>
        <div className="space-y-1.5 max-h-56 overflow-y-auto">
          {facultySessions.map((s) => {
            const course = getCourse(s.courseId);
            const meta = sessionTypeMeta[s.type];
            return (
              <div key={s.id} className="flex items-center gap-2.5 rounded border border-line px-3 py-2 text-sm">
                <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: meta.color }} />
                <span className="w-20 text-xs text-slate-400 shrink-0">{s.day.slice(0, 3)} {s.start}</span>
                <span className="flex-1 truncate">{course.name}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function InfoBlock({ label, value }) {
  return (
    <div className="rounded border border-line px-3 py-2.5">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-sm font-medium text-ink mt-0.5">{value}</p>
    </div>
  );
}
