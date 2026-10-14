import { useState } from "react";
import { Plus, BookOpen } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import EmptyState from "../components/ui/EmptyState";
import Modal from "../components/ui/Modal";
import { Field, Input, Select, Checkbox } from "../components/ui/Field";
import TableToolbar from "../components/tables/TableToolbar";
import DataTable from "../components/tables/DataTable";
import { courses } from "../data/courses";
import { departments } from "../data/academicStructure";
import { useToast } from "../context/ToastContext";

export default function Courses() {
  const { showToast } = useToast();
  const [search, setSearch] = useState("");
  const [semester, setSemester] = useState("all");
  const [openNew, setOpenNew] = useState(false);

  const filtered = courses.filter((c) => {
    const matchesSem = semester === "all" || String(c.semester) === semester;
    const matchesSearch = c.name.toLowerCase().includes(search.toLowerCase()) || c.code.toLowerCase().includes(search.toLowerCase());
    return matchesSem && matchesSearch;
  });

  const columns = [
    {
      key: "name",
      header: "Course",
      render: (r) => (
        <div>
          <p className="font-medium text-ink">{r.name}</p>
          <p className="text-xs text-slate-400">{r.code}</p>
        </div>
      ),
    },
    { key: "department", header: "Dept.", render: (r) => departments.find((d) => d.id === r.department)?.shortName },
    { key: "semester", header: "Semester", render: (r) => `Sem ${r.semester}` },
    { key: "weeklyHours", header: "Weekly hours" },
    {
      key: "sessionTypes",
      header: "Session breakdown",
      render: (r) => r.sessionTypes.map((t) => `${t.count}×${t.duration}h ${t.type.replace("_", " ")}`).join(", "),
    },
    {
      key: "labRequired",
      header: "Resource",
      render: (r) => <Badge tone={r.labRequired ? "info" : "neutral"}>{r.resourceType}</Badge>,
    },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Academic data"
        title="Courses"
        description="Each course generates one or more scheduling sessions based on its required weekly hours and session types."
        actions={<Button icon={Plus} onClick={() => setOpenNew(true)}>Add course</Button>}
      />

      <Card>
        <TableToolbar
          search={search}
          onSearch={setSearch}
          placeholder="Search by name or code…"
          filters={
            <Select value={semester} onChange={(e) => setSemester(e.target.value)} className="sm:w-44">
              <option value="all">All semesters</option>
              {[5, 7].map((s) => <option key={s} value={s}>Semester {s}</option>)}
            </Select>
          }
        />
        <DataTable
          columns={columns}
          rows={filtered}
          emptyState={<EmptyState icon={BookOpen} title="No courses match your filters" description="Try a different semester or search term." />}
        />
      </Card>

      <Modal
        open={openNew}
        onClose={() => setOpenNew(false)}
        title="Add course"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpenNew(false)}>Cancel</Button>
            <Button onClick={() => { showToast("Course added successfully.", "success"); setOpenNew(false); }}>Save course</Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Course code" required><Input placeholder="e.g. CS706" /></Field>
            <Field label="Course name" required><Input placeholder="e.g. Machine Learning" /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Department" required>
              <Select defaultValue="cse">
                {departments.map((d) => <option key={d.id} value={d.id}>{d.shortName}</option>)}
              </Select>
            </Field>
            <Field label="Semester" required>
              <Select defaultValue="7">
                {[1,2,3,4,5,6,7,8].map((s) => <option key={s} value={s}>Sem {s}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Required weekly hours" required><Input type="number" min="1" placeholder="e.g. 4" /></Field>
          <Field label="Default session type" required>
            <Select defaultValue="LECTURE">
              {["LECTURE", "PRACTICAL", "TUTE_ASSIGNMENT", "PROJECT", "SEMINAR"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
            </Select>
          </Field>
          <Checkbox label="Requires a laboratory / specific resource type" />
        </div>
      </Modal>
    </div>
  );
}
