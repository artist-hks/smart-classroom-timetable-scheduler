import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import { navSections } from "./navConfig";

function usePageTitle() {
  const { pathname } = useLocation();
  for (const section of navSections) {
    for (const item of section.items) {
      if (item.to === "/" && pathname === "/") return item.label;
      if (item.to !== "/" && pathname.startsWith(item.to)) return item.label;
    }
  }
  return "Smart Scheduler";
}

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const title = usePageTitle();

  return (
    <div className="flex min-h-screen bg-paper">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar title={title} onOpenMobile={() => setMobileOpen(true)} />
        <main className="flex-1 p-4 lg:p-6 max-w-[1400px] w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
