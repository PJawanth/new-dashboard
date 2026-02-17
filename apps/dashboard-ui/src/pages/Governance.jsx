import React from 'react';
import { useDashboard } from '../context/DashboardContext';
import { LoadingState, ErrorState } from '../components/StatusStates';
import PageHeader from '../components/PageHeader';
import KpiTile from '../components/KpiTile';
import TrendChart from '../components/TrendChart';
import Card from '../components/Card';
import { pct, fmt, deepGet } from '../utils/format';
import {
  ShieldCheck,
  PackageCheck,
  ScanSearch,
  KeyRound,
  GitBranch,
  CheckCircle,
  Link2,
  FileCode2,
  FileCheck,
  BookOpen,
  Tag,
  Timer,
} from 'lucide-react';

export default function Governance() {
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const metadata   = data?.metadata || {};
  const governance = data?.governance || {};
  const scores     = data?.scores || {};
  const repos      = data?.repos || [];

  /* Original adoption chart data */
  const adoptionData = [
    { name: 'Branch Protect',  value: governance.branch_protection_pct },
    { name: 'Dependabot',      value: governance.dependabot_pct },
    { name: 'Code Scanning',   value: governance.code_scanning_pct },
    { name: 'Secret Scanning', value: governance.secret_scanning_pct },
    { name: 'CI Enabled',      value: governance.ci_enabled_pct },
    { name: 'Security.md',     value: governance.security_md_pct },
    { name: 'Dependabot Cfg',  value: governance.dependabot_config_pct },
  ].filter((d) => d.value != null);

  /* New governance metrics chart data */
  const newGovData = [
    { name: 'Trunk Based',      value: governance.trunk_based_dev_pct },
    { name: 'PR→Work Item',     value: governance.pr_to_work_item_pct },
    { name: 'IaC Coverage',     value: governance.iac_coverage_pct },
    { name: 'Mandatory Checks', value: governance.mandatory_checks_pct },
    { name: 'Docs Coverage',    value: governance.docs_coverage_pct },
    { name: 'Naming Standards', value: governance.naming_standards_pct },
    { name: 'Review SLA',       value: governance.review_sla_met_pct },
  ].filter((d) => d.value != null);

  /* Extended governance table columns */
  const govColumns = [
    { key: 'name', label: 'Repository' },
    { key: 'governance.branch_protection_enabled', label: 'Branch Prot.', format: 'bool' },
    { key: 'governance.dependabot_enabled', label: 'Dependabot', format: 'bool' },
    { key: 'governance.code_scanning_enabled', label: 'Code Scan', format: 'bool' },
    { key: 'governance.secret_scanning_enabled', label: 'Secret Scan', format: 'bool' },
    { key: 'governance.ci_enabled', label: 'CI', format: 'bool' },
    { key: 'governance.trunk_based_dev', label: 'Trunk Dev', format: 'bool' },
    { key: 'governance.mandatory_checks_enforced', label: 'Checks', format: 'bool' },
    { key: 'governance.naming_standards_compliant', label: 'Naming', format: 'bool' },
    { key: 'governance.iac_coverage_pct', label: 'IaC %', format: 'pct' },
    { key: 'governance.pr_to_work_item_pct', label: 'PR Link %', format: 'pct' },
  ];

  return (
    <>
      <PageHeader
        title="Governance & Audit"
        subtitle="Policy enforcement, tooling adoption, and compliance metrics"
        lastUpdated={metadata.generated_at}
      />

      {/* Original KPI tiles */}
      <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Security Tooling Adoption</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-4 mb-6">
        <KpiTile label="Branch Protect"  value={pct(governance.branch_protection_pct)} icon={GitBranch} />
        <KpiTile label="Dependabot"      value={pct(governance.dependabot_pct)}        icon={PackageCheck} />
        <KpiTile label="Code Scanning"   value={pct(governance.code_scanning_pct)}     icon={ScanSearch} />
        <KpiTile label="Secret Scanning" value={pct(governance.secret_scanning_pct)}   icon={KeyRound} />
        <KpiTile label="CI Enabled"      value={pct(governance.ci_enabled_pct)}        icon={CheckCircle} />
        <KpiTile label="Security.md"     value={pct(governance.security_md_pct)}       icon={ShieldCheck} />
        <KpiTile label="Gov Score"       value={fmt(scores.governance, 0)}             icon={ShieldCheck} color="text-brand-400" />
      </div>

      {/* New governance KPI tiles */}
      <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Engineering Standards</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-4 mb-6">
        <KpiTile label="Trunk Based Dev" value={pct(governance.trunk_based_dev_pct)}    icon={GitBranch} />
        <KpiTile label="PR → Work Item"  value={pct(governance.pr_to_work_item_pct)}    icon={Link2} />
        <KpiTile label="IaC Coverage"    value={pct(governance.iac_coverage_pct)}        icon={FileCode2} />
        <KpiTile label="Mandatory Checks" value={pct(governance.mandatory_checks_pct)}   icon={FileCheck} />
        <KpiTile label="Docs Coverage"   value={pct(governance.docs_coverage_pct)}       icon={BookOpen} />
        <KpiTile label="Naming Std"      value={pct(governance.naming_standards_pct)}    icon={Tag} />
        <KpiTile label="Review SLA"      value={pct(governance.review_sla_met_pct)}      icon={Timer} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <TrendChart type="bar" title="Security Tooling Adoption (%)" data={adoptionData} dataKeys={['value']} xKey="name" />
        {newGovData.length > 0 ? (
          <TrendChart type="bar" title="Engineering Standards (%)" data={newGovData} dataKeys={['value']} xKey="name" />
        ) : (
          <Card title="Scan Metadata">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-slate-500 block">Scan Date</span>
                <span>{metadata.generated_at ? new Date(metadata.generated_at).toLocaleDateString() : 'N/A'}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Coverage</span>
                <span>{pct(metadata.scan_coverage_percent)}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Total Repos</span>
                <span>{metadata.total_repos ?? 'N/A'}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Exclusions</span>
                <span>{metadata.total_repos != null && metadata.scanned_repos != null ? metadata.total_repos - metadata.scanned_repos : 'N/A'}</span>
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* Per-repo governance table */}
      <h3 className="text-sm font-medium text-slate-300 mb-2">Repository Governance Status</h3>
      <div className="bg-surface-100 border border-surface-200 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left" role="table">
            <thead>
              <tr className="border-b border-surface-200">
                {govColumns.map((col) => (
                  <th key={col.key} className="px-3 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider whitespace-nowrap">
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {repos.map((repo) => (
                <tr key={repo.name} className="border-b border-surface-200/50 hover:bg-surface-200/30 transition">
                  {govColumns.map((col) => {
                    const val = deepGet(repo, col.key);
                    return (
                      <td key={col.key} className="px-3 py-3 whitespace-nowrap">
                        {col.format === 'bool'
                          ? val == null
                            ? <span className="text-slate-500">N/A</span>
                            : val
                              ? <span className="text-green-400">✓</span>
                              : <span className="text-red-400">✗</span>
                          : col.format === 'pct'
                            ? val != null ? `${val.toFixed(0)}%` : 'N/A'
                            : val ?? 'N/A'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
