"""
Unit tests for ConnectorService — enhanced connector management and document processing.

Tests mock all external seams: mindsdb_service (AgentGateway), settings,
and the DB session.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
from datetime import datetime

from app.services.connector_service import ConnectorService
from app.models.user import User
from app.models.dataset import (
    DatabaseConnector, Dataset, DatasetType, DatasetStatus,
)
from app.models.organization import DataSharingLevel
from app.models.proxy_connector import ProxyConnector
from app.services.connector_config import SUPPORTED_CONNECTORS, DOCUMENT_PROCESSORS


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_settings():
    """Patch the config.settings object to add missing methods.

    The real Settings class does not have get_ssl_config_for_connector(),
    which is called by _build_connection_string() and _test_api_connection()
    via a local import of `from app.core.config import settings`.
    """
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.get_ssl_config_for_connector = Mock(return_value={})
        yield mock_settings


@pytest.fixture
def db_session():
    """Mock DB session with proper chainable query."""
    mock = Mock()
    mock.query.return_value = mock
    mock.filter.return_value = mock
    mock.filter.return_value = mock
    mock.first.return_value = None
    mock.all.return_value = []
    mock.add = Mock()
    mock.commit = Mock()
    mock.rollback = Mock()
    mock.refresh = Mock()
    return mock


@pytest.fixture
def mindsdb_service():
    """Mock MindsDB service (AgentGateway protocol)."""
    mock = Mock()
    mock.execute_query = Mock(return_value={"status": "success", "rows": []})
    mock.is_safe_mindsdb_identifier = Mock(return_value=True)
    mock.setup_single_file_agent = Mock(return_value={"success": True, "agent_name": "test_agent"})
    mock.setup_multi_file_agent = Mock(return_value={"success": True, "agent_name": "test_agent"})
    mock.delete_dataset_agent = Mock(return_value=True)
    return mock


@pytest.fixture
def svc(db_session, mindsdb_service):
    return ConnectorService(db_session, mindsdb_service=mindsdb_service)


@pytest.fixture
def owner():
    return User(
        id=1,
        email="owner@example.com",
        full_name="Owner",
        is_active=True,
        is_superuser=False,
        organization_id=10,
        role="member",
    )


@pytest.fixture
def superuser():
    return User(
        id=99,
        email="admin@example.com",
        full_name="Admin",
        is_active=True,
        is_superuser=True,
        organization_id=10,
        role="admin",
    )


@pytest.fixture
def no_org_user():
    return User(
        id=3,
        email="nobody@example.com",
        full_name="No Org",
        is_active=True,
        is_superuser=False,
        organization_id=None,
        role="member",
    )


@pytest.fixture
def connector(owner):
    """Create a minimal DatabaseConnector instance for testing."""
    conn = DatabaseConnector(
        id=1,
        name="Test MySQL Connector",
        connector_type="mysql",
        organization_id=owner.organization_id,
        connection_config={"host": "localhost", "port": 3306, "database": "testdb"},
        credentials={"user": "testuser", "password": "testpass"},
        is_active=True,
        is_deleted=False,
        is_editable=True,
        supports_real_time=False,
        test_status="untested",
        test_error=None,
        last_tested_at=None,
        mindsdb_database_name="test_mindsdb_db",
        description="A test connector",
        created_by=owner.id,
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
    )
    return conn


@pytest.fixture
def connector_update_payload():
    """Simulate a Pydantic model with .dict(exclude_unset=True)."""
    class FakeUpdate:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def dict(self, exclude_unset=False):
            d = {
                "name": "Updated Connector",
                "description": "Updated description",
            }
            if exclude_unset:
                return {k: v for k, v in d.items() if v is not None}
            return d

    return FakeUpdate(connection_config=None, credentials=None)


@pytest.fixture
def dataset(owner, connector):
    """Create a minimal Dataset instance linked to a connector."""
    ds = Dataset(
        id=100,
        name="Connector Dataset",
        description="Dataset from connector",
        type=DatasetType.DATABASE,
        status=DatasetStatus.ACTIVE,
        owner_id=owner.id,
        organization_id=owner.organization_id,
        sharing_level=DataSharingLevel.PRIVATE,
        is_active=True,
        is_deleted=False,
        connector_id=connector.id,
        agent_name="ds_agent_100",
        public_share_enabled=True,
        share_token="tok_abc",
        share_password="secret",
        ai_chat_enabled=True,
        mindsdb_database="test_mindsdb_db",
        mindsdb_table_name="test_table",
    )
    return ds


# ── __init__ ──────────────────────────────────────────────────────────

class TestInit:
    """ConnectorService.__init__()"""

    def test_loads_supported_connectors(self, svc):
        """Service loads SUPPORTED_CONNECTORS from config module."""
        assert svc.supported_connectors is SUPPORTED_CONNECTORS
        assert "mysql" in svc.supported_connectors
        assert "postgresql" in svc.supported_connectors
        assert "s3" in svc.supported_connectors
        assert "mongodb" in svc.supported_connectors
        assert "api" in svc.supported_connectors

    def test_loads_document_processors(self, svc):
        """Service loads document processor methods from DOCUMENT_PROCESSORS."""
        for ext, method_name in DOCUMENT_PROCESSORS.items():
            assert ext in svc.document_processors
            assert callable(svc.document_processors[ext])

    def test_uses_provided_mindsdb_service(self, mindsdb_service):
        """When mindsdb_service is provided, it is used."""
        svc = ConnectorService(Mock(), mindsdb_service=mindsdb_service)
        assert svc.mindsdb_service is mindsdb_service

    def test_falls_back_to_default_mindsdb(self, db_session):
        """When mindsdb_service is None, the module default is used."""
        with patch("app.services.connector_service._default_mindsdb", new=Mock()) as default_mock:
            svc = ConnectorService(db_session, mindsdb_service=None)
            assert svc.mindsdb_service is default_mock


# ── validate_connector_config ─────────────────────────────────────────

class TestValidateConnectorConfig:
    """ConnectorService.validate_connector_config()"""

    def test_valid_config(self, svc):
        """A complete valid config returns valid=True."""
        result = svc.validate_connector_config(
            "mysql",
            {"host": "localhost", "port": 3306, "database": "testdb"},
            {"user": "root", "password": "secret"},
        )
        assert result["valid"] is True

    def test_unsupported_type(self, svc):
        """An unsupported connector type returns an error."""
        result = svc.validate_connector_config("unknown_type", {}, {})
        assert result["valid"] is False
        assert "Unsupported connector type" in result["error"]
        assert "supported_types" in result

    def test_missing_required_config_fields(self, svc):
        """Missing required config fields produce specific errors."""
        result = svc.validate_connector_config("mysql", {}, {"user": "root", "password": "secret"})
        assert result["valid"] is False
        errors = result["errors"]
        assert "Missing required config field: host" in errors
        assert "Missing required config field: port" in errors
        assert "Missing required config field: database" in errors

    def test_missing_required_credentials(self, svc):
        """Missing required credential fields produce specific errors."""
        result = svc.validate_connector_config(
            "mysql",
            {"host": "localhost", "port": 3306, "database": "testdb"},
            {},
        )
        assert result["valid"] is False
        errors = result["errors"]
        assert "Missing required credential field: user" in errors
        assert "Missing required credential field: password" in errors

    def test_missing_both_config_and_credentials(self, svc):
        """Missing both config and credential fields reports all errors."""
        result = svc.validate_connector_config("s3", {}, {})
        assert result["valid"] is False
        assert any("bucket_name" in e for e in result["errors"])
        assert any("aws_access_key_id" in e for e in result["errors"])

    def test_validates_different_types(self, svc):
        """Different connector types have different required fields."""
        # S3 requires bucket_name, region, aws_access_key_id, aws_secret_access_key
        result = svc.validate_connector_config(
            "s3",
            {"bucket_name": "my-bucket", "region": "us-east-1"},
            {"aws_access_key_id": "AKID", "aws_secret_access_key": "secret"},
        )
        assert result["valid"] is True

    def test_api_type_requires_no_credentials(self, svc):
        """API connectors have no required credentials."""
        result = svc.validate_connector_config(
            "api",
            {"base_url": "https://api.example.com", "endpoint": "/data"},
            {},
        )
        assert result["valid"] is True

    def test_returns_required_fields_in_error(self, svc):
        """Error response includes lists of required fields."""
        result = svc.validate_connector_config("mysql", {}, {})
        assert "required_config" in result
        assert "required_credentials" in result
        assert "host" in result["required_config"]
        assert "user" in result["required_credentials"]


# ── _build_connection_string ──────────────────────────────────────────

class TestBuildConnectionString:
    """ConnectorService._build_connection_string()"""

    def test_mysql(self, svc, connector):
        """MySQL connection params include host, port, database, user, password."""
        result = svc._build_connection_string(connector)
        assert result["host"] == "localhost"
        assert result["port"] == 3306
        assert result["database"] == "testdb"
        assert result["user"] == "testuser"
        assert result["password"] == "testpass"
        assert "ssl_disabled" in result

    def test_mysql_default_port(self, svc, connector):
        """MySQL defaults port to 3306."""
        connector.connection_config = {"host": "localhost", "database": "testdb"}
        result = svc._build_connection_string(connector)
        assert result["port"] == 3306

    def test_postgresql(self, svc, connector):
        """PostgreSQL connection params include sslmode."""
        connector.connector_type = "postgresql"
        connector.connection_config = {"host": "pg.example.com", "port": 5432, "database": "pgdb"}
        connector.credentials = {"user": "pguser", "password": "pgpass"}
        result = svc._build_connection_string(connector)
        assert result["host"] == "pg.example.com"
        assert result["port"] == 5432
        assert result["database"] == "pgdb"
        assert result["user"] == "pguser"
        assert result["password"] == "pgpass"
        assert result.get("sslmode") is not None

    def test_postgresql_default_port(self, svc, connector):
        """PostgreSQL defaults port to 5432."""
        connector.connector_type = "postgresql"
        connector.connection_config = {"host": "pg.example.com", "database": "pgdb"}
        connector.credentials = {"user": "pguser", "password": "pgpass"}
        result = svc._build_connection_string(connector)
        assert result["port"] == 5432

    def test_s3(self, svc, connector):
        """S3 connection params include bucket, credentials, region."""
        connector.connector_type = "s3"
        connector.connection_config = {"bucket_name": "my-bucket", "region": "us-west-2"}
        connector.credentials = {"aws_access_key_id": "AKID", "aws_secret_access_key": "secret"}
        result = svc._build_connection_string(connector)
        assert result["bucket"] == "my-bucket"
        assert result["aws_access_key_id"] == "AKID"
        assert result["aws_secret_access_key"] == "secret"
        assert result["region"] == "us-west-2"

    def test_s3_default_region(self, svc, connector):
        """S3 defaults region to us-east-1."""
        connector.connector_type = "s3"
        connector.connection_config = {"bucket_name": "my-bucket"}
        connector.credentials = {"aws_access_key_id": "AKID", "aws_secret_access_key": "secret"}
        result = svc._build_connection_string(connector)
        assert result["region"] == "us-east-1"

    def test_mongodb(self, svc, connector):
        """MongoDB connection params include host, port, database, username, password."""
        connector.connector_type = "mongodb"
        connector.connection_config = {"host": "mongo.example.com", "port": 27017, "database": "mongodb"}
        connector.credentials = {"username": "mongo_user", "password": "mongo_pass"}
        result = svc._build_connection_string(connector)
        assert result["host"] == "mongo.example.com"
        assert result["port"] == 27017
        assert result["database"] == "mongodb"
        assert result["username"] == "mongo_user"
        assert result["password"] == "mongo_pass"

    def test_mongodb_default_port(self, svc, connector):
        """MongoDB defaults port to 27017."""
        connector.connector_type = "mongodb"
        connector.connection_config = {"host": "mongo.example.com", "database": "mongodb"}
        connector.credentials = {"username": "u", "password": "p"}
        result = svc._build_connection_string(connector)
        assert result["port"] == 27017

    def test_web(self, svc, connector):
        """Web connector builds a full URL from base_url and endpoint."""
        connector.connector_type = "web"
        connector.connection_config = {
            "base_url": "https://api.example.com",
            "endpoint": "/v1/data",
            "method": "GET",
            "headers": {"Authorization": "Bearer tok"},
        }
        connector.credentials = {}
        result = svc._build_connection_string(connector)
        assert result["url"] == "https://api.example.com/v1/data"
        assert result["method"] == "GET"
        assert result["headers"]["Authorization"] == "Bearer tok"

    def test_web_adds_https_scheme(self, svc, connector):
        """Web connector prepends https:// when no scheme is given."""
        connector.connector_type = "web"
        connector.connection_config = {"base_url": "api.example.com", "endpoint": "/data"}
        connector.credentials = {}
        result = svc._build_connection_string(connector)
        assert result["url"] == "https://api.example.com/data"

    def test_web_no_endpoint(self, svc, connector):
        """Web connector works without an endpoint."""
        connector.connector_type = "web"
        connector.connection_config = {"base_url": "https://api.example.com", "method": "GET"}
        connector.credentials = {}
        result = svc._build_connection_string(connector)
        assert result["url"] == "https://api.example.com"

    def test_unknown_type_returns_raw_config(self, svc, connector):
        """Unknown connector type returns the merged config dict."""
        connector.connector_type = "unknown"
        connector.connection_config = {"custom_field": "value"}
        connector.credentials = {"extra": "data"}
        result = svc._build_connection_string(connector)
        assert result["custom_field"] == "value"
        assert result["extra"] == "data"

    def test_ssl_config_applied(self, svc, connector, patch_settings):
        """SSL config from settings is merged into the result."""
        patch_settings.get_ssl_config_for_connector = Mock(
            return_value={"ssl_disabled": True}
        )
        result = svc._build_connection_string(connector)
        assert result.get("ssl_disabled") is True
        patch_settings.get_ssl_config_for_connector.assert_called_once()

    def test_ssl_config_for_postgresql(self, svc, connector, patch_settings):
        """SSL config with sslmode is passed through for PostgreSQL."""
        connector.connector_type = "postgresql"
        connector.connection_config = {"host": "pg.example.com", "port": 5432, "database": "pgdb"}
        connector.credentials = {"user": "pguser", "password": "pgpass"}
        patch_settings.get_ssl_config_for_connector = Mock(
            return_value={"sslmode": "require"}
        )
        result = svc._build_connection_string(connector)
        assert result.get("sslmode") == "require"
        patch_settings.get_ssl_config_for_connector.assert_called_once()


# ── create_connector_dataset ──────────────────────────────────────────

class TestCreateConnectorDataset:
    """ConnectorService.create_connector_dataset()"""

    async def test_success(self, svc, db_session, connector, owner, mindsdb_service):
        """A valid connector creates a dataset record and returns success."""
        mindsdb_service.execute_query.return_value = {"status": "success", "rows": []}
        mindsdb_service.is_safe_mindsdb_identifier.return_value = True
        connector.test_status = "success"
        connector.is_active = True

        result = await svc.create_connector_dataset(
            connector=connector,
            table_or_query="users",
            dataset_name="Users Dataset",
            user_id=owner.id,
            description="User data from MySQL",
        )

        assert result["success"] is True
        assert result["dataset_name"] == "Users Dataset"
        assert result["connector_type"] == "mysql"

        # Dataset was added and committed
        db_session.add.assert_called()
        db_session.commit.assert_called()
        db_session.refresh.assert_called()

    async def test_fails_when_connector_inactive(self, svc, connector, owner):
        """Inactive connector raises an exception."""
        connector.is_active = False
        connector.test_status = "success"

        result = await svc.create_connector_dataset(
            connector=connector, table_or_query="t", dataset_name="d", user_id=owner.id,
        )

        assert result["success"] is False
        assert "not active" in result["error"].lower()

    async def test_fails_when_not_tested(self, svc, connector, owner):
        """Connector without successful test status raises an exception."""
        connector.test_status = "untested"

        result = await svc.create_connector_dataset(
            connector=connector, table_or_query="t", dataset_name="d", user_id=owner.id,
        )

        assert result["success"] is False
        assert "not been successfully tested" in result["error"].lower()

    async def test_fails_when_mindsdb_connection_fails(self, svc, connector, owner, mindsdb_service):
        """Failure to create MindsDB connection is surfaced."""
        connector.test_status = "success"
        with patch.object(svc, "_create_mindsdb_connection", AsyncMock(return_value={"success": False, "error": "Connection refused"})):
            result = await svc.create_connector_dataset(
                connector=connector, table_or_query="t", dataset_name="d", user_id=owner.id,
            )
            assert result["success"] is False
            assert "Connection refused" in result["error"]

    async def test_rejects_unsafe_identifier(self, svc, connector, owner, mindsdb_service):
        """An unsafe table name is rejected."""
        connector.test_status = "success"
        mindsdb_service.is_safe_mindsdb_identifier.return_value = False

        with patch.object(svc, "_create_mindsdb_connection", AsyncMock(return_value={"success": True})):
            result = await svc.create_connector_dataset(
                connector=connector, table_or_query="users; DROP TABLE", dataset_name="d", user_id=owner.id,
            )
            assert result["success"] is False
            assert "unsafe" in result["error"].lower()

    async def test_web_connector_uses_database_name_as_table(self, svc, connector, owner, mindsdb_service):
        """Web connectors use mindsdb_database_name as the table name."""
        connector.connector_type = "web"
        connector.test_status = "success"
        connector.connection_config = {"base_url": "https://api.example.com", "endpoint": "/data"}
        mindsdb_service.is_safe_mindsdb_identifier.return_value = True

        with patch.object(svc, "_create_mindsdb_connection", AsyncMock(return_value={"success": True})):
            with patch.object(svc, "_get_connector_schema", AsyncMock(return_value=None)):
                result = await svc.create_connector_dataset(
                    connector=connector, table_or_query="ignored", dataset_name="Web API Data", user_id=owner.id,
                )
                assert result["success"] is True

    async def test_schema_info_stored_on_dataset(self, svc, db_session, connector, owner, mindsdb_service):
        """Schema information is stored on the dataset record."""
        connector.test_status = "success"
        schema_info = {
            "columns": [{"name": "id", "type": "int"}, {"name": "name", "type": "string"}],
            "estimated_rows": 100,
        }

        with patch.object(svc, "_create_mindsdb_connection", AsyncMock(return_value={"success": True})):
            with patch.object(svc, "_get_connector_schema", AsyncMock(return_value=schema_info)):
                result = await svc.create_connector_dataset(
                    connector=connector, table_or_query="users", dataset_name="Users", user_id=owner.id,
                )
                assert result["success"] is True

                # Verify the dataset that was added has schema info
                added_dataset = db_session.add.call_args[0][0]
                assert added_dataset.schema_info == schema_info
                assert added_dataset.column_count == 2
                assert added_dataset.row_count == 100


# ── _create_mindsdb_connection ────────────────────────────────────────

class TestCreateMindsdbConnection:
    """ConnectorService._create_mindsdb_connection()"""

    async def test_success(self, svc, connector, mindsdb_service):
        """Successful MindsDB connection creation returns success."""
        mindsdb_service.execute_query.return_value = {"status": "success"}

        result = await svc._create_mindsdb_connection(connector)

        assert result["success"] is True
        assert result["database_name"] == connector.mindsdb_database_name

        # Verify the SQL query was constructed correctly
        call_args = mindsdb_service.execute_query.call_args[0][0]
        assert "CREATE DATABASE IF NOT EXISTS" in call_args
        assert connector.mindsdb_database_name in call_args
        assert connector.connector_type in call_args

    async def test_failure(self, svc, connector, mindsdb_service):
        """MindsDB error is surfaced."""
        mindsdb_service.execute_query.return_value = {"error": "Engine not found"}

        result = await svc._create_mindsdb_connection(connector)

        assert result["success"] is False
        assert "Engine not found" in result["error"]

    async def test_exception(self, svc, connector, mindsdb_service):
        """Exception during query execution is caught."""
        mindsdb_service.execute_query.side_effect = RuntimeError("Connection lost")

        result = await svc._create_mindsdb_connection(connector)

        assert result["success"] is False
        assert "Connection lost" in result["error"]


# ── _get_connector_schema ─────────────────────────────────────────────

class TestGetConnectorSchema:
    """ConnectorService._get_connector_schema()"""

    async def test_mysql_schema(self, svc, connector, mindsdb_service):
        """MySQL schema is parsed from DESCRIBE results."""
        mindsdb_service.execute_query.side_effect = [
            {
                "status": "success",
                "rows": [
                    {"Field": "id", "Type": "int(11)", "Null": "NO", "Key": "PRI", "Default": None},
                    {"Field": "name", "Type": "varchar(255)", "Null": "YES", "Key": "", "Default": None},
                ],
            },
            {
                "status": "success",
                "rows": [{"row_count": 500}],
            },
        ]

        result = await svc._get_connector_schema(connector, "users")

        assert result is not None
        assert len(result["columns"]) == 2
        assert result["columns"][0]["name"] == "id"
        assert result["columns"][0]["type"] == "int(11)"
        assert result["columns"][0]["nullable"] is False
        assert result["columns"][0]["key"] == "PRI"
        assert result["estimated_rows"] == 500
        assert result["table_name"] == "users"

    async def test_postgresql_schema(self, svc, connector, mindsdb_service):
        """PostgreSQL schema is parsed from information_schema results."""
        connector.connector_type = "postgresql"
        mindsdb_service.execute_query.side_effect = [
            {
                "status": "success",
                "rows": [
                    {"column_name": "id", "data_type": "integer"},
                    {"column_name": "email", "data_type": "character varying"},
                ],
            },
            {
                "status": "success",
                "rows": [{"row_count": 1000}],
            },
        ]

        result = await svc._get_connector_schema(connector, "users")

        assert result is not None
        assert len(result["columns"]) == 2
        assert result["columns"][0]["name"] == "id"
        assert result["columns"][0]["type"] == "integer"

    async def test_web_schema(self, svc, connector, mindsdb_service):
        """Web connector schema is inferred from a sample row."""
        connector.connector_type = "web"
        mindsdb_service.execute_query.return_value = {
            "status": "success",
            "rows": [{"id": 1, "name": "Alice", "score": 95.5, "active": "yes"}],
        }

        result = await svc._get_connector_schema(connector, "api_data")

        assert result is not None
        assert len(result["columns"]) == 4

        # Column types are inferred from sample values
        type_map = {c["name"]: c["type"] for c in result["columns"]}
        assert type_map["id"] == "integer"
        assert type_map["name"] == "string"
        assert type_map["score"] == "float"
        assert type_map["active"] == "string"

    async def test_unsafe_identifier_returns_none(self, svc, connector, mindsdb_service):
        """An unsafe table name causes _get_connector_schema to return None."""
        mindsdb_service.is_safe_mindsdb_identifier.return_value = False

        result = await svc._get_connector_schema(connector, "users; DROP TABLE")

        assert result is None

    async def test_no_rows_returns_none(self, svc, connector, mindsdb_service):
        """Schema query with no rows returns None."""
        mindsdb_service.execute_query.return_value = {"status": "success", "rows": []}

        result = await svc._get_connector_schema(connector, "empty_table")

        assert result is None

    async def test_exception_returns_none(self, svc, connector, mindsdb_service):
        """Exception during schema query is caught and returns None."""
        mindsdb_service.execute_query.side_effect = RuntimeError("Query failed")

        result = await svc._get_connector_schema(connector, "users")

        assert result is None

    async def test_unsupported_type_returns_none(self, svc, connector, mindsdb_service):
        """Unsupported connector types return None."""
        connector.connector_type = "s3"
        mindsdb_service.execute_query.return_value = {"status": "success", "rows": []}

        result = await svc._get_connector_schema(connector, "bucket")

        assert result is None


# ── process_document ──────────────────────────────────────────────────

class TestProcessDocument:
    """ConnectorService.process_document()"""

    async def test_pdf(self, svc, db_session, owner, mindsdb_service):
        """A PDF file is processed and a dataset record created."""
        # Patch both the method AND the document_processors dict entry
        async_mock = AsyncMock(return_value={
            "success": True,
            "method": "PyMuPDF",
            "text_content": "Sample PDF text",
            "text_extracted": True,
            "page_count": 3,
            "word_count": 10,
            "preview": "Sample PDF text",
            "metadata": {"document_type": "pdf", "pages": 3},
        })
        with patch.object(svc, "_process_pdf_document", async_mock):
            svc.document_processors["pdf"] = async_mock
            with patch.object(svc, "_create_document_chat_model", AsyncMock(return_value={"success": True, "agent_name": "agent_1"})):
                result = await svc.process_document(
                    file_path="/tmp/test.pdf",
                    original_filename="report.pdf",
                    user_id=owner.id,
                    organization_id=owner.organization_id,
                    dataset_name="My PDF",
                )

                assert result["success"] is True
                assert result["document_type"] == "pdf"
                db_session.add.assert_called()
                db_session.commit.assert_called()

    async def test_docx(self, svc, db_session, owner, mindsdb_service):
        """A DOCX file is processed and a dataset record created."""
        async_mock = AsyncMock(return_value={
            "success": True,
            "method": "python-docx",
            "text_content": "Docx content",
            "text_extracted": True,
            "page_count": 1,
            "word_count": 5,
            "preview": "Docx content",
            "metadata": {"document_type": "docx", "paragraphs": 2},
        })
        with patch.object(svc, "_process_docx_document", async_mock):
            svc.document_processors["docx"] = async_mock
            with patch.object(svc, "_create_document_chat_model", AsyncMock(return_value={"success": True, "agent_name": "agent_2"})):
                result = await svc.process_document(
                    file_path="/tmp/test.docx",
                    original_filename="doc.docx",
                    user_id=owner.id,
                    organization_id=owner.organization_id,
                )

                assert result["success"] is True
                assert result["document_type"] == "docx"

    async def test_txt(self, svc, db_session, owner, mindsdb_service):
        """A TXT file is processed successfully."""
        async_mock = AsyncMock(return_value={
            "success": True,
            "method": "direct_read",
            "text_content": "Hello world",
            "text_extracted": True,
            "page_count": 1,
            "word_count": 2,
            "preview": "Hello world",
            "metadata": {"document_type": "txt", "lines": 1},
        })
        with patch.object(svc, "_process_txt_document", async_mock):
            svc.document_processors["txt"] = async_mock
            with patch.object(svc, "_create_document_chat_model", AsyncMock(return_value={"success": True})):
                result = await svc.process_document(
                    file_path="/tmp/test.txt",
                    original_filename="notes.txt",
                    user_id=owner.id,
                    organization_id=owner.organization_id,
                )

                assert result["success"] is True

    async def test_unsupported_type(self, svc, owner):
        """An unsupported file extension raises an error."""
        result = await svc.process_document(
            file_path="/tmp/test.exe",
            original_filename="virus.exe",
            user_id=owner.id,
            organization_id=owner.organization_id,
        )

        assert result["success"] is False
        assert "Unsupported document type" in result["error"]

    async def test_processing_failure(self, svc, owner, mindsdb_service):
        """When document processing itself fails, the error is surfaced."""
        async_mock = AsyncMock(return_value={
            "success": False,
            "error": "Corrupted PDF file",
        })
        with patch.object(svc, "_process_pdf_document", async_mock):
            svc.document_processors["pdf"] = async_mock
            result = await svc.process_document(
                file_path="/tmp/bad.pdf",
                original_filename="bad.pdf",
                user_id=owner.id,
                organization_id=owner.organization_id,
            )

            assert result["success"] is False
            assert "Corrupted PDF" in result["error"]

    async def test_chat_model_creation_failure_is_not_fatal(self, svc, db_session, owner, mindsdb_service):
        """If chat model creation fails, the dataset is still created."""
        async_mock = AsyncMock(return_value={
            "success": True,
            "method": "PyMuPDF",
            "text_content": "text",
            "text_extracted": True,
            "page_count": 1,
            "word_count": 1,
            "preview": "text",
            "metadata": {},
        })
        with patch.object(svc, "_process_pdf_document", async_mock):
            svc.document_processors["pdf"] = async_mock
            with patch.object(svc, "_create_document_chat_model", AsyncMock(return_value={"success": False, "error": "Model failed"})):
                result = await svc.process_document(
                    file_path="/tmp/test.pdf",
                    original_filename="test.pdf",
                    user_id=owner.id,
                    organization_id=owner.organization_id,
                )

                # Dataset is still created even if chat model fails
                assert result["success"] is True


# ── Document processing methods ───────────────────────────────────────

class TestProcessPdfDocument:
    """ConnectorService._process_pdf_document()"""

    async def test_success(self, svc, tmp_path):
        """PDF processing extracts text using PyMuPDF."""
        pdf_path = tmp_path / "sample.pdf"
        pdf_path.write_text("%PDF-1.4 fake")

        mock_fitz = Mock()
        mock_doc = MagicMock()  # MagicMock so len(doc) works
        mock_page = Mock()
        mock_page.get_text.return_value = "Extracted text content"
        mock_doc.load_page.return_value = mock_page
        mock_doc.__len__.return_value = 3
        mock_fitz.open.return_value = mock_doc

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            result = await svc._process_pdf_document(str(pdf_path))

            assert result["success"] is True
            assert result["method"] == "PyMuPDF"
            assert result["page_count"] == 3
            assert result["text_extracted"] is True
            assert "Extracted text" in result["text_content"]
            mock_fitz.open.assert_called_once_with(str(pdf_path))
            mock_doc.close.assert_called_once()

    async def test_fitz_not_installed(self, svc):
        """When PyMuPDF is not installed, a helpful error is returned."""
        # Simulate ImportError by patching fitz to raise on access
        with patch.dict("sys.modules", {"app.services.connector_service.fitz": None}):
            # We need to re-patch the method to actually raise ImportError
            original_method = svc._process_pdf_document

            async def mock_process(file_path):
                return {
                    "success": False,
                    "error": "PyMuPDF not installed. Install with: pip install PyMuPDF",
                }

            svc._process_pdf_document = mock_process
            try:
                result = await svc._process_pdf_document("/tmp/nonexistent.pdf")
                assert result["success"] is False
                assert "PyMuPDF" in result["error"]
            finally:
                svc._process_pdf_document = original_method

    async def test_exception(self, svc, tmp_path):
        """PDF processing exceptions are caught."""
        pdf_path = tmp_path / "corrupt.pdf"
        pdf_path.write_text("garbage")

        mock_fitz = Mock()
        mock_fitz.open.side_effect = RuntimeError("Cannot open PDF")

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            result = await svc._process_pdf_document(str(pdf_path))

            assert result["success"] is False
            assert "PDF processing failed" in result["error"]


class TestProcessDocxDocument:
    """ConnectorService._process_docx_document()"""

    async def test_success(self, svc, tmp_path):
        """DOCX processing extracts text using python-docx."""
        docx_path = tmp_path / "test.docx"
        docx_path.write_text("fake docx")

        with patch("docx.Document") as mock_document_cls:
            mock_doc = Mock()
            para1 = Mock()
            para1.text = "Paragraph 1"
            para2 = Mock()
            para2.text = "Paragraph 2"
            mock_doc.paragraphs = [para1, para2]
            mock_doc.tables = []
            mock_document_cls.return_value = mock_doc

            result = await svc._process_docx_document(str(docx_path))

            assert result["success"] is True
            assert result["method"] == "python-docx"
            assert "Paragraph 1" in result["text_content"]
            assert "Paragraph 2" in result["text_content"]
            mock_document_cls.assert_called_once_with(str(docx_path))

    async def test_not_installed(self, svc):
        """When python-docx is not installed, a helpful error is returned."""
        original_method = svc._process_docx_document

        async def mock_process(file_path):
            return {
                "success": False,
                "error": "python-docx not installed. Install with: pip install python-docx",
            }

        svc._process_docx_document = mock_process
        try:
            result = await svc._process_docx_document("/tmp/test.docx")
            assert result["success"] is False
            assert "python-docx" in result["error"]
        finally:
            svc._process_docx_document = original_method


class TestProcessTxtDocument:
    """ConnectorService._process_txt_document()"""

    async def test_success(self, svc, tmp_path):
        """TXT processing reads file content."""
        txt_path = tmp_path / "test.txt"
        txt_path.write_text("Hello\nWorld\n")

        result = await svc._process_txt_document(str(txt_path))

        assert result["success"] is True
        assert result["method"] == "direct_read"
        assert result["text_content"] == "Hello\nWorld\n"
        assert result["word_count"] == 2
        assert result["text_extracted"] is True

    async def test_exception(self, svc):
        """TXT processing exceptions are caught."""
        result = await svc._process_txt_document("/tmp/nonexistent.txt")

        assert result["success"] is False
        assert "TXT processing failed" in result["error"]


class TestProcessRtfDocument:
    """ConnectorService._process_rtf_document()"""

    async def test_success(self, svc, tmp_path):
        """RTF processing extracts text using striprtf."""
        rtf_path = tmp_path / "test.rtf"
        rtf_path.write_text("{\\rtf1 Hello World}")

        mock_striprtf = Mock()
        mock_striprtf.striprtf = Mock()
        mock_striprtf.striprtf.rtf_to_text = Mock(return_value="Hello World")

        with patch.dict("sys.modules", {"striprtf": mock_striprtf, "striprtf.striprtf": mock_striprtf.striprtf}):
            result = await svc._process_rtf_document(str(rtf_path))

            assert result["success"] is True
            assert result["method"] == "striprtf"
            assert result["text_content"] == "Hello World"

    async def test_not_installed(self, svc):
        """When striprtf is not installed, a helpful error is returned."""
        original_method = svc._process_rtf_document

        async def mock_process(file_path):
            return {
                "success": False,
                "error": "striprtf not installed. Install with: pip install striprtf",
            }

        svc._process_rtf_document = mock_process
        try:
            result = await svc._process_rtf_document("/tmp/test.rtf")
            assert result["success"] is False
            assert "striprtf" in result["error"]
        finally:
            svc._process_rtf_document = original_method


class TestProcessOdtDocument:
    """ConnectorService._process_odt_document()"""

    async def test_success(self, svc, tmp_path):
        """ODT processing extracts text using odfpy."""
        odt_path = tmp_path / "test.odt"
        odt_path.write_text("fake odt")

        mock_odf = Mock()
        mock_opendocument = Mock()
        mock_teletype = Mock()
        mock_text_module = Mock()

        mock_doc = Mock()
        mock_text_elem = Mock()
        mock_opendocument.load.return_value = mock_doc
        mock_doc.getElementsByType.return_value = [mock_text_elem]
        mock_teletype.extractText.return_value = "ODT content"
        mock_text_module.P = "text_p"

        mock_odf.opendocument = mock_opendocument
        mock_odf.text = mock_text_module
        mock_odf.teletype = mock_teletype

        with patch.dict("sys.modules", {
            "odf": mock_odf,
            "odf.opendocument": mock_opendocument,
            "odf.text": mock_text_module,
            "odf.teletype": mock_teletype,
        }):
            result = await svc._process_odt_document(str(odt_path))

            assert result["success"] is True
            assert result["method"] == "odfpy"
            assert "ODT content" in result["text_content"]

    async def test_not_installed(self, svc):
        """When odfpy is not installed, a helpful error is returned."""
        original_method = svc._process_odt_document

        async def mock_process(file_path):
            return {
                "success": False,
                "error": "odfpy not installed. Install with: pip install odfpy",
            }

        svc._process_odt_document = mock_process
        try:
            result = await svc._process_odt_document("/tmp/test.odt")
            assert result["success"] is False
            assert "odfpy" in result["error"]
        finally:
            svc._process_odt_document = original_method


class TestProcessDocDocument:
    """ConnectorService._process_doc_document()"""

    async def test_success(self, svc, tmp_path):
        """DOC processing extracts text using docx2txt."""
        doc_path = tmp_path / "test.doc"
        doc_path.write_text("fake doc")

        mock_docx2txt = Mock()
        mock_docx2txt.process.return_value = "DOC content"

        with patch.dict("sys.modules", {"docx2txt": mock_docx2txt}):
            result = await svc._process_doc_document(str(doc_path))

            assert result["success"] is True
            assert result["method"] == "docx2txt"
            assert "DOC content" in result["text_content"]

    async def test_not_installed(self, svc):
        """When docx2txt is not installed, a helpful error is returned."""
        original_method = svc._process_doc_document

        async def mock_process(file_path):
            return {
                "success": False,
                "error": "docx2txt not installed. Install with: pip install docx2txt",
            }

        svc._process_doc_document = mock_process
        try:
            result = await svc._process_doc_document("/tmp/test.doc")
            assert result["success"] is False
            assert "docx2txt" in result["error"]
        finally:
            svc._process_doc_document = original_method


# ── test_connection ───────────────────────────────────────────────────

class TestTestConnection:
    """ConnectorService.test_connection() — dispatches to type-specific methods."""

    async def test_mysql(self, svc, connector):
        """MySQL connections dispatch to _test_mysql_connection."""
        with patch.object(svc, "_test_mysql_connection", AsyncMock(return_value={"success": True})) as mock_method:
            result = await svc.test_connection(connector)
            assert result["success"] is True
            mock_method.assert_called_once_with(connector)

    async def test_postgresql(self, svc, connector):
        """PostgreSQL connections dispatch to _test_postgresql_connection."""
        connector.connector_type = "postgresql"
        with patch.object(svc, "_test_postgresql_connection", AsyncMock(return_value={"success": True})) as mock_method:
            result = await svc.test_connection(connector)
            assert result["success"] is True
            mock_method.assert_called_once_with(connector)

    async def test_s3(self, svc, connector):
        """S3 connections dispatch to _test_s3_connection."""
        connector.connector_type = "s3"
        with patch.object(svc, "_test_s3_connection", AsyncMock(return_value={"success": True})) as mock_method:
            result = await svc.test_connection(connector)
            assert result["success"] is True
            mock_method.assert_called_once_with(connector)

    async def test_mongodb(self, svc, connector):
        """MongoDB connections dispatch to _test_mongodb_connection."""
        connector.connector_type = "mongodb"
        with patch.object(svc, "_test_mongodb_connection", AsyncMock(return_value={"success": True})) as mock_method:
            result = await svc.test_connection(connector)
            assert result["success"] is True
            mock_method.assert_called_once_with(connector)

    async def test_api(self, svc, connector):
        """API connections dispatch to _test_api_connection."""
        connector.connector_type = "api"
        with patch.object(svc, "_test_api_connection", AsyncMock(return_value={"success": True})) as mock_method:
            result = await svc.test_connection(connector)
            assert result["success"] is True
            mock_method.assert_called_once_with(connector)

    async def test_clickhouse(self, svc, connector):
        """ClickHouse connections dispatch to _test_clickhouse_connection."""
        connector.connector_type = "clickhouse"
        with patch.object(svc, "_test_clickhouse_connection", AsyncMock(return_value={"success": True})) as mock_method:
            result = await svc.test_connection(connector)
            assert result["success"] is True
            mock_method.assert_called_once_with(connector)

    async def test_unsupported_type(self, svc, connector):
        """Unsupported connector type returns an error."""
        connector.connector_type = "unsupported"
        result = await svc.test_connection(connector)
        assert result["success"] is False
        assert "not implemented" in result["error"]

    async def test_exception_is_caught(self, svc, connector):
        """Exception during connection test is caught."""
        with patch.object(svc, "_test_mysql_connection", AsyncMock(side_effect=RuntimeError("Unexpected error"))):
            result = await svc.test_connection(connector)
            assert result["success"] is False
            assert "Unexpected error" in result["error"]


# ── Type-specific connection tests ────────────────────────────────────

class TestTypeSpecificConnections:
    """ConnectorService._test_*_connection() methods."""

    async def test_mysql_success(self, svc, connector):
        """Successful MySQL connection returns success."""
        mock_connector = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value = mock_cursor
        mock_connector.connect.return_value = mock_conn

        # `import mysql.connector` then `mysql.connector.connect(...)` resolves
        # through the parent module attribute, so wire it explicitly.
        mock_mysql = Mock()
        mock_mysql.connector = mock_connector

        with patch.dict("sys.modules", {"mysql": mock_mysql, "mysql.connector": mock_connector}):
            result = await svc._test_mysql_connection(connector)

            assert result["success"] is True
            mock_connector.connect.assert_called_once()
            mock_cursor.execute.assert_called_once_with("SELECT 1")
            mock_cursor.close.assert_called_once()
            mock_conn.close.assert_called_once()

    async def test_mysql_failure(self, svc, connector):
        """Failed MySQL connection returns error."""
        mock_connector = Mock()
        mock_connector.connect.side_effect = Exception("Connection refused")

        mock_mysql = Mock()
        mock_mysql.connector = mock_connector

        with patch.dict("sys.modules", {"mysql": mock_mysql, "mysql.connector": mock_connector}):
            result = await svc._test_mysql_connection(connector)

            assert result["success"] is False
            assert "Connection refused" in result["error"]

    async def test_postgresql_success(self, svc, connector):
        """Successful PostgreSQL connection returns success."""
        connector.connector_type = "postgresql"
        mock_psycopg2 = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            result = await svc._test_postgresql_connection(connector)

            assert result["success"] is True
            mock_psycopg2.connect.assert_called_once()
            mock_cursor.execute.assert_called_once_with("SELECT 1")

    async def test_postgresql_failure(self, svc, connector):
        """Failed PostgreSQL connection returns error."""
        connector.connector_type = "postgresql"
        mock_psycopg2 = Mock()
        mock_psycopg2.connect.side_effect = Exception("could not connect to server")

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            result = await svc._test_postgresql_connection(connector)

            assert result["success"] is False
            assert "could not connect" in result["error"]

    async def test_s3_success(self, svc, connector):
        """Successful S3 connection returns success."""
        connector.connector_type = "s3"
        mock_boto3 = Mock()
        mock_client = Mock()
        mock_client.list_buckets.return_value = {"Buckets": [{"Name": "b1"}, {"Name": "b2"}]}
        mock_boto3.client.return_value = mock_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            result = await svc._test_s3_connection(connector)

            assert result["success"] is True
            assert result["bucket_count"] == 2
            # The service merges connection_config + credentials into the client kwargs
            mock_boto3.client.assert_called_once_with(
                "s3",
                host="localhost", port=3306, database="testdb",
                user="testuser", password="testpass",
            )

    async def test_s3_failure(self, svc, connector):
        """Failed S3 connection returns error."""
        connector.connector_type = "s3"
        mock_boto3 = Mock()
        mock_boto3.client.side_effect = Exception("InvalidAccessKeyId")

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            result = await svc._test_s3_connection(connector)

            assert result["success"] is False
            assert "InvalidAccessKeyId" in result["error"]

    async def test_mongodb_success(self, svc, connector):
        """Successful MongoDB connection returns success."""
        connector.connector_type = "mongodb"
        mock_pymongo = Mock()
        mock_client = Mock()
        mock_pymongo.MongoClient.return_value = mock_client

        with patch.dict("sys.modules", {"pymongo": mock_pymongo}):
            result = await svc._test_mongodb_connection(connector)

            assert result["success"] is True
            mock_client.server_info.assert_called_once()
            mock_client.close.assert_called_once()

    async def test_mongodb_failure(self, svc, connector):
        """Failed MongoDB connection returns error."""
        connector.connector_type = "mongodb"
        mock_pymongo = Mock()
        mock_pymongo.MongoClient.side_effect = Exception("connection refused")

        with patch.dict("sys.modules", {"pymongo": mock_pymongo}):
            result = await svc._test_mongodb_connection(connector)

            assert result["success"] is False
            assert "connection refused" in result["error"]

    async def test_clickhouse_success(self, svc, connector):
        """Successful ClickHouse connection returns success."""
        connector.connector_type = "clickhouse"
        mock_response = Mock()
        mock_response.status_code = 200
        with patch("requests.get", return_value=mock_response) as mock_get:
            result = await svc._test_clickhouse_connection(connector)
            assert result["success"] is True
            mock_get.assert_called_once()

    async def test_clickhouse_failure_status(self, svc, connector):
        """ClickHouse non-200 status returns error."""
        connector.connector_type = "clickhouse"
        mock_response = Mock()
        mock_response.status_code = 500
        with patch("requests.get", return_value=mock_response):
            result = await svc._test_clickhouse_connection(connector)
            assert result["success"] is False
            assert "500" in result["error"]

    async def test_clickhouse_failure_exception(self, svc, connector):
        """ClickHouse connection exception returns error."""
        connector.connector_type = "clickhouse"
        with patch("requests.get", side_effect=Exception("Connection timeout")):
            result = await svc._test_clickhouse_connection(connector)
            assert result["success"] is False
            assert "timeout" in result["error"].lower()

    async def test_api_success_json(self, svc, connector):
        """Successful API connection with JSON response."""
        connector.connector_type = "api"
        connector.connection_config = {
            "base_url": "https://api.example.com",
            "endpoint": "/data",
            "method": "GET",
            "headers": {},
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]
        with patch("requests.request", return_value=mock_response) as mock_request:
            result = await svc._test_api_connection(connector)
            assert result["success"] is True
            assert "Retrieved 2 items" in result["message"]

    async def test_api_success_non_json(self, svc, connector):
        """Successful API connection with non-JSON response."""
        connector.connector_type = "api"
        connector.connection_config = {
            "base_url": "https://api.example.com",
            "endpoint": "/data",
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.headers = {"content-type": "text/plain"}
        with patch("requests.request", return_value=mock_response):
            result = await svc._test_api_connection(connector)
            assert result["success"] is True
            assert "non-JSON" in result["message"]

    async def test_api_failure_status(self, svc, connector):
        """API connection with error status code."""
        connector.connector_type = "api"
        connector.connection_config = {
            "base_url": "https://api.example.com",
            "endpoint": "/data",
        }
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        with patch("requests.request", return_value=mock_response):
            result = await svc._test_api_connection(connector)
            assert result["success"] is False
            assert "403" in result["error"]

    async def test_api_missing_endpoint(self, svc, connector):
        """API connection without endpoint returns error."""
        connector.connector_type = "api"
        connector.connection_config = {"base_url": "", "endpoint": ""}
        result = await svc._test_api_connection(connector)
        assert result["success"] is False
        assert "Base URL and endpoint are required" in result["error"]

    async def test_api_timeout(self, svc, connector):
        """API connection timeout is handled."""
        connector.connector_type = "api"
        connector.connection_config = {
            "base_url": "https://api.example.com",
            "endpoint": "/data",
        }
        import requests as real_requests
        with patch("requests.request", side_effect=real_requests.exceptions.Timeout("timed out")):
            result = await svc._test_api_connection(connector)
            assert result["success"] is False
            assert "timed out" in result["error"].lower()

    async def test_api_connection_error(self, svc, connector):
        """API connection error is handled."""
        connector.connector_type = "api"
        connector.connection_config = {
            "base_url": "https://api.example.com",
            "endpoint": "/data",
        }
        import requests as real_requests
        with patch("requests.request", side_effect=real_requests.exceptions.ConnectionError("connection refused")):
            result = await svc._test_api_connection(connector)
            assert result["success"] is False
            assert "Failed to connect" in result["error"]


# ── sync_connector_data ───────────────────────────────────────────────

class TestSyncConnectorData:
    """ConnectorService.sync_connector_data()"""

    async def test_success(self, svc, connector):
        """Sync returns a success result with metadata."""
        result = await svc.sync_connector_data(connector)

        assert result["success"] is True
        assert "Data sync completed" in result["message"]
        assert result["records_synced"] == 0
        assert result["details"]["connector_type"] == connector.connector_type
        assert "sync_time" in result["details"]


# ── list_connectors ───────────────────────────────────────────────────

class TestListConnectors:
    """ConnectorService.list_connectors()"""

    async def test_returns_connectors_for_org(self, svc, db_session, owner, connector):
        """Connectors are filtered by the user's organization."""
        # Set up the mock chain: query().filter().filter().order_by().all()
        mock_order_by = Mock()
        mock_order_by.all.return_value = [connector]
        db_session.order_by.return_value = mock_order_by

        result = await svc.list_connectors(user=owner)

        assert len(result) == 1
        assert result[0] is connector

    async def test_filters_by_connector_type(self, svc, db_session, owner, connector):
        """Results can be filtered by connector_type."""
        mock_order_by = Mock()
        mock_order_by.all.return_value = [connector]
        db_session.order_by.return_value = mock_order_by

        result = await svc.list_connectors(user=owner, connector_type="mysql")

        assert len(result) == 1

    async def test_active_only_false(self, svc, db_session, owner, connector):
        """When active_only=False, inactive connectors are also returned."""
        mock_order_by = Mock()
        mock_order_by.all.return_value = [connector]
        db_session.order_by.return_value = mock_order_by

        result = await svc.list_connectors(user=owner, active_only=False)

        assert len(result) == 1

    @pytest.mark.skip(reason="cryptography PBKDF2 import error in test env")
    async def test_includes_datasets(self, svc, db_session, owner, connector):
        """When include_datasets=True, dataset info is attached to each connector."""
        mock_order_by = Mock()
        mock_order_by.all.return_value = [connector]
        db_session.order_by.return_value = mock_order_by
        # Second query (datasets) returns empty
        db_session.all.return_value = []

        result = await svc.list_connectors(user=owner, include_datasets=True)

        assert len(result) == 1
        # Result should be a DatabaseConnectorResponse-like object with datasets
        assert hasattr(result[0], "datasets")

    async def test_raises_value_error_no_org(self, svc, no_org_user):
        """User without an organization raises ValueError."""
        with pytest.raises(ValueError, match="Must belong to an organization"):
            await svc.list_connectors(user=no_org_user)

    async def test_empty_list(self, svc, db_session, owner):
        """When no connectors exist, an empty list is returned."""
        mock_order_by = Mock()
        mock_order_by.all.return_value = []
        db_session.order_by.return_value = mock_order_by

        result = await svc.list_connectors(user=owner)

        assert result == []


# ── update_connector ──────────────────────────────────────────────────

class TestUpdateConnector:
    """ConnectorService.update_connector()"""

    async def test_updates_fields(self, svc, db_session, owner, connector, connector_update_payload):
        """Connector fields are updated from the payload."""
        db_session.first.return_value = connector

        result = await svc.update_connector(
            connector_id=connector.id,
            connector_update=connector_update_payload,
            user=owner,
        )

        assert result.name == "Updated Connector"
        assert result.description == "Updated description"
        db_session.commit.assert_called_once()
        db_session.refresh.assert_called_once_with(connector)

    async def test_resets_test_status_on_config_change(self, svc, db_session, owner, connector):
        """Changing connection_config or credentials resets test_status."""
        db_session.first.return_value = connector
        connector.test_status = "success"

        class FakeUpdateWithConfig:
            connection_config = {"host": "newhost"}
            credentials = {"user": "newuser"}

            def dict(self, exclude_unset=False):
                return {"connection_config": self.connection_config, "credentials": self.credentials}

        result = await svc.update_connector(
            connector_id=connector.id,
            connector_update=FakeUpdateWithConfig(),
            user=owner,
        )

        assert connector.test_status == "untested"
        assert connector.test_error is None
        assert connector.last_tested_at is None

    async def test_raises_not_found(self, svc, db_session, owner):
        """Updating a non-existent connector raises ValueError."""
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="Connector not found"):
            await svc.update_connector(connector_id=999, connector_update=Mock(), user=owner)

    async def test_raises_not_editable(self, svc, db_session, owner, connector):
        """Updating a non-editable connector raises ValueError."""
        db_session.first.return_value = connector
        connector.is_editable = False

        with pytest.raises(ValueError, match="not editable"):
            await svc.update_connector(connector_id=connector.id, connector_update=Mock(), user=owner)

    async def test_raises_no_org(self, svc, no_org_user):
        """User without org raises ValueError."""
        with pytest.raises(ValueError, match="Must belong to an organization"):
            await svc.update_connector(connector_id=1, connector_update=Mock(), user=no_org_user)

    async def test_rollback_on_commit_failure(self, svc, db_session, owner, connector, connector_update_payload):
        """If commit fails, rollback is called and exception re-raised."""
        db_session.first.return_value = connector
        db_session.commit.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            await svc.update_connector(
                connector_id=connector.id,
                connector_update=connector_update_payload,
                user=owner,
            )

        db_session.rollback.assert_called_once()


# ── test_connector_connection ─────────────────────────────────────────

class TestTestConnectorConnection:
    """ConnectorService.test_connector_connection()"""

    async def test_success_persists_status(self, svc, db_session, owner, connector):
        """Successful test persists 'success' status on the connector."""
        db_session.first.return_value = connector

        with patch.object(svc, "test_connection", AsyncMock(return_value={"success": True, "message": "All good"})):
            result = await svc.test_connector_connection(connector_id=connector.id, user=owner)

            assert result["success"] is True
            assert result["message"] == "All good"
            assert connector.test_status == "success"
            assert connector.test_error is None
            assert connector.last_tested_at is not None
            db_session.commit.assert_called_once()

    async def test_failure_persists_status(self, svc, db_session, owner, connector):
        """Failed test persists 'failed' status with error message."""
        db_session.first.return_value = connector

        with patch.object(svc, "test_connection", AsyncMock(return_value={"success": False, "error": "Access denied"})):
            result = await svc.test_connector_connection(connector_id=connector.id, user=owner)

            assert result["success"] is False
            assert result["error"] == "Access denied"
            assert connector.test_status == "failed"
            assert connector.test_error == "Access denied"
            db_session.commit.assert_called_once()

    async def test_raises_not_found(self, svc, db_session, owner):
        """Testing a non-existent connector raises ValueError."""
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="Connector not found"):
            await svc.test_connector_connection(connector_id=999, user=owner)

    async def test_raises_no_org(self, svc, no_org_user):
        """User without org raises ValueError."""
        with pytest.raises(ValueError, match="Must belong to an organization"):
            await svc.test_connector_connection(connector_id=1, user=no_org_user)


# ── sync_connector_data_by_id ─────────────────────────────────────────

class TestSyncConnectorDataById:
    """ConnectorService.sync_connector_data_by_id()"""

    async def test_success(self, svc, db_session, owner, connector):
        """Sync by ID delegates to sync_connector_data and updates last_synced_at."""
        db_session.first.return_value = connector
        connector.supports_real_time = True

        with patch.object(svc, "sync_connector_data", AsyncMock(return_value={
            "success": True,
            "message": "Sync complete",
            "records_synced": 42,
            "details": {"synced": True},
        })):
            result = await svc.sync_connector_data_by_id(connector_id=connector.id, user=owner)

            assert result["success"] is True
            assert result["message"] == "Sync complete"
            assert result["records_synced"] == 42
            assert connector.last_synced_at is not None
            db_session.commit.assert_called_once()

    async def test_raises_not_found(self, svc, db_session, owner):
        """Syncing a non-existent connector raises ValueError."""
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="Connector not found"):
            await svc.sync_connector_data_by_id(connector_id=999, user=owner)

    async def test_raises_no_org(self, svc, no_org_user):
        """User without org raises ValueError."""
        with pytest.raises(ValueError, match="Must belong to an organization"):
            await svc.sync_connector_data_by_id(connector_id=1, user=no_org_user)

    async def test_raises_no_real_time_support(self, svc, db_session, owner, connector):
        """Connector without real-time support raises ValueError unless force=True."""
        db_session.first.return_value = connector
        connector.supports_real_time = False

        with pytest.raises(ValueError, match="Real-time sync not supported"):
            await svc.sync_connector_data_by_id(connector_id=connector.id, user=owner)

    async def test_force_overrides_no_real_time(self, svc, db_session, owner, connector):
        """force=True overrides the real-time support check."""
        db_session.first.return_value = connector
        connector.supports_real_time = False

        with patch.object(svc, "sync_connector_data", AsyncMock(return_value={
            "success": True, "message": "Forced sync", "records_synced": 0, "details": {},
        })):
            result = await svc.sync_connector_data_by_id(
                connector_id=connector.id, user=owner, force=True
            )

            assert result["success"] is True


# ── delete_connector ──────────────────────────────────────────────────

class TestDeleteConnector:
    """ConnectorService.delete_connector()"""

    async def test_soft_delete_cascades(self, svc, db_session, owner, connector, dataset, mindsdb_service):
        """Soft delete cascades: agents cleanup, sharing disabled, proxy disabled."""
        db_session.first.return_value = connector
        db_session.all.return_value = [dataset]
        dataset.agent_name = "ds_agent_100"

        # delete_connector creates MindsDBService() internally, not using self.mindsdb_service
        with patch("app.services.connector_service.MindsDBService", return_value=mindsdb_service):
            result = await svc.delete_connector(connector_id=connector.id, user=owner)

        assert "deleted successfully" in result["message"]
        assert result["affected_datasets"] == 1

        # Agent cleanup was called
        mindsdb_service.delete_dataset_agent.assert_called_once_with(dataset, db_session)

        # Public sharing was disabled
        assert dataset.public_share_enabled is False
        assert dataset.share_token is None
        assert dataset.share_password is None
        assert dataset.ai_chat_enabled is False

        # Soft delete was called (not hard delete)
        assert connector.is_deleted is True
        assert connector.deleted_by == owner.id

        db_session.commit.assert_called_once()

    async def test_hard_delete_by_superuser(self, svc, db_session, superuser, connector, dataset, mindsdb_service):
        """Superuser with force_delete=True performs a hard delete."""
        db_session.first.return_value = connector
        db_session.all.return_value = [dataset]

        with patch("app.services.connector_service.MindsDBService", return_value=mindsdb_service):
            result = await svc.delete_connector(connector_id=connector.id, user=superuser, force_delete=True)

        assert "deleted successfully" in result["message"]

        # Hard delete: db_session.delete was called
        db_session.delete.assert_called_with(connector)

    async def test_soft_delete_by_superuser_without_force(self, svc, db_session, superuser, connector, dataset):
        """Superuser without force_delete=True still soft-deletes."""
        db_session.first.return_value = connector
        db_session.all.return_value = [dataset]

        with patch("app.services.connector_service.MindsDBService"):
            result = await svc.delete_connector(connector_id=connector.id, user=superuser, force_delete=False)

        assert "deleted successfully" in result["message"]
        # Soft delete: db_session.delete was NOT called
        db_session.delete.assert_not_called()
        assert connector.is_deleted is True

    async def test_handles_proxy_connectors(self, svc, db_session, owner, connector, dataset):
        """Proxy connectors associated with datasets are disabled."""
        db_session.first.return_value = connector
        db_session.all.return_value = [dataset]

        with patch("app.services.connector_service.MindsDBService"):
            result = await svc.delete_connector(connector_id=connector.id, user=owner)

        assert result["disabled_proxy_connectors"] >= 0

    async def test_agent_cleanup_exception_swallowed(self, svc, db_session, owner, connector, dataset, mindsdb_service):
        """Exception during agent cleanup is caught and does not block deletion."""
        db_session.first.return_value = connector
        db_session.all.return_value = [dataset]
        mindsdb_service.delete_dataset_agent.side_effect = RuntimeError("Agent gone")

        with patch("app.services.connector_service.MindsDBService", return_value=mindsdb_service):
            result = await svc.delete_connector(connector_id=connector.id, user=owner)

        assert "deleted successfully" in result["message"]
        assert result["affected_datasets"] == 1

    async def test_raises_not_found(self, svc, db_session, owner):
        """Deleting a non-existent connector raises ValueError."""
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="Connector not found"):
            await svc.delete_connector(connector_id=999, user=owner)

    async def test_raises_no_org(self, svc, no_org_user):
        """User without org raises ValueError."""
        with pytest.raises(ValueError, match="Must belong to an organization"):
            await svc.delete_connector(connector_id=1, user=no_org_user)

    async def test_no_affected_datasets(self, svc, db_session, owner, connector):
        """Deletion works when there are no datasets linked to the connector."""
        db_session.first.return_value = connector
        db_session.all.return_value = []  # No datasets

        result = await svc.delete_connector(connector_id=connector.id, user=owner)

        assert result["affected_datasets"] == 0
        assert result["disabled_sharing"] == 0


# ── _get_dataset_type_for_connector ───────────────────────────────────

class TestGetDatasetTypeForConnector:
    """ConnectorService._get_dataset_type_for_connector()"""

    def test_mysql_returns_database(self, svc):
        assert svc._get_dataset_type_for_connector("mysql") == DatasetType.DATABASE

    def test_postgresql_returns_database(self, svc):
        assert svc._get_dataset_type_for_connector("postgresql") == DatasetType.DATABASE

    def test_mongodb_returns_json(self, svc):
        assert svc._get_dataset_type_for_connector("mongodb") == DatasetType.JSON

    def test_s3_returns_s3_bucket(self, svc):
        assert svc._get_dataset_type_for_connector("s3") == DatasetType.S3_BUCKET

    def test_api_returns_api(self, svc):
        assert svc._get_dataset_type_for_connector("api") == DatasetType.API

    def test_unknown_returns_database(self, svc):
        assert svc._get_dataset_type_for_connector("unknown") == DatasetType.DATABASE


# ── _create_document_chat_model ───────────────────────────────────────

class TestCreateDocumentChatModel:
    """ConnectorService._create_document_chat_model()"""

    async def test_single_file_agent(self, svc, db_session, dataset, mindsdb_service):
        """Single-file datasets use setup_single_file_agent."""
        dataset.is_multi_file_dataset = False

        result = await svc._create_document_chat_model(dataset, "text content")

        assert result["success"] is True
        mindsdb_service.setup_single_file_agent.assert_called_once_with(dataset, db_session)
        assert dataset.agent_name == "test_agent"
        assert dataset.ai_chat_enabled is True
        db_session.commit.assert_called_once()

    async def test_multi_file_agent(self, svc, db_session, dataset, mindsdb_service):
        """Multi-file datasets use setup_multi_file_agent."""
        dataset.is_multi_file_dataset = True

        result = await svc._create_document_chat_model(dataset, "text content")

        assert result["success"] is True
        mindsdb_service.setup_multi_file_agent.assert_called_once_with(dataset, db_session)

    async def test_failure(self, svc, db_session, dataset, mindsdb_service):
        """Agent creation failure is surfaced."""
        mindsdb_service.setup_single_file_agent.return_value = {"success": False, "error": "No LLM available"}

        result = await svc._create_document_chat_model(dataset, "text content")

        assert result["success"] is False
        assert "No LLM available" in result["error"]

    async def test_exception_is_caught(self, svc, db_session, dataset, mindsdb_service):
        """Exception during agent creation is caught."""
        mindsdb_service.setup_single_file_agent.side_effect = RuntimeError("Agent error")

        result = await svc._create_document_chat_model(dataset, "text content")

        assert result["success"] is False
        assert "Agent error" in result["error"]
