import React from 'react';
import { useDashboard } from '../context/DashboardContext';
import { LoadingState, ErrorState } from '../components/StatusStates';
import PageHeader from '../components/PageHeader';
import KpiTile from '../components/KpiTile';
import Card from '../components/Card';
import TrendChart from '../components/TrendChart';
import DonutChart from '../components/DonutChart';
import InfoTooltip from '../components/InfoTooltip';
import { fmt } from '../utils/format';
import {
  BarChart3,
  Clock,
  Code2,
  GitPullRequest,
  Rocket,
  ListTodo,
  CheckCircle,
  Timer,
} from 'lucide-react';

export default function ValueStream() {
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const metadata = data?.metadata || {};
  const vs       = data?.value_stream || {};
  const flow     = data?.flow || {};
  const dora     = data?.dora || {};

  const hasServiceNow = vs.avg_idea_to_prod_days != null || vs.avg_coding_time_hours != null;
  const hasWorkItems  = vs.total_work_items != null && vs.total_work_items > 0;

  /* Work item type distribution */
  const wiTypeData = vs.items_by_type
    ? Object.entries(vs.items_by_type).map(([name, value]) => ({ name, value }))
    : [];

  return (
    <>
      <PageHeader
        title="Value Stream"
        subtitle="End-to-end delivery flow — idea to production, work item tracking"
        lastUpdated={metadata.generated_at}
      />

      {/* Top KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiTile label="Idea → Prod"  value={fmt(vs.avg_idea_to_prod_days)} unit="days" icon={BarChart3} />
        <KpiTile label="Coding Time"  value={fmt(vs.avg_coding_time_hours ?? dora.lead_time_coding_hours)} unit="h" icon={Code2} />
        <KpiTile label="Review Time"  value={fmt(vs.avg_review_time_hours ?? flow.pr_review_time_hours)} unit="h" icon={GitPullRequest} />
        <KpiTile label="Deploy Time"  value={fmt(vs.avg_deploy_time_hours ?? dora.lead_time_deploy_hours)} unit="h" icon={Rocket} />
      </div>

      {/* Work Items KPIs */}
      {hasWorkItems && (
        <>
          <div className="flex items-center gap-1 mb-2">
            <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider">Work Items (Jira / ADO)</h3>
            <InfoTooltip term="Work Items" definition="Cycle time and lead time metrics from Jira or Azure DevOps work items." />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <KpiTile label="Total Items"   value={vs.total_work_items}                   icon={ListTodo} />
            <KpiTile label="Completed"     value={vs.completed_work_items}               icon={CheckCircle} />
            <KpiTile label="WI Cycle Time" value={fmt(vs.avg_work_item_cycle_time_hours)} unit="h" icon={Timer} />
            <KpiTile label="WI Lead Time"  value={fmt(vs.avg_work_item_lead_time_hours)}  unit="h" icon={Clock} />
          </div>
        </>
      )}

      {/* Flow breakdown & Value Stream details */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <Card title="Flow Breakdown">
          <div className="space-y-4 text-sm">
            <FlowRow label="PR Cycle Time" value={fmt(flow.pr_cycle_time_hours)} unit="h" />
            <FlowRow label="PR Review Time" value={fmt(flow.pr_review_time_hours)} unit="h" />
            <FlowRow label="Review SLA Met" value={flow.review_sla_met_pct != null ? `${flow.review_sla_met_pct.toFixed(1)}%` : 'N/A'} />
            <FlowRow label="WIP (open PRs)" value={flow.wip ?? 'N/A'} />
            <FlowRow label="Throughput" value={flow.throughput ?? 'N/A'} unit="PRs" />
            <FlowRow label="Deploy Frequency" value={fmt(dora.deployment_frequency)} unit="/day" />
            <FlowRow label="Lead Time" value={fmt(dora.lead_time_hours)} unit="h" />
          </div>
        </Card>

        {hasServiceNow ? (
          <Card title="ServiceNow Change Data">
            <div className="space-y-4 text-sm">
              <div className="flex items-center gap-1 mb-2">
                <span className="text-slate-400 text-xs uppercase tracking-wider">ServiceNow Integration</span>
                <InfoTooltip term="Value Stream" definition="Metrics from ServiceNow change requests — lifecycle from idea to production." />
              </div>
              <FlowRow label="Avg Idea → Prod" value={fmt(vs.avg_idea_to_prod_days)} unit="days" />
              <FlowRow label="Avg Coding Time" value={fmt(vs.avg_coding_time_hours)} unit="h" />
              <FlowRow label="Avg Review Time" value={fmt(vs.avg_review_time_hours)} unit="h" />
              <FlowRow label="Avg Deploy Time" value={fmt(vs.avg_deploy_time_hours)} unit="h" />
            </div>
          </Card>
        ) : (
          <Card title="Value Stream Details">
            <div className="flex flex-col items-center justify-center h-40 text-slate-500 text-sm">
              <Clock size={24} className="mb-2" />
              <p>ServiceNow integration not configured</p>
              <p className="text-xs mt-1 text-slate-600">Set SNOW_INSTANCE, SNOW_USER, SNOW_PASSWORD env vars</p>
            </div>
          </Card>
        )}
      </div>

      {/* Work item type distribution */}
      {wiTypeData.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <DonutChart title="Work Items by Type" data={wiTypeData} />
          <Card title="Work Item Summary">
            <div className="space-y-3 text-sm">
              <FlowRow label="Total Items" value={vs.total_work_items ?? 'N/A'} />
              <FlowRow label="Completed" value={vs.completed_work_items ?? 'N/A'} />
              <FlowRow label="Completion Rate" value={
                vs.total_work_items && vs.completed_work_items != null
                  ? `${((vs.completed_work_items / vs.total_work_items) * 100).toFixed(1)}%`
                  : 'N/A'
              } />
              <FlowRow label="Avg Cycle Time" value={fmt(vs.avg_work_item_cycle_time_hours)} unit="h" />
              <FlowRow label="Avg Lead Time" value={fmt(vs.avg_work_item_lead_time_hours)} unit="h" />
            </div>
          </Card>
        </div>
      )}

      {!hasServiceNow && !hasWorkItems && (
        <div className="flex flex-col items-center justify-center h-32 text-slate-500 text-sm">
          <ListTodo size={24} className="mb-2" />
          <p>No work item source configured</p>
          <p className="text-xs mt-1 text-slate-600">Set JIRA_URL or ADO_ORG env vars to enable work item tracking</p>
        </div>
      )}
    </>
  );
}

function FlowRow({ label, value, unit }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-surface-200/50 last:border-0">
      <span className="text-slate-400">{label}</span>
      <span className="text-slate-200 font-medium">
        {value}{value !== 'N/A' && unit ? <span className="text-slate-500 ml-1 text-xs">{unit}</span> : null}
      </span>
    </div>
  );
}
