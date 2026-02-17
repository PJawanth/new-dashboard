import React from 'react';
import { useDashboard } from '../context/DashboardContext';
import { LoadingState, ErrorState } from '../components/StatusStates';
import PageHeader from '../components/PageHeader';
import KpiTile from '../components/KpiTile';
import TrendChart from '../components/TrendChart';
import InfoTooltip from '../components/InfoTooltip';
import Card from '../components/Card';
import { fmt, cfrPct, pct } from '../utils/format';
import {
  Rocket,
  Clock,
  AlertTriangle,
  Timer,
  GitPullRequest,
  Layers,
  Zap,
  Wrench,
  Code2,
  Eye,
  Play,
} from 'lucide-react';

export default function DevOps() {
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const metadata = data?.metadata || {};
  const dora     = data?.dora || {};
  const flow     = data?.flow || {};
  const repos    = data?.repos || [];

  /* per-repo bar data */
  const doraPerRepo = repos
    .filter((r) => r.dora)
    .map((r) => ({
      name: (r.name || '').substring(0, 16),
      'Deploy Freq': r.dora?.deployment_frequency,
      'Lead Time (h)': r.dora?.lead_time_hours,
    }));

  const flowPerRepo = repos
    .filter((r) => r.flow)
    .map((r) => ({
      name: (r.name || '').substring(0, 16),
      'Cycle Time (h)': r.flow?.pr_cycle_time_hours,
      WIP: r.flow?.wip,
      Throughput: r.flow?.throughput,
    }));

  /* pipeline reliability */
  const pipelineData = repos
    .filter((r) => r.dora)
    .map((r) => ({
      name: r.name,
      deployments: r.dora?.total_deployments,
      failures: r.dora?.total_failures,
      cfr: r.dora?.change_failure_rate != null ? +(r.dora.change_failure_rate * 100).toFixed(1) : null,
      lead_time: r.dora?.lead_time_hours,
      build_repair: r.dora?.build_repair_time_hours,
    }));

  /* Lead time breakdown chart data */
  const ltBreakdown = [
    { name: 'Coding', value: dora.lead_time_coding_hours },
    { name: 'Review', value: dora.lead_time_review_hours },
    { name: 'Deploy', value: dora.lead_time_deploy_hours },
  ].filter((d) => d.value != null);

  /* DORA trends */
  const dfTrend = (dora.deployment_frequency_trend || []).map((t) => ({
    name: t.period,
    value: t.value,
  }));
  const ltTrend = (dora.lead_time_trend || []).map((t) => ({
    name: t.period,
    value: t.value,
  }));
  const cfrTrend = (dora.cfr_trend || []).map((t) => ({
    name: t.period,
    value: t.value,
  }));

  return (
    <>
      <PageHeader
        title="DevOps — DORA & Flow"
        subtitle="Delivery performance, value-stream metrics, and trends"
        lastUpdated={metadata.generated_at}
      />

      {/* DORA KPIs */}
      <div className="flex items-center gap-1 mb-2">
        <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider">DORA Metrics</h3>
        <InfoTooltip term="DORA" definition="DevOps Research & Assessment — the four key metrics: Deployment Frequency, Lead Time, Change Failure Rate, MTTR." />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-4 mb-6">
        <KpiTile label="Deploy Freq"      value={fmt(dora.deployment_frequency)}    unit="/day" icon={Rocket} />
        <KpiTile label="Lead Time"        value={fmt(dora.lead_time_hours)}         unit="h"   icon={Clock} />
        <KpiTile label="Change Fail %"    value={cfrPct(dora.change_failure_rate)}              icon={AlertTriangle} />
        <KpiTile label="MTTR"             value={fmt(dora.mttr_hours)}              unit="h"   icon={Timer} />
        <KpiTile label="Build Repair"     value={fmt(dora.build_repair_time_hours)} unit="h"   icon={Wrench} />
      </div>

      {/* Lead Time Breakdown */}
      {ltBreakdown.length > 0 && (
        <>
          <div className="flex items-center gap-1 mb-2">
            <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider">Lead Time Breakdown</h3>
            <InfoTooltip term="Lead Time Breakdown" definition="Coding: first commit → PR open. Review: PR open → merge. Deploy: merge → deploy." />
          </div>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <KpiTile label="Coding" value={fmt(dora.lead_time_coding_hours)} unit="h" icon={Code2} />
            <KpiTile label="Review" value={fmt(dora.lead_time_review_hours)} unit="h" icon={Eye} />
            <KpiTile label="Deploy" value={fmt(dora.lead_time_deploy_hours)} unit="h" icon={Play} />
          </div>
        </>
      )}

      {/* Flow KPIs */}
      <div className="flex items-center gap-1 mb-2">
        <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider">Flow Metrics</h3>
        <InfoTooltip term="Flow" definition="PR review & cycle times, WIP count, throughput, and review SLA compliance." />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <KpiTile label="PR Review Time" value={fmt(flow.pr_review_time_hours)} unit="h"   icon={GitPullRequest} />
        <KpiTile label="PR Cycle Time"  value={fmt(flow.pr_cycle_time_hours)}  unit="h"   icon={Clock} />
        <KpiTile label="WIP"            value={flow.wip != null ? flow.wip : 'N/A'}       icon={Layers} />
        <KpiTile label="Throughput"     value={flow.throughput != null ? flow.throughput : 'N/A'} unit="PRs" icon={Zap} />
        <KpiTile label="Review SLA"     value={pct(flow.review_sla_met_pct)}               icon={Timer} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <TrendChart type="bar" title="DORA per Repository" data={doraPerRepo} dataKeys={['Deploy Freq', 'Lead Time (h)']} />
        <TrendChart type="bar" title="Flow per Repository"  data={flowPerRepo} dataKeys={['Cycle Time (h)', 'WIP', 'Throughput']} />
      </div>

      {/* DORA Trends */}
      {(dfTrend.length > 0 || ltTrend.length > 0 || cfrTrend.length > 0) && (
        <>
          <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">DORA Trends</h3>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            {dfTrend.length > 0 && (
              <TrendChart type="line" title="Deploy Frequency Trend" data={dfTrend} dataKeys={['value']} xKey="name" height={200} />
            )}
            {ltTrend.length > 0 && (
              <TrendChart type="line" title="Lead Time Trend (h)" data={ltTrend} dataKeys={['value']} xKey="name" height={200} />
            )}
            {cfrTrend.length > 0 && (
              <TrendChart type="line" title="CFR Trend (%)" data={cfrTrend} dataKeys={['value']} xKey="name" height={200} />
            )}
          </div>
        </>
      )}

      {/* Pipeline reliability table */}
      <h3 className="text-sm font-medium text-slate-300 mb-2">Pipeline Reliability</h3>
      <div className="bg-surface-100 border border-surface-200 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left" role="table">
            <thead>
              <tr className="border-b border-surface-200">
                <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase">Repo</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase">Deployments</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase">Failures</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase">CFR %</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase">Lead Time (h)</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase">Build Repair (h)</th>
              </tr>
            </thead>
            <tbody>
              {pipelineData.map((r) => (
                <tr key={r.name} className="border-b border-surface-200/50 hover:bg-surface-200/30 transition">
                  <td className="px-4 py-3 font-medium">{r.name}</td>
                  <td className="px-4 py-3">{r.deployments ?? 'N/A'}</td>
                  <td className="px-4 py-3">{r.failures ?? 'N/A'}</td>
                  <td className="px-4 py-3">{r.cfr != null ? `${r.cfr}%` : 'N/A'}</td>
                  <td className="px-4 py-3">{fmt(r.lead_time)}</td>
                  <td className="px-4 py-3">{fmt(r.build_repair)}</td>
                </tr>
              ))}
              {!pipelineData.length && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">No pipeline data available</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
