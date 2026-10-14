export function Field({ label, required, error, hint, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-xs font-medium text-ink">
          {label} {required && <span className="text-danger">*</span>}
        </label>
      )}
      {children}
      {hint && !error && <p className="text-xs text-slate-400">{hint}</p>}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

export function Input({ error, className = "", ...props }) {
  return (
    <input
      className={`w-full rounded border px-3 py-2 text-sm bg-surface placeholder:text-slate-400 focus:outline-none focus:ring-1 ${
        error ? "border-danger focus:ring-danger" : "border-line focus:ring-ink-400 focus:border-ink-400"
      } ${className}`}
      {...props}
    />
  );
}

export function Select({ error, className = "", children, ...props }) {
  return (
    <select
      className={`w-full rounded border px-3 py-2 text-sm bg-surface focus:outline-none focus:ring-1 ${
        error ? "border-danger focus:ring-danger" : "border-line focus:ring-ink-400 focus:border-ink-400"
      } ${className}`}
      {...props}
    >
      {children}
    </select>
  );
}

export function Checkbox({ label, className = "", ...props }) {
  return (
    <label className={`inline-flex items-center gap-2 text-sm text-ink cursor-pointer ${className}`}>
      <input type="checkbox" className="h-4 w-4 rounded border-line text-ink accent-ink-600" {...props} />
      {label}
    </label>
  );
}

export function Textarea({ error, className = "", ...props }) {
  return (
    <textarea
      className={`w-full rounded border px-3 py-2 text-sm bg-surface placeholder:text-slate-400 focus:outline-none focus:ring-1 ${
        error ? "border-danger focus:ring-danger" : "border-line focus:ring-ink-400 focus:border-ink-400"
      } ${className}`}
      {...props}
    />
  );
}
