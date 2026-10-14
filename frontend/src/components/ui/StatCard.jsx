export default function StatCard({ label, value, icon: Icon, trend, tone = "neutral", suffix }) {
  const toneColor =
    tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : tone === "success" ? "text-success" : "text-ink";
  return (
    <div className="bg-surface border border-line rounded-md p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500">{label}</span>
        {Icon && <Icon size={16} className="text-ink-400" />}
      </div>
      <div className="flex items-end gap-2">
        <span className={`text-2xl font-semibold ${toneColor}`}>{value}</span>
        {suffix && <span className="text-xs text-slate-400 mb-1">{suffix}</span>}
      </div>
      {trend && <p className="text-xs text-slate-400">{trend}</p>}
    </div>
  );
}
