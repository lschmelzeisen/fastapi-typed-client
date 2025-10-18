.SILENT:


# See: https://www.thapaliya.com/en/writings/well-documented-makefiles/
.PHONY: help
help: ## Show this help message.
	awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

.PHONY: venv
venv: ## Set up virtual environment.
	uv sync --quiet

.PHONY: test
test: venv ## Run tests.
	uv run pytest

test-examples: venv ## Run example tests.
	uv run pytest examples

.PHONY: format
format: venv format-py-imports format-py ## Format code.

.PHONY: format-py-imports
format-py-imports: venv
	uv run ruff check --select I --fix --quiet

.PHONY: format-py
format-py: venv
	uv run ruff format --quiet

.PHONY: format-check
format-check: venv
	uv run ruff format --check --quiet

.PHONY: typecheck
typecheck: venv ## Type-check code.
	uv run pyrefly check

.PHONY: lint
lint: venv lint-py format-check ## Lint code.

.PHONY: lint-py
lint-py: venv
	uv run ruff check --quiet