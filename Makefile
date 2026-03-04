.PHONY: help install \
       collect-github collect-sonar collect-snyk collect-servicenow collect-logs collect-workitems collect-all \
       aggregate pipeline \
       ui build-ui copy-data dev build \
       clean

PYTHON   ?= python
NPM      ?= npm
UI_DIR   := apps/dashboard-ui

# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install Python + Node dependencies
	$(PYTHON) -m pip install -r requirements.txt
	cd $(UI_DIR) && $(NPM) install

# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------

collect-github: ## Collect GitHub metrics → data/raw/
	$(PYTHON) -m collectors.github.collect

collect-sonar: ## Enrich raw repos with SonarQube data
	-$(PYTHON) -m collectors.sonar.collect_sonar

collect-snyk: ## Enrich raw repos with Snyk vulnerability data
	-$(PYTHON) -m collectors.snyk.collect_snyk

collect-servicenow: ## Enrich raw repos + org summary from ServiceNow
	-$(PYTHON) -m collectors.servicenow.collect_servicenow

collect-logs: ## Collect GitHub Actions logging metrics
	-$(PYTHON) -m collectors.logging.collect_logs

collect-workitems: ## Collect Jira/ADO work item metrics
	-$(PYTHON) -m collectors.workitems.collect_workitems

collect-all: ## Run every collector then aggregate
	$(MAKE) collect-github
	-$(MAKE) collect-sonar
	-$(MAKE) collect-snyk
	-$(MAKE) collect-servicenow
	-$(MAKE) collect-logs
	-$(MAKE) collect-workitems
	$(MAKE) aggregate

# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

aggregate: ## Aggregate raw data → dashboard.json + history snapshot
	$(PYTHON) -m aggregator.aggregate

pipeline: collect-all ## Alias: full collection → aggregation pipeline

# ---------------------------------------------------------------------------
# Dashboard UI
# ---------------------------------------------------------------------------

copy-data: ## Copy dashboard.json into the React public dir
	@mkdir -p $(UI_DIR)/public
	cp data/aggregated/dashboard.json $(UI_DIR)/public/dashboard.json 2>/dev/null || true

ui: copy-data ## Start the React dev server (alias for dev)
	cd $(UI_DIR) && $(NPM) run dev

dev: ui ## Start the React dev server

build-ui: copy-data ## Build the React dashboard for production
	cd $(UI_DIR) && $(NPM) run build

build: build-ui ## Alias for build-ui

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

clean: ## Remove build artefacts & caches
	rm -rf $(UI_DIR)/dist $(UI_DIR)/node_modules/.cache
	find data/aggregated -name '*.json' -delete 2>/dev/null || true
