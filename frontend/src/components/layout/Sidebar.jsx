import { NavLink } from "react-router-dom";
import { ChevronsLeft, ChevronsRight, GraduationCap } from "lucide-react";
import { navSections, isVisible } from "./navConfig";
import { useAuth } from "../../context/AuthContext";

export default function Sidebar({ collapsed, onToggle, mobileOpen, onCloseMobile }) {
  const { role } = useAuth();

  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 bg-ink-900/40 z-30 lg:hidden" onClick={onCloseMobile} />
      )}
      <aside
        className={`fixed lg:sticky top-0 h-screen z-40 bg-ink text-white flex flex-col shrink-0 transition-all duration-200
        ${collapsed ? "w-16" : "w-64"}
        ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}
      >
        <div className="h-14 flex items-center justify-between px-3.5 border-b border-white/10 shrink-0">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="h-7 w-7 rounded bg-gold flex items-center justify-center shrink-0">
              <GraduationCap size={16} className="text-white" />
            </div>
            {!collapsed && (
              <div className="leading-tight overflow-hidden">
                <p className="text-sm font-semibold whitespace-nowrap">PIET Scheduler</p>
                <p className="text-[10px] text-white/50 whitespace-nowrap">Smart Timetable System</p>
              </div>
            )}
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto py-3 px-2.5 space-y-5">
          {navSections.map((section) => {
            const items = section.items.filter((item) => isVisible(item, role));
            if (items.length === 0) return null;
            return (
              <div key={section.label}>
                {!collapsed && (
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-white/35 px-2 mb-1.5">
                    {section.label}
                  </p>
                )}
                <div className="space-y-0.5">
                  {items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/"}
                      onClick={onCloseMobile}
                      className={({ isActive }) =>
                        `flex items-center gap-2.5 rounded px-2.5 py-2 text-sm transition-colors ${
                          isActive ? "bg-white/10 text-white font-medium" : "text-white/70 hover:bg-white/5 hover:text-white"
                        }`
                      }
                      title={collapsed ? item.label : undefined}
                    >
                      <item.icon size={17} className="shrink-0" />
                      {!collapsed && <span className="truncate">{item.label}</span>}
                    </NavLink>
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        <button
          onClick={onToggle}
          className="hidden lg:flex items-center gap-2 border-t border-white/10 px-4 py-3 text-white/60 hover:text-white text-xs"
        >
          {collapsed ? <ChevronsRight size={15} /> : <ChevronsLeft size={15} />}
          {!collapsed && "Collapse"}
        </button>
      </aside>
    </>
  );
}
