import React from 'react';

/**
 * Card — generic container with dark surface styling.
 *
 * Props:
 *   title     – optional heading
 *   subtitle  – optional sub-heading
 *   className – extra classes
 *   children  – content
 *   noPad     – skip default padding
 */
export default function Card({ title, subtitle, className = '', children, noPad = false }) {
  return (
    <div className={`bg-surface-100 border border-surface-200 rounded-xl ${noPad ? '' : 'p-5'} ${className}`}>
      {(title || subtitle) && (
        <div className={`${noPad ? 'px-5 pt-5' : ''} mb-3`}>
          {title && <h3 className="text-sm font-medium text-slate-300">{title}</h3>}
          {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
      )}
      {children}
    </div>
  );
}
