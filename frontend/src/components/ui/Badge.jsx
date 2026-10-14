const TONES = {
  neutral: "bg-ink-50 text-ink-600 border-ink-100",
  success: "bg-success-50 text-success border-success/25",
  warning: "bg-warning-50 text-warning border-warning/25",
  danger: "bg-danger-50 text-danger border-danger/25",
  info: "bg-info-50 text-info border-info/25",
  gold: "bg-gold-50 text-gold-600 border-gold-100",
};

export default function Badge({ tone = "neutral", children, dot = false, className = "" }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${dotColor(tone)}`} />}
      {children}
    </span>
  );
}

function dotColor(tone) {
  switch (tone) {
    case "success":
      return "bg-success";
    case "warning":
      return "bg-warning";
    case "danger":
      return "bg-danger";
    case "info":
      return "bg-info";
    case "gold":
      return "bg-gold";
    default:
      return "bg-slate-400";
  }
}
