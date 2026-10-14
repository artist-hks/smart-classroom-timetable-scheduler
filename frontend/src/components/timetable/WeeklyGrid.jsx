import { days } from "../../data/academicStructure";
import { sessionTypeMeta } from "../../data/timetable";
import { getCourse, getResource, formatFacultyNames, formatParticipants, timeToMinutes } from "../../utils/scheduling";

const START = 9 * 60; // 9:00
const END = 16 * 60 + 40; // 16:40
const ROW_MIN = 20;
const NUM_ROWS = (END - START) / ROW_MIN;
const LUNCH = { start: 12 * 60, end: 12 * 60 + 40 };

function rowFor(minute) {
  return Math.round((minute - START) / ROW_MIN) + 1;
}

export default function WeeklyGrid({ sessions, activeDays = days, onSelectSession, dense = false }) {
  const hourMarks = [];
  for (let m = START; m <= END; m += 60) hourMarks.push(m);

  return (
    <div className="overflow-x-auto">
      <div
        className="grid min-w-[760px]"
        style={{
          gridTemplateColumns: `72px repeat(${activeDays.length}, 1fr)`,
          gridTemplateRows: `36px repeat(${NUM_ROWS}, ${dense ? 16 : 20}px)`,
        }}
      >
        {/* header row */}
        <div className="sticky left-0 bg-paper" style={{ gridColumn: 1, gridRow: 1 }} />
        {activeDays.map((day, i) => (
          <div
            key={day}
            className="flex items-center justify-center text-xs font-semibold text-ink border-b border-l border-line bg-ink-50"
            style={{ gridColumn: i + 2, gridRow: 1 }}
          >
            {day}
          </div>
        ))}

        {/* hour labels */}
        {hourMarks.map((m) => (
          <div
            key={m}
            className="text-[10px] text-slate-400 text-right pr-2 -translate-y-2 sticky left-0 bg-paper"
            style={{ gridColumn: 1, gridRow: rowFor(m) + 1 }}
          >
            {minutesToLabel(m)}
          </div>
        ))}

        {/* grid lines background per day column */}
        {activeDays.map((day, i) => (
          <div
            key={`col-${day}`}
            className="border-l border-line"
            style={{ gridColumn: i + 2, gridRow: `2 / span ${NUM_ROWS}` }}
          />
        ))}

        {/* lunch break band */}
        {activeDays.map((day, i) => (
          <div
            key={`lunch-${day}`}
            className="bg-ink-50/70 border-l border-line flex items-center justify-center"
            style={{
              gridColumn: i + 2,
              gridRow: `${rowFor(LUNCH.start) + 1} / ${rowFor(LUNCH.end) + 1}`,
            }}
          >
            {i === 0 && <span className="text-[9px] text-slate-400 uppercase tracking-wide">Lunch</span>}
          </div>
        ))}

        {/* sessions */}
        {activeDays.map((day, i) =>
          sessions
            .filter((s) => s.day === day)
            .map((s) => {
              const course = getCourse(s.courseId);
              const resource = getResource(s.resource);
              const meta = sessionTypeMeta[s.type];
              const startRow = rowFor(timeToMinutes(s.start)) + 1;
              const endRow = rowFor(timeToMinutes(s.end)) + 1;
              const isFlagged = s.status === "flagged";
              return (
                <button
                  key={s.id}
                  onClick={() => onSelectSession?.(s)}
                  className={`m-0.5 rounded border text-left px-2 py-1 overflow-hidden flex flex-col justify-start hover:shadow-card transition-shadow ${
                    isFlagged ? "border-danger bg-danger-50" : "border-line bg-surface"
                  }`}
                  style={{
                    gridColumn: i + 2,
                    gridRow: `${startRow} / ${endRow}`,
                    borderLeftWidth: 3,
                    borderLeftColor: meta.color,
                    zIndex: 5,
                  }}
                  title={`${course?.name} · ${s.start}-${s.end}`}
                >
                  <span className="text-[11px] font-semibold text-ink truncate leading-tight">{course?.name}</span>
                  <span className="text-[10px] text-slate-500 truncate leading-tight">{formatFacultyNames(s.faculty)}</span>
                  <span className="text-[10px] text-slate-400 truncate leading-tight">
                    {formatParticipants(s.participants)} · {resource?.code}
                  </span>
                </button>
              );
            })
        )}
      </div>
    </div>
  );
}

function minutesToLabel(m) {
  const h = Math.floor(m / 60);
  const min = m % 60;
  const period = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}${min ? ":" + String(min).padStart(2, "0") : ""} ${period}`;
}
