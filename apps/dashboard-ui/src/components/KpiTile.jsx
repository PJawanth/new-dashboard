import React from 'react';
import { scoreColor } from '../utils/format';

/**
 * KPI Tile — a single metric card.
 *
 * Props:
 *   label  – metric name
 *   value  – primary display value (null/undefined → "N/A")
 *   unit   – optional suffix (%, h, /day)
 *   trend  – optional +/- delta string
 *   color  – tailwind text colour class override
 *   icon   – optional Lucide icon component
 */
export default function KpiTile({ label, value, unit = '', trend, color, icon: Icon }) {
  const display = value === null || value === undefined ? 'N/A' : value;
  const valColor =
    display === 'N/A'
      ? 'text-slate-500'
      : color || (typeof value === 'number' ? scoreColor(value) : 'text-slate-100');

  return (
    <div
      className="bg-surface-100 border border-surface-200 rounded-xl p-4 flex flex-col justify-between min-h-[110px] hover:border-brand-600/40 transition"
      role="group"
      aria-label={label}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</span>
        {Icon && <Icon size={16} className="text-slate-500" aria-hidden="true" />}
      </div>
      <div className="mt-2">
        <span className={`text-2xl font-bold ${valColor}`}>
          {display}
          {display !== 'N/A' && unit && (
            <span className="text-sm font-normal text-slate-400 ml-1">{unit}</span>
          )}
        </span>
        {trend && (
          <span
            className={`ml-2 text-xs ${
              trend.startsWith('+') ? 'text-green-400' : trend.startsWith('-') ? 'text-red-400' : 'text-slate-500'
            }`}
          >
            {trend}
          </span>
        )}
      </div>
    </div>
  );
}
