.DEFAULT_GOAL := help
PYTHON ?= python3
TF_DIR := infra/terraform

.PHONY: help install lint format typecheck test check run-dry-run site-preview tf-init tf-plan tf-apply clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## Install the package with development dependencies
	$(PYTHON) -m pip install -e ".[dev]"

lint: ## Static analysis
	ruff check .
	ruff format --check .

format: ## Auto-format the code base
	ruff check --fix .
	ruff format .

typecheck: ## Strict type checking
	mypy

test: ## Run the test suite (stdlib runner, no dependencies required)
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -t . -v

check: lint typecheck test ## Everything CI runs

run-dry-run: ## Compute today's lists against the real APIs without writing anything
	PYTHONPATH=src $(PYTHON) -m streaming_top_series --dry-run

site-preview: ## Build today's feeds (dry-run) into web/data and serve the website on :8765
	SITE_DIR=web/data PYTHONPATH=src $(PYTHON) -m streaming_top_series --dry-run
	$(PYTHON) -m http.server 8765 --bind 127.0.0.1 -d web

tf-init: ## Initialise Terraform (requires infra/terraform/backend.hcl)
	terraform -chdir=$(TF_DIR) init -backend-config=backend.hcl

tf-plan: ## Preview infrastructure changes
	terraform -chdir=$(TF_DIR) plan

tf-apply: ## Apply infrastructure changes
	terraform -chdir=$(TF_DIR) apply

clean: ## Remove build artefacts and caches
	rm -rf $(TF_DIR)/build .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
