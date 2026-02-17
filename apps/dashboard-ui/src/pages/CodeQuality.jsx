import React from 'react';
import { useDashboard } from '../context/DashboardContext';
import { LoadingState, ErrorState } from '../components/StatusStates';
import PageHeader from '../components/PageHeader';
import KpiTile from '../components/KpiTile';
import TrendChart from '../components/TrendChart';
import DonutChart from '../components/DonutChart';
import Card from '../components/Card';
import InfoTooltip from '../components/InfoTooltip';
import { fmt, pct, ratingLetter, ratingColor } from '../utils/format';
import {
  Bug,
  Code2,
  Layers,
  FileCode,
  Clock,
  GitPullRequest,
  Gauge,
  Scale,
  TrendingUp,
} from 'lucide-react';

export default function CodeQuality() {
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const metadata = data?.metadata || {};
  const quality  = data?.quality || {};
  const scores   = data?.scores || {};
  const repos    = data?.repos || [];

  /* per-repo coverage chart */
  const coverageData = repos
    .filter((r) => r.quality?.coverage_pct != null)
    .map((r) => ({
      name: (r.name || '').substring(0, 16),
      Coverage: r.quality.coverage_pct,
    }));

  /* per-repo bugs/smells */
  const codeHealthData = repos
    .filter((r) => r.quality && (r.quality.bugs != null || r.quality.code_smells != null))
    .map((r) => ({
      name: (r.name || '').substring(0, 16),
      Bugs: r.quality?.bugs ?? 0,
      'Code Smells': r.quality?.code_smells ?? 0,
    }));

  /* language donut */
  const languages = data?.languages?.breakdown || {};
  const langData = Object.entries(languages)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, value]) => ({ name, value }));

  /* coverage trend */
  const coverageTrend = (quality.coverage_trend || []).map((t) => ({
    name: t.period || t.date,
    value: t.value,
  }));

  /* rating distribution donut data */
  const maintDist = quality.rating_distribution?.maintainability || {};
  const maintData = Object.entries(maintDist)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, value]) => ({ name, value }));

  /* per-repo tech debt chart */
  const debtData = repos
    .filter((r) => r.quality?.tech_debt_ratio != null)
    .map((r) => ({
      name: (r.name || '').substring(0, 16),
      'Debt Ratio %': r.quality.tech_debt_ratio,
    }));

  return (
    <>
      <PageHeader
        title="Code Quality"
        subtitle="Coverage, bugs, technical debt, maintainability, and code health"
        lastUpdated={metadata.generated_at}
      />

      {/* KPI Row 1 */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-4 gap-4 mb-4">
        <KpiTile label="Quality Score"   value={fmt(scores.quality, 0)}         icon={Code2} color="text-brand-400" />
        <KpiTile label="Avg Coverage"    value={pct(quality.avg_coverage_pct)}   icon={FileCode} />
        <KpiTile label="Total Bugs"      value={quality.total_bugs}              icon={Bug} color={(quality.total_bugs ?? 0) > 0 ? 'text-orange-400' : 'text-green-400'} />
        <KpiTile label="Code Smells"     value={quality.total_code_smells}       icon={Layers} />
      </div>

      {/* KPI Row 2 — new metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-4 gap-4 mb-6">
        <KpiTile label="Maintainability" value={quality.avg_maintainability_rating != null ? ratingLetter(quality.avg_maintainability_rating) : 'N/A'} icon={Gauge} color={quality.avg_maintainability_rating != null ? ratingColor(quality.avg_maintainability_rating) : undefined} />
        <KpiTile label="Tech Debt Ratio" value={quality.avg_tech_debt_ratio != null ? `${fmt(quality.avg_tech_debt_ratio)}%` : 'N/A'} icon={Scale} />
        <KpiTile label="Total Tech Debt" value={quality.total_tech_debt_hours != null ? `${fmt(quality.total_tech_debt_hours, 0)}h` : 'N/A'} icon={Clock} />
        <KpiTile label="Merged PRs"      value={quality.total_merged_prs ?? 'N/A'} icon={GitPullRequest} />
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <TrendChart type="bar" title="Coverage by Repository (%)" data={coverageData} dataKeys={['Coverage']} height={280} />
        <TrendChart type="bar" title="Bugs & Code Smells per Repository" data={codeHealthData} dataKeys={['Bugs', 'Code Smells']} height={280} />
      </div>

      {/* Charts Row 2 — new */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {debtData.length > 0 && (
          <TrendChart type="bar" title="Tech Debt Ratio by Repository (%)" data={debtData} dataKeys={['Debt Ratio %']} height={280} />
        )}
        {coverageTrend.length > 0 ? (
          <TrendChart type="line" title="Coverage Trend" data={coverageTrend} dataKeys={['value']} xKey="name" height={280} />
        ) : debtData.length === 0 ? null : (
          <Card title="Coverage Trend">
            <p className="text-slate-500 text-sm py-8 text-center">No coverage trend data available</p>
          </Card>
        )}
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <DonutChart title="Language Distribution" data={langData} />

        {maintData.length > 0 && (
          <DonutChart title="Maintainability Rating Dist." data={maintData} />
        )}

        <Card title="Quality Details">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-slate-500 block">Avg Duplication %</span>
              <span className="text-slate-200">{pct(quality.avg_duplication_pct)}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Avg Cycle Time</span>
              <span className="text-slate-200">{fmt(quality.avg_pr_cycle_time_hours)} h</span>
            </div>
            <div>
              <span className="text-slate-500 block">Avg Review Time</span>
              <span className="text-slate-200">{fmt(quality.avg_review_time_hours)} h</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-slate-500">Quality Score</span>
              <InfoTooltip
                term="Quality Score"
                definition="Composite of PR cycle time, review time, coverage, tech debt, maintainability."
                formula="avg(cycle_inv, review_inv, cov_norm, debt_inv, ratio_inv, maint_inv)"
              />
              <span className="text-slate-200 ml-auto">{fmt(scores.quality, 0)}</span>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
