.PHONY: install
install: ## Install the virtual environment and install the pre-commit hooks
	@echo "🚀 Creating virtual environment using uv"
	@uv sync
	@uv run pre-commit install

.PHONY: check
check: ## Run code quality tools.
	@echo "🚀 Checking lock file consistency with 'pyproject.toml'"
	@uv lock --locked
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@echo "🚀 Static type checking: Running mypy"
	@uv run mypy
	@echo "🚀 Checking for obsolete dependencies: Running deptry"
	@cd packages/core && uv run deptry src
	@cd packages/cli && uv run deptry src

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@uv run python -m pytest --doctest-modules --cov=core --cov=cli --cov-report=term-missing

.PHONY: build
build: clean-build ## Build wheel file
	@echo "🚀 Creating wheel file"
	@uvx --from build pyproject-build --installer uv

.PHONY: clean-build
clean-build: ## Clean build artifacts
	@echo "🚀 Removing build artifacts"
	@uv run python -c "import shutil; import os; shutil.rmtree('dist') if os.path.exists('dist') else None"

.PHONY: docs-cli
docs-cli: ## Regenerate docs/cli-reference.md from the Typer app
	@uv run typer cli.app utils docs --name microfiche --title "CLI reference" --output docs/cli-reference.md

.PHONY: docs-test
docs-test: docs-cli ## Test if documentation can be built without warnings or errors
	@uv run mkdocs build -s

.PHONY: docs
docs: docs-cli ## Build and serve the documentation
	@uv run mkdocs serve

.PHONY: help
help:
	@uv run python -c "import re; \
	[[print(f'\033[36m{m[0]:<20}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
