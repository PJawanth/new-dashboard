#!/usr/bin/env python3
"""
Scoring Engine (v2) — weighted composite scoring for the
Engineering Intelligence Dashboard.

Engineering Health Score
========================
    Delivery   25 %
    Quality    25 %
    Security   30 %
    Governance 20 %

All sub-scores are normalised to 0–100.  Every function treats
``None`` as "unknown / missing" and degrades gracefully rather than
crashing or silently converting to 0.

Depends on ``aggregator.normalize`` for null-safe math.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from aggregator.normalize import clamp, get, num

# ---------------------------------------------------------------------------
# Weights  (must sum to 1.0)
# ---------------------------------------------------------------------------

WEIGHTS: Dict[str, float] = {
    "delivery": 0.25,
    "quality": 0.25,
    "security": 0.30,
    "governance": 0.20,
}

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _inverse_norm(value: Optional[float], worst: float) -> Optional[float]:
    """Lower-is-better: 100 at 0, 0 at *worst*.  ``None`` → ``None``."""
    if value is None:
        return None
    if worst <= 0:
        return 100.0
    return clamp((1 - value / worst) * 100)


def _linear_norm(value: Optional[float], best: float) -> Optional[float]:
    """Higher-is-better: 0 at 0, 100 at *best*.  ``None`` → ``None``."""
    if value is None:
        return None
    if best <= 0:
        return 0.0
    return clamp(value / best * 100)


def _avg_scores(*scores: Optional[float]) -> Optional[float]:
    """Average of available (non-None) sub-scores, or ``None``."""
    present = [s for s in scores if s is not None]
    if not present:
        return None
    return clamp(sum(present) / len(present))


# ---------------------------------------------------------------------------
# Thresholds  (tuneable per organisation)
# ---------------------------------------------------------------------------

# DORA elite targets
DEPLOY_FREQ_ELITE = 1.0       # ≥ 1 deploy / day
LEAD_TIME_WORST = 720.0       # 30 days in hours
CFR_WORST = 0.50               # 50 %
MTTR_WORST = 168.0             # 1 week in hours

# Quality
CYCLE_TIME_WORST = 336.0      # 14 days in hours
REVIEW_TIME_WORST = 168.0     # 7 days in hours
COVERAGE_BEST = 80.0          # target coverage %
TECH_DEBT_HOURS_WORST = 500.0

# Security
CRIT_VULN_WORST = 20
HIGH_VULN_WORST = 50
SEC_MTTR_WORST = 720.0        # 30 days

# ---------------------------------------------------------------------------
# Sub-score computation
# ---------------------------------------------------------------------------


def compute_delivery_score(dora: Optional[Dict[str, Any]]) -> Optional[float]:
    """Score delivery performance from DORA metrics (0–100).

    Components (equal weight):
      • Deployment frequency  — linear, elite = 1/day
      • Lead time             — inverse, worst = 30 days
      • Change failure rate   — inverse, worst = 50 %
      • MTTR                  — inverse, worst = 7 days
    """
    if not dora:
        return None

    df = _linear_norm(num(dora.get("deployment_frequency")), DEPLOY_FREQ_ELITE)
    lt = _inverse_norm(num(dora.get("lead_time_hours")), LEAD_TIME_WORST)
    cfr = _inverse_norm(num(dora.get("change_failure_rate")), CFR_WORST)
    mttr = _inverse_norm(num(dora.get("mttr_hours")), MTTR_WORST)

    return _avg_scores(df, lt, cfr, mttr)


def compute_quality_score(
    quality: Optional[Dict[str, Any]],
    flow: Optional[Dict[str, Any]],
) -> Optional[float]:
    """Score quality from flow + SonarQube metrics.

    Components:
      • PR cycle time         — inverse, worst = 14 days
      • PR review time        — inverse, worst = 7 days
      • Coverage              — linear, best = 80 %
      • Tech debt hours       — inverse, worst = 500 h
      • Tech debt ratio %     — inverse, worst = 20 %
      • Maintainability (1–5) — inverse, worst = 5
    """
    ct = _inverse_norm(num(get(flow, "pr_cycle_time_hours")), CYCLE_TIME_WORST)
    rt = _inverse_norm(num(get(flow, "pr_review_time_hours")), REVIEW_TIME_WORST)
    cov = _linear_norm(num(get(quality, "coverage_pct") or get(quality, "avg_coverage_pct")), COVERAGE_BEST)
    td = _inverse_norm(num(get(quality, "tech_debt_hours") or get(quality, "total_tech_debt_hours")), TECH_DEBT_HOURS_WORST)

    # Tech debt ratio (lower is better, worst = 20%)
    td_ratio = _inverse_norm(num(get(quality, "avg_tech_debt_ratio")), 20.0)
    # Maintainability rating (1=A best, 5=E worst)
    maint = _inverse_norm(num(get(quality, "avg_maintainability_rating")), 5.0)

    return _avg_scores(ct, rt, cov, td, td_ratio, maint)


def compute_security_score(security: Optional[Dict[str, Any]]) -> Optional[float]:
    """Score security posture — penalise open critical / high vulns.

    Components (weighted):
      • Critical vulns 35 %   — inverse
      • High vulns     25 %   — inverse
      • Sec MTTR       20 %   — inverse
      • Vuln density   10 %   — inverse (worst = 10 vulns/KLOC)
      • EOL penalty    10 %   — inverse (worst = 10 components)
      • Secrets penalty : −20 pts if any secrets detected
    """
    if not security:
        return None

    crit = _inverse_norm(num(security.get("critical"), 0), CRIT_VULN_WORST)
    high = _inverse_norm(num(security.get("high"), 0), HIGH_VULN_WORST)
    mttr = _inverse_norm(num(security.get("security_mttr_hours"), 0), SEC_MTTR_WORST)
    vd = _inverse_norm(num(security.get("vulnerability_density"), 0), 10.0)
    eol = _inverse_norm(num(security.get("eol_components") or security.get("eol_component_count"), 0), 10.0)

    if crit is None and high is None and mttr is None:
        return None

    raw = (
        (crit or 100) * 0.35
        + (high or 100) * 0.25
        + (mttr or 100) * 0.20
        + (vd or 100) * 0.10
        + (eol or 100) * 0.10
    )

    secrets = num(security.get("secrets"), 0)
    if secrets and secrets > 0:
        raw -= 20

    return clamp(raw)


def compute_governance_score(governance: Optional[Dict[str, Any]]) -> Optional[float]:
    """Score governance adoption from coverage percentages.

    Averages all ``*_pct`` fields present in the dict, including
    new governance metrics (trunk-based dev, PR linkage, IaC, etc.).
    """
    if not governance:
        return None

    pct_keys = [
        # Original
        "branch_protection_pct",
        "dependabot_pct",
        "code_scanning_pct",
        "secret_scanning_pct",
        "ci_enabled_pct",
        "security_md_pct",
        "dependabot_config_pct",
        # New governance metrics
        "trunk_based_dev_pct",
        "pr_to_work_item_pct",
        "iac_coverage_pct",
        "mandatory_checks_pct",
        "docs_coverage_pct",
        "naming_standards_pct",
        "review_sla_met_pct",
    ]
    vals = [num(governance.get(k)) for k in pct_keys]
    return _avg_scores(*vals)


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------


def composite_health_score(
    delivery: Optional[float],
    quality: Optional[float],
    security: Optional[float],
    governance: Optional[float],
) -> Optional[float]:
    """Weighted Engineering Health Score (0–100).

    If a component is ``None`` its weight is redistributed
    proportionally among available components.
    """
    components = {
        "delivery": delivery,
        "quality": quality,
        "security": security,
        "governance": governance,
    }
    present = {k: v for k, v in components.items() if v is not None}
    if not present:
        return None

    total_weight = sum(WEIGHTS[k] for k in present)
    if total_weight == 0:
        return None

    weighted = sum(v * (WEIGHTS[k] / total_weight) for k, v in present.items())
    return clamp(weighted)


# ---------------------------------------------------------------------------
# Per-repo convenience scores
# ---------------------------------------------------------------------------


def repo_health_score(repo: Dict[str, Any]) -> Optional[float]:
    """Compute a lightweight health score for a single repo dict."""
    d = compute_delivery_score(repo.get("dora"))
    q = compute_quality_score(repo.get("quality"), repo.get("flow"))
    s = compute_security_score(repo.get("security"))

    gov_raw = repo.get("governance") or {}
    gov_pct: Dict[str, Any] = {}
    for key, flag in [
        ("branch_protection_pct", "branch_protection_enabled"),
        ("dependabot_pct", "dependabot_enabled"),
        ("code_scanning_pct", "code_scanning_enabled"),
        ("secret_scanning_pct", "secret_scanning_enabled"),
        ("ci_enabled_pct", "ci_enabled"),
        ("security_md_pct", "security_md_exists"),
        ("dependabot_config_pct", "dependabot_config_exists"),
        ("trunk_based_dev_pct", "trunk_based_dev"),
        ("mandatory_checks_pct", "mandatory_checks_enforced"),
        ("naming_standards_pct", "naming_standards_compliant"),
    ]:
        val = gov_raw.get(flag)
        if val is not None:
            gov_pct[key] = 100.0 if val else 0.0
    # Pass numeric pcts through directly
    for key in ["pr_to_work_item_pct", "iac_coverage_pct"]:
        val = gov_raw.get(key)
        if val is not None:
            gov_pct[key] = val
    # Docs coverage
    docs = gov_raw.get("docs_coverage")
    if docs and isinstance(docs, dict):
        total = len(docs)
        present = sum(1 for v in docs.values() if v)
        gov_pct["docs_coverage_pct"] = present / total * 100 if total else 0.0
    # Review SLA from flow
    flow_raw = repo.get("flow") or {}
    sla = flow_raw.get("review_sla_met_pct")
    if sla is not None:
        gov_pct["review_sla_met_pct"] = sla

    g = compute_governance_score(gov_pct) if gov_pct else None
    return composite_health_score(d, q, s, g)


def repo_security_score(repo: Dict[str, Any]) -> Optional[float]:
    """Standalone security score for a repo."""
    return compute_security_score(repo.get("security"))


def risk_level(repo: Dict[str, Any]) -> str:
    """Classify repo risk as Critical / High / Medium / Low."""
    sec = repo.get("security") or {}
    crits = num(sec.get("critical"), 0) or 0
    highs = num(sec.get("high"), 0) or 0
    secrets = num(sec.get("secrets"), 0) or 0

    if crits >= 5 or secrets >= 3:
        return "Critical"
    if crits >= 1 or highs >= 5:
        return "High"
    if highs >= 1:
        return "Medium"
    return "Low"
