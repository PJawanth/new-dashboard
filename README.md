# Engineering Intelligence Dashboard

Enterprise-grade Engineering Intelligence Dashboard combining DevOps (DORA + Flow), DevSecOps, Code Quality, Governance, Value Stream, Logging Monitor, and per-repository drilldowns.

## Architecture

```
new-dashboard/
├─ apps/dashboard-ui/            React 18 + Vite 5 + Tailwind CSS 3
│  └─ src/
│     ├─ context/                DashboardContext (data loader)
│     ├─ components/             KpiTile, Card, Badge, InfoTooltip,
│     │                          TrendChart, DonutChart, RepoTable,
│     │                          Layout (collapsible sidebar)
│     └─ pages/                  Overview, DevOps, DevSecOps, CodeQuality,
│                                Governance, ValueStream, LoggingMonitor,
│                                Repos, RepoDetail
├─ collectors/
│  ├─ common.py                  Shared HTTP helpers (retry, pagination)
│  ├─ github/collect.py          GitHub REST API → data/raw/
│  ├─ sonar/collect_sonar.py     SonarQube / SonarCloud enrichment
│  ├─ snyk/collect_snyk.py       Snyk REST API enrichment
│  ├─ servicenow/collect_sn.py   ServiceNow change management
│  └─ logging/collect_logs.py    GitHub Actions workflow metrics
├─ aggregator/
│  ├─ normalize.py               Null-safe math helpers
│  ├─ scoring.py                 Weighted composite scoring engine
│  ├─ aggregate.py               Raw → dashboard.json aggregation
│  └─ schemas/                   Pydantic v2 contracts
├─ data/
│  ├─ raw/                       Per-repo JSON (git-ignored)
│  ├─ aggregated/                dashboard.json (consumed by UI)
│  ├─ history/                   Daily snapshots (YYYY-MM-DD/)
│  └─ meta/                      Org-level metadata
├─ .github/workflows/
│  ├─ collect_and_aggregate.yml  Daily cron → collect → aggregate → commit
│  └─ build_and_deploy_ui.yml    Build React → deploy to GitHub Pages
├─ Makefile
└─ requirements.txt
```

### Data Pipeline

```
Collectors (GitHub, Sonar, Snyk, ServiceNow, Logging)
    │
    ▼
data/raw/*.json   (per-repo payloads)
    │
    ▼
Aggregator   →  scoring engine  →  normalize helpers
    │
    ▼
data/aggregated/dashboard.json   →   React UI
data/history/YYYY-MM-DD/dashboard.json
```

### Scoring Model

```
Engineering Health Score (0–100)
  = Delivery   (25%)   ← DORA metrics
  + Quality    (25%)   ← coverage, cycle time, tech debt
  + Security   (30%)   ← critical/high vulns, MTTR, secrets
  + Governance (20%)   ← branch protection, scanning adoption
```

Thresholds are configurable in `aggregator/scoring.py`.

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- A GitHub PAT with `repo`, `read:org`, `security_events` scopes

### 1. Install dependencies

```bash
make install
```

### 2. Set environment variables

```bash
# Required
export GITHUB_TOKEN="ghp_..."
export GITHUB_ORG="your-org"

# Optional — enrichment collectors
export SONAR_URL="https://sonarcloud.io"      # or self-hosted URL
export SONAR_TOKEN="squ_..."
export SNYK_TOKEN="snyk_..."
export SNYK_ORG="your-snyk-org-id"
export SNOW_INSTANCE="your-company.service-now.com"
export SNOW_USER="api_user"
export SNOW_PASSWORD="api_password"

# Tuneable
export LOOKBACK_DAYS=30                       # default 30
```

### 3. Run the full pipeline

```bash
make collect-all          # runs all collectors → aggregates → dashboard.json
```

Or run collectors individually:

```bash
make collect-github       # GitHub metrics → data/raw/
make collect-sonar        # Enrich with SonarQube data
make collect-snyk         # Enrich with Snyk vulnerabilities
make collect-servicenow   # Enrich with ServiceNow change data
make collect-logs         # GitHub Actions workflow metrics
make aggregate            # Aggregate → data/aggregated/dashboard.json
```

### 4. Start the dashboard

```bash
make ui                   # copies dashboard.json → starts Vite dev server
```

Open [http://localhost:3000](http://localhost:3000)

### 5. Production build

```bash
make build-ui             # outputs to apps/dashboard-ui/dist/
```

## Dashboard Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Executive Overview | Eng health, DORA summary, risk & health distributions |
| `/devops` | DevOps | DORA + Flow KPIs, pipeline reliability per repo |
| `/devsecops` | DevSecOps | Severity breakdown, secrets, gate pass rate |
| `/quality` | Code Quality | Coverage, bugs, code smells, language distribution |
| `/governance` | Governance & Audit | Adoption %, per-repo governance status |
| `/value-stream` | Value Stream | Idea-to-prod, coding/review/deploy times |
| `/logging` | Logging Monitor | GitHub Actions runs, error rate |
| `/repos` | Repositories | Sortable + searchable repo table |
| `/repos/:name` | Repo Detail | Per-repo DORA, flow, security, governance drilldown |

## CI/CD — GitHub Actions

### `collect_and_aggregate.yml`

- **Trigger**: Daily at 06:00 UTC + manual dispatch
- **Steps**: Install Python → `make collect-all` → commit data to `main`
- **Concurrency**: Single-run lock (`collect-metrics` group)
- **Loop prevention**: Commits tagged `[skip ci]`

### `build_and_deploy_ui.yml`

- **Trigger**: Push to `main` (UI or data changes) + after successful collect workflow
- **Steps**: Install Node → copy `dashboard.json` → `npm run build` → deploy to GitHub Pages
- **Cache**: npm dependencies cached via `actions/setup-node`

### Required Secrets & Variables

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `GH_PAT` | Secret | Yes | GitHub PAT (`repo`, `read:org`, `security_events`) |
| `GITHUB_ORG` | Variable | Yes | Target GitHub organisation slug |
| `SONAR_URL` | Secret | No | SonarQube/Cloud base URL |
| `SONAR_TOKEN` | Secret | No | SonarQube user token |
| `SNYK_TOKEN` | Secret | No | Snyk API token |
| `SNYK_ORG` | Secret | No | Snyk org ID |
| `SNOW_INSTANCE` | Secret | No | ServiceNow instance hostname |
| `SNOW_USER` | Secret | No | ServiceNow API username |
| `SNOW_PASSWORD` | Secret | No | ServiceNow API password |

## License

Internal / Proprietary
