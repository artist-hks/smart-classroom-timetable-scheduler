export default function DataTable({ columns, rows, onRowClick, emptyState }) {
  if (rows.length === 0) return emptyState || null;

  return (
    <div className="overflow-x-auto -mx-5 px-5">
      <table className="w-full text-sm min-w-[640px]">
        <thead>
          <tr className="border-b border-line">
            {columns.map((col) => (
              <th key={col.key} className="text-left font-medium text-xs text-slate-400 uppercase tracking-wide py-2.5 pr-4 whitespace-nowrap">
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row.id || i}
              onClick={() => onRowClick?.(row)}
              className={`border-b border-line last:border-0 ${onRowClick ? "cursor-pointer hover:bg-ink-50" : ""}`}
            >
              {columns.map((col) => (
                <td key={col.key} className="py-3 pr-4 text-ink align-middle whitespace-nowrap">
                  {col.render ? col.render(row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
