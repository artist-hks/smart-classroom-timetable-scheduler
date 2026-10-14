import { useState } from "react";
import { GraduationCap, ShieldCheck, Users, BookUser, School } from "lucide-react";
import { useAuth, ROLES } from "../context/AuthContext";
import { Field, Input } from "../components/ui/Field";
import Button from "../components/ui/Button";

const ROLE_OPTIONS = [
  { role: ROLES.COORDINATOR, icon: Users, blurb: "Build sessions, generate timetables, resolve conflicts" },
  { role: ROLES.FACULTY, icon: BookUser, blurb: "View your schedule and report availability" },
  { role: ROLES.STUDENT, icon: School, blurb: "View your section timetable" },
  { role: ROLES.ADMIN, icon: ShieldCheck, blurb: "Manage users, departments and system configuration" },
];

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [selectedRole, setSelectedRole] = useState(ROLES.COORDINATOR);
  const [error, setError] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError("Enter your institutional email and password to continue.");
      return;
    }
    setError("");
    login(selectedRole);
  };

  return (
    <div className="min-h-screen bg-ink flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-4xl grid md:grid-cols-2 bg-surface rounded-md overflow-hidden border border-ink-600 shadow-card">
        {/* Left: brand panel */}
        <div className="bg-ink-700 text-white p-8 hidden md:flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2.5 mb-8">
              <div className="h-9 w-9 rounded bg-gold flex items-center justify-center">
                <GraduationCap size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold">PIET Scheduler</p>
                <p className="text-[11px] text-white/50">Smart Classroom & Timetable System</p>
              </div>
            </div>
            <h1 className="text-2xl font-semibold leading-snug">
              Conflict-free scheduling for sections, sub-batches, and sessions.
            </h1>
            <p className="text-sm text-white/60 mt-3 leading-relaxed">
              Generate feasible timetables, allocate resources intelligently, and reschedule
              incrementally when plans change — without breaking what already works.
            </p>
          </div>
          <div className="text-xs text-white/40">
            Poornima Institute of Engineering & Technology · Dept. of CSE
          </div>
        </div>

        {/* Right: form */}
        <div className="p-8">
          <h2 className="text-lg font-semibold text-ink mb-1">Sign in</h2>
          <p className="text-sm text-slate-500 mb-6">Use your institutional credentials to access the scheduler.</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <Field label="Institutional email" required>
              <Input
                type="email"
                placeholder="you@piet.ac.in"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Field label="Password" required>
              <Input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            {error && <p className="text-xs text-danger">{error}</p>}

            <div className="flex items-center justify-between text-xs">
              <label className="flex items-center gap-1.5 text-slate-500">
                <input type="checkbox" className="accent-ink-600" /> Remember me
              </label>
              <a href="#" className="text-ink-600 font-medium hover:underline">
                Forgot password?
              </a>
            </div>

            <div>
              <p className="text-xs font-medium text-ink mb-2">Continue as (demo role selector)</p>
              <div className="grid grid-cols-2 gap-2">
                {ROLE_OPTIONS.map(({ role, icon: Icon, blurb }) => (
                  <button
                    type="button"
                    key={role}
                    onClick={() => setSelectedRole(role)}
                    title={blurb}
                    className={`flex flex-col items-start gap-1 rounded border px-3 py-2.5 text-left transition-colors ${
                      selectedRole === role ? "border-ink-600 bg-ink-50" : "border-line hover:border-ink-400"
                    }`}
                  >
                    <Icon size={15} className="text-ink-600" />
                    <span className="text-xs font-medium text-ink">{role}</span>
                  </button>
                ))}
              </div>
            </div>

            <Button type="submit" className="w-full" size="lg">
              Sign in as {selectedRole}
            </Button>
          </form>

          <p className="text-[11px] text-slate-400 mt-5 leading-relaxed">
            This is a frontend demonstration. Authentication is mocked locally; a production
            deployment will validate credentials against the institution's identity provider
            over JWT-secured REST APIs.
          </p>
        </div>
      </div>
    </div>
  );
}
