import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { riskBg, scoreColor, fmt, deepGet } from '../utils/format';
import { ChevronUp, ChevronDown, Search } from 'lucide-react';

const DEFAULT_COLUMNS = [
  { key: 'name', label: 'Repository' },
  { key: 'risk_level', label: 'Risk' },
  { key: 'health_score', label: 'Health', format: 'score' },
  { key: 'security_score', label: 'Security', format: 'score' },
  { key: 'security.critical', label: 'Critical', format: 'number' },
  { key: 'governance.ci_enabled', label: 'CI', format: 'bool' },
  { key: 'language', label: 'Language' },
];

/**
 * Sortable + searchable repo table with click-through to drilldown.
 *
 * Props:
 *   repos       – array of repo summary objects
 *   columns     – array of { key, label, format?, align? }
 *   linkPrefix  – route prefix for row click (default '/repos/')
 *   searchable  – show search box (default true)
 */
export default function RepoTable({
  repos = [],
  columns = DEFAULT_COLUMNS,
  linkPrefix = '/repos/',
  searchable = true,
}) {
  const [sortKey, setSortKey] = useState('health_score');
  const [sortAsc, setSortAsc] = useState(false);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const filtered = useMemo(() => {
    if (!search.trim()) return repos;
    const q = search.toLowerCase();
    return repos.filter((r) => {
      const name = (r.name || '').toLowerCase();
      const lang = (r.language || '').toLowerCase();
      const risk = (r.risk_level || '').toLowerCase();
      return name.includes(q) || lang.includes(q) || risk.includes(q);
    });
  }, [repos, search]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      const av = deepGet(a, sortKey);
      const bv = deepGet(b, sortKey);
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') return sortAsc ? av - bv : bv - av;
      return sortAsc
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
    return arr;
  }, [filtered, sortKey, sortAsc]);

  const handleSort = (key) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const renderCell = (repo, col) => {
    const val = deepGet(repo, col.key);
    if (col.key === 'risk_level') {
      return val ? <span className={`px-2 py-0.5 rounded text-xs font-medium ${riskBg(val)}`}>{val}</span> : 'N/A';
    }
    if (col.format === 'score') {
      if (val == null) return <span className="text-slate-500">N/A</span>;
      return <span className={`font-semibold ${scoreColor(val)}`}>{fmt(val, 0)}</span>;
    }
    if (col.format === 'bool') {
      if (val == null) return <span className="text-slate-500">N/A</span>;
      return val ? <span className="text-green-400" aria-label="Yes">✓</span> : <span className="text-red-400" aria-label="No">✗</span>;
    }
    if (col.format === 'number') return val != null ? fmt(val, 0) : 'N/A';
    return val ?? 'N/A';
  };

  return (
    <div className="bg-surface-100 border border-surface-200 rounded-xl overflow-hidden">
      {/* Search */}
      {searchable && (
        <div className="px-4 py-3 border-b border-surface-200">
          <div className="relative max-w-xs">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search repos…"
              className="w-full bg-surface-200/50 border border-surface-200 rounded-lg pl-8 pr-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50"
              aria-label="Search repositories"
            />
          </div>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left" role="table">
          <thead>
            <tr className="border-b border-surface-200">
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className="px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 select-none"
                  scope="col"
                >
                  <span className="inline-flex items-center gap-1">
                    {col.label}
                    {sortKey === col.key && (sortAsc ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((repo) => (
              <tr
                key={repo.name}
                onClick={() => navigate(`${linkPrefix}${repo.name}`)}
                className="border-b border-surface-200/50 hover:bg-surface-200/30 cursor-pointer transition"
                role="row"
              >
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-3 whitespace-nowrap">
                    {renderCell(repo, col)}
                  </td>
                ))}
              </tr>
            ))}
            {!sorted.length && (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-slate-500">
                  {search ? 'No matching repositories' : 'No repositories found'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
