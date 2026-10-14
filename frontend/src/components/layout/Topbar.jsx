import { useState, useRef, useEffect } from "react";
import { Menu, Search, Bell, ChevronDown, LogOut, UserCircle2 } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { notifications } from "../../data/operations";

export default function Topbar({ title, onOpenMobile }) {
  const { user, role, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  const ref = useRef(null);
  const unread = notifications.filter((n) => !n.read).length;

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <header className="h-14 shrink-0 border-b border-line bg-surface/95 backdrop-blur flex items-center justify-between px-4 lg:px-6 sticky top-0 z-20">
      <div className="flex items-center gap-3 min-w-0">
        <button onClick={onOpenMobile} className="lg:hidden text-ink-600 p-1">
          <Menu size={20} />
        </button>
        <h2 className="text-sm font-semibold text-ink truncate">{title}</h2>
      </div>

      <div className="hidden md:flex items-center flex-1 max-w-sm mx-6">
        <div className="relative w-full">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            placeholder="Search faculty, rooms, sections…"
            className="w-full rounded border border-line bg-paper pl-8 pr-3 py-1.5 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-ink-400 focus:bg-surface"
          />
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <button
          onClick={() => navigate("/notifications")}
          className="relative p-1.5 rounded hover:bg-ink-50 text-ink-600"
          aria-label="Notifications"
        >
          <Bell size={18} />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 h-4 w-4 rounded-full bg-danger text-white text-[10px] flex items-center justify-center">
              {unread}
            </span>
          )}
        </button>

        <div className="relative" ref={ref}>
          <button onClick={() => setMenuOpen((o) => !o)} className="flex items-center gap-2 pl-2 pr-1 py-1 rounded hover:bg-ink-50">
            <div className="h-7 w-7 rounded-full bg-ink text-white text-xs font-semibold flex items-center justify-center">
              {user?.initials}
            </div>
            <div className="hidden sm:block text-left leading-tight">
              <p className="text-xs font-medium text-ink">{user?.name}</p>
              <p className="text-[11px] text-slate-400">{role}</p>
            </div>
            <ChevronDown size={14} className="text-slate-400" />
          </button>
          {menuOpen && (
            <div className="absolute right-0 mt-1.5 w-52 bg-surface border border-line rounded-md shadow-card py-1 z-30">
              <Link
                to="/settings"
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-sm text-ink hover:bg-ink-50"
              >
                <UserCircle2 size={15} /> Profile & Settings
              </Link>
              <button
                onClick={logout}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-danger hover:bg-danger-50"
              >
                <LogOut size={15} /> Switch role / Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
