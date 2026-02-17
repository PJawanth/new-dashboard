"""
aggregator.schemas.schema_dashboard
====================================
Pydantic models describing the aggregated ``data/aggregated/dashboard.json``
consumed by the React frontend.

All sections use ``Optional`` where data may be unavailable.
No fake defaults.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Metadata ──────────────────────────────────────────────────


class DashboardMetadata(BaseModel):
    generated_at: str = Field(..., description="ISO-8601 UTC timestamp")
    lookback_days: int
    total_repos: int
    scanned_repos: int
    scan_coverage_percent: float
    org: Optional[str] = None
    collector_version: Optional[str] = None


# ── DORA ──────────────────────────────────────────────────────


class DoraSummary(BaseModel):
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
    deployment_frequency_trend: Optional[List[Dict[str, Any]]] = None
    lead_time_trend: Optional[List[Dict[str, Any]]] = None
    cfr_trend: Optional[List[Dict[str, Any]]] = None


# ── Flow ──────────────────────────────────────────────────────


class FlowSummary(BaseModel):
    pr_review_time_hours: Optional[float] = None
    pr_cycle_time_hours: Optional[float] = None
    wip: Optional[int] = None
    throughput: Optional[int] = None
    review_sla_met_pct: Optional[float] = None
    review_sla_threshold_hours: Optional[float] = None


# ── Security ──────────────────────────────────────────────────


class SecuritySummary(BaseModel):
    critical: Optional[int] = None
    high: Optional[int] = None
    medium: Optional[int] = None
    low: Optional[int] = None
    secrets: Optional[int] = None
    dependency_alerts: Optional[int] = None
    code_scanning_alerts: Optional[int] = None
    security_mttr_hours: Optional[float] = None
    vulnerability_density: Optional[float] = None
    security_gate_pass_pct: Optional[float] = None
    eol_component_count: Optional[int] = None


# ── Quality ───────────────────────────────────────────────────


class QualitySummary(BaseModel):
    avg_pr_cycle_time_hours: Optional[float] = None
    avg_review_time_hours: Optional[float] = None
    total_merged_prs: Optional[int] = None
    total_tech_debt_hours: Optional[float] = None
    avg_tech_debt_ratio: Optional[float] = None
    avg_coverage_pct: Optional[float] = None
    avg_duplication_pct: Optional[float] = None
    total_bugs: Optional[int] = None
    total_code_smells: Optional[int] = None
    avg_maintainability_rating: Optional[float] = None
    rating_distribution: Optional[Dict[str, Dict[str, int]]] = None
    coverage_trend: Optional[List[Dict[str, Any]]] = None


# ── Value Stream ──────────────────────────────────────────────


class ValueStreamSummary(BaseModel):
    avg_idea_to_prod_days: Optional[float] = None
    avg_coding_time_hours: Optional[float] = None
    avg_review_time_hours: Optional[float] = None
    avg_deploy_time_hours: Optional[float] = None
    avg_work_item_cycle_time_hours: Optional[float] = None
    avg_work_item_lead_time_hours: Optional[float] = None
    total_work_items: Optional[int] = None
    completed_work_items: Optional[int] = None
    items_by_type: Optional[Dict[str, int]] = None


# ── Governance ────────────────────────────────────────────────


class GovernanceSummary(BaseModel):
    branch_protection_pct: Optional[float] = None
    dependabot_pct: Optional[float] = None
    code_scanning_pct: Optional[float] = None
    secret_scanning_pct: Optional[float] = None
    ci_enabled_pct: Optional[float] = None
    security_md_pct: Optional[float] = None
    dependabot_config_pct: Optional[float] = None
    # New governance org-level metrics
    trunk_based_dev_pct: Optional[float] = None
    pr_to_work_item_pct: Optional[float] = None
    iac_coverage_pct: Optional[float] = None
    mandatory_checks_pct: Optional[float] = None
    docs_coverage_pct: Optional[float] = None
    naming_standards_pct: Optional[float] = None
    review_sla_met_pct: Optional[float] = None


# ── Logging ───────────────────────────────────────────────────


class LoggingSummary(BaseModel):
    total_logs: Optional[int] = None
    total_errors: Optional[int] = None
    error_rate_pct: Optional[float] = None
    top_error_services: Optional[List[Dict[str, Any]]] = None


# ── Admin Config ──────────────────────────────────────────────


class AdminConfig(BaseModel):
    """Runtime admin configuration — scoring weights, thresholds, SLAs."""
    scoring_weights: Optional[Dict[str, float]] = None
    risk_thresholds: Optional[Dict[str, Any]] = None
    sla_targets: Optional[Dict[str, Any]] = None
    alert_rules: Optional[List[Dict[str, Any]]] = None
    org_hierarchy: Optional[Dict[str, Any]] = None


# ── Scores ────────────────────────────────────────────────────


class ScoresSummary(BaseModel):
    engineering_health: Optional[float] = None
    delivery: Optional[float] = None
    quality: Optional[float] = None
    security: Optional[float] = None
    governance: Optional[float] = None


# ── Per-repo summary row ─────────────────────────────────────


class RepoGovernanceRow(BaseModel):
    branch_protection_enabled: Optional[bool] = None
    dependabot_enabled: Optional[bool] = None
    code_scanning_enabled: Optional[bool] = None
    secret_scanning_enabled: Optional[bool] = None
    ci_enabled: Optional[bool] = None
    security_md_exists: Optional[bool] = None
    dependabot_config_exists: Optional[bool] = None
    trunk_based_dev: Optional[bool] = None
    pr_to_work_item_pct: Optional[float] = None
    iac_coverage_pct: Optional[float] = None
    mandatory_checks_enforced: Optional[bool] = None
    docs_coverage: Optional[Dict[str, bool]] = None
    naming_standards_compliant: Optional[bool] = None


class RepoSecurityRow(BaseModel):
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
    eol_components: Optional[int] = None


class RepoQualityRow(BaseModel):
    bugs: Optional[int] = None
    code_smells: Optional[int] = None
    coverage_pct: Optional[float] = None
    duplication_pct: Optional[float] = None
    tech_debt_hours: Optional[float] = None
    tech_debt_ratio: Optional[float] = None
    reliability_rating: Optional[str] = None
    security_rating: Optional[str] = None
    maintainability_rating: Optional[str] = None


class RepoRow(BaseModel):
    name: str
    full_name: Optional[str] = None
    language: Optional[str] = None
    languages: Optional[Dict[str, int]] = None
    visibility: Optional[str] = None
    default_branch: Optional[str] = None
    owner: Optional[str] = None

    risk_level: Optional[str] = None
    health_score: Optional[float] = None
    security_score: Optional[float] = None

    dora: Optional[DoraSummary] = None
    flow: Optional[FlowSummary] = None
    security: Optional[RepoSecurityRow] = None
    governance: Optional[RepoGovernanceRow] = None
    quality: Optional[RepoQualityRow] = None
    work_items: Optional[Dict[str, Any]] = None


# ── Contributors ──────────────────────────────────────────────


class ContributorSummary(BaseModel):
    total_contributors: Optional[int] = None
    top_contributors: Optional[List[Dict[str, Any]]] = None


# ── Languages ─────────────────────────────────────────────────


class LanguageSummary(BaseModel):
    total_languages: Optional[int] = None
    breakdown: Optional[Dict[str, int]] = None


# ── Top-level dashboard payload ──────────────────────────────


class DashboardPayload(BaseModel):
    """Schema for ``data/aggregated/dashboard.json``."""

    metadata: DashboardMetadata
    dora: Optional[DoraSummary] = None
    flow: Optional[FlowSummary] = None
    security: Optional[SecuritySummary] = None
    quality: Optional[QualitySummary] = None
    value_stream: Optional[ValueStreamSummary] = None
    governance: Optional[GovernanceSummary] = None
    logging: Optional[LoggingSummary] = None
    scores: Optional[ScoresSummary] = None
    repos: List[RepoRow] = Field(default_factory=list)
    contributors: Optional[ContributorSummary] = None
    languages: Optional[LanguageSummary] = None
    admin_config: Optional[AdminConfig] = None

    class Config:
        extra = "allow"
