# Tests Directory Structure

This directory contains all test files organized by category and purpose.

## Directory Structure

```
tests/
├── README.md                 # This file
├── api/                     # API endpoint tests
│   ├── test_*.py           # API-specific tests
│   └── test_dataset_deletion.py  # Dataset deletion API tests
├── frontend/                # Frontend and UI tests
│   ├── test_*.py           # Frontend-specific tests
│   └── test_connectionParser.ts  # TypeScript tests
├── integration/             # Integration tests
│   ├── comprehensive_test.py    # Full system integration test
│   └── test_*.py           # Integration tests
├── unit/                    # Unit tests
│   ├── test_s3_connection.py      # S3 connectivity tests
│   ├── test_mindsdb_*.py          # MindsDB service tests
│   └── test_*.py           # Other unit tests
└── utils/                   # Utility and debug files
    ├── debug_*.py          # Debug scripts
    ├── dataset_file_manager.py    # Utility scripts
    └── test_*_fix.py       # One-off fix scripts
```

## Test Categories

### Unit Tests (`unit/`)
- **Purpose**: Test individual components/functions in isolation
- **Examples**: S3 connection, MindsDB service methods, data parsing
- **Run with**: `pytest tests/unit/`

### API Tests (`api/`)
- **Purpose**: Test REST API endpoints and responses
- **Examples**: Dataset CRUD operations, authentication, data sharing
- **Run with**: `pytest tests/api/`

### Frontend Tests (`frontend/`)
- **Purpose**: Test UI components and frontend functionality
- **Examples**: User interface tests, form validation, component rendering
- **Run with**: `pytest tests/frontend/` or frontend testing framework

### Integration Tests (`integration/`)
- **Purpose**: Test complete workflows and system interactions
- **Examples**: End-to-end data upload, chat functionality, connector workflows
- **Run with**: `pytest tests/integration/`

### Utilities (`utils/`)
- **Purpose**: Debug scripts, utilities, and one-off fixes
- **Examples**: Database cleanup, system validation, debugging tools
- **Note**: These are typically not run as part of regular test suites

## Running Tests

### All Tests
```bash
pytest tests/
```

### Specific Category
```bash
pytest tests/unit/          # Unit tests only
pytest tests/api/           # API tests only
pytest tests/integration/   # Integration tests only
```

### Specific Test File
```bash
pytest tests/unit/test_s3_connection.py
pytest tests/api/test_dataset_deletion.py
```

## Test Data Files

Test data files are kept in their respective test directories:
- `test_data.csv`, `test_data.json` - Sample data for testing
- `test_document.txt`, `test_preview.csv` - Document test files

## Notes

- All test files follow the naming convention `test_*.py`
- Utility and debug scripts are kept in `utils/` to avoid confusion with actual tests
- Integration tests may require running services (backend, MindsDB, etc.)
- Some tests may require environment variables or configuration files