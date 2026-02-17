import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useDashboard } from '../context/DashboardContext';
import { LoadingState, ErrorState } from '../components/StatusStates';
import PageHeader from '../components/PageHeader';
import KpiTile from '../components/KpiTile';
import DonutChart from '../components/DonutChart';
import Badge from '../components/Badge';
import Card from '../components/Card';
import { fmt, cfrPct, pct, scoreColor, riskBg, ratingLetter, ratingColor } from '../utils/format';
import { ArrowLeft } from 'lucide-react';

export default function RepoDetail() {
  const { name } = useParams();
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const repos = data?.repos || [];
  const repo = repos.find((r) => r.name === name);

  if (!repo) {
    return (
      <div className="text-center py-20">
        <p className="text-slate-400">Repository &quot;{name}&quot; not found.</p>
        <Link to="/repos" className="text-brand-400 text-sm hover:underline mt-2 inline-block">
          ← Back to Repositories
        </Link>
      </div>
    );
  }

  const doraData   = repo.dora || {};
  const flow       = repo.flow || {};
  const security   = repo.security || {};
  const governance = repo.governance || {};
  const quality    = repo.quality || {};
  const workItems  = repo.work_items || {};

  const sevData = [
    { name: 'Critical', value: security.critical },
    { name: 'High',     value: security.high },
    { name: 'Medium',   value: security.medium },
    { name: 'Low',      value: security.low },
  ];

  /* Original + new governance checks */
  const govChecks = [
    { label: 'Branch Protection',    ok: governance.branch_protection_enabled },
    { label: 'Dependabot',           ok: governance.dependabot_enabled },
    { label: 'Code Scanning',        ok: governance.code_scanning_enabled },
    { label: 'Secret Scanning',      ok: governance.secret_scanning_enabled },
    { label: 'CI Enabled',           ok: governance.ci_enabled },
    { label: 'SECURITY.md',          ok: governance.security_md_exists },
    { label: 'Dependabot Config',    ok: governance.dependabot_config_exists },
    { label: 'Trunk-Based Dev',      ok: governance.trunk_based_dev },
    { label: 'Mandatory Checks',     ok: governance.mandatory_checks_enforced },
    { label: 'Naming Standards',     ok: governance.naming_standards_compliant },
  ];

  /* Docs coverage breakdown */
  const docsMap = governance.docs_coverage || {};
  const docsEntries = Object.entries(docsMap);

  return (
    <>
      <Link to="/repos" className="inline-flex items-center gap-1.5 text-sm text-brand-400 hover:underline mb-4">
        <ArrowLeft size={14} /> Back to Repositories
      </Link>

      <PageHeader
        title={repo.name}
        subtitle={`${repo.full_name || ''} · ${repo.language || 'N/A'} · ${repo.visibility || 'private'}`}
      />

      {/* Risk + scores banner */}
      <div className="flex flex-wrap items-center gap-4 mb-6">
        <Badge label={`${repo.risk_level || 'N/A'} Risk`} risk={repo.risk_level} />
        <span className={`text-lg font-bold ${scoreColor(repo.health_score)}`}>
          Health {fmt(repo.health_score, 0)}
        </span>
        <span className={`text-lg font-bold ${scoreColor(repo.security_score)}`}>
          Security {fmt(repo.security_score, 0)}
        </span>
      </div>

      {/* DORA tiles */}
      <h3 className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">DORA</h3>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
        <KpiTile label="Deploy Freq"   value={fmt(doraData.deployment_frequency)} unit="/day" />
        <KpiTile label="Lead Time"     value={fmt(doraData.lead_time_hours)}      unit="h" />
        <KpiTile label="CFR"           value={cfrPct(doraData.change_failure_rate)} />
        <KpiTile label="MTTR"          value={fmt(doraData.mttr_hours)}           unit="h" />
        <KpiTile label="Build Repair"  value={fmt(doraData.build_repair_time_hours)} unit="h" />
      </div>

      {/* Lead time breakdown */}
      {(doraData.lead_time_coding_hours != null || doraData.lead_time_review_hours != null) && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <KpiTile label="Code" value={fmt(doraData.lead_time_coding_hours)} unit="h" />
          <KpiTile label="Review" value={fmt(doraData.lead_time_review_hours)} unit="h" />
          <KpiTile label="Deploy" value={fmt(doraData.lead_time_deploy_hours)} unit="h" />
        </div>
      )}

      {/* Flow tiles */}
      <h3 className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">Flow</h3>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <KpiTile label="PR Review Time" value={fmt(flow.pr_review_time_hours)} unit="h" />
        <KpiTile label="PR Cycle Time"  value={fmt(flow.pr_cycle_time_hours)}  unit="h" />
        <KpiTile label="WIP"            value={flow.wip ?? 'N/A'} />
        <KpiTile label="Throughput"     value={flow.throughput ?? 'N/A'} unit="PRs" />
        <KpiTile label="Review SLA"     value={pct(flow.review_sla_met_pct)} />
      </div>

      {/* Quality Section */}
      {(quality.coverage_pct != null || quality.bugs != null || quality.maintainability_rating != null) && (
        <>
          <h3 className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">Quality (SonarQube)</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4 mb-6">
            <KpiTile label="Coverage"       value={quality.coverage_pct != null ? `${quality.coverage_pct}%` : 'N/A'} />
            <KpiTile label="Bugs"           value={quality.bugs ?? 'N/A'} />
            <KpiTile label="Code Smells"    value={quality.code_smells ?? 'N/A'} />
            <KpiTile label="Duplication"    value={quality.duplication_pct != null ? `${quality.duplication_pct}%` : 'N/A'} />
            <KpiTile label="Maintainability" value={quality.maintainability_rating ? ratingLetter(quality.maintainability_rating) : 'N/A'} />
            <KpiTile label="Tech Debt Ratio" value={quality.tech_debt_ratio != null ? `${quality.tech_debt_ratio}%` : 'N/A'} />
            <KpiTile label="KLOC"           value={quality.ncloc != null ? Math.round(quality.ncloc / 1000) : 'N/A'} unit="K" />
          </div>
        </>
      )}

      {/* Security + Governance */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div>
          <h3 className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">Security</h3>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <KpiTile label="Vuln Density" value={fmt(security.vulnerability_density)} unit="/KLOC" />
            <KpiTile label="Gate Pass" value={security.security_gate_pass === true ? '✓' : security.security_gate_pass === false ? '✗' : 'N/A'} />
            <KpiTile label="EOL Pkgs"  value={security.eol_components ?? 0} />
            <KpiTile label="Sec MTTR"  value={fmt(security.security_mttr_hours)} unit="h" />
          </div>
          <DonutChart title="Vulnerability Breakdown" data={sevData} height={220} />
        </div>

        <div>
          <h3 className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">Governance</h3>
          <Card>
            <ul className="space-y-2 text-sm" role="list">
              {govChecks.map((c) => (
                <li key={c.label} className="flex items-center justify-between">
                  <span className="text-slate-300">{c.label}</span>
                  {c.ok == null ? (
                    <span className="text-slate-500 text-xs">N/A</span>
                  ) : c.ok ? (
                    <span className="text-green-400 font-medium">Enabled</span>
                  ) : (
                    <span className="text-red-400 font-medium">Disabled</span>
                  )}
                </li>
              ))}
            </ul>
          </Card>

          {/* Governance numeric metrics */}
          <div className="mt-4 bg-surface-100 border border-surface-200 rounded-xl p-4">
            <h4 className="text-xs font-medium text-slate-400 mb-3 uppercase">Compliance Metrics</h4>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <MetricRow label="PR → Work Item" value={governance.pr_to_work_item_pct != null ? `${governance.pr_to_work_item_pct.toFixed(0)}%` : 'N/A'} />
              <MetricRow label="IaC Coverage" value={governance.iac_coverage_pct != null ? `${governance.iac_coverage_pct.toFixed(0)}%` : 'N/A'} />
            </div>
            {docsEntries.length > 0 && (
              <div className="mt-3 pt-3 border-t border-surface-200/50">
                <h5 className="text-xs text-slate-500 mb-2">Documentation</h5>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {docsEntries.map(([doc, exists]) => (
                    <div key={doc} className="flex items-center gap-2">
                      {exists ? (
                        <span className="text-green-400">✓</span>
                      ) : (
                        <span className="text-red-400">✗</span>
                      )}
                      <span className="text-slate-300">{doc}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Work Items section */}
      {workItems.total_items != null && workItems.total_items > 0 && (
        <>
          <h3 className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">Work Items</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <KpiTile label="Total Items"    value={workItems.total_items} />
            <KpiTile label="Completed"      value={workItems.completed_items} />
            <KpiTile label="Cycle Time"     value={fmt(workItems.avg_cycle_time_hours)} unit="h" />
            <KpiTile label="Lead Time"      value={fmt(workItems.avg_lead_time_hours)} unit="h" />
          </div>
        </>
      )}
    </>
  );
}

function MetricRow({ label, value }) {
  return (
    <div>
      <span className="text-slate-500 block text-xs">{label}</span>
      <span className="text-slate-200">{value}</span>
    </div>
  );
}
