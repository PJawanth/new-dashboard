import React from 'react';
import { useDashboard } from '../context/DashboardContext';
import { LoadingState, ErrorState } from '../components/StatusStates';
import PageHeader from '../components/PageHeader';
import KpiTile from '../components/KpiTile';
import TrendChart from '../components/TrendChart';
import Card from '../components/Card';
import { fmt, pct } from '../utils/format';
import {
  FileText,
  AlertCircle,
  CheckCircle,
  BarChart3,
} from 'lucide-react';

export default function LoggingMonitor() {
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const metadata = data?.metadata || {};
  const logging  = data?.logging || {};
  const repos    = data?.repos || [];

  const hasData = logging.total_logs != null;

  /* per-repo logging data from repo rows */
  const loggingPerRepo = repos
    .filter((r) => r.dora?.total_deployments != null)
    .map((r) => ({
      name: (r.name || '').substring(0, 16),
      Runs: r.dora?.total_deployments ?? 0,
      Failures: r.dora?.total_failures ?? 0,
    }));

  return (
    <>
      <PageHeader
        title="Logging Monitor"
        subtitle="GitHub Actions workflow execution and error tracking"
        lastUpdated={metadata.generated_at}
      />

      {hasData ? (
        <>
          {/* KPI Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <KpiTile label="Total Runs"  value={logging.total_logs}                       icon={FileText} />
            <KpiTile label="Total Errors" value={logging.total_errors}                     icon={AlertCircle} color={(logging.total_errors ?? 0) > 0 ? 'text-red-400' : 'text-green-400'} />
            <KpiTile label="Error Rate"   value={pct(logging.error_rate_pct)}               icon={BarChart3} color={(logging.error_rate_pct ?? 0) > 10 ? 'text-orange-400' : 'text-green-400'} />
            <KpiTile label="Success Rate" value={logging.error_rate_pct != null ? pct(100 - logging.error_rate_pct) : 'N/A'} icon={CheckCircle} />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <TrendChart
              type="bar"
              title="Runs & Failures per Repository"
              data={loggingPerRepo}
              dataKeys={['Runs', 'Failures']}
              height={280}
            />

            <Card title="Logging Summary">
              <div className="space-y-3 text-sm">
                <Row label="Total Workflow Runs" value={logging.total_logs ?? 'N/A'} />
                <Row label="Total Failures" value={logging.total_errors ?? 'N/A'} />
                <Row label="Error Rate" value={pct(logging.error_rate_pct)} />
                <Row label="Top Failing Services" value={
                  logging.top_error_services && logging.top_error_services.length > 0
                    ? logging.top_error_services.map((s) => s.name || s.workflow).join(', ')
                    : 'N/A'
                } />
              </div>
            </Card>
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center justify-center h-64 text-slate-500">
          <FileText size={32} className="mb-3" />
          <p className="text-sm font-medium">No logging data available</p>
          <p className="text-xs mt-1 text-slate-600">Run <code className="bg-surface-200 px-1 rounded">make collect-logs</code> to collect GitHub Actions metrics</p>
        </div>
      )}
    </>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-surface-200/50 last:border-0">
      <span className="text-slate-400">{label}</span>
      <span className="text-slate-200 font-medium">{value}</span>
    </div>
  );
}
