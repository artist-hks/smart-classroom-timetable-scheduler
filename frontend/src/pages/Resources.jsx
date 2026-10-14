import { useState } from "react";
import { Plus, DoorOpen } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import EmptyState from "../components/ui/EmptyState";
import Modal from "../components/ui/Modal";
import { Field, Input, Select } from "../components/ui/Field";
import TableToolbar from "../components/tables/TableToolbar";
import DataTable from "../components/tables/DataTable";
import { resources } from "../data/courses";
import { resourceUtilization } from "../data/operations";
import { useToast } from "../context/ToastContext";

const statusTone = { available: "success", "under-maintenance": "danger", occupied: "warning" };
const statusLabel = { available: "Available", "under-maintenance": "Under maintenance", occupied: "Occupied" };

export default function Resources() {
  const { showToast } = useToast();
  const [search, setSearch] = useState("");
  const [type, setType] = useState("all");
  const [openNew, setOpenNew] = useState(false);

  const filtered = resources.filter((r) => {
    const matchesType = type === "all" || r.type === type;
    const matchesSearch = r.code.toLowerCase().includes(search.toLowerCase());
    return matchesType && matchesSearch;
  });

  const utilFor = (code) => resourceUtilization.find((u) => u.resource === code)?.utilization;

  const columns = [
    { key: "code", header: "Resource", render: (r) => <span className="font-medium">{r.code}</span> },
    { key: "type", header: "Type" },
    { key: "block", header: "Block / Floor", render: (r) => `${r.block}, Floor ${r.floor}` },
    { key: "capacity", header: "Capacity" },
    {
      key: "equipment",
      header: "Equipment",
      render: (r) => <span className="text-xs text-slate-500">{r.equipment.join(", ")}</span>,
    },
    {
      key: "utilization",
      header: "Utilization",
      render: (r) => {
        const u = utilFor(r.code);
        if (u === undefined) return "—";
        return (
          <div className="flex items-center gap-2 w-28">
            <div className="h-1.5 flex-1 rounded-full bg-ink-50 overflow-hidden">
              <div className="h-full bg-ink-600" style={{ width: `${u}%` }} />
            </div>
            <span className="text-xs text-slate-500">{u}%</span>
          </div>
        );
      },
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
        title="Resources"
        description="Classrooms, laboratories, seminar halls, and the auditorium — scored and assigned by Smart Resource Allocation."
        actions={<Button icon={Plus} onClick={() => setOpenNew(true)}>Add resource</Button>}
      />

      <Card>
        <TableToolbar
          search={search}
          onSearch={setSearch}
          placeholder="Search by room code…"
          filters={
            <Select value={type} onChange={(e) => setType(e.target.value)} className="sm:w-48">
              <option value="all">All types</option>
              {["Classroom", "Laboratory", "Seminar Hall", "Auditorium"].map((t) => <option key={t}>{t}</option>)}
            </Select>
          }
        />
        <DataTable
          columns={columns}
          rows={filtered}
          emptyState={<EmptyState icon={DoorOpen} title="No resources match your filters" description="Try a different type or search term." />}
        />
      </Card>

      <Modal
        open={openNew}
        onClose={() => setOpenNew(false)}
        title="Add resource"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpenNew(false)}>Cancel</Button>
            <Button onClick={() => { showToast("Resource added successfully.", "success"); setOpenNew(false); }}>Save resource</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Resource code" required><Input placeholder="e.g. CR-402" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Resource type" required>
              <Select defaultValue="Classroom">
                {["Classroom", "Laboratory", "Seminar Hall", "Auditorium"].map((t) => <option key={t}>{t}</option>)}
              </Select>
            </Field>
            <Field label="Capacity" required><Input type="number" min="1" placeholder="e.g. 90" /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Block" required><Input placeholder="e.g. Block A" /></Field>
            <Field label="Floor" required><Input type="number" placeholder="e.g. 2" /></Field>
          </div>
          <Field label="Equipment" hint="Comma-separated, e.g. Projector, PA System">
            <Input placeholder="e.g. Projector, Whiteboard" />
          </Field>
        </div>
      </Modal>
    </div>
  );
}
