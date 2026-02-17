#!/usr/bin/env python3
"""
Work Item Collector (v1)
========================
Fetches work items (epics, stories, tasks, bugs) from **Jira** or
**Azure DevOps** and enriches per-repo raw JSON with a ``work_items``
section containing cycle time, lead time, and PR linkage metrics.

Source selection
----------------
If ``JIRA_URL`` is set the Jira REST API is used.
If ``ADO_ORG`` is set the Azure DevOps REST API is used.
Both can be configured simultaneously — Jira takes precedence.

Environment variables
---------------------
Jira:
    JIRA_URL      — e.g. https://myorg.atlassian.net
    JIRA_TOKEN    — Personal Access Token (base64 email:token)
    JIRA_USER     — Email address for basic auth
    JIRA_PROJECT  — Comma-separated project keys (optional, all if blank)
    JIRA_JQL      — Custom JQL filter (optional)

Azure DevOps:
    ADO_ORG       — Organisation name
    ADO_PROJECT   — Project name
    ADO_TOKEN     — Personal Access Token

Common:
    LOOKBACK_DAYS — default 30
    LOG_LEVEL     — default INFO
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from collectors.common import (
    CollectorError,
    is_configured,
    make_get,
    require_env,
    utc_now,
)

COLLECTOR_VERSION = "1.0.0"

logger = logging.getLogger("workitem-collector")

RAW_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "raw"

# ---------------------------------------------------------------------------
# Jira helpers
# ---------------------------------------------------------------------------

_JIRA_DONE_STATUSES = {"done", "closed", "resolved", "completed"}


def _jira_headers(url: str, user: str, token: str) -> Dict[str, str]:
    cred = base64.b64encode(f"{user}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {cred}",
        "Content-Type": "application/json",
    }


def fetch_jira_issues(
    url: str,
    user: str,
    token: str,
    project_keys: List[str],
    lookback: int,
    custom_jql: str = "",
) -> List[Dict[str, Any]]:
    """Fetch issues from Jira REST v2 search API."""
    since = (datetime.now(timezone.utc) - timedelta(days=lookback)).strftime("%Y-%m-%d")
    if custom_jql:
        jql = custom_jql
    else:
        project_clause = ""
        if project_keys:
            keys = ", ".join(f'"{k}"' for k in project_keys)
            project_clause = f"project IN ({keys}) AND "
        jql = f"{project_clause}updated >= '{since}' ORDER BY updated DESC"

    headers = _jira_headers(url, user, token)
    issues: List[Dict] = []
    start = 0
    max_results = 100
    max_pages = 20

    for _ in range(max_pages):
        body, err, status, _ = make_get(
            f"{url.rstrip('/')}/rest/api/2/search",
            headers=headers,
            params={
                "jql": jql,
                "startAt": str(start),
                "maxResults": str(max_results),
                "fields": "summary,status,issuetype,created,updated,"
                          "resolutiondate,assignee,labels,priority,"
                          "customfield_10016",  # story points
            },
            source="jira",
        )
        if err:
            logger.warning("Jira search error: %s", err)
            break
        batch = (body or {}).get("issues", [])
        issues.extend(batch)
        total = (body or {}).get("total", 0)
        start += len(batch)
        if start >= total or not batch:
            break

    logger.info("Fetched %d Jira issues (total=%d)", len(issues), total if body else 0)
    return issues


def _parse_jira_item(issue: Dict) -> Dict[str, Any]:
    """Normalise a single Jira issue into a unified work item dict."""
    fields = issue.get("fields", {})
    created = fields.get("created")
    resolved = fields.get("resolutiondate")
    status = (fields.get("status") or {}).get("name", "")
    issue_type = (fields.get("issuetype") or {}).get("name", "Task")

    cycle_hours = None
    lead_hours = None
    if created and resolved:
        try:
            c = datetime.fromisoformat(created.replace("Z", "+00:00"))
            r = datetime.fromisoformat(resolved.replace("Z", "+00:00"))
            lead_hours = max(0, (r - c).total_seconds() / 3600)
            cycle_hours = lead_hours  # Jira doesn't expose "in-progress" start natively
        except (ValueError, TypeError):
            pass

    return {
        "key": issue.get("key", ""),
        "title": fields.get("summary", ""),
        "type": issue_type,
        "status": status,
        "created": created,
        "resolved": resolved,
        "cycle_time_hours": round(cycle_hours, 2) if cycle_hours else None,
        "lead_time_hours": round(lead_hours, 2) if lead_hours else None,
        "labels": fields.get("labels", []),
    }


# ---------------------------------------------------------------------------
# Azure DevOps helpers
# ---------------------------------------------------------------------------


def _ado_headers(token: str) -> Dict[str, str]:
    cred = base64.b64encode(f":{token}".encode()).decode()
    return {
        "Authorization": f"Basic {cred}",
        "Content-Type": "application/json",
    }


def fetch_ado_items(
    org: str,
    project: str,
    token: str,
    lookback: int,
) -> List[Dict[str, Any]]:
    """Fetch work items via Azure DevOps WIQL + batch API."""
    since = (datetime.now(timezone.utc) - timedelta(days=lookback)).strftime("%Y-%m-%dT00:00:00Z")
    headers = _ado_headers(token)

    # WIQL query
    wiql_url = f"https://dev.azure.com/{org}/{project}/_apis/wit/wiql?api-version=7.1"
    wiql_body = {
        "query": (
            f"SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.TeamProject] = '{project}' "
            f"AND [System.ChangedDate] >= '{since}' "
            f"ORDER BY [System.ChangedDate] DESC"
        )
    }
    # WIQL uses POST
    import requests
    resp = requests.post(wiql_url, json=wiql_body, headers=headers, timeout=30)
    if resp.status_code != 200:
        logger.warning("ADO WIQL error %d: %s", resp.status_code, resp.text[:200])
        return []

    ids = [wi["id"] for wi in resp.json().get("workItems", [])]
    if not ids:
        return []

    # Batch fetch (max 200 per call)
    items: List[Dict] = []
    for i in range(0, len(ids), 200):
        batch_ids = ids[i: i + 200]
        ids_str = ",".join(str(x) for x in batch_ids)
        fields = (
            "System.Id,System.Title,System.WorkItemType,System.State,"
            "System.CreatedDate,Microsoft.VSTS.Common.ClosedDate,"
            "System.AssignedTo,System.Tags"
        )
        batch_url = (
            f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems"
            f"?ids={ids_str}&fields={fields}&api-version=7.1"
        )
        body, err, status, _ = make_get(batch_url, headers=headers, source="ado")
        if err:
            logger.warning("ADO batch error: %s", err)
            continue
        items.extend((body or {}).get("value", []))

    logger.info("Fetched %d ADO work items", len(items))
    return items


def _parse_ado_item(wi: Dict) -> Dict[str, Any]:
    """Normalise a single ADO work item."""
    fields = wi.get("fields", {})
    created = fields.get("System.CreatedDate")
    closed = fields.get("Microsoft.VSTS.Common.ClosedDate")
    state = fields.get("System.State", "")
    wi_type = fields.get("System.WorkItemType", "Task")

    cycle_hours = None
    lead_hours = None
    if created and closed:
        try:
            c = datetime.fromisoformat(created.replace("Z", "+00:00"))
            r = datetime.fromisoformat(closed.replace("Z", "+00:00"))
            lead_hours = max(0, (r - c).total_seconds() / 3600)
            cycle_hours = lead_hours
        except (ValueError, TypeError):
            pass

    return {
        "key": str(wi.get("id", "")),
        "title": fields.get("System.Title", ""),
        "type": wi_type,
        "status": state,
        "created": created,
        "resolved": closed,
        "cycle_time_hours": round(cycle_hours, 2) if cycle_hours else None,
        "lead_time_hours": round(lead_hours, 2) if lead_hours else None,
        "labels": [t.strip() for t in (fields.get("System.Tags") or "").split(";") if t.strip()],
    }


# ---------------------------------------------------------------------------
# Aggregation per-repo
# ---------------------------------------------------------------------------


def aggregate_work_items(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary metrics from a list of normalised work items."""
    total = len(items)
    done = [i for i in items if (i.get("status") or "").lower() in _JIRA_DONE_STATUSES | {"closed", "done", "resolved", "completed", "removed"}]
    completed = len(done)

    cycle_times = [i["cycle_time_hours"] for i in items if i.get("cycle_time_hours") is not None]
    lead_times = [i["lead_time_hours"] for i in items if i.get("lead_time_hours") is not None]

    by_type: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    for i in items:
        t = i.get("type", "Other")
        by_type[t] = by_type.get(t, 0) + 1
        s = i.get("status", "Unknown")
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "total_items": total,
        "completed_items": completed,
        "avg_cycle_time_hours": round(sum(cycle_times) / len(cycle_times), 2) if cycle_times else None,
        "avg_lead_time_hours": round(sum(lead_times) / len(lead_times), 2) if lead_times else None,
        "items_by_type": by_type,
        "items_by_status": by_status,
    }


# ---------------------------------------------------------------------------
# Repo matching
# ---------------------------------------------------------------------------


def match_items_to_repos(
    items: List[Dict[str, Any]],
    repo_names: Set[str],
) -> Tuple[Dict[str, List[Dict]], List[Dict]]:
    """Try to match work items to repos via labels or title mentions.

    Returns (matched_dict, unmatched_list).
    """
    matched: Dict[str, List[Dict]] = {}
    unmatched: List[Dict] = []

    for item in items:
        labels = [l.lower() for l in item.get("labels", [])]
        title = (item.get("title") or "").lower()
        found = False
        for rn in repo_names:
            rn_lower = rn.lower()
            if rn_lower in labels or rn_lower in title:
                matched.setdefault(rn, []).append(item)
                found = True
                break
        if not found:
            unmatched.append(item)

    return matched, unmatched


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def load_raw_repos() -> Dict[str, Tuple[Path, Dict]]:
    result: Dict[str, Tuple[Path, Dict]] = {}
    if not RAW_DATA_DIR.exists():
        return result
    for p in sorted(RAW_DATA_DIR.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            meta = data.get("repo_metadata") or data
            name = (meta.get("repo") or p.stem).lower()
            result[name] = (p, data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skip %s: %s", p.name, exc)
    return result


NR = "N/R"


def _disabled_workitems_section() -> Dict[str, Any]:
    """Stub when neither Jira nor ADO is configured."""
    return {
        "integration_status": "disabled",
        "total_items": NR,
        "completed_items": NR,
        "avg_cycle_time_hours": NR,
        "avg_lead_time_hours": NR,
        "items_by_type": {},
        "items_by_status": {},
    }


def _disabled_org_summary() -> Dict[str, Any]:
    return {
        "source": "none",
        "integration_status": "disabled",
        "collector_version": COLLECTOR_VERSION,
        "total_items": NR,
        "completed_items": NR,
        "avg_cycle_time_hours": NR,
        "avg_lead_time_hours": NR,
        "items_by_type": {},
        "items_by_status": {},
    }


def main() -> None:
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    lookback = int(os.environ.get("LOOKBACK_DAYS", "30"))
    jira_url = os.environ.get("JIRA_URL", "").strip()
    jira_user = os.environ.get("JIRA_USER", "").strip()
    jira_token = os.environ.get("JIRA_TOKEN", "").strip()
    ado_org = os.environ.get("ADO_ORG", "").strip()
    ado_project = os.environ.get("ADO_PROJECT", "").strip()
    ado_token = os.environ.get("ADO_TOKEN", "").strip()

    jira_ready = is_configured(jira_url, jira_user, jira_token)
    ado_ready = is_configured(ado_org, ado_project, ado_token)

    if not jira_ready and not ado_ready:
        logger.info(
            "No work-item source configured (Jira/ADO) — writing N/R stubs "
            "(integration_status=disabled)"
        )
        now = utc_now()
        org_stub = _disabled_org_summary()
        org_stub["collected_at"] = now.isoformat()

        meta_dir = Path(__file__).resolve().parents[2] / "data" / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_path = meta_dir / "workitems_summary.json"
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(org_stub, fh, indent=2, default=str)
        logger.info("Wrote disabled org summary → %s", meta_path)

        repos = load_raw_repos()
        for repo_name in repos:
            path, raw = repos[repo_name]
            raw["work_items"] = {
                **_disabled_workitems_section(),
                "collected_at": now.isoformat(),
            }
            raw.setdefault("availability", {})["work_items"] = False
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(raw, fh, indent=2, default=str)

        logger.info("Work items disabled — %d repos stamped with N/R", len(repos))
        return

    # ── Credentials present → normal collection ──
    all_items: List[Dict[str, Any]] = []
    source = "none"

    if jira_ready:
        source = "jira"
        project_keys = [
            k.strip() for k in os.environ.get("JIRA_PROJECT", "").split(",") if k.strip()
        ]
        custom_jql = os.environ.get("JIRA_JQL", "").strip()
        raw_issues = fetch_jira_issues(jira_url, jira_user, jira_token, project_keys, lookback, custom_jql)
        all_items = [_parse_jira_item(i) for i in raw_issues]
    elif ado_ready:
        source = "ado"
        raw_items = fetch_ado_items(ado_org, ado_project, ado_token, lookback)
        all_items = [_parse_ado_item(i) for i in raw_items]

    logger.info("Source=%s — %d normalised work items", source, len(all_items))
    if not all_items:
        logger.info("No work items found — nothing to enrich")
        return

    # Load repos and match
    repos = load_raw_repos()
    if not repos:
        logger.warning("No raw repo files found in %s", RAW_DATA_DIR)
        return

    matched, unmatched = match_items_to_repos(all_items, set(repos.keys()))
    logger.info(
        "Matched %d repos, %d unmatched items",
        len(matched),
        len(unmatched),
    )

    # Compute org-level summary
    org_summary = aggregate_work_items(all_items)
    org_summary["source"] = source
    org_summary["integration_status"] = "enabled"
    org_summary["collected_at"] = utc_now().isoformat()
    org_summary["collector_version"] = COLLECTOR_VERSION

    # Save org-level meta
    meta_dir = Path(__file__).resolve().parents[2] / "data" / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_path = meta_dir / "workitems_summary.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(org_summary, fh, indent=2, default=str)
    logger.info("Saved org summary → %s", meta_path)

    # Enrich per-repo
    enriched = 0
    for repo_name in repos:
        path, raw = repos[repo_name]
        if repo_name in matched:
            repo_items = matched[repo_name]
            summary = aggregate_work_items(repo_items)
        else:
            summary = {
                "total_items": 0,
                "completed_items": 0,
                "avg_cycle_time_hours": None,
                "avg_lead_time_hours": None,
                "items_by_type": {},
                "items_by_status": {},
            }

        raw["work_items"] = summary
        raw.setdefault("availability", {})["work_items"] = len(matched.get(repo_name, [])) > 0

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, indent=2, default=str)
        enriched += 1

    logger.info(
        "Work item collection complete — %d repos enriched, source=%s",
        enriched,
        source,
    )


if __name__ == "__main__":
    main()
