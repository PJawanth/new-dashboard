import React from 'react';
import { useDashboard } from '../context/DashboardContext';
import { LoadingState, ErrorState } from '../components/StatusStates';
import PageHeader from '../components/PageHeader';
import RepoTable from '../components/RepoTable';

const COLUMNS = [
  { key: 'name', label: 'Repository' },
  { key: 'risk_level', label: 'Risk Level' },
  { key: 'health_score', label: 'Health Score', format: 'score' },
  { key: 'security_score', label: 'Security Score', format: 'score' },
  { key: 'security.critical', label: 'Critical Vulns', format: 'number' },
  { key: 'governance.ci_enabled', label: 'CI', format: 'bool' },
  { key: 'governance.branch_protection_enabled', label: 'Branch Protect', format: 'bool' },
  { key: 'language', label: 'Language' },
];

export default function Repos() {
  const { data, loading, error } = useDashboard();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const repos = data?.repos || [];
  const metadata = data?.metadata || {};

  return (
    <>
      <PageHeader
        title="Repositories"
        subtitle={`${repos.length} repositories tracked`}
        lastUpdated={metadata.generated_at}
      />
      <RepoTable repos={repos} columns={COLUMNS} />
    </>
  );
}
