import React, { createContext, useContext, useState, useEffect } from 'react';

const DATA_URL = './dashboard.json';

const DashboardContext = createContext({
  data: null,
  loading: true,
  error: null,
});

/**
 * DashboardProvider — fetches /data/dashboard.json once and stores
 * it in React context.  All child components access data via
 * `useDashboard()` instead of per-component fetching.
 *
 * States:
 *   loading  – initial fetch in progress
 *   error    – fetch / parse failure (string message)
 *   data     – parsed DashboardPayload object
 *
 * No mock/fallback data — if the file is missing the error state
 * is surfaced to the UI.
 */
export function DashboardProvider({ children }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(DATA_URL);
        if (!res.ok) {
          throw new Error(`Failed to load dashboard data (HTTP ${res.status})`);
        }
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <DashboardContext.Provider value={{ data, loading, error }}>
      {children}
    </DashboardContext.Provider>
  );
}

/**
 * Hook — returns { data, loading, error } from the nearest
 * DashboardProvider.
 */
export function useDashboard() {
  return useContext(DashboardContext);
}

export default DashboardContext;
