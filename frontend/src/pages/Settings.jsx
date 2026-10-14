import { useMemo, useState } from "react";
import { ShieldCheck, Users, BookUser, School } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { Field, Input, Select, Checkbox } from "../components/ui/Field";
import { useAuth, ROLES } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";

const ROLE_OPTIONS = [
  { role: ROLES.COORDINATOR, icon: Users },
  { role: ROLES.FACULTY, icon: BookUser },
  { role: ROLES.STUDENT, icon: School },
  { role: ROLES.ADMIN, icon: ShieldCheck },
];

export default function Settings() {
  const { user, role, switchRole } = useAuth();
  const { showToast } = useToast();
  const [tab, setTab] = useState("Profile");

  const tabs = useMemo(() => {
    const base = ["Profile"];
    if (role === ROLES.FACULTY) base.push("Availability");
    base.push("Notifications", "Demo role");
    return base;
  }, [role]);

  // If a role switch removes the current tab (e.g. leaving Faculty while on
  // Availability), fall back to Profile rather than rendering nothing.
  const activeTab = tabs.includes(tab) ? tab : "Profile";

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="System" title="Settings" description="Manage your profile, availability, and notification preferences." />

      <div className="flex gap-1 border-b border-line">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3.5 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === t ? "border-ink text-ink" : "border-transparent text-slate-400 hover:text-ink"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {activeTab === "Profile" && (
        <Card className="max-w-xl">
          <CardHeader title="Profile information" />
          <div className="space-y-4">
            <div className="flex items-center gap-3 mb-2">
              <div className="h-12 w-12 rounded-full bg-ink text-white flex items-center justify-center font-semibold">
                {user.initials}
              </div>
              <div>
                <p className="text-sm font-medium text-ink">{user.name}</p>
                <p className="text-xs text-slate-400">{role}</p>
              </div>
            </div>
            <Field label="Full name"><Input defaultValue={user.name} /></Field>
            <Field label="Institutional email"><Input defaultValue={user.email} type="email" /></Field>
            {user.department && <Field label="Department"><Input defaultValue={user.department} disabled /></Field>}
            <Button onClick={() => showToast("Profile updated.", "success")}>Save changes</Button>
          </div>
        </Card>
      )}

      {activeTab === "Availability" && (
        <Card className="max-w-xl">
          <CardHeader title="Availability & preferred slots" subtitle="Used by CP-SAT feasibility checks and rescheduling proposals." />
          <div className="space-y-4">
            <Field label="Available days">
              <div className="flex flex-wrap gap-2">
                {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                  <Checkbox key={d} label={d} defaultChecked={d !== "Sat" || role !== ROLES.FACULTY} />
                ))}
              </div>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Available from"><Input type="time" defaultValue="09:00" /></Field>
              <Field label="Available until"><Input type="time" defaultValue="16:40" /></Field>
            </div>
            <Field label="Preferred slot"><Select defaultValue="Morning"><option>Morning</option><option>Early Afternoon</option><option>Afternoon</option></Select></Field>
            <Button onClick={() => showToast("Availability submitted to the Timetable Coordinator.", "success")}>
              Submit availability
            </Button>
          </div>
        </Card>
      )}

      {activeTab === "Notifications" && (
        <Card className="max-w-xl">
          <CardHeader title="Notification preferences" />
          <div className="space-y-3">
            <Checkbox label="Schedule changes affecting me" defaultChecked />
            <Checkbox label="New conflicts detected" defaultChecked />
            <Checkbox label="Timetable published / approved" defaultChecked />
            <Checkbox label="Academic events" defaultChecked />
            <Button className="mt-2" onClick={() => showToast("Notification preferences saved.", "success")}>
              Save preferences
            </Button>
          </div>
        </Card>
      )}

      {activeTab === "Demo role" && (
        <Card className="max-w-xl">
          <CardHeader title="Switch demo role" subtitle="This is a frontend-only setting for exploring role-based views." />
          <div className="grid grid-cols-2 gap-2">
            {ROLE_OPTIONS.map(({ role: r, icon: Icon }) => (
              <button
                key={r}
                onClick={() => { switchRole(r); showToast(`Switched to ${r} view.`, "info"); }}
                className={`flex flex-col items-start gap-1.5 rounded border px-3 py-2.5 text-left ${
                  role === r ? "border-ink-600 bg-ink-50" : "border-line hover:border-ink-400"
                }`}
              >
                <Icon size={15} className="text-ink-600" />
                <span className="text-xs font-medium text-ink">{r}</span>
                {role === r && <Badge tone="success" className="mt-1">Current</Badge>}
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
