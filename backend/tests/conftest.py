"""
Pytest configuration and shared fixtures

This file contains pytest configuration and fixtures that are shared
across all test modules.
"""

import pytest
import os
from unittest.mock import Mock, MagicMock
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Import app components
from app.core.config import Settings
from app.models import Base, User, Dataset, Organization


@pytest.fixture(scope="session")
def test_encryption_key():
    """Generate a test encryption key for the entire test session"""
    return Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def set_test_encryption_key(test_encryption_key, monkeypatch):
    """Automatically set encryption key for all tests"""
    monkeypatch.setenv("ENCRYPTION_KEY", test_encryption_key)


@pytest.fixture(scope="session")
def test_database_url():
    """Test database URL (in-memory SQLite for speed)"""
    return "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_engine(test_database_url):
    """Create a test database engine"""
    engine = create_engine(
        test_database_url,
        connect_args={"check_same_thread": False}  # Needed for SQLite
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a test database session"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_db_session():
    """Create a mock database session for unit tests"""
    mock_session = Mock()
    mock_session.query = Mock(return_value=mock_session)
    mock_session.filter = Mock(return_value=mock_session)
    mock_session.first = Mock()
    mock_session.all = Mock(return_value=[])
    mock_session.add = Mock()
    mock_session.commit = Mock()
    mock_session.rollback = Mock()
    mock_session.refresh = Mock()
    return mock_session


@pytest.fixture
def test_user():
    """Create a test user"""
    return User(
        id=1,
        email="test@example.com",
        full_name="Test User",
        hashed_password="hashed_password_123",
        is_active=True,
        is_superuser=False,
        organization_id=1,
        role="member",
    )


@pytest.fixture
def test_superuser():
    """Create a test superuser"""
    return User(
        id=99,
        email="admin@example.com",
        full_name="Admin User",
        hashed_password="hashed_password_123",
        is_active=True,
        is_superuser=True,
        organization_id=1,
        role="admin",
    )


@pytest.fixture
def test_organization():
    """Create a test organization"""
    return Organization(
        id=1,
        name="Test Organization",
        slug="test-org",
        type="company",
        is_active=True,
    )


@pytest.fixture
def test_dataset():
    """Create a test dataset"""
    return Dataset(
        id=100,
        name="Test Dataset",
        description="A test dataset",
        user_id=1,
        organization_id=1,
        file_path="/data/test.csv",
        file_type="csv",
        file_size=1024,
        sharing_level="private",
        is_active=True,
    )


@pytest.fixture
def test_settings(test_encryption_key):
    """Create test settings"""
    return Settings(
        ENCRYPTION_KEY=test_encryption_key,
        DATABASE_URL="sqlite:///:memory:",
        SECRET_KEY="test_secret_key_123",
        ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=30,
    )


@pytest.fixture
def mock_permissions_service():
    """Create a mock permissions service"""
    from unittest.mock import AsyncMock

    mock_service = Mock()
    mock_service.check_dataset_access = AsyncMock(return_value=True)
    mock_service.require_dataset_access = AsyncMock()
    mock_service.check_org_permission = AsyncMock(return_value=True)
    return mock_service


@pytest.fixture
def mock_encryption_service(test_encryption_key):
    """Create a mock encryption service"""
    from app.core.encryption import EncryptionService
    import os

    os.environ["ENCRYPTION_KEY"] = test_encryption_key
    return EncryptionService()


@pytest.fixture
def sample_credentials():
    """Sample credentials for testing"""
    return {
        "username": "test_user",
        "password": "test_password_123",
        "api_key": "sk-1234567890abcdef",
        "database": "test_db",
        "host": "localhost",
        "port": 5432,
    }


@pytest.fixture
def sample_encrypted_credentials(mock_encryption_service, sample_credentials):
    """Sample encrypted credentials"""
    return mock_encryption_service.encrypt_dict(sample_credentials)


# Pytest markers for categorizing tests
def pytest_configure(config):
    """Configure custom pytest markers"""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow-running"
    )
    config.addinivalue_line(
        "markers", "encryption: mark test as testing encryption functionality"
    )
    config.addinivalue_line(
        "markers", "permissions: mark test as testing permission/authorization"
    )
    config.addinivalue_line(
        "markers", "downloads: mark test as testing download functionality"
    )


# Pytest hooks for better output
def pytest_runtest_setup(item):
    """Hook that runs before each test"""
    # Add any pre-test setup here
    pass


def pytest_runtest_teardown(item, nextitem):
    """Hook that runs after each test"""
    # Add any post-test cleanup here
    pass


# Helper functions for tests
@pytest.fixture
def create_test_file(tmp_path):
    """Helper to create test files"""
    def _create_file(filename, content="test content"):
        file_path = tmp_path / filename
        file_path.write_text(content)
        return str(file_path)
    return _create_file


@pytest.fixture
def cleanup_test_files():
    """Helper to cleanup test files"""
    files_to_cleanup = []

    def _register(filepath):
        files_to_cleanup.append(filepath)

    yield _register

    # Cleanup
    import os
    for filepath in files_to_cleanup:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
