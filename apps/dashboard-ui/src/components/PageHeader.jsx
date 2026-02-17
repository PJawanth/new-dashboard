import React from 'react';

export default function PageHeader({ title, subtitle, lastUpdated, children }) {
  return (
    <div className="mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{title}</h2>
          {subtitle && <p className="text-sm text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-4">
          {lastUpdated && (
            <span className="text-xs text-slate-500">
              Updated {new Date(lastUpdated).toLocaleString()}
            </span>
          )}
          {children}
        </div>
      </div>
    </div>
  );
}
