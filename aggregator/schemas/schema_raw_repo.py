"""
aggregator.schemas.schema_raw_repo
===================================
Pydantic models describing the per-repo raw JSON produced by collectors
and consumed by the aggregator.

Every section is Optional so the schema works even when a particular
collector was not run.  No fake defaults — missing data stays ``None``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# Type alias for fields that may hold their normal type OR the "N/R" sentinel
NRInt = Optional[Union[int, str]]       # int | "N/R" | None
NRFloat = Optional[Union[float, str]]   # float | "N/R" | None


# ── Repo metadata ─────────────────────────────────────────────


class RepoMetadata(BaseModel):
    repo: str = Field(..., description="Short repository name")
    full_name: str = Field(..., description="owner/repo")
    default_branch: Optional[str] = None
    language: Optional[str] = None
    languages: Optional[Dict[str, int]] = Field(None, description="Language → byte count map")
    visibility: Optional[str] = None
    archived: Optional[bool] = None
    topics: Optional[List[str]] = None
    updated_at: Optional[str] = None
    owner: Optional[str] = None


# ── Collection run metadata ──────────────────────────────────


class CollectionMeta(BaseModel):
    run_id: Optional[str] = None
    collected_at: str = Field(..., description="ISO-8601 UTC timestamp")
    lookback_days: int = Field(..., ge=1)
    collector_version: Optional[str] = None


# ── DORA metrics ─────────────────────────────────────────────


class DoraMetrics(BaseModel):
    deployment_frequency: Optional[float] = None
    lead_time_hours: Optional[float] = None
    lead_time_coding_hours: Optional[float] = None
    lead_time_review_hours: Optional[float] = None
    lead_time_deploy_hours: Optional[float] = None
    change_failure_rate: Optional[float] = None
    mttr_hours: Optional[float] = None
    build_repair_time_hours: Optional[float] = None
    total_deployments: Optional[int] = None
    total_failures: Optional[int] = None
    merged_prs: Optional[int] = None
    releases_per_month: Optional[float] = None
    # Trend history (last N periods)
    deployment_frequency_trend: Optional[List[Dict[str, Any]]] = None
    lead_time_trend: Optional[List[Dict[str, Any]]] = None
    cfr_trend: Optional[List[Dict[str, Any]]] = None


# ── Flow metrics ─────────────────────────────────────────────


class FlowMetrics(BaseModel):
    pr_review_time_hours: Optional[float] = None
    pr_cycle_time_hours: Optional[float] = None
    wip: Optional[int] = None
    throughput: Optional[int] = None
    review_sla_met_pct: Optional[float] = None
    review_sla_threshold_hours: Optional[float] = None


# ── Security metrics ─────────────────────────────────────────


class SecurityMetrics(BaseModel):
    critical: Optional[int] = None
    high: Optional[int] = None
    medium: Optional[int] = None
    low: Optional[int] = None
    secrets: Optional[int] = None
    dependency_alerts: Optional[int] = None
    code_scanning_alerts: Optional[int] = None
    security_mttr_hours: Optional[float] = None
    vulnerability_density: Optional[float] = None
    security_gate_pass: Optional[bool] = None
    security_gate_details: Optional[Dict[str, Any]] = None
    eol_components: Optional[int] = None
    eol_component_list: Optional[List[Dict[str, Any]]] = None


# ── Quality metrics ──────────────────────────────────────────


class QualityMetrics(BaseModel):
    bugs: Optional[int] = None
    code_smells: Optional[int] = None
    coverage_pct: Optional[float] = None
    duplication_pct: Optional[float] = None
    tech_debt_hours: Optional[float] = None
    tech_debt_ratio: Optional[float] = None
    reliability_rating: Optional[str] = None
    security_rating: Optional[str] = None
    maintainability_rating: Optional[str] = None
    ncloc: Optional[int] = None
    coverage_trend: Optional[List[Dict[str, Any]]] = None


# ── Governance flags ─────────────────────────────────────────


class GovernanceFlags(BaseModel):
    branch_protection_enabled: Optional[bool] = None
    dependabot_enabled: Optional[bool] = None
    code_scanning_enabled: Optional[bool] = None
    secret_scanning_enabled: Optional[bool] = None
    ci_enabled: Optional[bool] = None
    security_md_exists: Optional[bool] = None
    dependabot_config_exists: Optional[bool] = None
    # New governance metrics
    trunk_based_dev: Optional[bool] = None
    active_branch_count: Optional[int] = None
    long_lived_branch_count: Optional[int] = None
    pr_to_work_item_pct: Optional[float] = None
    iac_coverage_pct: Optional[float] = None
    iac_files_detected: Optional[List[str]] = None
    mandatory_checks_enforced: Optional[bool] = None
    required_status_checks: Optional[List[str]] = None
    docs_coverage: Optional[Dict[str, bool]] = None
    naming_standards_compliant: Optional[bool] = None


# ── Work Item Tracker (Jira/ADO) ─────────────────────────────


class WorkItemMetrics(BaseModel):
    total_items: NRInt = None
    completed_items: NRInt = None
    avg_cycle_time_hours: NRFloat = None
    avg_lead_time_hours: NRFloat = None
    items_by_type: Optional[Union[Dict[str, int], str]] = None
    items_by_status: Optional[Union[Dict[str, int], str]] = None
    linked_prs: NRInt = None
    unlinked_prs: NRInt = None


# ── Availability flags ───────────────────────────────────────


class AvailabilityFlags(BaseModel):
    pulls: Optional[bool] = None
    commits: Optional[bool] = None
    workflows: Optional[bool] = None
    branch_protection: Optional[bool] = None
    code_scanning: Optional[bool] = None
    dependabot: Optional[bool] = None
    secret_scanning: Optional[bool] = None
    sonar: Optional[bool] = None
    snyk: Optional[bool] = None
    servicenow: Optional[bool] = None
    logging: Optional[bool] = None
    work_items: Optional[bool] = None


# ── Source-specific raw sections ─────────────────────────────


class GitHubRaw(BaseModel):
    pr_count: Optional[int] = None
    commit_count: Optional[int] = None
    workflow_run_count: Optional[int] = None
    dependabot_alert_count: Optional[int] = None
    code_scanning_alert_count: Optional[int] = None
    secret_scanning_alert_count: Optional[int] = None
    branch_protection: Optional[Dict[str, Any]] = None
    ci_success_count: Optional[int] = None
    ci_failure_count: Optional[int] = None
    avg_run_duration_seconds: Optional[float] = None
    truncated: Optional[bool] = None
    errors: Optional[List[Dict[str, Any]]] = None
    active_branches: Optional[int] = None
    stale_branches: Optional[int] = None
    contributors: Optional[List[Dict[str, Any]]] = None
    pr_linked_issues: Optional[int] = None
    pr_unlinked: Optional[int] = None


class SonarRaw(BaseModel):
    project_key: Optional[str] = None
    measures: Optional[Dict[str, Any]] = None
    gate_status: Optional[str] = None


class SnykRaw(BaseModel):
    project_id: Optional[str] = None
    total_issues: Optional[int] = None
    severity: Optional[Dict[str, int]] = None
    project_type: Optional[str] = None
    eol_components: Optional[List[Dict[str, Any]]] = None


class ServiceNowRaw(BaseModel):
    total_changes: NRInt = None
    successful: NRInt = None
    failed: NRInt = None
    change_success_rate: NRFloat = None
    change_failure_rate: NRFloat = None


class LoggingRaw(BaseModel):
    total_logs: Optional[int] = None
    error_count: Optional[int] = None
    by_level: Optional[Dict[str, int]] = None
    errors_by_service: Optional[Dict[str, int]] = None


class WorkItemRaw(BaseModel):
    source: Optional[str] = None
    project_key: Optional[str] = None
    total_items: Optional[int] = None
    items: Optional[List[Dict[str, Any]]] = None


# ── Top-level raw repo payload ───────────────────────────────


class RawRepoPayload(BaseModel):
    """Schema for ``data/raw/{repo}.json``."""

    repo_metadata: RepoMetadata
    collection: CollectionMeta

    dora: Optional[DoraMetrics] = None
    flow: Optional[FlowMetrics] = None
    security: Optional[SecurityMetrics] = None
    quality: Optional[QualityMetrics] = None
    governance: Optional[GovernanceFlags] = None
    work_items: Optional[WorkItemMetrics] = None

    availability: Optional[AvailabilityFlags] = None

    github: Optional[GitHubRaw] = None
    sonar: Optional[SonarRaw] = None
    snyk: Optional[SnykRaw] = None
    servicenow: Optional[ServiceNowRaw] = None
    logging: Optional[LoggingRaw] = None
    work_item_raw: Optional[WorkItemRaw] = None

    class Config:
        extra = "allow"
