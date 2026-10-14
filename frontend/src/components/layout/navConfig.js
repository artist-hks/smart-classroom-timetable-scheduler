import {
  LayoutGrid,
  CalendarDays,
  Users,
  BookOpen,
  DoorOpen,
  Layers,
  SlidersHorizontal,
  PlayCircle,
  ShieldAlert,
  RefreshCw,
  PartyPopper,
  BadgeCheck,
  BarChart3,
  Bell,
  Settings,
} from "lucide-react";
import { ROLES } from "../../context/AuthContext";

export const navSections = [
  {
    label: "Overview",
    items: [{ to: "/", label: "Dashboard", icon: LayoutGrid, roles: "all" }],
  },
  {
    label: "Scheduling",
    items: [
      { to: "/timetable", label: "Timetable", icon: CalendarDays, roles: "all" },
      { to: "/session-builder", label: "Session Builder", icon: Layers, roles: [ROLES.COORDINATOR] },
      { to: "/generate", label: "Generate & Optimize", icon: PlayCircle, roles: [ROLES.COORDINATOR] },
      { to: "/conflicts", label: "Conflicts", icon: ShieldAlert, roles: [ROLES.COORDINATOR] },
      { to: "/rescheduling", label: "Rescheduling", icon: RefreshCw, roles: [ROLES.COORDINATOR] },
      { to: "/events", label: "Academic Events", icon: PartyPopper, roles: [ROLES.COORDINATOR] },
      { to: "/approvals", label: "Approval & Versions", icon: BadgeCheck, roles: [ROLES.COORDINATOR] },
    ],
  },
  {
    label: "Academic Data",
    items: [
      { to: "/sections", label: "Sections & Sub-Batches", icon: Layers, roles: [ROLES.COORDINATOR] },
      { to: "/faculty", label: "Faculty", icon: Users, roles: [ROLES.COORDINATOR] },
      { to: "/courses", label: "Courses", icon: BookOpen, roles: [ROLES.COORDINATOR] },
      { to: "/resources", label: "Resources", icon: DoorOpen, roles: [ROLES.COORDINATOR] },
      { to: "/constraints", label: "Constraints & Breaks", icon: SlidersHorizontal, roles: [ROLES.COORDINATOR] },
    ],
  },
  {
    label: "Insights",
    items: [
      { to: "/reports", label: "Reports & Analytics", icon: BarChart3, roles: [ROLES.COORDINATOR, ROLES.ADMIN] },
      { to: "/notifications", label: "Notifications", icon: Bell, roles: "all" },
    ],
  },
  {
    label: "System",
    items: [{ to: "/settings", label: "Settings", icon: Settings, roles: "all" }],
  },
];

export function isVisible(item, role) {
  if (item.roles === "all") return true;
  return item.roles.includes(role);
}
