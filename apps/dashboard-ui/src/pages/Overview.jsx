import React from 'react';
import { useDashboard } from '../context/DashboardContext';
import { LoadingState, ErrorState } from '../components/StatusStates';
import PageHeader from '../components/PageHeader';
import KpiTile from '../components/KpiTile';
import TrendChart from '../components/TrendChart';
import DonutChart from '../components/DonutChart';
import RepoTable from '../components/RepoTable';
import { fmt, pct, cfrPct } from '../utils/format';
import {
  Activity,
  Rocket,
  Clock,
  AlertTriangle,
  ShieldAlert,
  Timer,
  Code2,
  CheckCircle,
  Wrench,
  Bug,
  FileCode,
  Shield,
  PackageX,
  GitBranch,
  Server,
  Layers,
  ArrowUpDown,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';

/* ── Helper: trend arrow ── */
function TrendArrow({ direction }) {
  if (direction === 'up') return <TrendingUp className="inline w-4 h-4 text-green-400 ml-1" />;
  if (direction === 'down') return <TrendingDown className="inline w-4 h-4 text-red-400 ml-1" />;
  return null;
}

/* ── Section header ── */
function SectionHeader({ title }) {
  return <h2 className="text-lg font-semibold text-slate-100 mb-3 mt-6 border-b border-slate-700 pb-1">{title}</h2>;
}

export default function Overview() {
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const metadata   = data?.metadata   || {};
  const dora       = data?.dora       || {};
  const security   = data?.security   || {};
  const quality    = data?.quality    || {};
  const scores     = data?.scores     || {};
  const governance = data?.governance || {};
  const repos      = data?.repos      || [];

  /* ── Quick helper ── */
  const v = (val, digits = 2) => (val != null ? Number(val).toFixed(digits) : 'N/A');

  /* ── MSD: distribution charts ── */
  const vulnDist = [
    { name: 'Critical', value: security.critical },
    { name: 'High', value: security.high },
    { name: 'Medium', value: security.medium },
    { name: 'Low', value: security.low },
  ];

  const riskCounts = { Critical: 0, High: 0, Medium: 0, Low: 0 };
  repos.forEach((r) => { if (r.risk_level) riskCounts[r.risk_level] = (riskCounts[r.risk_level] || 0) + 1; });
  const riskDist = Object.entries(riskCounts).map(([name, value]) => ({ name, value }));

  const healthBuckets = { '80–100': 0, '60–79': 0, '40–59': 0, '0–39': 0 };
  repos.forEach((r) => {
    const s = r.health_score;
    if (s == null) return;
    if (s >= 80) healthBuckets['80–100']++;
    else if (s >= 60) healthBuckets['60–79']++;
    else if (s >= 40) healthBuckets['40–59']++;
    else healthBuckets['0–39']++;
  });
  const healthDist = Object.entries(healthBuckets).map(([name, value]) => ({ name, value }));

  /* ── DORA bar chart ── */
  const doraBar = [
    { name: 'Deploy Freq', value: dora.deployment_frequency },
    { name: 'Lead Time (h)', value: dora.lead_time_hours },
    { name: 'CFR %',  value: dora.change_failure_rate != null ? +(dora.change_failure_rate * 100).toFixed(1) : null },
    { name: 'MTTR (h)', value: dora.mttr_hours },
  ].filter((d) => d.value != null);

  return (
    <>
      <PageHeader
        title="Executive Overview"
        subtitle={`${metadata.total_repos ?? 0} repositories · ${metadata.scanned_repos ?? 0} scanned`}
        lastUpdated={metadata.generated_at}
      />

      {/* ── Engineering Health Score ── */}
      <div className="grid grid-cols-1 mb-4">
        <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-5 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">Engineering Health Score</p>
            <p className="text-4xl font-bold text-brand-400 mt-1">{fmt(scores.engineering_health, 1)}</p>
          </div>
          <Activity className="w-12 h-12 text-brand-400 opacity-60" />
        </div>
      </div>

      {/* ═══════ SPEED ═══════ */}
      <SectionHeader title="Speed" />
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4 mb-4">
        <KpiTile label="Avg Lead Time"      value={dora.lead_time_days != null ? v(dora.lead_time_days) : v((dora.lead_time_hours || 0) / 24)} unit="days" icon={Clock} />
        <KpiTile label="Prod Deploys"        value={dora.total_prod_deploys ?? dora.total_deployments ?? 'N/A'} icon={Rocket} color="text-sky-400" />
        <KpiTile label="Build Repair Time"   value={fmt(dora.build_repair_time_hours)} unit="h" icon={Wrench} />
        <KpiTile label="Deploy Freq"         value={fmt(dora.deployment_frequency)} unit="/day" icon={ArrowUpDown} />
        <KpiTile label="Change Fail %"       value={cfrPct(dora.change_failure_rate)} icon={AlertTriangle} />
      </div>

      {/* ═══════ QUALITY ═══════ */}
      <SectionHeader title="Quality" />
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4 mb-4">
        <KpiTile
          label="Total Tech Debt"
          value={quality.total_tech_debt_days != null ? v(quality.total_tech_debt_days, 1) : (quality.total_tech_debt_hours != null ? v(quality.total_tech_debt_hours / 24, 1) : 'N/A')}
          unit="days"
          icon={Clock}
          color="text-amber-400"
        />
        <KpiTile
          label="SonarQube D Rating"
          value={quality.sonar_d_count ?? 0}
          unit="repos"
          icon={Bug}
          color={quality.sonar_d_count > 0 ? 'text-orange-400' : 'text-green-400'}
        />
        <KpiTile
          label="SonarQube E Rating"
          value={quality.sonar_e_count ?? 0}
          unit="repos"
          icon={Bug}
          color={quality.sonar_e_count > 0 ? 'text-red-400' : 'text-green-400'}
        />
        <KpiTile label="Total Code Coverage" value={pct(quality.avg_coverage_pct)} icon={FileCode} />
        <KpiTile label="Quality Score" value={fmt(scores.quality, 0)} icon={Code2} color="text-brand-400" />
      </div>

      {/* ═══════ SECURITY ═══════ */}
      <SectionHeader title="Security" />
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4 mb-4">
        <KpiTile
          label="Repositories EOL"
          value={governance.eol_repos_count ?? security.eol_component_count ?? 'N/A'}
          icon={PackageX}
          color="text-red-400"
        />
        <KpiTile
          label="Snyk High Vulns"
          value={security.snyk_high ?? security.high ?? 'N/A'}
          icon={ShieldAlert}
          color="text-orange-400"
        />
        <KpiTile
          label="Snyk Critical Vulns"
          value={security.snyk_critical ?? security.critical ?? 'N/A'}
          icon={ShieldAlert}
          color={((security.snyk_critical ?? security.critical) > 0) ? 'text-red-500' : 'text-green-400'}
        />
        <KpiTile label="Sec MTTR" value={fmt(security.security_mttr_hours)} unit="h" icon={Timer} />
        <KpiTile label="Security Score" value={fmt(scores.security, 0)} icon={Shield} color="text-brand-400" />
      </div>

      {/* ═══════ REPOSITORY STATS ═══════ */}
      <SectionHeader title="Repository Stats" />
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4 mb-6">
        <KpiTile label="Trunk Branching" value={pct(governance.trunk_based_dev_pct)} icon={GitBranch} />
        <KpiTile label="IaC Repos" value={governance.iac_repos_count ?? 'N/A'} unit="repos" icon={Server} />
        <KpiTile label="CI Enterprise Repos" value={governance.ci_enabled_count ?? 'N/A'} icon={Layers} />
        <KpiTile label="CD Enterprise Repos" value={governance.cd_enabled_count ?? 'N/A'} icon={Rocket} />
        <KpiTile label="PaaS Repos" value={governance.paas_repos_count ?? 0} unit="repos" icon={Server} />
      </div>

      {/* ═══════ CHARTS ═══════ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <TrendChart type="bar" title="DORA Metrics" data={doraBar} dataKeys={['value']} xKey="name" />
        <TrendChart type="bar" title="Vulnerability Summary" data={vulnDist} dataKeys={['value']} xKey="name" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <DonutChart title="Risk Distribution" data={riskDist} />
        <DonutChart title="Health Score Dist." data={healthDist} />
        <DonutChart title="Vulnerability Dist." data={vulnDist} />
      </div>

      {/* Repo Table */}
      <h3 className="text-sm font-medium text-slate-300 mb-2">Repositories by Risk</h3>
      <RepoTable repos={repos} />
    </>
  );
}
