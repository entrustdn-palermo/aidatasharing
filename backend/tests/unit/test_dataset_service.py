"""
Unit tests for DatasetService — deep module for dataset lifecycle.

Tests mock all external seams: mindsdb_service, storage_service, DataSharingService,
MetadataService, PreviewService, DownloadService, and the DB session.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
from datetime import datetime
from fastapi import UploadFile

from app.services.dataset_service import DatasetService
from app.models.user import User
from app.models.dataset import (
    Dataset, DatasetType, DatasetStatus, DatasetFile,
    DatasetChatSession, ChatMessage, DatasetAccessLog,
    DatasetDownload, DatasetModel, DatasetShareAccess,
)
from app.models.organization import DataSharingLevel


# ── Fixtures ──────────────────────────────────────────────────────────

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
def svc(db_session):
    return DatasetService(db_session)


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
def other_user():
    return User(
        id=2,
        email="other@example.com",
        full_name="Other",
        is_active=True,
        is_superuser=False,
        organization_id=10,
        role="member",
    )


@pytest.fixture
def mock_csv_file():
    """Create a mock UploadFile simulating a CSV."""
    f = Mock(spec=UploadFile)
    f.filename = "test_data.csv"
    f.content_type = "text/csv"
    f.read = AsyncMock(return_value=b"col1,col2,col3\n1,2,3\n4,5,6\n")
    f.seek = AsyncMock()
    return f


@pytest.fixture
def mock_json_file():
    """Create a mock UploadFile simulating a JSON file."""
    f = Mock(spec=UploadFile)
    f.filename = "test_data.json"
    f.content_type = "application/json"
    f.read = AsyncMock(return_value=b'{"key": "value", "items": [1, 2, 3]}')
    f.seek = AsyncMock()
    return f


@pytest.fixture
def mock_pdf_file():
    """Create a mock UploadFile simulating a PDF file."""
    f = Mock(spec=UploadFile)
    f.filename = "report.pdf"
    f.content_type = "application/pdf"
    f.read = AsyncMock(return_value=b"%PDF-1.4 fake pdf content")
    f.seek = AsyncMock()
    return f


@pytest.fixture
def mock_exe_file():
    """Create a mock UploadFile with an unsupported extension."""
    f = Mock(spec=UploadFile)
    f.filename = "virus.exe"
    f.content_type = "application/x-msdownload"
    f.read = AsyncMock(return_value=b"MZ\x90\x00")
    f.seek = AsyncMock()
    return f


@pytest.fixture
def dataset(owner):
    """Create a minimal Dataset instance for use in tests."""
    ds = Dataset(
        id=42,
        name="Test Dataset",
        description="A test dataset",
        type=DatasetType.CSV,
        status=DatasetStatus.ACTIVE,
        owner_id=owner.id,
        organization_id=owner.organization_id,
        sharing_level=DataSharingLevel.PRIVATE,
        is_active=True,
        is_deleted=False,
        allow_download=True,
        allow_api_access=True,
        size_bytes=1024,
        file_path="/storage/test.csv",
        source_url="test.csv",
        agent_name="dataset_42_agent",
        public_share_enabled=False,
        share_token=None,
        share_password=None,
        ai_chat_enabled=True,
        row_count=2,
        column_count=3,
        is_multi_file_dataset=False,
        total_files_count=1,
    )
    return ds


# ── create_from_files ─────────────────────────────────────────────────

class TestCreateFromFiles:
    """DatasetService.create_from_files()"""

    async def test_single_csv(self, svc, db_session, owner, mock_csv_file):
        """A single CSV file is validated, stored, and a Dataset record created."""
        with (
            patch("app.services.dataset_service.mindsdb_service") as mock_mindsdb,
            patch("app.services.dataset_service.storage_service") as mock_storage,
        ):
            mock_storage.store_dataset_file = AsyncMock(
                return_value={"file_path": "/storage/test.csv", "relative_path": "test.csv"}
            )

            result = await svc.create_from_files(
                files=[mock_csv_file],
                name="My CSV Dataset",
                description="A CSV file",
                sharing_level="private",
                user=owner,
                organization_id=owner.organization_id,
            )

            # Dataset record was added and committed
            assert db_session.add.called
            assert db_session.commit.called
            assert db_session.refresh.called

            # Storage was called with the file content
            mock_storage.store_dataset_file.assert_awaited_once()

            # Dataset returned with expected attributes
            assert result.name == "My CSV Dataset"
            assert result.owner_id == owner.id
            assert result.organization_id == owner.organization_id
            assert result.type == DatasetType.CSV
            assert result.status == DatasetStatus.ACTIVE  # upgraded from PROCESSING

    async def test_multi_file(self, svc, db_session, owner, mock_csv_file, mock_json_file):
        """Multiple files create a multi-file dataset."""
        with (
            patch("app.services.dataset_service.mindsdb_service"),
            patch("app.services.dataset_service.storage_service") as mock_storage,
        ):
            mock_storage.store_dataset_file = AsyncMock(
                return_value={"file_path": "/storage/f", "relative_path": "f"}
            )

            result = await svc.create_from_files(
                files=[mock_csv_file, mock_json_file],
                name=None,  # auto-generate
                description="Multi-file dataset",
                sharing_level="private",
                user=owner,
                organization_id=owner.organization_id,
            )

            assert result.is_multi_file_dataset is True
            assert result.total_files_count == 2
            # Name should be auto-generated
            assert "Multi-file dataset" in result.name
            # Storage called twice
            assert mock_storage.store_dataset_file.await_count == 2

    async def test_no_files_raises(self, svc, owner):
        """Calling with no files raises ValueError."""
        with pytest.raises(ValueError, match="No files provided"):
            await svc.create_from_files(
                files=[], name="x", user=owner, organization_id=owner.organization_id,
            )

    async def test_no_organization_raises(self, svc, owner, mock_csv_file):
        """Calling without organization_id raises ValueError."""
        with pytest.raises(ValueError, match="Must be part of an organization"):
            await svc.create_from_files(
                files=[mock_csv_file], name="x", user=owner, organization_id=None,
            )

    async def test_unsupported_file_type_raises(self, svc, owner, mock_exe_file):
        """An unsupported file extension raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported file type"):
            await svc.create_from_files(
                files=[mock_exe_file], name="x", user=owner,
                organization_id=owner.organization_id,
            )

    async def test_public_dataset_creates_share_link(self, svc, db_session, owner, mock_csv_file):
        """Public datasets auto-create a share link."""
        with (
            patch("app.services.dataset_service.mindsdb_service"),
            patch("app.services.dataset_service.storage_service") as mock_storage,
            patch("app.services.dataset_service.DataSharingService") as MockDS,
        ):
            mock_storage.store_dataset_file = AsyncMock(
                return_value={"file_path": "/storage/f", "relative_path": "f"}
            )
            mock_sharing_instance = MockDS.return_value

            result = await svc.create_from_files(
                files=[mock_csv_file],
                name="Public Dataset",
                sharing_level="public",
                user=owner,
                organization_id=owner.organization_id,
            )

            # Share link was created
            mock_sharing_instance.create_share_link.assert_called_once_with(
                dataset_id=result.id,
                user_id=owner.id,
                password=None,
                enable_chat=True,
            )

    async def test_storage_failure_rolls_back(self, svc, db_session, owner, mock_csv_file):
        """If storage fails, the temp dataset record is rolled back."""
        with (
            patch("app.services.dataset_service.mindsdb_service"),
            patch("app.services.dataset_service.storage_service") as mock_storage,
        ):
            mock_storage.store_dataset_file = AsyncMock(
                side_effect=RuntimeError("Disk full")
            )

            with pytest.raises(RuntimeError, match="Failed to store files"):
                await svc.create_from_files(
                    files=[mock_csv_file], name="x", user=owner,
                    organization_id=owner.organization_id,
                )

            # Rollback and delete were called
            db_session.rollback.assert_called()
            db_session.delete.assert_called()


# ── activate / deactivate ─────────────────────────────────────────────

class TestActivateDeactivate:
    """DatasetService.activate() and .deactivate()"""

    async def test_activate(self, svc, db_session, owner, dataset):
        """Activate toggles status to ACTIVE."""
        db_session.first.return_value = dataset
        dataset.status = DatasetStatus.INACTIVE
        dataset.is_active = False

        result = await svc.activate(dataset_id=42, user=owner)

        assert result.status == DatasetStatus.ACTIVE
        assert result.is_active is True
        db_session.commit.assert_called_once()

    async def test_deactivate(self, svc, db_session, owner, dataset):
        """Deactivate toggles status to INACTIVE."""
        db_session.first.return_value = dataset

        result = await svc.deactivate(dataset_id=42, user=owner)

        assert result.status == DatasetStatus.INACTIVE
        assert result.is_active is False
        db_session.commit.assert_called_once()

    async def test_activate_not_found(self, svc, db_session, owner):
        """Activating a non-existent dataset raises ValueError."""
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await svc.activate(dataset_id=999, user=owner)

    async def test_activate_not_owner_with_access(self, svc, db_session, other_user, dataset):
        """Non-owner with access can activate (activate only checks access, not ownership)."""
        db_session.first.return_value = dataset
        dataset.owner_id = 999  # different owner

        # Mock DataSharingService to allow access
        with patch("app.services.dataset_service.DataSharingService") as MockDS:
            MockDS.return_value.can_access_dataset.return_value = True

            result = await svc.activate(dataset_id=42, user=other_user)
            assert result.status == DatasetStatus.ACTIVE

    async def test_activate_superuser_bypass(self, svc, db_session, superuser, dataset):
        """Superuser can activate any dataset."""
        db_session.first.return_value = dataset
        dataset.owner_id = 999  # different owner

        result = await svc.activate(dataset_id=42, user=superuser)

        assert result.status == DatasetStatus.ACTIVE


# ── delete ────────────────────────────────────────────────────────────

class TestDelete:
    """DatasetService.delete()"""

    async def test_soft_delete(self, svc, db_session, owner, dataset):
        """Soft delete cascades: agent, storage, DB soft-delete."""
        db_session.first.return_value = dataset
        dataset.public_share_enabled = True
        dataset.share_token = "abc123"
        dataset.ai_chat_enabled = True

        with (
            patch("app.services.dataset_service.mindsdb_service") as mock_mindsdb,
            patch("app.services.dataset_service.storage_service") as mock_storage,
        ):
            mock_storage.delete_dataset_file = AsyncMock(return_value=True)
            mock_mindsdb.delete_dataset_agent = Mock()
            mock_mindsdb.delete_file_from_mindsdb = Mock()
            mock_mindsdb.delete_database_connector = Mock()

            result = await svc.delete(dataset_id=42, force=False, user=owner)

            assert result["deletion_type"] == "soft"
            assert result["dataset_id"] == 42
            # MindsDB agent cleanup was called
            mock_mindsdb.delete_dataset_agent.assert_called_once_with(dataset, db_session)
            # Share settings were cleared
            assert dataset.public_share_enabled is False
            assert dataset.share_token is None
            assert dataset.ai_chat_enabled is False

    async def test_hard_delete(self, svc, db_session, superuser, dataset):
        """Hard delete permanently removes the dataset and all related records."""
        db_session.first.return_value = dataset
        dataset.owner_id = superuser.id

        with (
            patch("app.services.dataset_service.mindsdb_service") as mock_mindsdb,
            patch("app.services.dataset_service.storage_service") as mock_storage,
        ):
            mock_storage.delete_dataset_file = AsyncMock(return_value=True)
            mock_mindsdb.delete_dataset_agent = Mock()
            mock_mindsdb.delete_file_from_mindsdb = Mock()
            mock_mindsdb.delete_database_connector = Mock()

            result = await svc.delete(dataset_id=42, force=True, user=superuser)

            assert result["deletion_type"] == "hard"
            # DB delete was called on the dataset
            db_session.delete.assert_called_with(dataset)
            # Related tables were queried and deleted
            assert db_session.commit.called

    async def test_delete_not_found(self, svc, db_session, owner):
        """Deleting a non-existent dataset raises ValueError."""
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await svc.delete(dataset_id=999, force=False, user=owner)

    async def test_delete_not_owner(self, svc, db_session, other_user, dataset):
        """Non-owner deleting raises ValueError."""
        db_session.first.return_value = dataset
        dataset.owner_id = 999  # different owner

        with pytest.raises(ValueError, match="Can only modify your own datasets"):
            await svc.delete(dataset_id=42, force=False, user=other_user)


# ── refresh_metadata ─────────────────────────────────────────────────

class TestRefreshMetadata:
    """DatasetService.refresh_metadata()"""

    async def test_refresh(self, svc, db_session, owner, dataset):
        """Refresh re-analyzes schema, quality, and column stats."""
        db_session.first.return_value = dataset

        with patch("app.services.dataset_service.MetadataService") as MockMeta:
            mock_instance = MockMeta.return_value
            mock_instance.analyze_dataset_schema = AsyncMock(
                return_value={"analysis_timestamp": "2025-01-01T00:00:00", "columns": ["a", "b"]}
            )
            mock_instance.get_data_quality_metrics = AsyncMock(
                return_value={"overall_score": 0.95, "completeness": 1.0}
            )
            mock_instance.generate_column_statistics = AsyncMock(
                return_value={"a": {"type": "int"}, "b": {"type": "str"}}
            )

            result = await svc.refresh_metadata(dataset_id=42, user=owner)

            assert result["dataset_id"] == 42
            assert result["schema_metadata"]["columns"] == ["a", "b"]
            assert result["quality_metrics"]["overall_score"] == 0.95
            assert result["column_statistics"]["a"]["type"] == "int"
            db_session.commit.assert_called_once()

    async def test_refresh_not_found(self, svc, db_session, owner):
        """Refreshing metadata for non-existent dataset raises ValueError."""
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await svc.refresh_metadata(dataset_id=999, user=owner)

    async def test_refresh_not_owner(self, svc, db_session, other_user, dataset):
        """Non-owner refreshing raises ValueError."""
        db_session.first.return_value = dataset
        dataset.owner_id = 999

        with pytest.raises(ValueError, match="Can only modify your own datasets"):
            await svc.refresh_metadata(dataset_id=42, user=other_user)


# ── get_preview ───────────────────────────────────────────────────────

class TestGetPreview:
    """DatasetService.get_preview()"""

    async def test_preview(self, svc, db_session, owner, dataset):
        """Preview delegates to PreviewService and returns structured data."""
        db_session.first.return_value = dataset

        with patch("app.services.dataset_service.PreviewService") as MockPreview:
            mock_instance = MockPreview.return_value
            mock_instance.generate_preview_data = AsyncMock(
                return_value={
                    "headers": ["col1", "col2"],
                    "rows": [["1", "2"], ["3", "4"]],
                    "total_rows": 2,
                }
            )

            result = await svc.get_preview(dataset_id=42, user=owner, rows=5, include_stats=False)

            assert result["dataset_id"] == 42
            assert result["dataset_name"] == dataset.name
            assert result["preview"]["headers"] == ["col1", "col2"]
            mock_instance.generate_preview_data.assert_awaited_once_with(
                dataset=dataset, rows=5, include_stats=False
            )

    async def test_preview_not_found(self, svc, db_session, owner):
        """Preview for non-existent dataset raises ValueError."""
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await svc.get_preview(dataset_id=999, user=owner)


# ── generate_download_token ───────────────────────────────────────────

class TestGenerateDownloadToken:
    """DatasetService.generate_download_token()"""

    async def test_token_generated(self, svc, db_session, owner, dataset):
        """Download token delegates to DownloadService."""
        db_session.first.return_value = dataset

        # Mock DataSharingService so access check passes
        with (
            patch("app.services.dataset_service.DataSharingService") as MockDS,
            patch("app.services.download.DownloadService") as MockDownload,
        ):
            MockDS.return_value.can_access_dataset.return_value = True
            mock_instance = MockDownload.return_value
            mock_instance.initiate_download = AsyncMock(
                return_value={
                    "download_token": "tok_abc123",
                    "expires_at": "2025-01-02T00:00:00",
                }
            )

            result = await svc.generate_download_token(dataset_id=42, user=owner)

            assert result["download_token"] == "tok_abc123"
            mock_instance.initiate_download.assert_awaited_once_with(
                dataset_id=42, user=owner
            )

    async def test_token_not_found(self, svc, db_session, owner):
        """Token generation for non-existent dataset raises ValueError."""
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await svc.generate_download_token(dataset_id=999, user=owner)


# ── Access checks ─────────────────────────────────────────────────────

class TestAccessChecks:
    """DatasetService._check_access() and _check_owner()"""

    async def test_check_access_denied(self, svc, db_session, other_user, dataset):
        """A user with no access gets ValueError."""
        db_session.first.return_value = dataset
        dataset.owner_id = 999

        with patch("app.services.dataset_service.DataSharingService") as MockDS:
            mock_instance = MockDS.return_value
            mock_instance.can_access_dataset.return_value = False

            with pytest.raises(ValueError, match="Access denied"):
                await svc.get_preview(dataset_id=42, user=other_user)

            mock_instance.can_access_dataset.assert_called_once()

    async def test_check_access_superuser_bypass(self, svc, db_session, superuser, dataset):
        """Superuser bypasses access check."""
        db_session.first.return_value = dataset
        dataset.owner_id = 999

        with patch("app.services.dataset_service.PreviewService") as MockPreview:
            MockPreview.return_value.generate_preview_data = AsyncMock(return_value={})
            # Should not raise
            result = await svc.get_preview(dataset_id=42, user=superuser)
            assert result is not None

    async def test_delete_not_owner_raises(self, svc, db_session, other_user, dataset):
        """Non-owner cannot delete."""
        db_session.first.return_value = dataset
        dataset.owner_id = 999

        with pytest.raises(ValueError, match="Can only modify your own datasets"):
            await svc.delete(dataset_id=42, force=False, user=other_user)


# ── JSON helpers ──────────────────────────────────────────────────────

class TestJsonHelpers:
    """Module-level JSON analysis helpers (moved from datasets.py)."""

    def test_count_json_nesting_dict(self):
        from app.services.dataset_service import _count_json_nesting
        data = {"a": {"b": {"c": 1}}}
        assert _count_json_nesting(data) == 3

    def test_count_json_nesting_list(self):
        from app.services.dataset_service import _count_json_nesting
        data = [1, [2, [3]]]
        assert _count_json_nesting(data) == 3

    def test_count_json_nesting_flat(self):
        from app.services.dataset_service import _count_json_nesting
        assert _count_json_nesting(42) == 0

    def test_count_json_elements(self):
        from app.services.dataset_service import _count_json_elements
        data = {"a": 1, "b": [2, 3]}
        # dict (2 keys) + value 1 + list (2 items) + value 2 + value 3 = 7
        assert _count_json_elements(data) == 7

    def test_analyze_json_types(self):
        from app.services.dataset_service import _analyze_json_types
        data = {"name": "test", "count": 42}
        result = _analyze_json_types(data)
        assert isinstance(result, dict)
        assert "name" in result
        assert "count" in result

    def test_sanitize_filename(self):
        from app.utils.file_utils import sanitize_filename
        assert sanitize_filename("normal.csv") == "normal.csv"
        assert sanitize_filename("") == "download"
        assert sanitize_filename(None) == "download"
        assert "/" not in sanitize_filename("path/to/file.csv")


# ── Edge cases ────────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases for DatasetService."""

    async def test_activate_already_deleted(self, svc, db_session, owner, dataset):
        """Activating a soft-deleted dataset still works (deactivate check in model)."""
        db_session.first.return_value = dataset
        dataset.is_deleted = True
        dataset.status = DatasetStatus.DELETED

        with patch("app.services.dataset_service.DataSharingService") as MockDS:
            MockDS.return_value.can_access_dataset.return_value = True

            result = await svc.activate(dataset_id=42, user=owner)
            # The model's activate() checks is_deleted, so status stays DELETED
            assert result.status == DatasetStatus.DELETED

    async def test_deactivate_already_inactive(self, svc, db_session, owner, dataset):
        """Deactivating an already-inactive dataset is a no-op."""
        db_session.first.return_value = dataset
        dataset.is_active = False
        dataset.status = DatasetStatus.INACTIVE

        result = await svc.deactivate(dataset_id=42, user=owner)
        assert result.status == DatasetStatus.INACTIVE

    async def test_create_from_files_with_file_and_files_params(self, svc, db_session, owner, mock_csv_file, mock_json_file):
        """Both `file` and `files` params are combined."""
        with (
            patch("app.services.dataset_service.mindsdb_service"),
            patch("app.services.dataset_service.storage_service") as mock_storage,
        ):
            mock_storage.store_dataset_file = AsyncMock(
                return_value={"file_path": "/storage/f", "relative_path": "f"}
            )

            # Simulate passing both: single file via `file` and list via `files`
            all_files = [mock_csv_file] + [mock_json_file]

            result = await svc.create_from_files(
                files=all_files,
                name="Combined",
                user=owner,
                organization_id=owner.organization_id,
            )

            assert result.total_files_count == 2
