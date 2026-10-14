import { useState } from "react";
import { BellOff, CheckCheck, AlertTriangle, XCircle, Info, CheckCircle2 } from "lucide-react";
import PageHeader from "../components/ui/PageHeader";
import { Card } from "../components/ui/Card";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import { notifications as initialNotifications } from "../data/operations";

const ICONS = { error: XCircle, warning: AlertTriangle, success: CheckCircle2, info: Info };
const TONES = {
  error: "text-danger bg-danger-50",
  warning: "text-warning bg-warning-50",
  success: "text-success bg-success-50",
  info: "text-info bg-info-50",
};

export default function Notifications() {
  const [items, setItems] = useState(initialNotifications);
  const unreadCount = items.filter((n) => !n.read).length;

  const markAllRead = () => setItems((prev) => prev.map((n) => ({ ...n, read: true })));
  const markRead = (id) => setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Insights"
        title="Notifications"
        description={unreadCount > 0 ? `${unreadCount} unread notification${unreadCount > 1 ? "s" : ""}` : "You're all caught up."}
        actions={
          unreadCount > 0 && (
            <Button variant="secondary" icon={CheckCheck} onClick={markAllRead}>
              Mark all as read
            </Button>
          )
        }
      />

      <Card padded={false}>
        {items.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={BellOff} title="No notifications" description="Schedule changes, conflicts, and approvals will appear here." />
          </div>
        ) : (
          <div>
            {items.map((n, i) => {
              const Icon = ICONS[n.type] || Info;
              return (
                <button
                  key={n.id}
                  onClick={() => markRead(n.id)}
                  className={`w-full flex items-start gap-3 px-5 py-4 text-left transition-colors ${
                    i !== items.length - 1 ? "border-b border-line" : ""
                  } ${n.read ? "bg-surface" : "bg-ink-50/50"} hover:bg-ink-50`}
                >
                  <div className={`h-8 w-8 rounded flex items-center justify-center shrink-0 ${TONES[n.type]}`}>
                    <Icon size={15} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className={`text-sm ${n.read ? "text-ink" : "text-ink font-semibold"}`}>{n.title}</p>
                      {!n.read && <span className="h-1.5 w-1.5 rounded-full bg-gold shrink-0" />}
                    </div>
                    <p className="text-sm text-slate-500 mt-0.5">{n.body}</p>
                    <p className="text-xs text-slate-400 mt-1">{n.time}</p>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
