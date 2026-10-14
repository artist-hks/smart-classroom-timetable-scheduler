import { Search } from "lucide-react";

export default function TableToolbar({ search, onSearch, placeholder = "Search…", filters, actions }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
      <div className="relative sm:w-64">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded border border-line bg-surface pl-8 pr-3 py-2 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-ink-400"
        />
      </div>
      {filters}
      <div className="sm:ml-auto flex items-center gap-2">{actions}</div>
    </div>
  );
}
