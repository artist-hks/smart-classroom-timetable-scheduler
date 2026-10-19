import { useCallback, useEffect, useState } from "react";
import { fetchReferenceData } from "../services/referenceService";

let cache = null;

export default function useReferenceData({ enabled = true } = {}) {
  const [state, setState] = useState({ data: cache, loading: enabled && !cache, error: null });

  // Initial load (skipped when cached or disabled). State is only set after the request settles.
  useEffect(() => {
    if (!enabled || cache) return undefined;
    let cancelled = false;
    fetchReferenceData()
      .then((data) => {
        cache = data;
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((err) => {
        if (!cancelled) setState({ data: null, loading: false, error: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const reload = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      cache = await fetchReferenceData();
      setState({ data: cache, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err.message });
    }
  }, []);

  return { ...state, reload };
}
