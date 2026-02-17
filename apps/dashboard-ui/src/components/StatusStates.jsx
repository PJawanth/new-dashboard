import React from 'react';

/** Full-page loading spinner. */
export function LoadingState() {
  return (
    <div className="flex items-center justify-center h-64" role="status" aria-label="Loading">
      <div className="animate-spin h-8 w-8 border-4 border-brand-500 border-t-transparent rounded-full" />
      <span className="sr-only">Loading dashboard data…</span>
    </div>
  );
}

/** Full-page error display. */
export function ErrorState({ message }) {
  return (
    <div className="flex items-center justify-center h-64" role="alert">
      <div className="text-center space-y-2">
        <p className="text-red-400 font-medium">Error loading data</p>
        <p className="text-sm text-slate-500">{message}</p>
      </div>
    </div>
  );
}
