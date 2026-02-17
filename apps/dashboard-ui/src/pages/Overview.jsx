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
} from 'lucide-react';

export default function Overview() {
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const metadata   = data?.metadata || {};
  const dora       = data?.dora || {};
  const security   = data?.security || {};
  const scores     = data?.scores || {};
  const governance = data?.governance || {};
  const repos      = data?.repos || [];

  /* ── distribution charts ── */
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

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-4 mb-6">
        <KpiTile label="Eng Health"    value={fmt(scores.engineering_health, 0)} icon={Activity} color="text-brand-400" />
        <KpiTile label="Deploy Freq"   value={fmt(dora.deployment_frequency)}     unit="/day" icon={Rocket} />
        <KpiTile label="Lead Time"     value={fmt(dora.lead_time_hours)}          unit="h"   icon={Clock} />
        <KpiTile label="Change Fail %" value={cfrPct(dora.change_failure_rate)}              icon={AlertTriangle} />
        <KpiTile label="Open Critical" value={security.critical != null ? security.critical : 'N/A'} icon={ShieldAlert} color={security.critical > 0 ? 'text-red-400' : 'text-green-400'} />
        <KpiTile label="Sec MTTR"      value={fmt(security.security_mttr_hours)}  unit="h"   icon={Timer} />
        <KpiTile label="Sec Score"     value={fmt(scores.security, 0)}                       icon={Code2} color="text-brand-400" />
        <KpiTile label="Compliance"    value={pct(governance.branch_protection_pct)}          icon={CheckCircle} />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <TrendChart type="bar" title="DORA Metrics" data={doraBar} dataKeys={['value']} xKey="name" />
        <TrendChart type="bar" title="Vulnerability Summary" data={vulnDist} dataKeys={['value']} xKey="name" />
      </div>

      {/* Distribution Row */}
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
