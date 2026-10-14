import { sessionTypeMeta } from "../../data/timetable";

export default function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {Object.entries(sessionTypeMeta).map(([key, meta]) => (
        <div key={key} className="flex items-center gap-1.5 text-xs text-slate-500">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: meta.color }} />
          {meta.label}
        </div>
      ))}
    </div>
  );
}
