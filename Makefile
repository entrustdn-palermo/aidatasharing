.PHONY: help test test-unit test-integration test-api test-frontend test-all coverage lint format clean

help:
	@echo "Available commands:"
	@echo "  make test            - Run all tests (except slow)"
	@echo "  make test-unit       - Run unit tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo "  make test-api        - Run API tests only"
	@echo "  make test-frontend   - Run frontend tests only"
	@echo "  make test-all        - Run all tests including slow ones"
	@echo "  make test-smoke      - Run smoke tests (quick sanity check)"
	@echo "  make coverage        - Run tests with coverage report"
	@echo "  make lint            - Run code linters"
	@echo "  make format          - Format code with black and isort"
	@echo "  make clean           - Remove test artifacts"

# Run all tests except slow ones
test:
	pytest -m "not slow" --tb=short -v

# Run unit tests
test-unit:
	pytest tests/unit/ -v --tb=short

# Run integration tests
test-integration:
	pytest tests/integration/ -v --tb=short

# Run API tests
test-api:
	pytest tests/api/ -v --tb=short

# Run frontend tests
test-frontend:
	pytest tests/frontend/ -v --tb=short

# Run all tests including slow ones
test-all:
	pytest -v --tb=short

# Run smoke tests (basic functionality)
test-smoke:
	pytest -m smoke -v --tb=short

# Run tests with coverage
coverage:
	pytest --cov=backend --cov-report=html --cov-report=term -v
	@echo "Coverage report generated in htmlcov/index.html"

# Run tests in parallel (faster execution)
test-parallel:
	pytest -n auto -v --tb=short

# Run specific test file
test-file:
	@read -p "Enter test file path: " file; \
	pytest $$file -v --tb=short

# Run linters
lint:
	@echo "Running flake8..."
	flake8 backend/ tests/ --max-line-length=120 --exclude=venv,env,migrations
	@echo "Running pylint..."
	pylint backend/ tests/ --disable=C0111,R0903,W0613 || true
	@echo "Running mypy..."
	mypy backend/ --ignore-missing-imports || true

# Format code
format:
	@echo "Formatting with black..."
	black backend/ tests/ --line-length=120
	@echo "Sorting imports with isort..."
	isort backend/ tests/ --profile black --line-length=120

# Security scan
security:
	@echo "Running security scan with bandit..."
	bandit -r backend/ -ll
	@echo "Checking dependencies with safety..."
	safety check || true

# Clean test artifacts
clean:
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -f test.db
	rm -rf __pycache__/
	rm -rf .mypy_cache/
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete

# Run tests and generate HTML report
test-report:
	pytest --html=test_report.html --self-contained-html -v
	@echo "Test report generated: test_report.html"

# Watch tests (re-run on file changes)
test-watch:
	pytest-watch tests/ -v --tb=short