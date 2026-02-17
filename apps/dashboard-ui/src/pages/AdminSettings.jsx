import React from 'react';
import { useDashboard } from '../context/DashboardContext';
import { LoadingState, ErrorState } from '../components/StatusStates';
import PageHeader from '../components/PageHeader';
import Card from '../components/Card';
import { Settings, Scale, AlertTriangle, Clock, Bell } from 'lucide-react';

export default function AdminSettings() {
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const cfg = data?.admin_config || {};
  const weights     = cfg.scoring_weights || {};
  const risk        = cfg.risk_thresholds || {};
  const sla         = cfg.sla_targets || {};
  const alerts      = cfg.alert_rules || [];
  const hierarchy   = cfg.org_hierarchy || {};

  return (
    <>
      <PageHeader
        title="Admin Settings"
        subtitle="View the current dashboard configuration (read-only). Update data/config/admin_config.json to change."
      />

      {/* Scoring Weights */}
      <Section title="Scoring Weights" icon={Scale}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <ConfigTile label="Delivery" value={`${(weights.delivery ?? 0) * 100}%`} />
          <ConfigTile label="Quality"  value={`${(weights.quality ?? 0) * 100}%`} />
          <ConfigTile label="Security" value={`${(weights.security ?? 0) * 100}%`} />
          <ConfigTile label="Governance" value={`${(weights.governance ?? 0) * 100}%`} />
        </div>
      </Section>

      {/* Risk Thresholds */}
      <Section title="Risk Thresholds" icon={AlertTriangle}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="text-slate-400 border-b border-surface-200">
                <th className="py-2 pr-4">Level</th>
                <th className="py-2 pr-4">Score Range</th>
                <th className="py-2">Extra Conditions</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(risk).map(([level, cfg_r]) => (
                <tr key={level} className="border-b border-surface-200/50">
                  <td className="py-2 pr-4">
                    <span className={`font-medium ${
                      level === 'critical' ? 'text-red-400' :
                      level === 'high' ? 'text-orange-400' :
                      level === 'medium' ? 'text-yellow-400' : 'text-green-400'
                    }`}>{level.charAt(0).toUpperCase() + level.slice(1)}</span>
                  </td>
                  <td className="py-2 pr-4 text-slate-300">
                    {cfg_r.min_score != null && `≥ ${cfg_r.min_score}`}
                    {cfg_r.min_score != null && cfg_r.max_score != null && ' – '}
                    {cfg_r.max_score != null && `< ${cfg_r.max_score}`}
                  </td>
                  <td className="py-2 text-slate-500 text-xs">
                    {cfg_r.conditions ? JSON.stringify(cfg_r.conditions) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* SLA Targets */}
      <Section title="SLA Targets" icon={Clock}>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <ConfigTile label="Review SLA"      value={`${sla.review_sla_hours ?? '?'}h`} />
          <ConfigTile label="Deploy Freq"     value={`${sla.deploy_frequency_per_day ?? '?'}/day`} />
          <ConfigTile label="Lead Time"       value={`${sla.lead_time_hours ?? '?'}h`} />
          <ConfigTile label="CFR Target"      value={`${sla.change_failure_rate_pct ?? '?'}%`} />
          <ConfigTile label="MTTR Target"     value={`${sla.mttr_hours ?? '?'}h`} />
          <ConfigTile label="Coverage Target" value={`${sla.coverage_pct ?? '?'}%`} />
        </div>
      </Section>

      {/* Alert Rules */}
      <Section title="Alert Rules" icon={Bell}>
        {alerts.length === 0 ? (
          <p className="text-slate-500 text-sm">No alert rules configured.</p>
        ) : (
          <div className="space-y-3">
            {alerts.map((rule, i) => (
              <div key={i} className="bg-surface-100 border border-surface-200 rounded-lg p-3 flex flex-col sm:flex-row sm:items-center gap-2">
                <span className={`text-xs font-medium uppercase px-2 py-0.5 rounded ${
                  rule.severity === 'critical' ? 'bg-red-500/20 text-red-400' :
                  rule.severity === 'high' ? 'bg-orange-500/20 text-orange-400' :
                  'bg-yellow-500/20 text-yellow-400'
                }`}>
                  {rule.severity || 'info'}
                </span>
                <span className="text-slate-300 text-sm flex-1">{rule.name || `Rule ${i + 1}`}</span>
                <span className="text-slate-500 text-xs font-mono">{rule.condition || '—'}</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Org Hierarchy */}
      {Object.keys(hierarchy).length > 0 && (
        <Section title="Organization Hierarchy" icon={Settings}>
          <pre className="text-xs text-slate-400 bg-surface-100 border border-surface-200 rounded-lg p-4 overflow-x-auto">
            {JSON.stringify(hierarchy, null, 2)}
          </pre>
        </Section>
      )}
    </>
  );
}

function Section({ title, icon: Icon, children }) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        {Icon && <Icon size={16} className="text-brand-400" />}
        <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
      </div>
      <Card>{children}</Card>
    </div>
  );
}

function ConfigTile({ label, value }) {
  return (
    <div className="bg-surface-100 border border-surface-200/50 rounded-lg p-3 text-center">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-lg font-bold text-slate-200">{value}</p>
    </div>
  );
}
