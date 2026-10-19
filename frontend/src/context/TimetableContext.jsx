import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { adaptAllocations } from "../utils/timetableAdapter";

const TimetableContext = createContext(null);

// Holds the most recent generation run so Generate & Optimize and Timetable share it.
export function TimetableProvider({ children }) {
  const [generated, setGenerated] = useState(null); // { request, response, sessions, generatedAt }

  const saveGeneration = useCallback((request, response, reference) => {
    const sessions = response.is_feasible ? adaptAllocations(response.allocations, reference) : [];
    setGenerated({
      request,
      response,
      sessions,
      // Rows the grid could not place (unparseable time or day) — surfaced, never hidden.
      droppedCount: response.is_feasible ? response.allocations.length - sessions.length : 0,
      generatedAt: new Date(),
    });
  }, []);

  const value = useMemo(() => ({ generated, saveGeneration, clearGeneration: () => setGenerated(null) }), [generated, saveGeneration]);
  return <TimetableContext.Provider value={value}>{children}</TimetableContext.Provider>;
}

export function useTimetable() {
  const ctx = useContext(TimetableContext);
  if (!ctx) throw new Error("useTimetable must be used within TimetableProvider");
  return ctx;
}
