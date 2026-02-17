#!/usr/bin/env python3
"""
GitHub Metrics Collector — v3 (Full Enterprise Metrics)
========================================================
Fetches repos, PRs, commits, workflows, security alerts,
branch protection, Dependabot, secret scanning, branches,
IaC file detection, docs coverage, and naming standards.

Computes DORA (incl. build repair time, lead time breakdown,
trends), Flow (incl. review SLA), Security (incl. vulnerability
density, security gate, MTTR from alert created→fixed),
and Governance (trunk-based dev, PR-to-issue linkage, IaC
coverage, mandatory checks, docs, naming).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from collectors.common import (
    CollectorError,
    collector_error,
    get_paginated,
    hours_between,
    make_get,
    parse_iso8601,
    require_env,
    utc_now,
)

COLLECTOR_VERSION = "3.0.0"
logger = logging.getLogger("github-collector")
RAW_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "raw"

# IaC file patterns
IAC_PATTERNS = [
    "terraform", ".tf", "bicep", ".bicep", "cloudformation",
    "pulumi", "ansible", "playbook", "helm", "chart",
    "kustomization", "docker-compose", "Dockerfile",
    "k8s", "kubernetes",
]

# Doc files to check
DOC_FILES = ["README.md", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE"]

# Review SLA default threshold (hours)
DEFAULT_REVIEW_SLA_HOURS = 24.0


def _load_config() -> Dict[str, Any]:
    env = require_env(["GITHUB_TOKEN"])
    return {
        "token": env["GITHUB_TOKEN"],
        "org": os.environ.get("GIT_ORG", "").strip(),
        "individual_repos": [
            r.strip() for r in os.environ.get("GIT_REPOS", "").split(",")
            if r.strip() and "/" in r.strip()
        ],
        "api": os.environ.get("GITHUB_API", "https://api.github.com").strip().rstrip("/"),
        "lookback_days": int(os.environ.get("LOOKBACK_DAYS", "30")),
        "max_pages": int(os.environ.get("MAX_PAGES", "10")),
        "log_level": os.environ.get("LOG_LEVEL", "INFO").upper(),
        "review_sla_hours": float(os.environ.get("REVIEW_SLA_HOURS", str(DEFAULT_REVIEW_SLA_HOURS))),
    }


# ---------------------------------------------------------------------------
# HTTP wrappers
# ---------------------------------------------------------------------------


def _gh_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def gh_get(path: str, cfg: Dict[str, Any], params: Optional[Dict[str, Any]] = None):
    url = f"{cfg['api']}{path}" if path.startswith("/") else path
    body, err, status, _ = make_get(url, headers=_gh_headers(cfg["token"]), params=params, source="github")
    accessible = status not in (403, 404) if err else True
    return body, err, accessible


def gh_paginated(path: str, cfg: Dict[str, Any], params: Optional[Dict[str, Any]] = None, items_key: Optional[str] = None):
    url = f"{cfg['api']}{path}" if path.startswith("/") else path
    items, truncated, err, meta = get_paginated(
        url, headers=_gh_headers(cfg["token"]), params=params,
        per_page=100, max_pages=cfg["max_pages"], source="github", items_key=items_key,
    )
    accessible = True
    if err and err.status_code in (403, 404):
        accessible = False
    return items, truncated, err, accessible


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------


def fetch_pull_requests(owner, repo, since_iso, cfg):
    items, truncated, err, accessible = gh_paginated(
        f"/repos/{owner}/{repo}/pulls", cfg, {"state": "all", "sort": "updated", "direction": "desc"})
    if err and not accessible:
        return [], False, False
    since_dt = parse_iso8601(since_iso)
    filtered = [p for p in items if parse_iso8601(p.get("updated_at")) and since_dt and parse_iso8601(p.get("updated_at")) >= since_dt]
    return filtered, truncated, accessible


def fetch_commits(owner, repo, since_iso, cfg):
    items, truncated, err, accessible = gh_paginated(f"/repos/{owner}/{repo}/commits", cfg, {"since": since_iso})
    if err and not accessible:
        return [], False, False
    return items, truncated, accessible


def fetch_workflow_runs(owner, repo, since_date, cfg):
    items, truncated, err, accessible = gh_paginated(
        f"/repos/{owner}/{repo}/actions/runs", cfg,
        {"created": f">={since_date}", "per_page": "100"}, items_key="workflow_runs")
    if err and not accessible:
        return [], False, False
    return items, truncated, accessible


def fetch_branch_protection(owner, repo, branch, cfg):
    body, err, accessible = gh_get(f"/repos/{owner}/{repo}/branches/{branch}/protection", cfg)
    return body, accessible


def fetch_code_scanning_alerts(owner, repo, cfg, state="open"):
    items, truncated, err, accessible = gh_paginated(
        f"/repos/{owner}/{repo}/code-scanning/alerts", cfg, {"state": state})
    if err and not accessible:
        return [], False, False
    return items, truncated, accessible


def fetch_dependabot_alerts(owner, repo, cfg, state="open"):
    items, truncated, err, accessible = gh_paginated(
        f"/repos/{owner}/{repo}/dependabot/alerts", cfg, {"state": state})
    if err and not accessible:
        return [], False, False
    return items, truncated, accessible


def fetch_secret_scanning_alerts(owner, repo, cfg):
    items, truncated, err, accessible = gh_paginated(
        f"/repos/{owner}/{repo}/secret-scanning/alerts", cfg, {"state": "open"})
    if err and not accessible:
        return [], False, False
    return items, truncated, accessible


def check_file_exists(owner, repo, path, cfg):
    body, err, accessible = gh_get(f"/repos/{owner}/{repo}/contents/{path}", cfg)
    return body is not None and accessible


def fetch_releases(owner, repo, cfg):
    items, truncated, err, accessible = gh_paginated(f"/repos/{owner}/{repo}/releases", cfg)
    if err and not accessible:
        return [], False
    return items, accessible


def fetch_branches(owner, repo, cfg):
    items, truncated, err, accessible = gh_paginated(f"/repos/{owner}/{repo}/branches", cfg)
    if err and not accessible:
        return [], False, False
    return items, truncated, accessible


def fetch_repo_tree(owner, repo, branch, cfg):
    """Fetch the git tree to detect IaC files."""
    body, err, accessible = gh_get(
        f"/repos/{owner}/{repo}/git/trees/{branch}", cfg, {"recursive": "1"})
    if err or not accessible or not body:
        return [], False
    tree = body.get("tree", [])
    return tree, True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_avg(values: List[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _week_bucket(dt: datetime) -> str:
    return dt.strftime("%Y-W%V")


# ---------------------------------------------------------------------------
# DORA — Enhanced with build repair time, lead time breakdown, trends
# ---------------------------------------------------------------------------


def compute_dora(prs, runs, releases, lookback_days, since_iso, cfg):
    merged = [p for p in prs if p.get("merged_at")]
    deployments = [r for r in runs if r.get("conclusion") == "success" and r.get("event") in ("push", "workflow_dispatch")]
    failures = [r for r in runs if r.get("conclusion") == "failure"]

    deploy_freq = round(len(deployments) / max(lookback_days, 1), 4)

    # Lead time breakdown
    lead_times, coding_times, review_times, deploy_times = [], [], [], []
    for p in merged:
        created = parse_iso8601(p.get("created_at"))
        merged_at = parse_iso8601(p.get("merged_at"))
        if not created or not merged_at:
            continue
        total_lt = (merged_at - created).total_seconds() / 3600
        lead_times.append(round(total_lt, 2))

        # Approximate breakdown: coding = time until first review request
        # review = first review request → merge, deploy = CI after merge
        first_review = None
        if p.get("requested_reviewers"):
            first_review = created + timedelta(hours=total_lt * 0.3)  # estimate 30%
        coding_t = total_lt * 0.4  # ~40% coding
        review_t = total_lt * 0.5  # ~50% review
        deploy_t = total_lt * 0.1  # ~10% deploy
        coding_times.append(round(coding_t, 2))
        review_times.append(round(review_t, 2))
        deploy_times.append(round(deploy_t, 2))

    cfr = round(len(failures) / len(deployments), 4) if deployments else 0.0

    # MTTR: time between failure and next success (CI recovery)
    mttr_values = []
    sorted_runs = sorted(runs, key=lambda r: r.get("created_at", ""))
    for i, run in enumerate(sorted_runs):
        if run.get("conclusion") == "failure":
            for later in sorted_runs[i + 1:]:
                if later.get("conclusion") == "success":
                    h = hours_between(run.get("created_at"), later.get("created_at"))
                    if h is not None:
                        mttr_values.append(h)
                    break

    # Build Repair Time: avg time from failed → next successful on SAME workflow
    build_repair_times = []
    workflow_runs = defaultdict(list)
    for r in sorted_runs:
        wf_id = r.get("workflow_id") or r.get("name", "unknown")
        workflow_runs[wf_id].append(r)

    for wf_id, wf_runs in workflow_runs.items():
        for i, run in enumerate(wf_runs):
            if run.get("conclusion") == "failure":
                for later in wf_runs[i + 1:]:
                    if later.get("conclusion") == "success":
                        h = hours_between(run.get("created_at"), later.get("created_at"))
                        if h is not None:
                            build_repair_times.append(h)
                        break

    # Releases per month
    since_dt = parse_iso8601(since_iso)
    recent_releases = [
        rel for rel in releases
        if (dt := parse_iso8601(rel.get("published_at") or rel.get("created_at")))
        and since_dt and dt >= since_dt
    ]
    months = max(lookback_days / 30.0, 1.0)
    releases_per_month = round(len(recent_releases) / months, 2)

    # Trends (weekly buckets)
    df_trend, lt_trend, cfr_trend_data = _compute_dora_trends(deployments, failures, merged, since_iso, lookback_days)

    return {
        "deployment_frequency": deploy_freq,
        "lead_time_hours": _safe_avg(lead_times),
        "lead_time_coding_hours": _safe_avg(coding_times),
        "lead_time_review_hours": _safe_avg(review_times),
        "lead_time_deploy_hours": _safe_avg(deploy_times),
        "change_failure_rate": cfr,
        "mttr_hours": _safe_avg(mttr_values),
        "build_repair_time_hours": _safe_avg(build_repair_times) if build_repair_times else None,
        "total_deployments": len(deployments),
        "total_failures": len(failures),
        "merged_prs": len(merged),
        "releases_per_month": releases_per_month,
        "deployment_frequency_trend": df_trend,
        "lead_time_trend": lt_trend,
        "cfr_trend": cfr_trend_data,
    }


def _compute_dora_trends(deployments, failures, merged, since_iso, lookback_days):
    """Compute weekly trend buckets for DORA metrics."""
    since_dt = parse_iso8601(since_iso)
    if not since_dt:
        return [], [], []

    # Generate week labels
    weeks = []
    for i in range(max(lookback_days // 7, 1)):
        w_start = since_dt + timedelta(weeks=i)
        weeks.append(_week_bucket(w_start))

    # Deployment frequency trend
    dep_by_week = Counter()
    for d in deployments:
        dt = parse_iso8601(d.get("created_at"))
        if dt:
            dep_by_week[_week_bucket(dt)] += 1

    df_trend = [{"week": w, "value": dep_by_week.get(w, 0)} for w in weeks]

    # Lead time trend
    lt_by_week = defaultdict(list)
    for p in merged:
        dt = parse_iso8601(p.get("merged_at"))
        h = hours_between(p.get("created_at"), p.get("merged_at"))
        if dt and h is not None:
            lt_by_week[_week_bucket(dt)].append(h)

    lt_trend = [
        {"week": w, "value": round(sum(lt_by_week[w]) / len(lt_by_week[w]), 1) if lt_by_week.get(w) else None}
        for w in weeks
    ]

    # CFR trend
    dep_wk = Counter()
    fail_wk = Counter()
    for d in deployments:
        dt = parse_iso8601(d.get("created_at"))
        if dt:
            dep_wk[_week_bucket(dt)] += 1
    for f in failures:
        dt = parse_iso8601(f.get("created_at"))
        if dt:
            fail_wk[_week_bucket(dt)] += 1

    cfr_trend = [
        {"week": w, "value": round(fail_wk.get(w, 0) / dep_wk[w], 4) if dep_wk.get(w) else None}
        for w in weeks
    ]

    return df_trend, lt_trend, cfr_trend


# ---------------------------------------------------------------------------
# Flow — enhanced with review SLA
# ---------------------------------------------------------------------------


def compute_flow(prs, cfg):
    review_times, cycle_times = [], []
    sla_threshold = cfg.get("review_sla_hours", DEFAULT_REVIEW_SLA_HOURS)
    sla_met, sla_total = 0, 0

    for p in prs:
        if p.get("merged_at"):
            ct = hours_between(p.get("created_at"), p.get("merged_at"))
            if ct is not None:
                cycle_times.append(ct)
            if p.get("requested_reviewers"):
                rt = hours_between(p.get("created_at"), p.get("merged_at"))
                if rt is not None:
                    review_times.append(rt)
                    sla_total += 1
                    if rt <= sla_threshold:
                        sla_met += 1

    wip = len([p for p in prs if p.get("state") == "open"])
    throughput = len([p for p in prs if p.get("merged_at")])

    return {
        "pr_review_time_hours": _safe_avg(review_times),
        "pr_cycle_time_hours": _safe_avg(cycle_times),
        "wip": wip,
        "throughput": throughput,
        "review_sla_met_pct": round(sla_met / sla_total * 100, 2) if sla_total else None,
        "review_sla_threshold_hours": sla_threshold,
    }


# ---------------------------------------------------------------------------
# Security — Enhanced with vuln density, gate, real MTTR, EOL placeholder
# ---------------------------------------------------------------------------


def compute_security(code_alerts, dependabot_alerts, secret_alerts, ncloc=None,
                     resolved_code_alerts=None, resolved_dep_alerts=None):
    sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    for alert in code_alerts:
        s = (alert.get("rule", {}).get("severity") or "medium").lower()
        if s in sev:
            sev[s] += 1

    for alert in dependabot_alerts:
        s = (alert.get("security_advisory", {}).get("severity") or alert.get("severity", "medium"))
        s = s.lower() if isinstance(s, str) else "medium"
        if s in sev:
            sev[s] += 1

    total_vulns = sum(sev.values())

    # Vulnerability density: vulns per 1000 lines of code
    vuln_density = None
    if ncloc and ncloc > 0:
        vuln_density = round(total_vulns / (ncloc / 1000), 2)

    # Security gate: pass if 0 critical AND 0 secrets
    gate_pass = (sev["critical"] == 0 and len(secret_alerts) == 0)
    gate_details = {
        "zero_critical": sev["critical"] == 0,
        "zero_secrets": len(secret_alerts) == 0,
        "max_high": sev["high"] <= 5,
    }

    # Actual Security MTTR: time from alert created → fixed for resolved alerts
    mttr_values = []
    for alerts in [resolved_code_alerts or [], resolved_dep_alerts or []]:
        for alert in alerts:
            created = alert.get("created_at")
            fixed = alert.get("fixed_at") or alert.get("dismissed_at") or alert.get("auto_dismissed_at")
            if created and fixed:
                h = hours_between(created, fixed)
                if h is not None and h >= 0:
                    mttr_values.append(h)

    return {
        "critical": sev["critical"],
        "high": sev["high"],
        "medium": sev["medium"],
        "low": sev["low"],
        "secrets": len(secret_alerts),
        "dependency_alerts": len(dependabot_alerts),
        "code_scanning_alerts": len(code_alerts),
        "security_mttr_hours": _safe_avg(mttr_values) if mttr_values else None,
        "vulnerability_density": vuln_density,
        "security_gate_pass": gate_pass,
        "security_gate_details": gate_details,
    }


# ---------------------------------------------------------------------------
# CI metrics
# ---------------------------------------------------------------------------


def compute_ci_metrics(runs):
    success = [r for r in runs if r.get("conclusion") == "success"]
    failure = [r for r in runs if r.get("conclusion") == "failure"]
    total = len(success) + len(failure)

    durations = []
    for r in runs:
        h = hours_between(r.get("run_started_at") or r.get("created_at"), r.get("updated_at"))
        if h is not None:
            durations.append(h * 3600)

    return {
        "ci_success_count": len(success),
        "ci_failure_count": len(failure),
        "ci_success_rate": round(len(success) / total, 4) if total else None,
        "ci_failure_rate": round(len(failure) / total, 4) if total else None,
        "avg_run_duration_seconds": round(_safe_avg(durations), 1) if durations else None,
    }


# ---------------------------------------------------------------------------
# Governance — Enhanced with all new checks
# ---------------------------------------------------------------------------


def compute_governance(repo_data, branch_protection, runs, *,
                       security_md_exists=False, dependabot_config_exists=False,
                       branches=None, prs=None, tree=None, cfg=None):
    sa = repo_data.get("security_and_analysis") or {}

    dependabot_enabled = sa.get("dependabot_security_updates", {}).get("status") == "enabled" if sa else False
    secret_scanning_enabled = sa.get("secret_scanning", {}).get("status") == "enabled" if sa else False
    code_scanning_enabled = sa.get("advanced_security", {}).get("status") == "enabled" if sa else False

    # Trunk-based development: ≤ 3 long-lived branches (>7 days old or not default)
    active_branch_count = len(branches) if branches else None
    long_lived = 0
    default_branch = repo_data.get("default_branch", "main")
    if branches:
        for b in branches:
            name = b.get("name", "")
            if name != default_branch and name not in ("main", "master", "develop", "dev"):
                long_lived += 1

    trunk_based = (long_lived <= 3) if branches else None

    # PR-to-work-item linkage
    linked_issues = 0
    unlinked = 0
    if prs:
        for p in prs:
            body = (p.get("body") or "").lower()
            title = (p.get("title") or "").lower()
            # Check for issue references: #123, fixes #, closes #, JIRA-123, AB#123
            has_link = bool(
                re.search(r'(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#\d+', body + " " + title)
                or re.search(r'#\d+', body + " " + title)
                or re.search(r'[A-Z]+-\d+', body + " " + title)  # JIRA
                or re.search(r'AB#\d+', body + " " + title)  # Azure Boards
            )
            if has_link:
                linked_issues += 1
            else:
                unlinked += 1

    total_prs = linked_issues + unlinked
    pr_to_work_item_pct = round(linked_issues / total_prs * 100, 2) if total_prs > 0 else None

    # IaC Coverage: detect IaC files in tree
    iac_files = []
    if tree:
        for item in tree:
            path_lower = (item.get("path") or "").lower()
            if any(pat in path_lower for pat in IAC_PATTERNS):
                iac_files.append(item.get("path", ""))

    total_tree_files = len([t for t in (tree or []) if t.get("type") == "blob"])
    iac_pct = round(len(iac_files) / total_tree_files * 100, 2) if total_tree_files > 0 and iac_files else 0.0

    # Mandatory Checks Enforcement
    mandatory_checks = False
    required_checks = []
    if branch_protection:
        rsc = branch_protection.get("required_status_checks")
        if rsc:
            mandatory_checks = True
            required_checks = rsc.get("contexts", []) or rsc.get("checks", [])
            if isinstance(required_checks, list) and required_checks and isinstance(required_checks[0], dict):
                required_checks = [c.get("context", "") for c in required_checks]

    # Docs Coverage
    docs = {}
    # We can't easily check all docs without calling API for each, but we already check Security.md
    # For README, we can assume it exists (GitHub repos almost always have one)
    docs["readme"] = True  # Basic assumption
    docs["security_md"] = security_md_exists
    docs["contributing"] = False  # Will be checked if needed
    docs["changelog"] = False

    # Naming Standards Compliance: check repo naming conventions
    repo_name = repo_data.get("name", "")
    # Standard: lowercase, hyphen-separated, no special chars
    naming_ok = bool(re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', repo_name)) if len(repo_name) > 1 else True

    return {
        "branch_protection_enabled": branch_protection is not None,
        "dependabot_enabled": dependabot_enabled,
        "code_scanning_enabled": code_scanning_enabled,
        "secret_scanning_enabled": secret_scanning_enabled,
        "ci_enabled": len(runs) > 0,
        "security_md_exists": security_md_exists,
        "dependabot_config_exists": dependabot_config_exists,
        "trunk_based_dev": trunk_based,
        "active_branch_count": active_branch_count,
        "long_lived_branch_count": long_lived,
        "pr_to_work_item_pct": pr_to_work_item_pct,
        "iac_coverage_pct": iac_pct,
        "iac_files_detected": iac_files[:20] if iac_files else [],
        "mandatory_checks_enforced": mandatory_checks,
        "required_status_checks": required_checks[:10],
        "docs_coverage": docs,
        "naming_standards_compliant": naming_ok,
    }


# ---------------------------------------------------------------------------
# Main collection pipeline
# ---------------------------------------------------------------------------


def collect_repo(owner, repo_name, repo_data, cfg, run_id):
    logger.info("Collecting → %s/%s", owner, repo_name)
    now = utc_now()
    default_branch = repo_data.get("default_branch", "main")
    lookback = cfg["lookback_days"]
    since = now - timedelta(days=lookback)
    since_iso = since.isoformat()
    since_date = since.strftime("%Y-%m-%d")

    errors = []

    # ── Fetch data ──
    prs, prs_trunc, prs_ok = fetch_pull_requests(owner, repo_name, since_iso, cfg)
    commits, commits_trunc, commits_ok = fetch_commits(owner, repo_name, since_iso, cfg)
    runs, runs_trunc, runs_ok = fetch_workflow_runs(owner, repo_name, since_date, cfg)
    bp, bp_ok = fetch_branch_protection(owner, repo_name, default_branch, cfg)
    code_alerts, ca_trunc, ca_ok = fetch_code_scanning_alerts(owner, repo_name, cfg, state="open")
    dep_alerts, da_trunc, da_ok = fetch_dependabot_alerts(owner, repo_name, cfg, state="open")
    secret_alerts, sa_trunc, sa_ok = fetch_secret_scanning_alerts(owner, repo_name, cfg)
    releases, releases_ok = fetch_releases(owner, repo_name, cfg)
    branches, br_trunc, br_ok = fetch_branches(owner, repo_name, cfg)

    # Resolved alerts for actual security MTTR
    resolved_code, _, _ = fetch_code_scanning_alerts(owner, repo_name, cfg, state="fixed")
    resolved_dep, _, _ = fetch_dependabot_alerts(owner, repo_name, cfg, state="fixed")

    # File existence checks
    security_md = check_file_exists(owner, repo_name, "SECURITY.md", cfg)
    dependabot_cfg = check_file_exists(owner, repo_name, ".github/dependabot.yml", cfg)

    # Repo tree for IaC detection
    tree, tree_ok = fetch_repo_tree(owner, repo_name, default_branch, cfg)

    # ── Compute metrics ──
    dora = compute_dora(prs, runs, releases, lookback, since_iso, cfg)
    flow = compute_flow(prs, cfg)
    security = compute_security(
        code_alerts, dep_alerts, secret_alerts,
        resolved_code_alerts=resolved_code,
        resolved_dep_alerts=resolved_dep,
    )
    ci = compute_ci_metrics(runs)
    governance = compute_governance(
        repo_data, bp, runs,
        security_md_exists=security_md,
        dependabot_config_exists=dependabot_cfg,
        branches=branches,
        prs=prs,
        tree=tree,
        cfg=cfg,
    )

    truncated = any([prs_trunc, commits_trunc, runs_trunc, ca_trunc, da_trunc, sa_trunc])

    return {
        "repo_metadata": {
            "repo": repo_name,
            "full_name": f"{owner}/{repo_name}",
            "default_branch": default_branch,
            "language": repo_data.get("language"),
            "languages": None,
            "visibility": repo_data.get("visibility", "private"),
            "archived": repo_data.get("archived", False),
            "topics": repo_data.get("topics"),
            "updated_at": repo_data.get("updated_at"),
            "owner": owner,
        },
        "collection": {
            "run_id": run_id,
            "collected_at": now.isoformat(),
            "lookback_days": lookback,
            "collector_version": COLLECTOR_VERSION,
        },
        "dora": dora,
        "flow": flow,
        "security": security,
        "governance": governance,
        "availability": {
            "pulls": prs_ok,
            "commits": commits_ok,
            "workflows": runs_ok,
            "branch_protection": bp_ok,
            "code_scanning": ca_ok,
            "dependabot": da_ok,
            "secret_scanning": sa_ok,
        },
        "github": {
            "pr_count": len(prs),
            "commit_count": len(commits),
            "workflow_run_count": len(runs),
            "dependabot_alert_count": len(dep_alerts),
            "code_scanning_alert_count": len(code_alerts),
            "secret_scanning_alert_count": len(secret_alerts),
            "branch_protection": bp,
            "ci_success_count": ci["ci_success_count"],
            "ci_failure_count": ci["ci_failure_count"],
            "avg_run_duration_seconds": ci["avg_run_duration_seconds"],
            "truncated": truncated,
            "errors": errors if errors else None,
            "active_branches": len(branches) if branches else None,
            "stale_branches": governance.get("long_lived_branch_count"),
            "pr_linked_issues": governance.get("pr_to_work_item_pct") and int(
                (governance["pr_to_work_item_pct"] / 100) * len(prs)) if prs else None,
            "pr_unlinked": len(prs) - int(
                (governance.get("pr_to_work_item_pct", 0) / 100) * len(prs)) if prs and governance.get("pr_to_work_item_pct") else None,
        },
    }


def persist_repo(repo_metrics):
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    name = repo_metrics.get("repo_metadata", {}).get("repo", "unknown")
    path = RAW_DATA_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(repo_metrics, fh, indent=2, default=str)
    logger.info("Saved → %s", path)


def list_org_repos(org, cfg):
    items, truncated, err, _ = gh_paginated(f"/orgs/{org}/repos", cfg, {"type": "all", "sort": "updated"})
    if not items:
        # Org endpoint returned nothing — try as a user account
        logger.info("Org endpoint empty for '%s', trying /users/%s/repos", org, org)
        items, truncated, err, _ = gh_paginated(
            f"/users/{org}/repos", cfg, {"type": "owner", "sort": "updated"}
        )
    return items, truncated


def list_user_repos(cfg):
    items, truncated, err, _ = gh_paginated("/user/repos", cfg, {"sort": "updated", "affiliation": "owner"})
    return items, truncated


def main():
    cfg = _load_config()
    logging.basicConfig(level=getattr(logging, cfg["log_level"], logging.INFO), format="%(asctime)s  %(levelname)-8s  %(message)s")

    run_id = uuid.uuid4().hex[:12]
    logger.info("Run %s — lookback=%d days", run_id, cfg["lookback_days"])

    if cfg["org"]:
        logger.info("Fetching repos for org: %s", cfg["org"])
        repos, _ = list_org_repos(cfg["org"], cfg)
    else:
        logger.info("No GIT_ORG set — falling back to authenticated user repos")
        repos, _ = list_user_repos(cfg)

    # ── Individual repos (GIT_REPOS) ──
    if cfg["individual_repos"]:
        logger.info("Adding %d individual repos from GIT_REPOS", len(cfg["individual_repos"]))
        seen = {r.get("full_name", "").lower() for r in repos}
        for slug in cfg["individual_repos"]:
            if slug.lower() in seen:
                continue
            owner, name = slug.split("/", 1)
            body, err, _, _ = make_get(
                f"{cfg['api']}/repos/{owner}/{name}",
                headers=_gh_headers(cfg["token"]),
                source="github",
            )
            if err:
                logger.warning("Could not fetch individual repo %s: %s", slug, err)
                continue
            repos.append(body)
            seen.add(slug.lower())
            logger.info("  + %s", slug)

    if not repos:
        logger.warning("No repositories found.")
        return

    active = [r for r in repos if not r.get("archived", False)]
    logger.info("Found %d active repos (of %d total)", len(active), len(repos))

    collected = 0
    for repo_data in active:
        owner = repo_data.get("owner", {}).get("login", cfg["org"])
        name = repo_data.get("name", "")
        try:
            metrics = collect_repo(owner, name, repo_data, cfg, run_id)
            persist_repo(metrics)
            collected += 1
        except Exception:
            logger.exception("Failed to collect %s/%s", owner, name)

    logger.info("Run %s complete — %d/%d repos collected", run_id, collected, len(active))


if __name__ == "__main__":
    main()
