"""
Unit tests for SharingService -- share-link lifecycle, access, analytics.

Tests mock all external seams: DB session, auth helpers, storage_service,
and settings.  No database is required.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
from datetime import datetime
from fastapi import HTTPException

from app.services.sharing import SharingService
from app.models.dataset import (
    Dataset, DatasetType, DatasetStatus, DatasetFile,
    DatasetChatSession, ChatMessage, DatasetShareAccess,
    DatabaseConnector,
)
from app.models.organization import DataSharingLevel, Organization
from app.models.user import User


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def db_session():
    """Mock DB session with chainable query/filter/first/all/join/count."""
    mock = Mock()
    # Chain: query().filter().filter().order_by().all()
    # DatasetFile.is_primary.desc() needs desc to return a callable
    mock.desc = Mock(return_value=Mock())
    mock.query.return_value = mock
    mock.filter.return_value = mock
    mock.join.return_value = mock
    mock.order_by.return_value = mock
    mock.first.return_value = None
    mock.all.return_value = []
    mock.count.return_value = 0
    mock.add = Mock()
    mock.commit = Mock()
    mock.rollback = Mock()
    mock.refresh = Mock()
    mock.delete = Mock()
    return mock


@pytest.fixture
def svc(db_session):
    return SharingService(db_session)


@pytest.fixture
def owner():
    return User(
        id=1,
        email="owner@example.com",
        full_name="Owner User",
        is_active=True,
        is_superuser=False,
        organization_id=10,
        role="owner",
    )


@pytest.fixture
def admin():
    return User(
        id=2,
        email="admin@example.com",
        full_name="Admin User",
        is_active=True,
        is_superuser=False,
        organization_id=10,
        role="admin",
    )


@pytest.fixture
def member():
    return User(
        id=3,
        email="member@example.com",
        full_name="Member User",
        is_active=True,
        is_superuser=False,
        organization_id=10,
        role="member",
    )


@pytest.fixture
def other_org_user():
    return User(
        id=99,
        email="other@example.com",
        full_name="Other Org User",
        is_active=True,
        is_superuser=False,
        organization_id=20,  # different org
        role="member",
    )


@pytest.fixture
def organization():
    return Organization(
        id=10,
        name="Test Org",
        slug="test-org",
        allow_external_sharing=True,
        is_active=True,
    )


@pytest.fixture
def dataset(owner, organization):
    """Minimal Dataset instance for share-link tests."""
    ds = Dataset(
        id=100,
        name="Test Dataset",
        description="A test dataset for sharing",
        type=DatasetType.CSV,
        status=DatasetStatus.ACTIVE,
        owner_id=owner.id,
        organization_id=organization.id,
        organization=organization,
        sharing_level=DataSharingLevel.PRIVATE,
        is_active=True,
        is_deleted=False,
        allow_download=True,
        allow_api_access=True,
        allow_ai_chat=True,
        ai_chat_enabled=False,
        public_share_enabled=False,
        share_token=None,
        share_password=None,
        share_view_count=0,
        size_bytes=2048,
        row_count=100,
        column_count=5,
        file_path="/storage/test.csv",
        source_url="test.csv",
        schema_info={"columns": [{"name": "id", "type": "int"}, {"name": "name", "type": "text"}]},
        ai_summary="A test dataset summary",
        ai_insights={"key_insight": "test insight"},
        is_multi_file_dataset=False,
        owner=owner,
        created_at=datetime(2025, 1, 1),
        last_accessed=None,
    )
    return ds


@pytest.fixture
def multi_file_dataset(owner, organization):
    ds = Dataset(
        id=101,
        name="Multi-File Dataset",
        description="A multi-file dataset",
        type=DatasetType.CSV,
        status=DatasetStatus.ACTIVE,
        owner_id=owner.id,
        organization_id=organization.id,
        organization=organization,
        sharing_level=DataSharingLevel.PRIVATE,
        is_active=True,
        is_deleted=False,
        is_multi_file_dataset=True,
        allow_ai_chat=True,
        ai_chat_enabled=False,
        public_share_enabled=False,
        share_token=None,
        share_password=None,
        share_view_count=0,
        file_path=None,
        source_url="multi-file-upload",
        owner=owner,
        created_at=datetime(2025, 1, 1),
    )
    return ds


@pytest.fixture
def connector_dataset(owner, organization):
    """Dataset backed by a DatabaseConnector."""
    ds = Dataset(
        id=102,
        name="Connector Dataset",
        description="From a database connector",
        type=DatasetType.DATABASE,
        status=DatasetStatus.ACTIVE,
        owner_id=owner.id,
        organization_id=organization.id,
        organization=organization,
        sharing_level=DataSharingLevel.PRIVATE,
        is_active=True,
        is_deleted=False,
        connector_id=50,
        public_share_enabled=True,
        share_token="tok_connector",
        share_password=None,
        share_view_count=0,
        owner=owner,
        created_at=datetime(2025, 1, 1),
    )
    return ds


@pytest.fixture
def password_protected_dataset(owner, organization):
    ds = Dataset(
        id=103,
        name="Password Protected",
        type=DatasetType.CSV,
        status=DatasetStatus.ACTIVE,
        owner_id=owner.id,
        organization_id=organization.id,
        organization=organization,
        sharing_level=DataSharingLevel.PUBLIC,
        is_active=True,
        is_deleted=False,
        public_share_enabled=True,
        share_token="tok_password_protected",
        share_password="$2b$12$hashedpassword123",
        share_view_count=5,
        owner=owner,
        created_at=datetime(2025, 1, 1),
        last_accessed=datetime(2025, 6, 1),
    )
    return ds


@pytest.fixture
def dataset_file():
    return DatasetFile(
        id=1,
        dataset_id=100,
        filename="data.csv",
        file_path="/storage/datasets/100/data.csv",
        relative_path="datasets/100/data.csv",
        file_size=1024,
        file_type="csv",
        is_primary=True,
        is_deleted=False,
    )


@pytest.fixture
def share_access_log():
    return DatasetShareAccess(
        id=1,
        dataset_id=100,
        share_token="abc123",
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0",
    )


# ── create_share_link ─────────────────────────────────────────────────

class TestCreateShareLink:
    """SharingService.create_share_link()"""

    def test_creates_share_link(self, svc, db_session, owner, dataset):
        """Happy path: a share link is created with token and URL."""
        db_session.first.return_value = dataset

        with (
            patch("app.services.sharing.get_password_hash") as mock_hash,
            patch("app.services.sharing.settings") as mock_settings,
        ):
            mock_hash.return_value = "$2b$12$fakehash"
            mock_settings.ENABLE_AI_CHAT = True

            result = svc.create_share_link(
                dataset_id=dataset.id,
                user_id=owner.id,
                password="mypassword",
                enable_chat=True,
            )

        assert result["share_token"] is not None
        assert len(result["share_token"]) == 32  # SHA256 hex[:32]
        assert result["share_url"] == f"/shared/{result['share_token']}"
        assert result["chat_enabled"] is True
        assert result["password_protected"] is True
        assert result["dataset_name"] == dataset.name

        # Dataset was updated
        assert dataset.public_share_enabled is True
        assert dataset.share_token == result["share_token"]
        assert dataset.share_password == "$2b$12$fakehash"
        assert dataset.ai_chat_enabled is True

        # commit is called at least once (method + _init_ai_context both commit)
        db_session.commit.assert_called()
        db_session.refresh.assert_called_once_with(dataset)

    def test_creates_share_link_no_password(self, svc, db_session, owner, dataset):
        """Share link without password sets share_password to None."""
        db_session.first.return_value = dataset

        with (
            patch("app.services.sharing.get_password_hash") as mock_hash,
            patch("app.services.sharing.settings") as mock_settings,
        ):
            mock_settings.ENABLE_AI_CHAT = True

            result = svc.create_share_link(
                dataset_id=dataset.id,
                user_id=owner.id,
                password=None,
                enable_chat=True,
            )

        assert result["password_protected"] is False
        assert dataset.share_password is None
        mock_hash.assert_not_called()

    def test_creates_share_link_chat_disabled(self, svc, db_session, owner, dataset):
        """When enable_chat=False, ai_chat_enabled stays off."""
        db_session.first.return_value = dataset

        with patch("app.services.sharing.settings") as mock_settings:
            mock_settings.ENABLE_AI_CHAT = True

            result = svc.create_share_link(
                dataset_id=dataset.id,
                user_id=owner.id,
                password=None,
                enable_chat=False,
            )

        assert result["chat_enabled"] is False
        assert dataset.ai_chat_enabled is False

    def test_creates_share_link_chat_blocked_by_settings(self, svc, db_session, owner, dataset):
        """When settings.ENABLE_AI_CHAT is False, chat is always disabled."""
        db_session.first.return_value = dataset

        with patch("app.services.sharing.settings") as mock_settings:
            mock_settings.ENABLE_AI_CHAT = False

            result = svc.create_share_link(
                dataset_id=dataset.id,
                user_id=owner.id,
                password=None,
                enable_chat=True,
            )

        assert result["chat_enabled"] is False
        assert dataset.ai_chat_enabled is False

    def test_creates_share_link_chat_blocked_by_dataset(self, svc, db_session, owner, dataset):
        """When dataset.allow_ai_chat is False, chat cannot be enabled."""
        db_session.first.return_value = dataset
        dataset.allow_ai_chat = False

        with patch("app.services.sharing.settings") as mock_settings:
            mock_settings.ENABLE_AI_CHAT = True

            result = svc.create_share_link(
                dataset_id=dataset.id,
                user_id=owner.id,
                password=None,
                enable_chat=True,
            )

        assert result["chat_enabled"] is False
        assert dataset.ai_chat_enabled is False

    def test_dataset_not_found(self, svc, db_session, owner):
        """Non-existent or non-owned dataset raises 404."""
        db_session.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.create_share_link(
                dataset_id=999, user_id=owner.id,
            )

        assert exc.value.status_code == 404
        assert "Dataset not found" in exc.value.detail

    def test_external_sharing_disabled(self, svc, db_session, owner, dataset):
        """Organization with external sharing disabled raises 403."""
        dataset.organization.allow_external_sharing = False
        db_session.first.return_value = dataset

        with pytest.raises(HTTPException) as exc:
            svc.create_share_link(
                dataset_id=dataset.id, user_id=owner.id,
            )

        assert exc.value.status_code == 403
        assert "External sharing is disabled" in exc.value.detail

    def test_creates_share_link_with_connector(self, svc, db_session, owner, connector_dataset):
        """Connector-based datasets trigger proxy connector creation."""
        db_session.first.return_value = connector_dataset

        with (
            patch("app.services.sharing.get_password_hash"),
            patch("app.services.sharing.settings") as mock_settings,
            patch.object(svc, "_create_proxy_connector_sync") as mock_proxy,
        ):
            mock_settings.ENABLE_AI_CHAT = True
            mock_proxy.return_value = Mock()

            result = svc.create_share_link(
                dataset_id=connector_dataset.id,
                user_id=owner.id,
            )

        assert result["share_token"] is not None
        mock_proxy.assert_called_once()

    def test_share_link_ai_context_initialized(self, svc, db_session, owner, dataset):
        """When chat is enabled, _init_ai_context is called."""
        db_session.first.return_value = dataset

        with (
            patch("app.services.sharing.get_password_hash"),
            patch("app.services.sharing.settings") as mock_settings,
            patch.object(svc, "_init_ai_context") as mock_init,
        ):
            mock_settings.ENABLE_AI_CHAT = True

            svc.create_share_link(
                dataset_id=dataset.id,
                user_id=owner.id,
                enable_chat=True,
            )

        mock_init.assert_called_once_with(dataset)

    def test_share_link_ai_context_not_initialized_when_chat_off(self, svc, db_session, owner, dataset):
        """When chat is disabled, _init_ai_context is NOT called."""
        db_session.first.return_value = dataset

        with (
            patch("app.services.sharing.get_password_hash"),
            patch("app.services.sharing.settings") as mock_settings,
            patch.object(svc, "_init_ai_context") as mock_init,
        ):
            mock_settings.ENABLE_AI_CHAT = True

            svc.create_share_link(
                dataset_id=dataset.id,
                user_id=owner.id,
                enable_chat=False,
            )

        mock_init.assert_not_called()


# ── get_shared_dataset ────────────────────────────────────────────────

class TestGetSharedDataset:
    """SharingService.get_shared_dataset()"""

    async def test_get_shared_dataset(self, svc, db_session, dataset):
        """Happy path: returns dataset info with preview."""
        db_session.first.return_value = dataset
        dataset.share_view_count = 0

        with (
            patch.object(svc, "_verify_files_exist") as mock_verify,
            patch.object(svc, "_log_access") as mock_log,
            patch.object(svc, "_generate_preview") as mock_preview,
        ):
            mock_verify.return_value = None
            mock_preview.return_value = {"headers": ["a", "b"], "rows": [["1", "2"]]}

            result = await svc.get_shared_dataset(
                share_token="abc123",
                password=None,
                ip_address="192.168.1.1",
                user_agent="curl/7.0",
            )

        assert result["dataset_id"] == dataset.id
        assert result["dataset_name"] == "Test Dataset"
        assert result["share_token"] == "abc123"
        assert result["access_allowed"] is True
        assert result["requires_password"] is False
        assert result["preview_data"] == {"headers": ["a", "b"], "rows": [["1", "2"]]}
        assert result["is_uploaded_file"] is True
        assert result["is_connector_dataset"] is False

        # View count was incremented
        assert dataset.share_view_count == 1
        db_session.commit.assert_called_once()

    async def test_get_shared_dataset_not_found(self, svc, db_session):
        """Non-existent share token raises 404."""
        db_session.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await svc.get_shared_dataset(share_token="invalid_token")

        assert exc.value.status_code == 404
        assert "not found" in exc.value.detail.lower()

    async def test_get_shared_dataset_wrong_password(self, svc, db_session, password_protected_dataset):
        """Wrong password raises 401."""
        db_session.first.return_value = password_protected_dataset

        with patch("app.services.sharing.verify_password") as mock_verify:
            mock_verify.return_value = False

            with pytest.raises(HTTPException) as exc:
                await svc.get_shared_dataset(
                    share_token="tok_password_protected",
                    password="wrong_password",
                )

        assert exc.value.status_code == 401
        assert "Invalid password" in exc.value.detail

    async def test_get_shared_dataset_correct_password(self, svc, db_session, password_protected_dataset):
        """Correct password allows access."""
        db_session.first.return_value = password_protected_dataset

        with (
            patch("app.services.sharing.verify_password") as mock_verify,
            patch.object(svc, "_verify_files_exist"),
            patch.object(svc, "_log_access"),
            patch.object(svc, "_generate_preview") as mock_preview,
        ):
            mock_verify.return_value = True
            mock_preview.return_value = None

            result = await svc.get_shared_dataset(
                share_token="tok_password_protected",
                password="correct_password",
            )

        assert result["access_allowed"] is True
        assert result["requires_password"] is True

    async def test_get_shared_dataset_connector_gone(self, svc, db_session, connector_dataset):
        """When the underlying connector is deleted, sharing is disabled and 410 raised."""
        connector_dataset.public_share_enabled = True
        connector_dataset.share_password = None  # no password required
        db_session.first.return_value = connector_dataset

        # Second query (for connector) returns None -> connector is deleted
        # Use side_effect on first to return dataset first, then None for connector
        first_results = iter([connector_dataset, None])
        db_session.first.side_effect = lambda: next(first_results)

        with patch.object(svc, "_verify_files_exist"):
            with pytest.raises(HTTPException) as exc:
                await svc.get_shared_dataset(share_token="tok_connector")

        assert exc.value.status_code == 410
        assert "no longer available" in exc.value.detail.lower()
        assert connector_dataset.public_share_enabled is False
        db_session.commit.assert_called()

    async def test_get_shared_dataset_file_check_fails(self, svc, db_session, dataset):
        """When _verify_files_exist raises, the caller propagates."""
        db_session.first.return_value = dataset

        with patch.object(svc, "_verify_files_exist") as mock_verify:
            mock_verify.side_effect = HTTPException(
                status_code=410, detail="Dataset file is no longer available"
            )

            with pytest.raises(HTTPException) as exc:
                await svc.get_shared_dataset(share_token="abc123")

            assert exc.value.status_code == 410

    async def test_get_shared_dataset_with_connector_info(self, svc, db_session, connector_dataset):
        """Connector-based datasets include proxy connection info."""
        connector_dataset.public_share_enabled = True
        connector_dataset.share_password = None  # no password
        db_session.first.return_value = connector_dataset

        # Connector exists -- first() returns the dataset, then the connector
        mock_connector = Mock(id=50, is_deleted=False, is_active=True)
        first_results = iter([connector_dataset, mock_connector])
        db_session.first.side_effect = lambda: next(first_results)

        with (
            patch.object(svc, "_verify_files_exist"),
            patch.object(svc, "_log_access"),
            patch.object(svc, "_generate_preview") as mock_preview,
        ):
            mock_preview.return_value = None

            result = await svc.get_shared_dataset(share_token="tok_connector")

        assert result["is_connector_dataset"] is True
        assert result["has_proxy_connection"] is True
        assert result["proxy_connection_info"] is not None
        assert result["proxy_connection_info"]["access_token"] == "tok_connector"
        assert result["proxy_connection_info"]["database_name"] == connector_dataset.name


# ── verify_password / require_password ────────────────────────────────

class TestVerifyPassword:
    """SharingService.verify_password() and require_password()"""

    def test_no_password_set_returns_true(self, svc, dataset):
        """If dataset has no share_password, any password is accepted."""
        dataset.share_password = None
        assert svc.verify_password(dataset, None) is True
        assert svc.verify_password(dataset, "anything") is True

    def test_password_set_no_input_returns_false(self, svc, password_protected_dataset):
        """If password is set but None provided, returns False."""
        assert svc.verify_password(password_protected_dataset, None) is False

    def test_password_set_correct(self, svc, password_protected_dataset):
        """Correct password delegates to verify_password and returns True."""
        with patch("app.services.sharing.verify_password") as mock_vp:
            mock_vp.return_value = True
            assert svc.verify_password(password_protected_dataset, "right") is True
            mock_vp.assert_called_once_with("right", password_protected_dataset.share_password)

    def test_password_set_wrong(self, svc, password_protected_dataset):
        """Wrong password returns False."""
        with patch("app.services.sharing.verify_password") as mock_vp:
            mock_vp.return_value = False
            assert svc.verify_password(password_protected_dataset, "wrong") is False

    def test_password_verify_raises_fallback(self, svc, password_protected_dataset):
        """If verify_password raises, falls back to plaintext comparison."""
        with patch("app.services.sharing.verify_password") as mock_vp:
            mock_vp.side_effect = Exception("bcrypt error")
            assert svc.verify_password(password_protected_dataset, "wrong") is False

    def test_password_verify_fallback_plaintext_match(self, svc, password_protected_dataset):
        """Fallback plaintext comparison can match."""
        with patch("app.services.sharing.verify_password") as mock_vp:
            mock_vp.side_effect = Exception("bcrypt error")
            assert svc.verify_password(
                password_protected_dataset,
                password_protected_dataset.share_password,
            ) is True

    def test_require_password_raises_on_wrong(self, svc, password_protected_dataset):
        """require_password raises 401 for wrong password."""
        with patch.object(svc, "verify_password") as mock_vp:
            mock_vp.return_value = False
            with pytest.raises(HTTPException) as exc:
                svc.require_password(password_protected_dataset, "wrong")
            assert exc.value.status_code == 401

    def test_require_password_passes(self, svc, password_protected_dataset):
        """require_password is a no-op for correct password."""
        with patch.object(svc, "verify_password") as mock_vp:
            mock_vp.return_value = True
            svc.require_password(password_protected_dataset, "right")  # no exception


# ── update_sharing_level ─────────────────────────────────────────────

class TestUpdateSharingLevel:
    """SharingService.update_sharing_level()"""

    def test_owner_can_update(self, svc, db_session, owner, dataset):
        """Dataset owner can update sharing level."""
        dataset.owner_id = owner.id
        result = svc.update_sharing_level(owner, dataset, DataSharingLevel.PUBLIC)
        assert result is True
        assert dataset.sharing_level == DataSharingLevel.PUBLIC
        db_session.commit.assert_called_once()

    def test_admin_can_update(self, svc, db_session, admin, dataset):
        """Org admin can update sharing level of any dataset in their org."""
        dataset.owner_id = 999  # not admin
        dataset.organization_id = admin.organization_id
        result = svc.update_sharing_level(admin, dataset, DataSharingLevel.ORGANIZATION)
        assert result is True
        assert dataset.sharing_level == DataSharingLevel.ORGANIZATION

    def test_member_cannot_update_others(self, svc, db_session, member, dataset):
        """Regular member cannot update someone else's dataset."""
        dataset.owner_id = 999  # not member
        result = svc.update_sharing_level(member, dataset, DataSharingLevel.PUBLIC)
        assert result is False
        db_session.commit.assert_not_called()

    def test_other_org_admin_cannot_update(self, svc, db_session, other_org_user, dataset):
        """Admin from a different org cannot update."""
        dataset.organization_id = 10
        result = svc.update_sharing_level(other_org_user, dataset, DataSharingLevel.PUBLIC)
        assert result is False

    def test_update_to_private(self, svc, db_session, owner, dataset):
        """Update to PRIVATE level works."""
        dataset.sharing_level = DataSharingLevel.PUBLIC
        result = svc.update_sharing_level(owner, dataset, DataSharingLevel.PRIVATE)
        assert result is True
        assert dataset.sharing_level == DataSharingLevel.PRIVATE


# ── get_sharing_stats ────────────────────────────────────────────────

class TestGetSharingStats:
    """SharingService.get_sharing_stats()"""

    def test_org_admin_gets_stats(self, svc, db_session, admin, dataset, multi_file_dataset):
        """Admin sees aggregated sharing stats."""
        dataset.sharing_level = DataSharingLevel.PUBLIC
        dataset.type = DatasetType.CSV
        multi_file_dataset.sharing_level = DataSharingLevel.ORGANIZATION
        multi_file_dataset.type = DatasetType.CSV

        # all() returns datasets first, then access logs
        db_session.all.side_effect = [
            [dataset, multi_file_dataset],   # datasets query
            [Mock(user_id=1), Mock(user_id=2), Mock(user_id=1)],  # access logs
        ]

        stats = svc.get_sharing_stats(org_id=admin.organization_id, user=admin)

        assert stats["total_datasets"] == 2
        assert stats["by_sharing_level"]["public"] == 1
        assert stats["by_sharing_level"]["organization"] == 1
        assert stats["by_sharing_level"]["private"] == 0
        assert stats["by_type"]["csv"] == 2
        assert stats["total_access_logs"] == 3
        assert stats["unique_users_accessed"] == 2  # two unique user_ids

    def test_non_admin_gets_empty(self, svc, db_session, member):
        """Regular member gets empty dict."""
        stats = svc.get_sharing_stats(org_id=10, user=member)
        assert stats == {}

    def test_wrong_org_gets_empty(self, svc, db_session, admin):
        """Admin from wrong org gets empty dict."""
        stats = svc.get_sharing_stats(org_id=999, user=admin)
        assert stats == {}

    def test_owner_role_gets_stats(self, svc, db_session, owner):
        """Org owner (role='owner') gets stats."""
        db_session.all.side_effect = [[], []]
        owner.role = "owner"
        stats = svc.get_sharing_stats(org_id=owner.organization_id, user=owner)
        assert stats["total_datasets"] == 0


# ── get_org_shared_datasets ──────────────────────────────────────────

class TestGetOrgSharedDatasets:
    """SharingService.get_org_shared_datasets()"""

    def test_org_member_gets_shared(self, svc, db_session, member, dataset):
        """Member can list organization-shared datasets."""
        dataset.sharing_level = DataSharingLevel.ORGANIZATION
        db_session.all.return_value = [dataset]

        result = svc.get_org_shared_datasets(org_id=member.organization_id, user=member)

        assert len(result) == 1
        assert result[0].id == dataset.id

    def test_wrong_org_returns_empty(self, svc, db_session, member):
        """User from different org gets empty list."""
        result = svc.get_org_shared_datasets(org_id=999, user=member)
        assert result == []


# ── get_dataset_analytics ────────────────────────────────────────────

class TestGetDatasetAnalytics:
    """SharingService.get_dataset_analytics()"""

    def test_owner_gets_analytics(self, svc, db_session, owner, dataset):
        """Owner can view analytics for their dataset."""
        db_session.first.return_value = dataset
        # .count() on chained queries returns these values
        db_session.count.side_effect = [5, 3, 20]

        result = svc.get_dataset_analytics(dataset_id=dataset.id, user_id=owner.id)

        assert result["dataset_id"] == dataset.id
        assert result["dataset_name"] == dataset.name
        assert result["share_enabled"] is False
        assert result["view_count"] == 0
        assert result["total_accesses"] == 5
        assert result["chat_sessions"] == 3
        assert result["total_chat_messages"] == 20

    def test_not_found_raises(self, svc, db_session, owner):
        """Non-existent dataset raises 404."""
        db_session.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.get_dataset_analytics(dataset_id=999, user_id=owner.id)

        assert exc.value.status_code == 404

    def test_not_owner_raises(self, svc, db_session, member, dataset):
        """Non-owner gets 404 (owner_id filter in query)."""
        db_session.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.get_dataset_analytics(dataset_id=dataset.id, user_id=member.id)

        assert exc.value.status_code == 404


# ── validate_dataset_files ───────────────────────────────────────────

class TestValidateDatasetFiles:
    """SharingService.validate_dataset_files()"""

    async def test_connector_dataset_valid(self, svc, db_session, connector_dataset):
        """Connector-based dataset is valid when connector exists and is active."""
        mock_connector = Mock(id=50, is_deleted=False, is_active=True)
        db_session.first.return_value = mock_connector

        result = await svc.validate_dataset_files(connector_dataset)

        assert result["file_valid"] is True
        assert result["file_check_method"] == "connector_check"
        assert "error" not in result

    async def test_connector_dataset_invalid(self, svc, db_session, connector_dataset):
        """Connector-based dataset is invalid when connector is deleted."""
        db_session.first.return_value = None

        result = await svc.validate_dataset_files(connector_dataset)

        assert result["file_valid"] is False
        assert result["file_check_method"] == "connector_check"
        assert result["error"] == "Connector is deleted or inactive"

    async def test_uploaded_file_via_dataset_files_table(self, svc, db_session, dataset, dataset_file):
        """Uploaded file found via DatasetFile table."""
        db_session.all.return_value = [dataset_file]

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(return_value=True)

            result = await svc.validate_dataset_files(dataset)

        assert result["file_valid"] is True
        assert result["file_check_method"] == "dataset_files_table"

    async def test_uploaded_file_not_found_in_storage(self, svc, db_session, dataset, dataset_file):
        """DatasetFile record exists but file not in storage."""
        db_session.all.return_value = [dataset_file]

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(return_value=False)

            result = await svc.validate_dataset_files(dataset)

        assert result["file_valid"] is False
        assert result["file_check_method"] == "dataset_files_table"
        assert result["error"] == "No files found in storage"

    async def test_uploaded_file_uses_relative_path(self, svc, db_session, dataset, dataset_file):
        """Uses relative_path when available."""
        db_session.all.return_value = [dataset_file]
        dataset_file.relative_path = "datasets/100/data.csv"
        dataset_file.file_path = "/storage/datasets/100/data.csv"

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(return_value=True)

            result = await svc.validate_dataset_files(dataset)

        assert result["file_valid"] is True
        mock_storage.dataset_file_exists.assert_awaited_once_with("datasets/100/data.csv")

    async def test_legacy_file_path(self, svc, db_session, dataset):
        """Legacy single file_path check."""
        db_session.all.return_value = []  # no DatasetFile records
        dataset.file_path = "/storage/test.csv"

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(return_value=True)

            result = await svc.validate_dataset_files(dataset)

        assert result["file_valid"] is True
        assert result["file_check_method"] == "legacy_file_path"

    async def test_legacy_file_path_not_found(self, svc, db_session, dataset):
        """Legacy file_path check returns False when file missing."""
        db_session.all.return_value = []
        dataset.file_path = "/storage/missing.csv"

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(return_value=False)

            result = await svc.validate_dataset_files(dataset)

        assert result["file_valid"] is False
        assert result["file_check_method"] == "legacy_file_path"

    async def test_legacy_file_path_storage_error(self, svc, db_session, dataset):
        """Storage error during legacy check is caught and reported.

        Note: file_check_method stays at the default ``not_applicable``
        because the exception is raised inside the try block, before the
        method label is set.
        """
        db_session.all.return_value = []
        dataset.file_path = "/storage/test.csv"
        dataset.source_url = None  # prevent source_url branch

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(
                side_effect=RuntimeError("Storage unavailable")
            )

            result = await svc.validate_dataset_files(dataset)

        assert result["file_valid"] is False
        assert result["file_check_method"] == "not_applicable"
        assert "Storage unavailable" in result["error"]

    async def test_source_url_non_http(self, svc, db_session, dataset):
        """source_url that doesn't start with http:// or https:// is treated as file path."""
        db_session.all.return_value = []
        dataset.file_path = None
        dataset.source_url = "uploads/myfile.csv"

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(return_value=True)

            result = await svc.validate_dataset_files(dataset)

        assert result["file_valid"] is True
        assert result["file_check_method"] == "source_url"
        mock_storage.dataset_file_exists.assert_awaited_once_with("uploads/myfile.csv")

    async def test_http_source_url_skipped(self, svc, db_session, dataset):
        """source_url that IS http:// is not checked (falls through to no_references)."""
        db_session.all.return_value = []
        dataset.file_path = None
        dataset.source_url = "https://example.com/data.csv"

        result = await svc.validate_dataset_files(dataset)

        assert result["file_valid"] is False
        assert result["file_check_method"] == "no_references"
        assert result["error"] == "Dataset has no file references"

    async def test_no_file_references(self, svc, db_session, dataset):
        """Dataset with no file references returns invalid."""
        db_session.all.return_value = []
        dataset.file_path = None
        dataset.source_url = None
        dataset.connector_id = None

        result = await svc.validate_dataset_files(dataset)

        assert result["file_valid"] is False
        assert result["file_check_method"] == "no_references"
        assert result["error"] == "Dataset has no file references"


# ── _is_uploaded_file ─────────────────────────────────────────────────

class TestIsUploadedFile:
    """SharingService._is_uploaded_file()"""

    def test_source_url_not_http(self, svc):
        """source_url that does not start with http is uploaded."""
        ds = Mock(source_url="uploads/data.csv", is_multi_file_dataset=False,
                  file_path=None, connector_id=None, type=Mock(value="csv"))
        assert svc._is_uploaded_file(ds) is True

    def test_source_url_http(self, svc):
        """source_url that starts with http but type is uploaded-type."""
        ds = Mock(source_url="https://example.com/data.csv", is_multi_file_dataset=False,
                  file_path=None, connector_id=None, type=Mock(value="csv"))
        assert svc._is_uploaded_file(ds) is True

    def test_multi_file_dataset(self, svc):
        """Multi-file datasets are uploaded files."""
        ds = Mock(source_url=None, is_multi_file_dataset=True,
                  file_path=None, connector_id=None, type=Mock(value="csv"))
        assert svc._is_uploaded_file(ds) is True

    def test_has_file_path(self, svc):
        """Dataset with file_path is uploaded."""
        ds = Mock(source_url=None, is_multi_file_dataset=False,
                  file_path="/storage/data.csv", connector_id=None, type=Mock(value="csv"))
        assert svc._is_uploaded_file(ds) is True

    def test_connector_dataset_not_uploaded(self, svc):
        """Connector-based dataset with non-uploaded type returns False."""
        ds = Mock(source_url="https://api.example.com", is_multi_file_dataset=False,
                  file_path=None, connector_id=50, type=Mock(value="database"))
        assert svc._is_uploaded_file(ds) is False

    def test_unknown_type_not_uploaded(self, svc):
        """Dataset with unrecognized type and no file references returns False."""
        ds = Mock(source_url="https://api.example.com", is_multi_file_dataset=False,
                  file_path=None, connector_id=50, type=Mock(value="api"))
        assert svc._is_uploaded_file(ds) is False


# ── _generate_token ──────────────────────────────────────────────────

class TestGenerateToken:
    """SharingService._generate_token()"""

    def test_generates_32_char_token(self, svc):
        """Token is always 32 hex characters."""
        token = svc._generate_token(dataset_id=100, user_id=1)
        assert len(token) == 32
        assert isinstance(token, str)
        # Hex chars only
        int(token, 16)

    def test_different_inputs_different_tokens(self, svc):
        """Different dataset/user pairs produce different tokens."""
        t1 = svc._generate_token(100, 1)
        t2 = svc._generate_token(100, 2)
        t3 = svc._generate_token(200, 1)
        assert t1 != t2
        assert t1 != t3
        assert t2 != t3

    def test_same_inputs_different_tokens(self, svc):
        """Same inputs produce different tokens because secrets.token_hex varies."""
        t1 = svc._generate_token(100, 1)
        t2 = svc._generate_token(100, 1)
        assert t1 != t2


# ── _log_access ──────────────────────────────────────────────────────

class TestLogAccess:
    """SharingService._log_access()"""

    def test_logs_access(self, svc, db_session, dataset):
        """Access log entry is created and committed."""
        svc._log_access(dataset, "tok123", "10.0.0.1", "test-agent")

        assert db_session.add.called
        added = db_session.add.call_args[0][0]
        assert isinstance(added, DatasetShareAccess)
        assert added.dataset_id == dataset.id
        assert added.share_token == "tok123"
        assert added.ip_address == "10.0.0.1"
        assert added.user_agent == "test-agent"
        db_session.commit.assert_called_once()

    def test_logs_access_with_none(self, svc, db_session, dataset):
        """Access log handles None ip and user_agent."""
        svc._log_access(dataset, "tok123", None, None)

        added = db_session.add.call_args[0][0]
        assert added.ip_address is None
        assert added.user_agent is None


# ── _init_ai_context ─────────────────────────────────────────────────

class TestInitAIContext:
    """SharingService._init_ai_context()"""

    def test_skips_if_context_exists(self, svc, db_session, dataset):
        """If chat_context is already set, do nothing."""
        dataset.chat_context = {"existing": "data"}

        with patch("app.services.sharing.storage_service") as mock_storage:
            svc._init_ai_context(dataset)

        mock_storage.get_dataset_file_url.assert_not_called()
        assert dataset.chat_context == {"existing": "data"}

    def test_initializes_context_with_file_url(self, svc, db_session, dataset):
        """Context includes file_url when storage_service provides one."""
        with (
            patch("app.services.sharing.storage_service") as mock_storage,
            patch("app.services.sharing.settings") as mock_settings,
        ):
            mock_storage.get_dataset_file_url.return_value = "/api/files/serve/test.csv"
            mock_settings.BASE_URL = "http://localhost:8000"
            mock_settings.DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

            svc._init_ai_context(dataset)

        assert dataset.chat_context is not None
        assert dataset.chat_context["dataset_name"] == "Test Dataset"
        assert dataset.chat_context["type"] == DatasetType.CSV
        assert dataset.chat_context["columns"] == [{"name": "id", "type": "int"}, {"name": "name", "type": "text"}]
        assert dataset.chat_context["file_url"] == "http://localhost:8000/api/files/serve/test.csv"
        assert dataset.chat_context["accessible_via_url"] is True
        assert dataset.chat_context["file_path"] == "/storage/test.csv"
        assert dataset.chat_context["mindsdb_datasource"] is None
        assert dataset.chat_context["mindsdb_available"] is False
        assert dataset.chat_model_name is not None

    def test_initializes_context_with_http_file_url(self, svc, db_session, dataset):
        """If get_dataset_file_url already returns an http URL, no base prefix added."""
        with (
            patch("app.services.sharing.storage_service") as mock_storage,
            patch("app.services.sharing.settings") as mock_settings,
        ):
            mock_storage.get_dataset_file_url.return_value = "https://cdn.example.com/files/data.csv"
            mock_settings.BASE_URL = "http://localhost:8000"
            mock_settings.DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

            svc._init_ai_context(dataset)

        assert dataset.chat_context["file_url"] == "https://cdn.example.com/files/data.csv"

    def test_initializes_context_without_file_path(self, svc, db_session, dataset):
        """Dataset without file_path gets no file_url."""
        dataset.file_path = None
        dataset.source_url = None

        with (
            patch("app.services.sharing.storage_service") as mock_storage,
            patch("app.services.sharing.settings") as mock_settings,
        ):
            svc._init_ai_context(dataset)

        assert dataset.chat_context["file_url"] is None
        assert dataset.chat_context["accessible_via_url"] is False
        mock_storage.get_dataset_file_url.assert_not_called()

    def test_file_url_generation_failure(self, svc, db_session, dataset):
        """When get_dataset_file_url raises, accessible_via_url is False."""
        with (
            patch("app.services.sharing.storage_service") as mock_storage,
            patch("app.services.sharing.settings") as mock_settings,
        ):
            mock_storage.get_dataset_file_url.side_effect = RuntimeError("timeout")
            mock_settings.BASE_URL = "http://localhost:8000"
            mock_settings.DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

            svc._init_ai_context(dataset)

        assert dataset.chat_context["file_url"] is None
        assert dataset.chat_context["accessible_via_url"] is False


# ── _disable_sharing ─────────────────────────────────────────────────

class TestDisableSharing:
    """SharingService._disable_sharing()"""

    def test_disables_sharing(self, svc, db_session, dataset):
        """Sets public_share_enabled to False and commits."""
        dataset.public_share_enabled = True
        svc._disable_sharing(dataset)
        assert dataset.public_share_enabled is False
        db_session.commit.assert_called_once()


# ── _create_proxy_connector_sync ─────────────────────────────────────

class TestCreateProxyConnectorSync:
    """SharingService._create_proxy_connector_sync()"""

    def test_creates_new_proxy_connector(self, svc, db_session, connector_dataset):
        """Creates a ProxyConnector for a connector-based dataset."""
        mock_connector = Mock(id=50, connection_config={"base_url": "https://db.example.com"})
        db_session.first.side_effect = [None, mock_connector]  # no existing proxy, original found

        # uuid, quote, ProxyConnector are imported inside the function body
        with (
            patch("uuid.uuid4", return_value="proxy-uuid-123"),
            patch("urllib.parse.quote", return_value="Connector+Dataset"),
            patch("app.models.proxy_connector.ProxyConnector") as MockProxy,
        ):
            mock_proxy_instance = MockProxy.return_value
            result = svc._create_proxy_connector_sync(connector_dataset, "tok_abc")

        assert result is mock_proxy_instance
        assert db_session.add.called
        assert db_session.commit.called

    def test_returns_existing_proxy(self, svc, db_session, connector_dataset):
        """If a proxy already exists, returns it without creating a new one."""
        existing_proxy = Mock()
        db_session.first.return_value = existing_proxy

        result = svc._create_proxy_connector_sync(connector_dataset, "tok_abc")

        assert result is existing_proxy
        db_session.add.assert_not_called()

    def test_creates_proxy_without_connector(self, svc, db_session, dataset):
        """Dataset without connector_id still gets a proxy."""
        dataset.connector_id = None
        db_session.first.side_effect = [None]  # no existing proxy

        with (
            patch("uuid.uuid4", return_value="proxy-uuid-456"),
            patch("urllib.parse.quote", return_value="Dataset"),
            patch("app.models.proxy_connector.ProxyConnector") as MockProxy,
        ):
            mock_proxy_instance = MockProxy.return_value
            result = svc._create_proxy_connector_sync(dataset, "tok_def")

        assert result is mock_proxy_instance

    def test_exception_returns_none(self, svc, db_session, connector_dataset):
        """If an exception occurs, returns None and logs error."""
        db_session.first.side_effect = RuntimeError("DB error")

        result = svc._create_proxy_connector_sync(connector_dataset, "tok_abc")

        assert result is None


# ── _generate_preview ────────────────────────────────────────────────

class TestGeneratePreview:
    """SharingService._generate_preview()"""

    async def test_preview_for_single_csv(self, svc, db_session, dataset):
        """Single CSV file generates a preview."""
        import pandas as pd
        import numpy as np

        df = pd.DataFrame({"a": ["1", "2"], "b": ["3", "4"]})

        with (
            patch("app.services.sharing.storage_service") as mock_storage,
            patch("app.services.sharing.pd.read_csv", return_value=df) as mock_read_csv,
            patch("app.services.sharing.os.path.exists", return_value=True),
        ):
            mock_storage.backend = Mock(storage_dir="/tmp/storage")

            preview = await svc._generate_preview(dataset)

        assert preview is not None
        assert preview["type"] == "csv"
        assert preview["preview_source"] == "single_file"
        assert preview["headers"] == ["a", "b"]
        assert preview["rows"] == [["1", "3"], ["2", "4"]]

    async def test_preview_for_multi_file(self, svc, db_session, multi_file_dataset):
        """Multi-file dataset generates a file-list preview."""
        files = [
            DatasetFile(id=1, dataset_id=101, filename="primary.csv", file_path="/p/primary.csv",
                        file_type="csv", file_size=500, is_primary=True, file_order=0, is_deleted=False),
            DatasetFile(id=2, dataset_id=101, filename="secondary.csv", file_path="/p/secondary.csv",
                        file_type="csv", file_size=300, is_primary=False, file_order=1, is_deleted=False),
        ]
        # The code chains: query().filter().order_by().all()
        # Set up order_by to return self, then all to return files
        db_session.order_by.return_value = db_session
        db_session.all.return_value = files

        preview = await svc._generate_preview(multi_file_dataset)

        assert preview is not None
        assert preview["type"] == "multi_file"
        assert preview["total_files"] == 2
        assert len(preview["files_list"]) == 2
        assert preview["primary_file"]["filename"] == "primary.csv"

    async def test_preview_multi_file_no_files(self, svc, db_session, multi_file_dataset):
        """Multi-file dataset with no files returns None."""
        db_session.all.return_value = []

        preview = await svc._generate_preview(multi_file_dataset)
        assert preview is None

    async def test_preview_returns_none_on_exception(self, svc, db_session, dataset):
        """When preview generation raises, returns None gracefully."""
        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.backend = Mock(storage_dir="/tmp/storage")
            with patch("app.services.sharing.os.path.exists") as mock_exists:
                mock_exists.side_effect = PermissionError("Access denied")

                preview = await svc._generate_preview(dataset)

        assert preview is None


# ── _proxy_info ──────────────────────────────────────────────────────

class TestProxyInfo:
    """SharingService._proxy_info()"""

    def test_proxy_info_contains_expected_fields(self, svc):
        """Proxy info dict has all required keys."""
        ds = Mock()
        ds.type.value = "csv"
        ds.name = "My Dataset"

        with patch("app.services.sharing.settings") as mock_settings:
            mock_settings.BASE_URL = "http://localhost:8000"
            info = svc._proxy_info(ds, "tok_abc")

        assert info["connection_type"] == "csv"
        assert info["proxy_url"] == "http://localhost:8000/api/proxy"
        assert info["access_token"] == "tok_abc"
        assert info["database_name"] == "My Dataset"
        assert info["supports_sql"] is True

    def test_proxy_info_database_type(self, svc):
        """database type also supports SQL."""
        ds = Mock()
        ds.type.value = "database"
        ds.name = "My DB"
        with patch("app.services.sharing.settings") as mock_settings:
            mock_settings.BASE_URL = "http://localhost:8000"
            info = svc._proxy_info(ds, "tok_abc")
        assert info["supports_sql"] is True

    def test_proxy_info_non_sql_type(self, svc):
        """pdf type does NOT support SQL."""
        ds = Mock()
        ds.type.value = "pdf"
        ds.name = "My PDF"
        with patch("app.services.sharing.settings") as mock_settings:
            mock_settings.BASE_URL = "http://localhost:8000"
            info = svc._proxy_info(ds, "tok_abc")
        assert info["supports_sql"] is False


# ── _verify_files_exist ──────────────────────────────────────────────

class TestVerifyFilesExist:
    """SharingService._verify_files_exist()"""

    async def test_single_file_exists(self, svc, db_session, dataset):
        """Single file that exists passes."""
        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(return_value=True)

            await svc._verify_files_exist(dataset)  # no exception

    async def test_single_file_missing_disables_sharing(self, svc, db_session, dataset):
        """Missing single file disables sharing and raises 410."""
        dataset.public_share_enabled = True

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc:
                await svc._verify_files_exist(dataset)

            assert exc.value.status_code == 410
            assert dataset.public_share_enabled is False
            db_session.commit.assert_called_once()

    async def test_multi_file_at_least_one_exists(self, svc, db_session, multi_file_dataset):
        """Multi-file dataset with at least one valid file passes."""
        files = [
            DatasetFile(id=1, dataset_id=101, filename="a.csv", file_path="/p/a.csv",
                        relative_path="a.csv", is_deleted=False),
            DatasetFile(id=2, dataset_id=101, filename="b.csv", file_path="/p/b.csv",
                        relative_path="b.csv", is_deleted=False),
        ]
        db_session.all.return_value = files

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(side_effect=[False, True])

            await svc._verify_files_exist(multi_file_dataset)  # no exception

    async def test_multi_file_all_missing_disables_sharing(self, svc, db_session, multi_file_dataset):
        """Multi-file dataset with no valid files disables sharing."""
        files = [
            DatasetFile(id=1, dataset_id=101, filename="a.csv", file_path="/p/a.csv",
                        relative_path="a.csv", is_deleted=False),
        ]
        db_session.all.return_value = files
        multi_file_dataset.public_share_enabled = True

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc:
                await svc._verify_files_exist(multi_file_dataset)

            assert exc.value.status_code == 410
            assert multi_file_dataset.public_share_enabled is False

    async def test_file_check_exception_handled(self, svc, db_session, dataset):
        """Exception during file check is caught and treated as file missing."""
        dataset.public_share_enabled = True

        with patch("app.services.sharing.storage_service") as mock_storage:
            mock_storage.dataset_file_exists = AsyncMock(
                side_effect=RuntimeError("timeout")
            )

            with pytest.raises(HTTPException) as exc:
                await svc._verify_files_exist(dataset)

            assert exc.value.status_code == 410


# ── _attach_csv_preview ──────────────────────────────────────────────

class TestAttachCSVPreview:
    """SharingService._attach_csv_preview()"""

    def test_attach_csv_preview(self, svc):
        """Attaches headers and rows from a DataFrame.

        Note: ``bool`` is a subclass of ``int`` in Python, so
        ``isinstance(True, (np.integer, int))`` is ``True`` -- booleans
        appear as ``1`` / ``0`` in the output.  ``pd.NA`` is caught by
        ``pd.isna`` and becomes ``None``.
        """
        import pandas as pd
        import numpy as np

        df = pd.DataFrame({
            "id": [1, 2],
            "name": ["Alice", "Bob"],
            "score": [95.5, 87.3],
            "active": [True, False],
            "comment": ["Hello", pd.NA],
        })

        preview = {}
        svc._attach_csv_preview(preview, df)

        assert preview["headers"] == ["id", "name", "score", "active", "comment"]
        assert len(preview["rows"]) == 2
        assert preview["total_rows"] == 2

        # bool is subclass of int in Python -> True becomes 1, False becomes 0
        assert preview["rows"][0] == [1, "Alice", 95.5, 1, "Hello"]
        assert preview["rows"][1] == [2, "Bob", 87.3, 0, None]
