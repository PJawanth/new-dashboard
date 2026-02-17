import React, { useState, useRef } from 'react';
import { HelpCircle } from 'lucide-react';

/**
 * InfoTooltip — an accessible hover/focus tooltip showing
 * a definition and optional formula.
 *
 * Props:
 *   term       – metric name
 *   definition – plain-English explanation
 *   formula    – optional calculation formula
 */
export default function InfoTooltip({ term, definition, formula }) {
  const [open, setOpen] = useState(false);
  const timeout = useRef(null);

  const show = () => { clearTimeout(timeout.current); setOpen(true); };
  const hide = () => { timeout.current = setTimeout(() => setOpen(false), 150); };

  return (
    <span
      className="relative inline-flex items-center"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <button
        type="button"
        className="text-slate-500 hover:text-slate-300 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 rounded"
        aria-label={`Info: ${term}`}
        tabIndex={0}
      >
        <HelpCircle size={14} />
      </button>

      {open && (
        <div
          role="tooltip"
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 rounded-lg
                     bg-surface-100 border border-surface-200 shadow-xl text-xs text-slate-300
                     animate-in fade-in slide-in-from-bottom-1"
        >
          <p className="font-semibold text-slate-200 mb-1">{term}</p>
          <p>{definition}</p>
          {formula && (
            <p className="mt-1.5 text-slate-500 font-mono text-[10px]">{formula}</p>
          )}
          {/* Arrow */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 w-2 h-2 bg-surface-100 border-r border-b border-surface-200 rotate-45 -mt-1" />
        </div>
      )}
    </span>
  );
}
