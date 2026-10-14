import { useState } from "react";
import { Plus, Layers } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card } from "../components/ui/Card";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Modal from "../components/ui/Modal";
import { Field, Input, Select } from "../components/ui/Field";
import TableToolbar from "../components/tables/TableToolbar";
import DataTable from "../components/tables/DataTable";
import { departments, sections, subBatches } from "../data/academicStructure";
import { useToast } from "../context/ToastContext";

export default function Sections() {
  const { showToast } = useToast();
  const [search, setSearch] = useState("");
  const [dept, setDept] = useState("all");
  const [openNew, setOpenNew] = useState(false);
  const [expanded, setExpanded] = useState(null);

  const filtered = sections.filter((s) => {
    const matchesDept = dept === "all" || s.department === dept;
    const matchesSearch = s.name.toLowerCase().includes(search.toLowerCase());
    return matchesDept && matchesSearch;
  });

  const columns = [
    { key: "name", header: "Section", render: (r) => <span className="font-medium">{r.name}</span> },
    { key: "department", header: "Department", render: (r) => departments.find((d) => d.id === r.department)?.shortName },
    { key: "semester", header: "Semester", render: (r) => `Sem ${r.semester}` },
    { key: "strength", header: "Strength" },
    { key: "subBatchCount", header: "Sub-batches" },
    {
      key: "actions",
      header: "",
      render: (r) => (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setExpanded(expanded === r.id ? null : r.id);
          }}
          className="text-xs font-medium text-ink-600 hover:underline"
        >
          {expanded === r.id ? "Hide sub-batches" : "View sub-batches"}
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Academic data"
        title="Sections & sub-batches"
        description="Hierarchy: Department → Semester → Section → Sub-Batch."
        actions={
          <Button icon={Plus} onClick={() => setOpenNew(true)}>
            Add section
          </Button>
        }
      />

      <Card>
        <TableToolbar
          search={search}
          onSearch={setSearch}
          placeholder="Search sections…"
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
          emptyState={
            <EmptyState icon={Layers} title="No sections match your filters" description="Try clearing the search or department filter." />
          }
        />
        {expanded && (
          <div className="mt-4 pt-4 border-t border-line">
            <p className="text-xs font-medium text-ink mb-2">
              Sub-batches — {sections.find((s) => s.id === expanded)?.name}
            </p>
            <div className="grid sm:grid-cols-3 gap-2">
              {subBatches
                .filter((b) => b.parentSection === expanded)
                .map((b) => (
                  <div key={b.id} className="rounded border border-line px-3 py-2.5">
                    <p className="text-sm font-medium text-ink">{b.name}</p>
                    <p className="text-xs text-slate-400">{b.strength} students</p>
                  </div>
                ))}
            </div>
          </div>
        )}
      </Card>

      <Modal
        open={openNew}
        onClose={() => setOpenNew(false)}
        title="Add section"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpenNew(false)}>Cancel</Button>
            <Button
              onClick={() => {
                showToast("Section created successfully.", "success");
                setOpenNew(false);
              }}
            >
              Save section
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Section name" required>
            <Input placeholder="e.g. Section E" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Department" required>
              <Select defaultValue="cse">
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>{d.shortName}</option>
                ))}
              </Select>
            </Field>
            <Field label="Semester" required>
              <Select defaultValue="7">
                {[1,2,3,4,5,6,7,8].map((s) => <option key={s} value={s}>Sem {s}</option>)}
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Student strength" required>
              <Input type="number" min="1" placeholder="e.g. 88" />
            </Field>
            <Field label="Number of sub-batches" required>
              <Input type="number" min="1" placeholder="e.g. 3" />
            </Field>
          </div>
        </div>
      </Modal>
    </div>
  );
}
