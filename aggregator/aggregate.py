#!/usr/bin/env python3
"""
Aggregator (v3)
================
Loads ``data/raw/*.json``, validates each file with Pydantic schemas,
merges all collector sections, and produces:

    • ``data/aggregated/dashboard.json``       — consumed by the React UI
    • ``data/history/YYYY-MM-DD/dashboard.json`` — daily snapshot

Sections produced
-----------------
metadata, dora, flow, security, quality, value_stream, governance,
logging, scores, repos, contributors, languages, admin_config.

``None`` is **never** silently converted to ``0`` — only explicit
intent (e.g. ``safe_sum``) aggregates across non-None values.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from aggregator.normalize import (
    bool_pct,
    collect_values,
    get,
    num,
    percent,
    safe_avg,
    safe_sum,
)
from aggregator.scoring import (
    composite_health_score,
    compute_delivery_score,
    compute_governance_score,
    compute_quality_score,
    compute_security_score,
    repo_health_score,
    repo_security_score,
    risk_level,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("aggregator")

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
META_DIR = BASE_DIR / "data" / "meta"
AGG_DIR = BASE_DIR / "data" / "aggregated"
HISTORY_DIR = BASE_DIR / "data" / "history"
CONFIG_DIR = BASE_DIR / "data" / "config"

GITHUB_ORG: str = os.environ.get("GIT_ORG", "")


# ---------------------------------------------------------------------------
# Load raw data
# ---------------------------------------------------------------------------


def load_raw_repos() -> List[Dict[str, Any]]:
    """Load all per-repo JSON files from ``data/raw/``."""
    repos: List[Dict[str, Any]] = []
    if not RAW_DIR.exists():
        logger.warning("Raw data directory does not exist: %s", RAW_DIR)
        return repos
    for path in sorted(RAW_DIR.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            repos.append(data)
        except Exception:
            logger.exception("Failed to load %s", path)
    return repos


def _try_validate(repo: Dict[str, Any]) -> List[str]:
    """Best-effort Pydantic validation — returns error strings."""
    try:
        from aggregator.schemas.validators import assert_raw_repo

        name = get(repo, "repo_metadata", "repo", default="?")
        return assert_raw_repo(repo, repo=name)
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------


def detect_sources(repos: List[Dict[str, Any]]) -> Dict[str, bool]:
    """Return ``{source: available}`` based on which collector sections exist.

    A source is ``True`` only if it has real data (``integration_status``
    is **not** ``"disabled"``).
    """
    sources: Dict[str, bool] = {
        "github": False,
        "sonar": False,
        "snyk": False,
        "servicenow": False,
        "logging": False,
        "work_items": False,
    }
    for r in repos:
        if r.get("github"):
            sources["github"] = True
        if r.get("sonar") and get(r, "sonar", "available"):
            sources["sonar"] = True
        if r.get("snyk") and get(r, "snyk", "available"):
            sources["snyk"] = True
        if (r.get("servicenow")
                and get(r, "servicenow", "available")
                and get(r, "servicenow", "integration_status") != "disabled"):
            sources["servicenow"] = True
        if r.get("logging") and get(r, "logging", "available"):
            sources["logging"] = True
        if (r.get("work_items")
                and get(r, "work_items", "total_items")
                and get(r, "work_items", "integration_status") != "disabled"):
            sources["work_items"] = True
    # Check for meta-level summaries (only if enabled)
    sn_meta = META_DIR / "servicenow_value_stream.json"
    if sn_meta.exists():
        try:
            with open(sn_meta, "r", encoding="utf-8") as fh:
                sn_data = json.load(fh)
            if sn_data.get("integration_status") != "disabled":
                sources["servicenow"] = True
        except (json.JSONDecodeError, OSError):
            pass
    wi_meta = META_DIR / "workitems_summary.json"
    if wi_meta.exists():
        try:
            with open(wi_meta, "r", encoding="utf-8") as fh:
                wi_data = json.load(fh)
            if wi_data.get("integration_status") != "disabled":
                sources["work_items"] = True
        except (json.JSONDecodeError, OSError):
            pass
    return sources


# ---------------------------------------------------------------------------
# Admin config loader
# ---------------------------------------------------------------------------


def load_admin_config() -> Optional[Dict[str, Any]]:
    """Load admin configuration from ``data/config/admin_config.json``."""
    cfg_path = CONFIG_DIR / "admin_config.json"
    if not cfg_path.exists():
        return None
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load admin config: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Aggregation: DORA
# ---------------------------------------------------------------------------


def _merge_trends(dicts: List[Dict], key: str) -> Optional[List[Dict[str, Any]]]:
    """Merge per-repo trend arrays into an org-level averaged trend."""
    all_trends = [d.get(key) for d in dicts if d.get(key)]
    if not all_trends:
        return None
    # Collect by period label
    period_map: Dict[str, List[float]] = {}
    for trend_list in all_trends:
        for entry in trend_list:
            label = entry.get("period") or entry.get("week") or ""
            val = entry.get("value")
            if label and val is not None:
                period_map.setdefault(label, []).append(val)
    if not period_map:
        return None
    return [
        {"period": k, "value": round(sum(v) / len(v), 2)}
        for k, v in sorted(period_map.items())
    ]


def aggregate_dora(repos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    dora_dicts = [r["dora"] for r in repos if r.get("dora")]
    if not dora_dicts:
        return None
    return {
        "deployment_frequency": safe_avg(collect_values(dora_dicts, "deployment_frequency")),
        "lead_time_hours": safe_avg(collect_values(dora_dicts, "lead_time_hours")),
        "lead_time_coding_hours": safe_avg(collect_values(dora_dicts, "lead_time_coding_hours")),
        "lead_time_review_hours": safe_avg(collect_values(dora_dicts, "lead_time_review_hours")),
        "lead_time_deploy_hours": safe_avg(collect_values(dora_dicts, "lead_time_deploy_hours")),
        "change_failure_rate": safe_avg(collect_values(dora_dicts, "change_failure_rate")),
        "mttr_hours": safe_avg(collect_values(dora_dicts, "mttr_hours")),
        "build_repair_time_hours": safe_avg(collect_values(dora_dicts, "build_repair_time_hours")),
        "total_deployments": safe_sum(collect_values(dora_dicts, "total_deployments")),
        "total_failures": safe_sum(collect_values(dora_dicts, "total_failures")),
        "merged_prs": safe_sum(collect_values(dora_dicts, "merged_prs")),
        "releases_per_month": safe_avg(collect_values(dora_dicts, "releases_per_month")),
        "deployment_frequency_trend": _merge_trends(dora_dicts, "deployment_frequency_trend"),
        "lead_time_trend": _merge_trends(dora_dicts, "lead_time_trend"),
        "cfr_trend": _merge_trends(dora_dicts, "cfr_trend"),
    }


# ---------------------------------------------------------------------------
# Aggregation: Flow
# ---------------------------------------------------------------------------


def aggregate_flow(repos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    flow_dicts = [r["flow"] for r in repos if r.get("flow")]
    if not flow_dicts:
        return None
    return {
        "pr_review_time_hours": safe_avg(collect_values(flow_dicts, "pr_review_time_hours")),
        "pr_cycle_time_hours": safe_avg(collect_values(flow_dicts, "pr_cycle_time_hours")),
        "wip": safe_sum(collect_values(flow_dicts, "wip")),
        "throughput": safe_sum(collect_values(flow_dicts, "throughput")),
        "review_sla_met_pct": safe_avg(collect_values(flow_dicts, "review_sla_met_pct")),
        "review_sla_threshold_hours": safe_avg(collect_values(flow_dicts, "review_sla_threshold_hours")),
    }


# ---------------------------------------------------------------------------
# Aggregation: Security
# ---------------------------------------------------------------------------


def aggregate_security(repos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    sec_dicts = [r["security"] for r in repos if r.get("security")]
    if not sec_dicts:
        return None

    mttr_vals = [
        v for v in collect_values(sec_dicts, "security_mttr_hours")
        if v is not None and v > 0
    ]

    # Vulnerability density (avg across repos)
    vd_vals = collect_values(sec_dicts, "vulnerability_density")

    # Security gate pass percentage
    gate_vals = collect_values(sec_dicts, "security_gate_pass")
    gate_pass_pct = None
    if gate_vals:
        passing = sum(1 for v in gate_vals if v is True)
        gate_pass_pct = round(passing / len(gate_vals) * 100, 2)

    # EOL component count
    eol_vals = collect_values(sec_dicts, "eol_components")

    return {
        "critical": safe_sum(collect_values(sec_dicts, "critical")),
        "high": safe_sum(collect_values(sec_dicts, "high")),
        "medium": safe_sum(collect_values(sec_dicts, "medium")),
        "low": safe_sum(collect_values(sec_dicts, "low")),
        "secrets": safe_sum(collect_values(sec_dicts, "secrets")),
        "dependency_alerts": safe_sum(collect_values(sec_dicts, "dependency_alerts")),
        "code_scanning_alerts": safe_sum(collect_values(sec_dicts, "code_scanning_alerts")),
        "security_mttr_hours": safe_avg(mttr_vals) if mttr_vals else None,
        "vulnerability_density": safe_avg(vd_vals) if vd_vals else None,
        "security_gate_pass_pct": gate_pass_pct,
        "eol_component_count": safe_sum(eol_vals) if eol_vals else None,
    }


# ---------------------------------------------------------------------------
# Aggregation: Quality
# ---------------------------------------------------------------------------


def _build_rating_distribution(repos: List[Dict[str, Any]]) -> Optional[Dict[str, Dict[str, int]]]:
    """Count repos by SonarQube rating (A-E) for each rating type."""
    dist: Dict[str, Dict[str, int]] = {
        "reliability": {},
        "security": {},
        "maintainability": {},
    }
    has_any = False
    for r in repos:
        q = r.get("quality") or {}
        for field, key in [
            ("reliability_rating", "reliability"),
            ("security_rating", "security"),
            ("maintainability_rating", "maintainability"),
        ]:
            val = q.get(field)
            if val is not None:
                has_any = True
                dist[key][str(val)] = dist[key].get(str(val), 0) + 1
    return dist if has_any else None


def _build_coverage_trend(repos: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Merge per-repo coverage_trend arrays into org-level avg."""
    all_trends = [r["quality"]["coverage_trend"]
                  for r in repos
                  if r.get("quality") and r["quality"].get("coverage_trend")]
    if not all_trends:
        return None
    period_map: Dict[str, List[float]] = {}
    for trend_list in all_trends:
        for entry in trend_list:
            label = entry.get("period") or entry.get("date") or ""
            val = entry.get("value")
            if label and val is not None:
                period_map.setdefault(label, []).append(val)
    if not period_map:
        return None
    return [
        {"period": k, "value": round(sum(v) / len(v), 2)}
        for k, v in sorted(period_map.items())
    ]


def aggregate_quality(
    repos: List[Dict[str, Any]],
    flow: Optional[Dict[str, Any]],
    dora: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    qual_dicts = [r["quality"] for r in repos if r.get("quality")]

    # Maintainability rating as numeric for averaging
    maint_vals = []
    for q in qual_dicts:
        mr = q.get("maintainability_rating")
        if mr is not None:
            # If string rating (A=1, B=2, ...), convert
            if isinstance(mr, str) and mr in "ABCDE":
                maint_vals.append(float(ord(mr) - ord("A") + 1))
            else:
                v = num(mr)
                if v is not None:
                    maint_vals.append(v)

    return {
        "avg_pr_cycle_time_hours": get(flow, "pr_cycle_time_hours"),
        "avg_review_time_hours": get(flow, "pr_review_time_hours"),
        "total_merged_prs": get(dora, "merged_prs"),
        "total_tech_debt_hours": safe_sum(collect_values(qual_dicts, "tech_debt_hours")) if qual_dicts else None,
        "avg_tech_debt_ratio": safe_avg(collect_values(qual_dicts, "tech_debt_ratio")) if qual_dicts else None,
        "avg_coverage_pct": safe_avg(collect_values(qual_dicts, "coverage_pct")) if qual_dicts else None,
        "avg_duplication_pct": safe_avg(collect_values(qual_dicts, "duplication_pct")) if qual_dicts else None,
        "total_bugs": safe_sum(collect_values(qual_dicts, "bugs")) if qual_dicts else None,
        "total_code_smells": safe_sum(collect_values(qual_dicts, "code_smells")) if qual_dicts else None,
        "avg_maintainability_rating": round(sum(maint_vals) / len(maint_vals), 2) if maint_vals else None,
        "rating_distribution": _build_rating_distribution(repos),
        "coverage_trend": _build_coverage_trend(repos),
    }


# ---------------------------------------------------------------------------
# Aggregation: Value Stream (from ServiceNow meta + work items)
# ---------------------------------------------------------------------------


def aggregate_value_stream(repos: List[Dict[str, Any]]) -> Dict[str, Any]:
    NR = "N/R"

    # ServiceNow data
    sn_path = META_DIR / "servicenow_value_stream.json"
    sn: Dict[str, Any] = {}
    sn_status = "disabled"
    if sn_path.exists():
        try:
            with open(sn_path, "r", encoding="utf-8") as fh:
                sn = json.load(fh)
            sn_status = sn.get("integration_status", "enabled")
        except (json.JSONDecodeError, OSError):
            pass

    # Work item data
    wi_path = META_DIR / "workitems_summary.json"
    wi: Dict[str, Any] = {}
    wi_status = "disabled"
    if wi_path.exists():
        try:
            with open(wi_path, "r", encoding="utf-8") as fh:
                wi = json.load(fh)
            wi_status = wi.get("integration_status", "enabled")
        except (json.JSONDecodeError, OSError):
            pass

    # ServiceNow metrics (respect N/R)
    avg_lead = sn.get("avg_lead_time_hours")
    avg_impl = sn.get("avg_implementation_time_hours")

    def _nr_safe_days(hours_val):
        """Convert hours to days, but pass through N/R."""
        if hours_val == NR:
            return NR
        if hours_val is not None:
            return round(hours_val / 24, 2)
        return None

    # Per-repo work items aggregation
    wi_dicts = [
        r["work_items"] for r in repos
        if r.get("work_items")
        and r["work_items"].get("integration_status") != "disabled"
        and r["work_items"].get("total_items")
        and r["work_items"]["total_items"] != NR
    ]
    wi_cycle = collect_values(wi_dicts, "avg_cycle_time_hours") if wi_dicts else []
    wi_lead = collect_values(wi_dicts, "avg_lead_time_hours") if wi_dicts else []

    # Merge items_by_type across repos
    merged_by_type: Dict[str, int] = {}
    if wi_status == "enabled":
        merged_by_type = wi.get("items_by_type") or {}
        for wd in wi_dicts:
            for t, c in (wd.get("items_by_type") or {}).items():
                if t not in merged_by_type:
                    merged_by_type[t] = merged_by_type.get(t, 0)

    # Work item metrics — use N/R if integration is disabled
    def _wi_metric(key):
        if wi_status == "disabled":
            return NR
        val = wi.get(key)
        if val == NR:
            return NR
        return val

    wi_total = _wi_metric("total_items") or safe_sum(collect_values(wi_dicts, "total_items"))
    wi_completed = _wi_metric("completed_items") or safe_sum(collect_values(wi_dicts, "completed_items"))
    wi_cycle_val = _wi_metric("avg_cycle_time_hours") or safe_avg(wi_cycle)
    wi_lead_val = _wi_metric("avg_lead_time_hours") or safe_avg(wi_lead)

    return {
        "servicenow_status": sn_status,
        "workitems_status": wi_status,
        "avg_idea_to_prod_days": _nr_safe_days(avg_lead),
        "avg_coding_time_hours": avg_impl if avg_impl != NR else NR,
        "avg_review_time_hours": None,
        "avg_deploy_time_hours": None,
        "avg_work_item_cycle_time_hours": wi_cycle_val,
        "avg_work_item_lead_time_hours": wi_lead_val,
        "total_work_items": wi_total,
        "completed_work_items": wi_completed,
        "items_by_type": merged_by_type or None,
    }


# ---------------------------------------------------------------------------
# Aggregation: Governance
# ---------------------------------------------------------------------------


def aggregate_governance(repos: List[Dict[str, Any]], total: int) -> Optional[Dict[str, Any]]:
    gov_dicts = [r["governance"] for r in repos if r.get("governance")]
    if not gov_dicts:
        return None

    # New governance aggregate metrics
    flow_dicts = [r["flow"] for r in repos if r.get("flow")]

    return {
        # Original governance metrics
        "branch_protection_pct": bool_pct(collect_values(gov_dicts, "branch_protection_enabled")),
        "dependabot_pct": bool_pct(collect_values(gov_dicts, "dependabot_enabled")),
        "code_scanning_pct": bool_pct(collect_values(gov_dicts, "code_scanning_enabled")),
        "secret_scanning_pct": bool_pct(collect_values(gov_dicts, "secret_scanning_enabled")),
        "ci_enabled_pct": bool_pct(collect_values(gov_dicts, "ci_enabled")),
        "security_md_pct": bool_pct(collect_values(gov_dicts, "security_md_exists")),
        "dependabot_config_pct": bool_pct(collect_values(gov_dicts, "dependabot_config_exists")),
        # New governance metrics
        "trunk_based_dev_pct": bool_pct(collect_values(gov_dicts, "trunk_based_dev")),
        "pr_to_work_item_pct": safe_avg(collect_values(gov_dicts, "pr_to_work_item_pct")),
        "iac_coverage_pct": safe_avg(collect_values(gov_dicts, "iac_coverage_pct")),
        "mandatory_checks_pct": bool_pct(collect_values(gov_dicts, "mandatory_checks_enforced")),
        "docs_coverage_pct": _compute_docs_coverage_pct(gov_dicts),
        "naming_standards_pct": bool_pct(collect_values(gov_dicts, "naming_standards_compliant")),
        "review_sla_met_pct": safe_avg(
            collect_values(flow_dicts, "review_sla_met_pct")
        ) if flow_dicts else None,
    }


def _compute_docs_coverage_pct(gov_dicts: List[Dict[str, Any]]) -> Optional[float]:
    """Compute % of repos that have all required docs."""
    scores: List[float] = []
    for g in gov_dicts:
        docs = g.get("docs_coverage")
        if docs and isinstance(docs, dict):
            total = len(docs)
            present = sum(1 for v in docs.values() if v)
            scores.append(present / total * 100 if total else 0)
    return safe_avg(scores) if scores else None


# ---------------------------------------------------------------------------
# Aggregation: Logging
# ---------------------------------------------------------------------------


def aggregate_logging(repos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    log_dicts = [r["logging"] for r in repos if r.get("logging") and get(r, "logging", "available")]
    if not log_dicts:
        # Try org-level meta
        meta_path = META_DIR / "logging_summary.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
                total = meta.get("total_runs", 0)
                failures = meta.get("failure_count", 0)
                return {
                    "total_logs": total,
                    "total_errors": failures,
                    "error_rate_pct": percent(failures, total),
                    "top_error_services": None,
                }
            except (json.JSONDecodeError, OSError):
                pass
        return None

    total_runs = safe_sum(collect_values(log_dicts, "total_runs"))
    total_fail = safe_sum(collect_values(log_dicts, "failure_count"))

    return {
        "total_logs": total_runs,
        "total_errors": total_fail,
        "error_rate_pct": percent(total_fail, total_runs),
        "top_error_services": None,
    }


# ---------------------------------------------------------------------------
# Per-repo summary rows
# ---------------------------------------------------------------------------


def build_repo_row(r: Dict[str, Any]) -> Dict[str, Any]:
    """Build a single repo summary row for the dashboard."""
    meta = r.get("repo_metadata") or {}
    name = meta.get("repo") or r.get("repo", "unknown")
    hs = repo_health_score(r)
    ss = repo_security_score(r)
    rl = risk_level(r)

    return {
        "name": name,
        "full_name": meta.get("full_name") or r.get("full_name", ""),
        "language": meta.get("language") or r.get("language"),
        "languages": meta.get("languages"),
        "visibility": meta.get("visibility") or r.get("visibility", "private"),
        "default_branch": meta.get("default_branch") or r.get("default_branch", "main"),
        "owner": meta.get("owner"),
        "risk_level": rl,
        "health_score": hs,
        "security_score": ss,
        "dora": r.get("dora"),
        "flow": r.get("flow"),
        "security": r.get("security"),
        "governance": r.get("governance"),
        "quality": r.get("quality"),
        "work_items": r.get("work_items"),
    }


# ---------------------------------------------------------------------------
# Contributors
# ---------------------------------------------------------------------------


def aggregate_contributors(repos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Aggregate contributor data from GitHub collector."""
    all_contributors: Dict[str, int] = {}
    for r in repos:
        gh = r.get("github") or {}
        contribs = gh.get("contributors") or []
        for c in contribs:
            login = c.get("login") or c.get("author") or ""
            if login:
                all_contributors[login] = all_contributors.get(login, 0) + c.get("contributions", 1)

    if not all_contributors:
        commit_counts = collect_values(repos, "github", "commit_count")
        if not commit_counts:
            return None
        return {"total_contributors": None, "top_contributors": None}

    sorted_contribs = sorted(all_contributors.items(), key=lambda x: x[1], reverse=True)
    return {
        "total_contributors": len(all_contributors),
        "top_contributors": [
            {"login": login, "contributions": count}
            for login, count in sorted_contribs[:20]
        ],
    }


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------


def aggregate_languages(repos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Aggregate language byte-counts across all repos."""
    combined: Dict[str, int] = {}
    for r in repos:
        meta = r.get("repo_metadata") or {}
        langs = meta.get("languages")
        if langs and isinstance(langs, dict):
            for lang, count in langs.items():
                combined[lang] = combined.get(lang, 0) + (count or 0)

    if not combined:
        for r in repos:
            meta = r.get("repo_metadata") or r
            lang = meta.get("language")
            if lang:
                combined[lang] = combined.get(lang, 0) + 1

    if not combined:
        return None

    return {
        "total_languages": len(combined),
        "breakdown": dict(sorted(combined.items(), key=lambda x: x[1], reverse=True)),
    }


# ---------------------------------------------------------------------------
# Integration status detection
# ---------------------------------------------------------------------------


def _read_meta_status(filename: str) -> str:
    """Read ``integration_status`` from a meta JSON file."""
    path = META_DIR / filename
    if not path.exists():
        return "disabled"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("integration_status", "enabled")
    except (json.JSONDecodeError, OSError):
        return "disabled"


def _detect_integration_statuses() -> Dict[str, str]:
    """Return ``{integration: status}`` for optional integrations."""
    return {
        "servicenow": _read_meta_status("servicenow_value_stream.json"),
        "jira_ado": _read_meta_status("workitems_summary.json"),
    }


# ---------------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------------


def aggregate(repos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Produce the ``dashboard.json`` payload from per-repo data."""
    total = len(repos)

    scanned = sum(
        1
        for r in repos
        if get(r, "collection", "collected_at") or r.get("collected_at")
    )

    # Validate each repo
    validation_errors: int = 0
    for r in repos:
        errs = _try_validate(r)
        if errs:
            name = get(r, "repo_metadata", "repo", default="?")
            logger.warning("Validation issues in %s: %s", name, errs[:3])
            validation_errors += 1

    # Detect sources
    sources = detect_sources(repos)

    # Aggregate sections
    dora = aggregate_dora(repos)
    flow = aggregate_flow(repos)
    security = aggregate_security(repos)
    quality = aggregate_quality(repos, flow, dora)
    value_stream = aggregate_value_stream(repos)
    governance = aggregate_governance(repos, total)
    logging_section = aggregate_logging(repos)

    # Repo table
    repo_rows = [build_repo_row(r) for r in repos]

    # Contributors & Languages
    contributors = aggregate_contributors(repos)
    languages = aggregate_languages(repos)

    # Admin config
    admin_config = load_admin_config()

    # Scores
    delivery_score = compute_delivery_score(dora)
    quality_score = compute_quality_score(quality, flow)
    security_score = compute_security_score(security)
    governance_score = compute_governance_score(governance)
    eng_health = composite_health_score(
        delivery_score, quality_score, security_score, governance_score
    )

    scores = {
        "engineering_health": eng_health,
        "delivery": delivery_score,
        "quality": quality_score,
        "security": security_score,
        "governance": governance_score,
    }

    # Lookback
    lookback = None
    for r in repos:
        lb = get(r, "collection", "lookback_days") or r.get("lookback_days")
        if lb is not None:
            lookback = lb
            break
    lookback = lookback or 30

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback,
        "total_repos": total,
        "scanned_repos": scanned,
        "scan_coverage_percent": round(scanned / total * 100, 2) if total else 0.0,
        "org": GITHUB_ORG or None,
        "sources": sources,
        "integration_statuses": _detect_integration_statuses(),
        "validation_errors": validation_errors,
    }

    return {
        "metadata": metadata,
        "dora": dora,
        "flow": flow,
        "security": security,
        "quality": quality,
        "value_stream": value_stream,
        "governance": governance,
        "logging": logging_section,
        "scores": scores,
        "repos": repo_rows,
        "contributors": contributors,
        "languages": languages,
        "admin_config": admin_config,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_dashboard(payload: Dict[str, Any]) -> None:
    """Write aggregated ``dashboard.json`` and a daily history snapshot."""
    AGG_DIR.mkdir(parents=True, exist_ok=True)
    out = AGG_DIR / "dashboard.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    logger.info("Saved aggregated dashboard → %s", out)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_dir = HISTORY_DIR / today
    day_dir.mkdir(parents=True, exist_ok=True)
    archive = day_dir / "dashboard.json"
    with open(archive, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    logger.info("Archived → %s", archive)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    repos = load_raw_repos()
    if not repos:
        logger.error("No raw repo data found in %s", RAW_DIR)
        sys.exit(1)

    logger.info("Aggregating %d repos …", len(repos))
    payload = aggregate(repos)
    save_dashboard(payload)

    health = payload["scores"].get("engineering_health")
    health_str = f"{health:.1f}" if health is not None else "N/A"
    logger.info(
        "Aggregation complete — engineering health: %s  |  sources: %s",
        health_str,
        ", ".join(k for k, v in payload["metadata"]["sources"].items() if v),
    )


if __name__ == "__main__":
    main()
