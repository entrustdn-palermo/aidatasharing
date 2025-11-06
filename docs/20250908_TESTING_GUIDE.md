# Comprehensive Testing Guide

## 🧪 Testing Overview

This guide provides comprehensive information about testing the AI Share Platform, including test organization, execution, and best practices.

## 📋 Table of Contents

- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Writing Tests](#writing-tests)
- [Test Categories](#test-categories)
- [Fixtures and Utilities](#fixtures-and-utilities)
- [Continuous Integration](#continuous-integration)
- [Troubleshooting](#troubleshooting)

## 📁 Test Structure

```
tests/
├── TESTING_GUIDE.md        # This comprehensive guide
├── README.md               # Quick reference for tests
├── conftest.py            # Shared fixtures and configuration
├── api/                   # API endpoint tests
│   ├── test_auth.py      # Authentication tests
│   ├── test_datasets.py  # Dataset API tests
│   └── test_connectors.py # Connector API tests
├── frontend/              # Frontend tests
│   ├── test_ui.py        # UI component tests
│   └── test_flow.py      # User flow tests
├── integration/           # Integration tests
│   ├── test_e2e.py       # End-to-end tests
│   └── test_workflow.py  # Workflow tests
├── unit/                  # Unit tests
│   ├── test_models.py    # Database model tests
│   ├── test_services.py  # Service layer tests
│   └── test_utils.py     # Utility function tests
└── utils/                 # Test utilities
    ├── fixtures.py       # Additional fixtures
    └── helpers.py        # Test helper functions
```

## 🚀 Running Tests

### Quick Start

```bash
# Install test dependencies
pip install -r test-requirements.txt

# Run all tests (except slow)
make test

# Run with coverage
make coverage
```

### Using Pytest Directly

```bash
# Run all tests
pytest

# Run specific category
pytest tests/unit/
pytest tests/api/
pytest tests/integration/

# Run specific file
pytest tests/unit/test_models.py

# Run specific test
pytest tests/unit/test_models.py::TestUserModel::test_create_user

# Run with markers
pytest -m unit          # Unit tests only
pytest -m "not slow"    # Skip slow tests
pytest -m api           # API tests only
```

### Using Make Commands

```bash
make test              # Run standard tests
make test-unit         # Unit tests only
make test-api          # API tests only
make test-integration  # Integration tests only
make test-frontend     # Frontend tests only
make test-all          # All tests including slow
make test-smoke        # Quick smoke tests
make test-parallel     # Run tests in parallel
make coverage          # Generate coverage report
make test-watch        # Auto-run tests on changes
```

## ✍️ Writing Tests

### Test Naming Convention

```python
# File naming
test_<module_name>.py

# Test class naming
class Test<ComponentName>:
    pass

# Test method naming
def test_<action>_<expected_result>():
    pass

# Example
class TestUserAuthentication:
    def test_login_with_valid_credentials_returns_token(self):
        pass
    
    def test_login_with_invalid_password_returns_401(self):
        pass
```

### Test Structure (AAA Pattern)

```python
def test_user_creation():
    # Arrange - Set up test data and conditions
    user_data = {
        "email": "test@example.com",
        "password": "SecurePass123!"
    }
    
    # Act - Execute the code being tested
    response = api_client.post("/api/users", json=user_data)
    
    # Assert - Verify the results
    assert response.status_code == 201
    assert response.json()["email"] == user_data["email"]
```

### Using Fixtures

```python
# In conftest.py or test file
@pytest.fixture
def sample_user(db_session):
    user = User(email="test@example.com", password="hashed")
    db_session.add(user)
    db_session.commit()
    return user

# In test
def test_get_user(api_client, sample_user, mock_auth):
    response = api_client.get(f"/api/users/{sample_user.id}")
    assert response.status_code == 200
    assert response.json()["email"] == sample_user.email
```

### Using Markers

```python
import pytest

@pytest.mark.unit
def test_password_hashing():
    # Unit test code
    pass

@pytest.mark.api
@pytest.mark.requires_db
def test_create_dataset_endpoint(api_client, db_session):
    # API test requiring database
    pass

@pytest.mark.slow
@pytest.mark.integration
def test_full_workflow():
    # Slow integration test
    pass
```

## 📊 Test Categories

### Unit Tests (`@pytest.mark.unit`)
- Test individual functions and methods
- Mock external dependencies
- Fast execution
- No database or network calls

```python
@pytest.mark.unit
def test_calculate_file_hash():
    content = b"test content"
    hash_value = calculate_hash(content)
    assert hash_value == "expected_hash"
```

### API Tests (`@pytest.mark.api`)
- Test REST endpoints
- Validate request/response
- Check status codes
- Verify data structure

```python
@pytest.mark.api
def test_get_datasets(api_client, mock_auth):
    response = api_client.get("/api/datasets")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

### Integration Tests (`@pytest.mark.integration`)
- Test component interactions
- Use real database
- Test workflows
- May include external services

```python
@pytest.mark.integration
def test_dataset_upload_workflow(api_client, db_session, s3_client):
    # Test complete upload workflow
    file_data = {"file": ("test.csv", b"data", "text/csv")}
    response = api_client.post("/api/datasets/upload", files=file_data)
    assert response.status_code == 201
    
    # Verify database entry
    dataset = db_session.query(Dataset).first()
    assert dataset is not None
    
    # Verify S3 upload
    assert s3_client.object_exists(dataset.file_path)
```

### Frontend Tests (`@pytest.mark.frontend`)
- Test UI components
- Validate user interactions
- Check rendering

```python
@pytest.mark.frontend
def test_login_form_validation(browser):
    browser.get("http://localhost:3000/login")
    browser.find_element_by_id("email").send_keys("invalid")
    browser.find_element_by_id("submit").click()
    error = browser.find_element_by_class("error")
    assert "Invalid email" in error.text
```

## 🔧 Fixtures and Utilities

### Available Fixtures (from conftest.py)

| Fixture | Description | Scope |
|---------|-------------|-------|
| `test_config` | Test configuration dict | session |
| `temp_dir` | Temporary directory | function |
| `mock_database` | Mocked database session | function |
| `mock_auth` | Mocked authentication | function |
| `mock_s3_client` | Mocked S3 client | function |
| `sample_dataset` | Sample dataset dict | function |
| `sample_connector` | Sample connector dict | function |
| `api_client` | FastAPI test client | function |
| `mock_mindsdb` | Mocked MindsDB connection | function |
| `mock_gemini` | Mocked Gemini AI | function |

### Creating Custom Fixtures

```python
# In conftest.py or test file
@pytest.fixture
def authenticated_client(api_client, test_config):
    # Login and get token
    response = api_client.post("/api/auth/login", json={
        "email": test_config["test_user"]["email"],
        "password": test_config["test_user"]["password"]
    })
    token = response.json()["access_token"]
    
    # Set authorization header
    api_client.headers["Authorization"] = f"Bearer {token}"
    return api_client
```

## 🔄 Continuous Integration

### GitHub Actions Configuration

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r test-requirements.txt
    
    - name: Run tests
      run: pytest --cov=backend --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

## 🐛 Troubleshooting

### Common Issues

#### 1. Import Errors
```bash
# Solution: Add backend to Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/backend"
```

#### 2. Database Connection Errors
```bash
# Solution: Use test database
export DATABASE_URL="sqlite:///./test.db"
```

#### 3. Slow Test Execution
```bash
# Solution: Run tests in parallel
pytest -n auto
# Or skip slow tests
pytest -m "not slow"
```

#### 4. Flaky Tests
```python
# Solution: Use retry decorator
@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_external_api_call():
    pass
```

### Debugging Tests

```bash
# Run with verbose output
pytest -vv

# Show print statements
pytest -s

# Drop into debugger on failure
pytest --pdb

# Show local variables on failure
pytest -l

# Stop on first failure
pytest -x
```

## 📈 Coverage Reports

### Generate Coverage Report

```bash
# Terminal report
pytest --cov=backend --cov-report=term

# HTML report
pytest --cov=backend --cov-report=html
# Open htmlcov/index.html in browser

# XML report (for CI)
pytest --cov=backend --cov-report=xml
```

### Coverage Configuration

```ini
# In pytest.ini
[coverage:run]
source = backend
omit = 
    */tests/*
    */migrations/*

[coverage:report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
```

## 🎯 Best Practices

1. **Keep Tests Independent**: Each test should be able to run in isolation
2. **Use Descriptive Names**: Test names should clearly indicate what they test
3. **Follow AAA Pattern**: Arrange, Act, Assert
4. **Mock External Dependencies**: Don't make real API calls or database connections in unit tests
5. **Use Fixtures**: Reuse common setup code
6. **Test Edge Cases**: Include tests for error conditions and boundary values
7. **Keep Tests Fast**: Use mocks and avoid slow operations when possible
8. **Clean Up**: Ensure tests clean up after themselves
9. **Document Complex Tests**: Add comments for non-obvious test logic
10. **Regular Maintenance**: Update tests when code changes

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Testing Best Practices](https://realpython.com/pytest-python-testing/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)