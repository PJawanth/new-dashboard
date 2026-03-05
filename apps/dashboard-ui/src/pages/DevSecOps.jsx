import React from 'react';
import { useDashboard } from '../context/DashboardContext';
import { LoadingState, ErrorState } from '../components/StatusStates';
import PageHeader from '../components/PageHeader';
import KpiTile from '../components/KpiTile';
import TrendChart from '../components/TrendChart';
import DonutChart from '../components/DonutChart';
import RepoTable from '../components/RepoTable';
import Card from '../components/Card';
import { fmt, pct } from '../utils/format';
import {
  ShieldAlert,
  Bug,
  KeyRound,
  PackageOpen,
  Timer,
  Lock,
  CheckCircle2,
  XCircle,
  AlertOctagon,
  BarChart3,
  PackageX,
} from 'lucide-react';

export default function DevSecOps() {
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const metadata = data?.metadata || {};
  const security = data?.security || {};
  const scores   = data?.scores || {};
  const repos    = data?.repos || [];

  const governance = data?.governance || {};

  const sevData = [
    { name: 'Critical', value: security.critical },
    { name: 'High',     value: security.high },
    { name: 'Medium',   value: security.medium },
    { name: 'Low',      value: security.low },
  ];

  /* gate pass from aggregated data */
  const gatePassPct = security.security_gate_pass_pct;

  /* repos at risk */
  const atRisk = repos
    .filter((r) => {
      const s = r.security || {};
      return (s.critical ?? 0) > 0 || (s.secrets ?? 0) > 0;
    })
    .sort((a, b) => ((b.security?.critical ?? 0) - (a.security?.critical ?? 0)));

  /* per-repo vulns bar */
  const vulnPerRepo = repos.slice(0, 15).map((r) => ({
    name: (r.name || '').substring(0, 14),
    Critical: r.security?.critical ?? 0,
    High: r.security?.high ?? 0,
    Medium: r.security?.medium ?? 0,
  }));

  /* EOL components across all repos */
  const eolRepos = repos.filter((r) => (r.security?.eol_components ?? 0) > 0);

  const secColumns = [
    { key: 'name', label: 'Repository' },
    { key: 'risk_level', label: 'Risk' },
    { key: 'security_score', label: 'Sec Score', format: 'score' },
    { key: 'security.critical', label: 'Critical', format: 'number' },
    { key: 'security.high', label: 'High', format: 'number' },
    { key: 'security.secrets', label: 'Secrets', format: 'number' },
    { key: 'security.vulnerability_density', label: 'Vuln/KLOC', format: 'number' },
    { key: 'security.eol_components', label: 'EOL', format: 'number' },
  ];

  return (
    <>
      <PageHeader
        title="DevSecOps — Security Posture"
        subtitle="Vulnerability management, secrets, gate compliance, and EOL tracking"
        lastUpdated={metadata.generated_at}
      />

      {/* ── MSD Prominent Snyk & EOL KPIs ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-5 text-center">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Repositories EOL (Past Due)</p>
          <p className="text-3xl font-bold text-red-400">{governance.eol_repos_count ?? security.eol_component_count ?? 0}</p>
        </div>
        <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-5 text-center">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Snyk High Vulnerabilities</p>
          <p className="text-3xl font-bold text-orange-400">{security.snyk_high ?? security.high ?? 0}</p>
        </div>
        <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-5 text-center">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Snyk Critical Vulnerabilities</p>
          <p className={`text-3xl font-bold ${((security.snyk_critical ?? security.critical ?? 0) > 0) ? 'text-red-500' : 'text-green-400'}`}>
            {security.snyk_critical ?? security.critical ?? 0}
          </p>
        </div>
      </div>

      {/* KPI tiles — 2 rows */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-4 mb-4">
        <KpiTile label="Critical"     value={security.critical}                    icon={ShieldAlert} color={(security.critical ?? 0) > 0 ? 'text-red-400' : 'text-green-400'} />
        <KpiTile label="High"         value={security.high}                        icon={Bug}         color={(security.high ?? 0) > 0 ? 'text-orange-400' : 'text-green-400'} />
        <KpiTile label="Medium"       value={security.medium}                      icon={Bug} />
        <KpiTile label="Secrets"      value={security.secrets}                     icon={KeyRound}    color={(security.secrets ?? 0) > 0 ? 'text-red-400' : 'text-green-400'} />
        <KpiTile label="Dep Alerts"   value={security.dependency_alerts}           icon={PackageOpen} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-4 mb-6">
        <KpiTile label="Sec MTTR"     value={fmt(security.security_mttr_hours)}    unit="h" icon={Timer} />
        <KpiTile label="Vuln Density" value={fmt(security.vulnerability_density)}  unit="/KLOC" icon={BarChart3} />
        <KpiTile label="Gate Pass"    value={gatePassPct != null ? `${gatePassPct}%` : 'N/A'}   icon={gatePassPct != null && gatePassPct >= 100 ? CheckCircle2 : XCircle} color={gatePassPct != null && gatePassPct >= 80 ? 'text-green-400' : 'text-orange-400'} />
        <KpiTile label="EOL Pkgs"     value={security.eol_component_count ?? 0}    icon={PackageX}    color={(security.eol_component_count ?? 0) > 0 ? 'text-orange-400' : 'text-green-400'} />
        <KpiTile label="Sec Score"    value={fmt(scores.security, 0)}              icon={Lock} color="text-brand-400" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <DonutChart title="Severity Breakdown" data={sevData} />
        <TrendChart type="bar" title="Vulnerabilities per Repository" data={vulnPerRepo} dataKeys={['Critical', 'High', 'Medium']} />
      </div>

      {/* Security Gate & EOL details */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <Card title="Security Gate Status">
          <div className="space-y-3 text-sm">
            <GateRow label="Gate Pass Rate" value={gatePassPct != null ? `${gatePassPct}%` : 'N/A'} ok={gatePassPct != null && gatePassPct >= 80} />
            <GateRow label="0 Critical Vulns" value={`${repos.filter((r) => (r.security?.critical ?? 0) === 0).length}/${repos.length} repos`} ok={repos.every((r) => (r.security?.critical ?? 0) === 0)} />
            <GateRow label="0 Leaked Secrets" value={`${repos.filter((r) => (r.security?.secrets ?? 0) === 0).length}/${repos.length} repos`} ok={repos.every((r) => (r.security?.secrets ?? 0) === 0)} />
            <GateRow label="Sec MTTR < 72h" value={security.security_mttr_hours != null ? `${fmt(security.security_mttr_hours)}h` : 'N/A'} ok={security.security_mttr_hours != null && security.security_mttr_hours < 72} />
          </div>
        </Card>

        <Card title={`EOL / Deprecated Components (${eolRepos.length} repos)`}>
          {eolRepos.length > 0 ? (
            <div className="space-y-2 text-sm max-h-48 overflow-y-auto">
              {eolRepos.map((r) => (
                <div key={r.name} className="flex justify-between items-center border-b border-surface-200/50 py-1 last:border-0">
                  <span className="text-slate-300">{r.name}</span>
                  <span className="text-orange-400 font-medium">{r.security?.eol_components} EOL pkgs</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500 text-sm py-4 text-center">No EOL components detected</p>
          )}
        </Card>
      </div>

      {/* Repos at risk */}
      <h3 className="text-sm font-medium text-slate-300 mb-2">
        {atRisk.length ? 'Repos at Risk' : 'All Repositories — Security'}
      </h3>
      <RepoTable repos={atRisk.length ? atRisk : repos} columns={secColumns} />
    </>
  );
}

function GateRow({ label, value, ok }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-surface-200/50 last:border-0">
      <span className="text-slate-400">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-slate-200 font-medium">{value}</span>
        {ok ? (
          <CheckCircle2 size={14} className="text-green-400" />
        ) : (
          <AlertOctagon size={14} className="text-red-400" />
        )}
      </div>
    </div>
  );
}
