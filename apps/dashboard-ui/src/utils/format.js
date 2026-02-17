/** Formatting & display helpers — null-safe throughout. */

/**
 * Safe value display: returns formatted value or 'N/A'.
 * Never returns 0 for missing data.
 */
export function v(value, fallback = 'N/A') {
  if (value === null || value === undefined) return fallback;
  return value;
}

/** Format a number with optional decimals, or 'N/A'. */
export function fmt(value, decimals = 1) {
  if (value === null || value === undefined) return 'N/A';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'N/A';
    return Number.isInteger(value) && decimals === 0
      ? value.toLocaleString()
      : value.toFixed(decimals);
  }
  return String(value);
}

/** Format as percentage string, or 'N/A'. */
export function pct(value) {
  if (value === null || value === undefined) return 'N/A';
  if (typeof value === 'number') return `${value.toFixed(1)}%`;
  return `${value}%`;
}

/** Safe multiply for CFR (raw 0–1) → display percent. */
export function cfrPct(value) {
  if (value === null || value === undefined) return 'N/A';
  return `${(value * 100).toFixed(1)}%`;
}

/** Risk level → text colour class. */
export function riskColor(level) {
  const map = {
    Critical: 'text-red-400',
    High: 'text-orange-400',
    Medium: 'text-yellow-400',
    Low: 'text-green-400',
  };
  return map[level] || 'text-slate-400';
}

/** Risk level → badge background + text. */
export function riskBg(level) {
  const map = {
    Critical: 'bg-red-500/20 text-red-400',
    High: 'bg-orange-500/20 text-orange-400',
    Medium: 'bg-yellow-500/20 text-yellow-400',
    Low: 'bg-green-500/20 text-green-400',
  };
  return map[level] || 'bg-slate-500/20 text-slate-400';
}

/** Score → colour class. */
export function scoreColor(score) {
  if (score === null || score === undefined) return 'text-slate-400';
  if (score >= 80) return 'text-green-400';
  if (score >= 60) return 'text-yellow-400';
  if (score >= 40) return 'text-orange-400';
  return 'text-red-400';
}

/** ISO string → relative time (3 h ago). */
export function relativeTime(iso) {
  if (!iso) return 'N/A';
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

/** Deep get — safely traverse nested paths. */
export function deepGet(obj, path) {
  if (!obj || !path) return undefined;
  return path.split('.').reduce((o, k) => (o != null ? o[k] : undefined), obj);
}

/** Format hours into a human-friendly string. */
export function hoursToStr(h) {
  if (h === null || h === undefined) return 'N/A';
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

/** SonarQube numeric rating (1-5) to letter (A-E). */
export function ratingLetter(val) {
  if (val === null || val === undefined) return 'N/A';
  const n = typeof val === 'number' ? val : parseFloat(val);
  if (n <= 1) return 'A';
  if (n <= 2) return 'B';
  if (n <= 3) return 'C';
  if (n <= 4) return 'D';
  return 'E';
}

/** Rating letter colour. */
export function ratingColor(val) {
  const letter = typeof val === 'string' ? val : ratingLetter(val);
  const map = { A: 'text-green-400', B: 'text-lime-400', C: 'text-yellow-400', D: 'text-orange-400', E: 'text-red-400' };
  return map[letter] || 'text-slate-400';
}
