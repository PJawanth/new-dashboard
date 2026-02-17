import React from 'react';
import { riskBg } from '../utils/format';

const VARIANT_CLASSES = {
  success: 'bg-green-500/20 text-green-400',
  warning: 'bg-yellow-500/20 text-yellow-400',
  danger:  'bg-red-500/20 text-red-400',
  info:    'bg-blue-500/20 text-blue-400',
  neutral: 'bg-slate-500/20 text-slate-400',
};

/**
 * Badge — small labelled pill.
 *
 * Props:
 *   label   – display text
 *   variant – 'success' | 'warning' | 'danger' | 'info' | 'neutral'
 *   risk    – if provided, uses risk-level colour logic instead
 */
export default function Badge({ label, variant = 'neutral', risk }) {
  const cls = risk ? riskBg(risk) : (VARIANT_CLASSES[variant] || VARIANT_CLASSES.neutral);

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}
