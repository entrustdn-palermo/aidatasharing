"""
Unit tests for DataSharingService — backward-compatible delegating wrapper.

Tests mock all external seams: DB session, MindsDBService, StorageService,
SharingService, AccessControlService, ChatSessionService, and related utilities.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
from datetime import datetime
from fastapi import HTTPException

from app.services.data_sharing import DataSharingService
from app.models.user import User
from app.models.dataset import (
    Dataset, DatasetType, DatasetStatus, DatasetFile,
    DatasetChatSession, ChatMessage, DatasetShareAccess,
)
from app.models.organization import DataSharingLevel


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def db_session():
    """Mock DB session with proper chainable query."""
    mock = Mock()
    mock.query.return_value = mock
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
    return DataSharingService(db_session)


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
        allow_ai_chat=True,
        size_bytes=1024,
        file_path="/storage/test.csv",
        source_url="test.csv",
        agent_name="dataset_42_agent",
        public_share_enabled=True,
        share_token="abc123def456",
        share_password=None,
        ai_chat_enabled=True,
        row_count=10,
        column_count=3,
        is_multi_file_dataset=False,
        total_files_count=1,
        share_view_count=5,
        last_accessed=datetime(2025, 1, 1),
    )
    return ds


@pytest.fixture
def shared_dataset(owner):
    """Create a dataset configured for public sharing."""
    ds = Dataset(
        id=50,
        name="Shared Dataset",
        description="A publicly shared dataset",
        type=DatasetType.CSV,
        status=DatasetStatus.ACTIVE,
        owner_id=owner.id,
        organization_id=owner.organization_id,
        sharing_level=DataSharingLevel.PUBLIC,
        is_active=True,
        is_deleted=False,
        allow_download=True,
        allow_api_access=True,
        allow_ai_chat=True,
        size_bytes=2048,
        file_path="/storage/shared.csv",
        source_url="shared.csv",
        agent_name="dataset_50_agent",
        public_share_enabled=True,
        share_token="shared_token_789",
        share_password=None,
        ai_chat_enabled=True,
        row_count=20,
        column_count=5,
        is_multi_file_dataset=False,
        total_files_count=1,
        share_view_count=10,
    )
    return ds


@pytest.fixture
def multi_file_dataset(owner):
    """Create a multi-file dataset."""
    ds = Dataset(
        id=60,
        name="Multi File Dataset",
        description="A dataset with multiple files",
        type=DatasetType.CSV,
        status=DatasetStatus.ACTIVE,
        owner_id=owner.id,
        organization_id=owner.organization_id,
        sharing_level=DataSharingLevel.PUBLIC,
        is_active=True,
        is_deleted=False,
        allow_download=True,
        allow_api_access=True,
        allow_ai_chat=True,
        size_bytes=4096,
        file_path=None,
        source_url=None,
        agent_name="dataset_60_agent",
        public_share_enabled=True,
        share_token="multi_token_111",
        share_password=None,
        ai_chat_enabled=True,
        row_count=30,
        column_count=4,
        is_multi_file_dataset=True,
        total_files_count=3,
        share_view_count=0,
    )
    return ds


@pytest.fixture
def password_protected_dataset(owner):
    """Create a password-protected dataset."""
    ds = Dataset(
        id=70,
        name="Protected Dataset",
        description="Password-protected",
        type=DatasetType.CSV,
        status=DatasetStatus.ACTIVE,
        owner_id=owner.id,
        organization_id=owner.organization_id,
        sharing_level=DataSharingLevel.PUBLIC,
        is_active=True,
        is_deleted=False,
        allow_download=True,
        allow_api_access=True,
        allow_ai_chat=True,
        size_bytes=1024,
        file_path="/storage/protected.csv",
        source_url="protected.csv",
        public_share_enabled=True,
        share_token="protected_token",
        share_password="$2b$12$hashed_password_string",
        ai_chat_enabled=True,
        row_count=5,
        column_count=2,
        is_multi_file_dataset=False,
        total_files_count=1,
        share_view_count=0,
    )
    return ds


@pytest.fixture
def chat_session():
    """Create a mock chat session."""
    session = Mock(spec=DatasetChatSession)
    session.id = 100
    session.dataset_id = 42
    session.session_token = "session_token_abc"
    session.share_token = "abc123def456"
    session.is_active = True
    session.message_count = 3
    session.ai_model_name = "gemini-2.0-flash"
    session.total_tokens_used = 150
    session.updated_at = datetime(2025, 6, 1)
    return session


@pytest.fixture
def mock_chat_request():
    """Create a mock chat request."""
    req = Mock()
    req.message = "Show me trends in this data"
    req.password = None
    req.session_token = "session_token_abc"
    return req


@pytest.fixture
def mock_analyze_request():
    """Create a mock analyze request."""
    req = Mock()
    req.query = "Analyze the data"
    req.password = None
    req.max_visualizations = 3
    return req


@pytest.fixture
def mock_dataset_file():
    """Create a mock DatasetFile."""
    f = Mock(spec=DatasetFile)
    f.id = 1
    f.dataset_id = 42
    f.filename = "data.csv"
    f.file_path = "/storage/data.csv"
    f.relative_path = "data.csv"
    f.file_size = 1024
    f.file_type = "csv"
    f.is_primary = True
    f.file_order = 0
    f.is_deleted = False
    return f


# ── can_access_dataset ─────────────────────────────────────────────────

class TestCanAccessDataset:
    """DataSharingService.can_access_dataset() — delegates to AccessControlService."""

    def test_owner_can_access(self, svc, owner, dataset):
        """Owner should be able to access their own dataset."""
        with patch.object(svc.access, 'can_access_dataset', return_value=True):
            assert svc.can_access_dataset(owner, dataset) is True
            svc.access.can_access_dataset.assert_called_once_with(owner, dataset)

    def test_superuser_can_access(self, svc, superuser, dataset):
        """Superuser should be able to access any dataset."""
        with patch.object(svc.access, 'can_access_dataset', return_value=True):
            assert svc.can_access_dataset(superuser, dataset) is True

    def test_org_member_with_permission_can_access(self, svc, other_user, dataset):
        """Org member with permission should be able to access."""
        with patch.object(svc.access, 'can_access_dataset', return_value=True):
            assert svc.can_access_dataset(other_user, dataset) is True

    def test_no_access_returns_false(self, svc, other_user, dataset):
        """User without access should get False."""
        with patch.object(svc.access, 'can_access_dataset', return_value=False):
            assert svc.can_access_dataset(other_user, dataset) is False

    def test_deleted_dataset_no_access(self, svc, owner, dataset):
        """Deleted dataset should return False."""
        dataset.is_deleted = True
        with patch.object(svc.access, 'can_access_dataset', return_value=False):
            assert svc.can_access_dataset(owner, dataset) is False


# ── can_download_dataset ───────────────────────────────────────────────

class TestCanDownloadDataset:
    """DataSharingService.can_download_dataset() — delegates to AccessControlService."""

    def test_owner_can_download(self, svc, owner, dataset):
        """Owner should be able to download."""
        with patch.object(svc.access, 'can_download_dataset', return_value=True):
            assert svc.can_download_dataset(owner, dataset) is True

    def test_download_disabled_returns_false(self, svc, owner, dataset):
        """When allow_download is False, should return False."""
        dataset.allow_download = False
        with patch.object(svc.access, 'can_download_dataset', return_value=False):
            assert svc.can_download_dataset(owner, dataset) is False

    def test_no_access_returns_false(self, svc, other_user, dataset):
        """User without access should get False."""
        with patch.object(svc.access, 'can_download_dataset', return_value=False):
            assert svc.can_download_dataset(other_user, dataset) is False


# ── get_accessible_datasets ────────────────────────────────────────────

class TestGetAccessibleDatasets:
    """DataSharingService.get_accessible_datasets() — delegates to AccessControlService."""

    def test_returns_list(self, svc, owner, dataset):
        """Should return list of accessible datasets."""
        with patch.object(svc.access, 'get_accessible_datasets', return_value=[dataset]):
            result = svc.get_accessible_datasets(owner)
            assert result == [dataset]
            assert len(result) == 1

    def test_empty_when_no_access(self, svc, other_user):
        """Should return empty list when no datasets accessible."""
        with patch.object(svc.access, 'get_accessible_datasets', return_value=[]):
            result = svc.get_accessible_datasets(other_user)
            assert result == []

    def test_filters_applied(self, svc, owner, dataset):
        """Should pass filter parameters to AccessControlService."""
        with patch.object(svc.access, 'get_accessible_datasets', return_value=[dataset]):
            svc.get_accessible_datasets(
                owner,
                sharing_level=DataSharingLevel.PUBLIC,
                include_inactive=False,
                include_deleted=False,
                dataset_type=DatasetType.CSV,
                skip=0,
                limit=10,
            )
            svc.access.get_accessible_datasets.assert_called_once_with(
                owner, DataSharingLevel.PUBLIC, False, False,
                DatasetType.CSV, 0, 10,
            )


# ── create_share_link ──────────────────────────────────────────────────

class TestCreateShareLink:
    """DataSharingService.create_share_link() — delegates to SharingService."""

    def test_creates_link(self, svc, owner, dataset):
        """Should create share link for valid dataset."""
        expected = {
            "share_token": "new_token",
            "share_url": "/shared/new_token",
            "chat_enabled": True,
            "password_protected": False,
            "dataset_name": dataset.name,
        }
        with patch.object(svc.sharing, 'create_share_link', return_value=expected):
            result = svc.create_share_link(
                dataset_id=dataset.id,
                user_id=owner.id,
                password=None,
                enable_chat=True,
            )
            assert result["share_token"] == "new_token"
            assert result["chat_enabled"] is True
            svc.sharing.create_share_link.assert_called_once_with(
                dataset.id, owner.id, None, True,
            )

    def test_updates_existing_link(self, svc, owner, dataset):
        """Should update existing link when called again."""
        expected = {
            "share_token": "updated_token",
            "share_url": "/shared/updated_token",
            "chat_enabled": False,
            "password_protected": True,
            "dataset_name": dataset.name,
        }
        with patch.object(svc.sharing, 'create_share_link', return_value=expected):
            result = svc.create_share_link(
                dataset_id=dataset.id,
                user_id=owner.id,
                password="newpass",
                enable_chat=False,
            )
            assert result["password_protected"] is True
            assert result["chat_enabled"] is False

    def test_enables_chat(self, svc, owner, dataset):
        """Should enable chat when requested."""
        expected = {
            "share_token": "chat_token",
            "share_url": "/shared/chat_token",
            "chat_enabled": True,
            "password_protected": False,
            "dataset_name": dataset.name,
        }
        with patch.object(svc.sharing, 'create_share_link', return_value=expected):
            result = svc.create_share_link(
                dataset_id=dataset.id,
                user_id=owner.id,
                enable_chat=True,
            )
            assert result["chat_enabled"] is True


# ── get_shared_dataset ─────────────────────────────────────────────────

class TestGetSharedDataset:
    """DataSharingService.get_shared_dataset() — delegates to SharingService."""

    async def test_returns_dataset_info(self, svc, shared_dataset):
        """Should return shared dataset info."""
        expected = {
            "dataset_id": shared_dataset.id,
            "dataset_name": shared_dataset.name,
            "enable_chat": True,
            "allow_download": True,
        }
        with patch.object(svc.sharing, 'get_shared_dataset', AsyncMock(return_value=expected)):
            result = await svc.get_shared_dataset(
                share_token=shared_dataset.share_token,
            )
            assert result["dataset_id"] == shared_dataset.id
            assert result["enable_chat"] is True

    async def test_not_found(self, svc):
        """Should raise 404 when dataset not found."""
        with patch.object(svc.sharing, 'get_shared_dataset', AsyncMock(side_effect=HTTPException(404))):
            with pytest.raises(HTTPException) as exc:
                await svc.get_shared_dataset(share_token="nonexistent")
            assert exc.value.status_code == 404


# ── verify_share_password ──────────────────────────────────────────────

class TestVerifySharePassword:
    """DataSharingService.verify_share_password() — delegates to SharingService."""

    def test_no_password(self, svc, dataset):
        """Should return True when no password set."""
        dataset.share_password = None
        with patch.object(svc.sharing, 'verify_password', return_value=True):
            assert svc.verify_share_password(dataset, None) is True

    def test_correct_password(self, svc, password_protected_dataset):
        """Should return True for correct password."""
        with patch.object(svc.sharing, 'verify_password', return_value=True):
            assert svc.verify_share_password(password_protected_dataset, "correct_password") is True

    def test_incorrect_password(self, svc, password_protected_dataset):
        """Should return False for incorrect password."""
        with patch.object(svc.sharing, 'verify_password', return_value=False):
            assert svc.verify_share_password(password_protected_dataset, "wrong_password") is False


# ── update_sharing_level ───────────────────────────────────────────────

class TestUpdateSharingLevel:
    """DataSharingService.update_sharing_level() — delegates to SharingService."""

    def test_owner_can_update(self, svc, owner, dataset):
        """Owner should be able to update sharing level."""
        with patch.object(svc.sharing, 'update_sharing_level', return_value=True):
            result = svc.update_sharing_level(owner, dataset, DataSharingLevel.PUBLIC)
            assert result is True
            svc.sharing.update_sharing_level.assert_called_once_with(
                owner, dataset, DataSharingLevel.PUBLIC,
            )

    def test_non_owner_cannot_update(self, svc, other_user, dataset):
        """Non-owner should not be able to update sharing level."""
        with patch.object(svc.sharing, 'update_sharing_level', return_value=False):
            result = svc.update_sharing_level(other_user, dataset, DataSharingLevel.PUBLIC)
            assert result is False

    def test_superuser_can_update(self, svc, superuser, dataset):
        """Superuser should be able to update any sharing level."""
        with patch.object(svc.sharing, 'update_sharing_level', return_value=True):
            result = svc.update_sharing_level(superuser, dataset, DataSharingLevel.ORGANIZATION)
            assert result is True


# ── create_chat_session ────────────────────────────────────────────────

class TestCreateChatSession:
    """DataSharingService.create_chat_session() — delegates to ChatSessionService."""

    def test_creates_session(self, svc, shared_dataset, chat_session):
        """Should create a chat session for a shared dataset."""
        expected = {
            "session_token": chat_session.session_token,
            "model_name": chat_session.ai_model_name,
            "dataset_name": shared_dataset.name,
        }
        with patch.object(svc.chat_session, 'create_session', return_value=expected):
            result = svc.create_chat_session(
                share_token=shared_dataset.share_token,
            )
            assert result["session_token"] == chat_session.session_token
            svc.chat_session.create_session.assert_called_once_with(
                shared_dataset.share_token, None, None, None,
            )

    def test_raises_when_dataset_not_found(self, svc):
        """Should raise 404 when dataset not found."""
        with patch.object(svc.chat_session, 'create_session', side_effect=HTTPException(404)):
            with pytest.raises(HTTPException) as exc:
                svc.create_chat_session(share_token="nonexistent")
            assert exc.value.status_code == 404

    def test_raises_when_limit_reached(self, svc, shared_dataset):
        """Should raise 429 when session limit reached."""
        with patch.object(svc.chat_session, 'create_session', side_effect=HTTPException(429)):
            with pytest.raises(HTTPException) as exc:
                svc.create_chat_session(share_token=shared_dataset.share_token)
            assert exc.value.status_code == 429


# ── send_chat_message ──────────────────────────────────────────────────

class TestSendChatMessage:
    """DataSharingService.send_chat_message() — delegates to ChatSessionService."""

    def test_sends_message(self, svc, chat_session):
        """Should send a chat message and return response."""
        expected = {
            "user_message": {"id": 1, "content": "Hello", "type": "user"},
            "ai_response": {"id": 2, "content": "Hi there!", "tokens_used": 50},
        }
        with patch.object(svc.chat_session, 'send_message', return_value=expected):
            result = svc.send_chat_message(
                session_token=chat_session.session_token,
                message="Hello",
            )
            assert result["ai_response"]["content"] == "Hi there!"
            svc.chat_session.send_message.assert_called_once_with(
                chat_session.session_token, "Hello", "user",
            )

    def test_raises_when_session_not_found(self, svc):
        """Should raise 404 when session not found."""
        with patch.object(svc.chat_session, 'send_message', side_effect=HTTPException(404)):
            with pytest.raises(HTTPException) as exc:
                svc.send_chat_message(session_token="invalid", message="Hello")
            assert exc.value.status_code == 404


# ── get_chat_history ───────────────────────────────────────────────────

class TestGetChatHistory:
    """DataSharingService.get_chat_history() — delegates to ChatSessionService."""

    def test_returns_history(self, svc, chat_session):
        """Should return chat message history."""
        expected = [
            {"id": 1, "type": "user", "content": "Hello"},
            {"id": 2, "type": "assistant", "content": "Hi!"},
        ]
        with patch.object(svc.chat_session, 'get_history', return_value=expected):
            result = svc.get_chat_history(session_token=chat_session.session_token)
            assert len(result) == 2
            assert result[0]["content"] == "Hello"

    def test_raises_when_session_not_found(self, svc):
        """Should raise 404 when session not found."""
        with patch.object(svc.chat_session, 'get_history', side_effect=HTTPException(404)):
            with pytest.raises(HTTPException) as exc:
                svc.get_chat_history(session_token="invalid")
            assert exc.value.status_code == 404


# ── end_chat_session ───────────────────────────────────────────────────

class TestEndChatSession:
    """DataSharingService.end_chat_session() — delegates to ChatSessionService."""

    def test_ends_session(self, svc, chat_session):
        """Should end a chat session."""
        with patch.object(svc.chat_session, 'end_session', return_value=True):
            result = svc.end_chat_session(session_token=chat_session.session_token)
            assert result is True

    def test_session_not_found(self, svc):
        """Should return False when session not found."""
        with patch.object(svc.chat_session, 'end_session', return_value=False):
            result = svc.end_chat_session(session_token="nonexistent")
            assert result is False


# ── chat_with_shared_dataset ───────────────────────────────────────────

class TestChatWithSharedDataset:
    """DataSharingService.chat_with_shared_dataset()"""

    async def test_returns_chat_response(self, svc, db_session, shared_dataset, chat_session, mock_chat_request):
        """Should return chat response when all inputs are valid."""
        db_session.first.return_value = shared_dataset
        # Second query returns the chat session
        def first_side_effect():
            # Called twice: first for dataset, second for session
            if hasattr(first_side_effect, 'call_count'):
                first_side_effect.call_count += 1
            else:
                first_side_effect.call_count = 0
            if first_side_effect.call_count == 0:
                return shared_dataset
            return chat_session

        db_session.first.side_effect = first_side_effect

        mock_chat_response = {
            "answer": "Here are the trends I found...",
            "response": "Here are the trends I found...",
            "source": "anton_shared_chat",
            "agent_name": "Anton",
            "has_visualizations": True,
            "visualization_count": 2,
            "model": "gemini-2.0-flash",
            "visualizations": [{"type": "bar", "data": []}],
            "data_analysis": {"summary": "good"},
        }

        with (
            patch("app.services.mindsdb.MindsDBService") as MockMindsDB,
            patch("app.services.prompt_templates.with_anton_context", return_value="Anton context message"),
            patch("app.core.config.settings") as mock_settings,
        ):
            mock_settings.MAX_CHAT_SESSIONS_PER_DATASET = 10
            mock_settings.USE_AGENT_BASED_CHAT = True
            mock_mindsdb_instance = MockMindsDB.return_value
            mock_mindsdb_instance.chat_with_dataset_agent = AsyncMock(return_value=mock_chat_response)

            # Patch _attach_shared_chat_visualizations to avoid viz logic
            with patch.object(svc, '_attach_shared_chat_visualizations', AsyncMock(return_value=mock_chat_response)):
                result = await svc.chat_with_shared_dataset(
                    share_token=shared_dataset.share_token,
                    chat_request=mock_chat_request,
                    request=None,
                )

            assert result["answer"] == "Here are the trends I found..."
            assert result["has_visualizations"] is True
            assert db_session.add.called
            assert db_session.commit.called
            # Two chat messages should be added (user + assistant)
            assert db_session.add.call_count >= 2

    async def test_raises_404_when_dataset_not_found(self, svc, db_session, mock_chat_request):
        """Should raise 404 when shared dataset not found."""
        db_session.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await svc.chat_with_shared_dataset(
                share_token="nonexistent",
                chat_request=mock_chat_request,
            )
        assert exc.value.status_code == 404
        assert "not found" in str(exc.value.detail).lower()

    async def test_raises_403_when_chat_disabled(self, svc, db_session, shared_dataset, mock_chat_request):
        """Should raise 403 when allow_ai_chat is False."""
        shared_dataset.allow_ai_chat = False
        db_session.first.return_value = shared_dataset

        with patch.object(svc.sharing, 'require_password', Mock()):
            with pytest.raises(HTTPException) as exc:
                await svc.chat_with_shared_dataset(
                    share_token=shared_dataset.share_token,
                    chat_request=mock_chat_request,
                )
            assert exc.value.status_code == 403
            assert "disabled" in str(exc.value.detail).lower()

    async def test_raises_413_when_message_too_long(self, svc, db_session, shared_dataset, mock_chat_request):
        """Should raise 413 when message exceeds 4000 characters."""
        mock_chat_request.message = "A" * 4001
        db_session.first.return_value = shared_dataset

        with patch.object(svc.sharing, 'require_password', Mock()):
            with pytest.raises(HTTPException) as exc:
                await svc.chat_with_shared_dataset(
                    share_token=shared_dataset.share_token,
                    chat_request=mock_chat_request,
                )
            assert exc.value.status_code == 413
            assert "too long" in str(exc.value.detail).lower()

    async def test_raises_401_when_no_session_token(self, svc, db_session, shared_dataset, mock_chat_request):
        """Should raise 401 when session_token is missing."""
        mock_chat_request.session_token = None
        db_session.first.return_value = shared_dataset

        with patch.object(svc.sharing, 'require_password', Mock()):
            with pytest.raises(HTTPException) as exc:
                await svc.chat_with_shared_dataset(
                    share_token=shared_dataset.share_token,
                    chat_request=mock_chat_request,
                )
            assert exc.value.status_code == 401
            assert "session" in str(exc.value.detail).lower()

    async def test_raises_401_when_session_expired(self, svc, db_session, shared_dataset, mock_chat_request):
        """Should raise 401 when chat session has expired or is not found."""
        db_session.first.return_value = shared_dataset

        with patch.object(svc.sharing, 'require_password', Mock()):
            # First call returns dataset, second returns None (no active session)
            db_session.first.side_effect = [shared_dataset, None]

            with pytest.raises(HTTPException) as exc:
                await svc.chat_with_shared_dataset(
                    share_token=shared_dataset.share_token,
                    chat_request=mock_chat_request,
                )
            assert exc.value.status_code == 401
            assert "expired" in str(exc.value.detail).lower()

    async def test_raises_429_when_message_limit_reached(self, svc, db_session, shared_dataset, chat_session, mock_chat_request):
        """Should raise 429 when session message limit reached."""
        chat_session.message_count = 10  # At or above MAX_CHAT_SESSIONS_PER_DATASET
        db_session.first.side_effect = [shared_dataset, chat_session]

        with (
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.core.config.settings") as mock_settings,
        ):
            mock_settings.MAX_CHAT_SESSIONS_PER_DATASET = 10

            with pytest.raises(HTTPException) as exc:
                await svc.chat_with_shared_dataset(
                    share_token=shared_dataset.share_token,
                    chat_request=mock_chat_request,
                )
            assert exc.value.status_code == 429
            assert "limit" in str(exc.value.detail).lower()

    async def test_requires_password(self, svc, db_session, password_protected_dataset, mock_chat_request):
        """Should call require_password for password-protected dataset."""
        db_session.first.return_value = password_protected_dataset
        password_protected_dataset.allow_ai_chat = True
        # Short message to avoid 413
        mock_chat_request.message = "Hello"

        with (
            patch.object(svc.sharing, 'require_password', Mock(side_effect=HTTPException(401, detail="Invalid password"))),
        ):
            with pytest.raises(HTTPException) as exc:
                await svc.chat_with_shared_dataset(
                    share_token=password_protected_dataset.share_token,
                    chat_request=mock_chat_request,
                )
            assert exc.value.status_code == 401
            svc.sharing.require_password.assert_called_once_with(
                password_protected_dataset, mock_chat_request.password,
            )

    async def test_non_agent_chat_path(self, svc, db_session, shared_dataset, chat_session, mock_chat_request):
        """Should fall back to chat_with_dataset when USE_AGENT_BASED_CHAT is False."""
        db_session.first.side_effect = [shared_dataset, chat_session]
        mock_chat_request.message = "Hello"

        mock_chat_response = {"answer": "Non-agent response", "source": "legacy"}

        with (
            patch("app.services.mindsdb.MindsDBService") as MockMindsDB,
            patch("app.services.prompt_templates.with_anton_context", return_value="Anton context"),
            patch("app.core.config.settings") as mock_settings,
        ):
            mock_settings.MAX_CHAT_SESSIONS_PER_DATASET = 10
            mock_settings.USE_AGENT_BASED_CHAT = False
            mock_mindsdb_instance = MockMindsDB.return_value
            mock_mindsdb_instance.chat_with_dataset = AsyncMock(return_value=mock_chat_response)

            with patch.object(svc, '_attach_shared_chat_visualizations', AsyncMock(return_value=mock_chat_response)):
                result = await svc.chat_with_shared_dataset(
                    share_token=shared_dataset.share_token,
                    chat_request=mock_chat_request,
                )

            assert result["answer"] == "Non-agent response"
            mock_mindsdb_instance.chat_with_dataset.assert_awaited_once()
            mock_mindsdb_instance.chat_with_dataset_agent.assert_not_called()


# ── _is_visualization_prompt ──────────────────────────────────────────

class TestIsVisualizationPrompt:
    """DataSharingService._is_visualization_prompt()"""

    def test_none_message(self):
        """Should return False for None message."""
        assert DataSharingService._is_visualization_prompt(None) is False

    def test_empty_message(self):
        """Should return False for empty message."""
        assert DataSharingService._is_visualization_prompt("") is False

    def test_visualize_keyword(self):
        """Should return True for 'visualize' keyword."""
        assert DataSharingService._is_visualization_prompt("Can you visualize this data?") is True

    def test_chart_keyword(self):
        """Should return True for 'chart' keyword."""
        assert DataSharingService._is_visualization_prompt("Show me a chart") is True

    def test_graph_keyword(self):
        """Should return True for 'graph' keyword."""
        assert DataSharingService._is_visualization_prompt("Draw a graph") is True

    def test_plot_keyword(self):
        """Should return True for 'plot' keyword."""
        assert DataSharingService._is_visualization_prompt("Plot the distribution") is True

    def test_diagram_keyword(self):
        """Should return True for 'diagram' keyword."""
        assert DataSharingService._is_visualization_prompt("Create a diagram") is True

    def test_show_keyword(self):
        """Should return True for 'show' keyword."""
        assert DataSharingService._is_visualization_prompt("Show me the data") is True

    def test_display_keyword(self):
        """Should return True for 'display' keyword."""
        assert DataSharingService._is_visualization_prompt("Display the results") is True

    def test_trend_keyword(self):
        """Should return True for 'trend' keyword."""
        assert DataSharingService._is_visualization_prompt("What are the trends?") is True

    def test_distribution_keyword(self):
        """Should return True for 'distribution' keyword."""
        assert DataSharingService._is_visualization_prompt("Show distribution") is True

    def test_correlation_keyword(self):
        """Should return True for 'correlation' keyword."""
        assert DataSharingService._is_visualization_prompt("Find correlations") is True

    def test_relationship_keyword(self):
        """Should return True for 'relationship' keyword."""
        assert DataSharingService._is_visualization_prompt("Show relationships") is True

    def test_compare_keyword(self):
        """Should return True for 'compare' keyword."""
        assert DataSharingService._is_visualization_prompt("Compare A and B") is True

    def test_histogram_keyword(self):
        """Should return True for 'histogram' keyword."""
        assert DataSharingService._is_visualization_prompt("Create a histogram") is True

    def test_scatter_keyword(self):
        """Should return True for 'scatter' keyword."""
        assert DataSharingService._is_visualization_prompt("Scatter plot") is True

    def test_heatmap_keyword(self):
        """Should return True for 'heatmap' keyword."""
        assert DataSharingService._is_visualization_prompt("Show heatmap") is True

    def test_bar_keyword(self):
        """Should return True for 'bar' keyword."""
        assert DataSharingService._is_visualization_prompt("Bar chart please") is True

    def test_line_keyword(self):
        """Should return True for 'line' keyword."""
        assert DataSharingService._is_visualization_prompt("Line graph") is True

    def test_pie_keyword(self):
        """Should return True for 'pie' keyword."""
        assert DataSharingService._is_visualization_prompt("Pie chart") is True

    def test_dashboard_keyword(self):
        """Should return True for 'dashboard' keyword."""
        assert DataSharingService._is_visualization_prompt("Build a dashboard") is True

    def test_visualiz_triggers(self):
        """Should trigger on 'visualiz' substring (covers visualize/visualization)."""
        assert DataSharingService._is_visualization_prompt("data visualization") is True

    def test_general_question_no_viz(self):
        """Should return False for a general data question without viz keywords."""
        assert DataSharingService._is_visualization_prompt("What is the average?") is False

    def test_case_insensitive(self):
        """Should be case-insensitive."""
        assert DataSharingService._is_visualization_prompt("SHOW ME THE CHART") is True

    def test_viz_in_long_text(self):
        """Should find viz keyword in longer text."""
        assert DataSharingService._is_visualization_prompt(
            "I would like to understand the relationship between age and income"
        ) is True


# ── _attach_shared_chat_visualizations ─────────────────────────────────

class TestAttachSharedChatVisualizations:
    """DataSharingService._attach_shared_chat_visualizations()"""

    async def test_non_viz_prompt_returns_defaults(self, svc, shared_dataset):
        """Should return response with default viz fields for non-viz prompt."""
        chat_response = {"answer": "Some answer"}
        result = await svc._attach_shared_chat_visualizations(
            chat_response=chat_response,
            dataset=shared_dataset,
            message="What is the average?",
            mindsdb_service=Mock(),
            max_visualizations=3,
        )
        assert result["visualizations"] == []
        assert result["data_analysis"] == {}
        assert result["has_visualizations"] is False
        assert result["visualization_count"] == 0

    async def test_viz_prompt_generates_visualizations(self, svc, shared_dataset):
        """Should generate visualizations for a viz prompt."""
        chat_response = {"answer": "Here are the trends"}
        mock_df = MagicMock()
        mock_df.empty = False
        mock_mindsdb = Mock()
        mock_mindsdb.load_dataset_for_visualization = AsyncMock(return_value=mock_df)
        mock_mindsdb.api_key = "test_key"

        mock_viz_service = Mock()
        mock_viz_service.analyze_dataset.return_value = {"summary": "good", "columns": ["a", "b"]}
        mock_viz_service.generate_chat_visualizations.return_value = [
            {"type": "bar", "data": [1, 2, 3]},
            {"type": "line", "data": [4, 5, 6]},
        ]

        with patch("app.services.data_visualization.get_visualization_service", return_value=mock_viz_service):
            with patch("app.services.data_visualization.sanitize_visualization_payload", side_effect=lambda x: x):
                result = await svc._attach_shared_chat_visualizations(
                    chat_response=chat_response,
                    dataset=shared_dataset,
                    message="Show me a chart",
                    mindsdb_service=mock_mindsdb,
                    max_visualizations=3,
                )

        assert result["has_visualizations"] is True
        assert result["visualization_count"] == 2
        assert len(result["visualizations"]) == 2
        assert result["source"] == "anton_shared_chat"

    async def test_empty_dataframe_returns_no_viz(self, svc, shared_dataset):
        """Should return no visualizations when dataset dataframe is empty."""
        chat_response = {"answer": "Some answer"}
        mock_mindsdb = Mock()
        mock_mindsdb.load_dataset_for_visualization = AsyncMock(return_value=MagicMock())
        mock_mindsdb.load_dataset_for_visualization.return_value.empty = True

        result = await svc._attach_shared_chat_visualizations(
            chat_response=chat_response,
            dataset=shared_dataset,
            message="Show me a chart",
            mindsdb_service=mock_mindsdb,
            max_visualizations=3,
        )

        assert result["has_visualizations"] is False
        assert result["visualization_count"] == 0
        assert "visualization_message" in result

    async def test_none_dataframe_returns_no_viz(self, svc, shared_dataset):
        """Should return no visualizations when dataset dataframe is None."""
        chat_response = {"answer": "Some answer"}
        mock_mindsdb = Mock()
        mock_mindsdb.load_dataset_for_visualization = AsyncMock(return_value=None)

        result = await svc._attach_shared_chat_visualizations(
            chat_response=chat_response,
            dataset=shared_dataset,
            message="Show me a chart",
            mindsdb_service=mock_mindsdb,
            max_visualizations=3,
        )

        assert result["has_visualizations"] is False
        assert result["visualization_count"] == 0

    async def test_viz_generation_failure_graceful(self, svc, shared_dataset):
        """Should gracefully handle visualization generation failure."""
        chat_response = {"answer": "Some answer"}
        mock_mindsdb = Mock()
        mock_mindsdb.load_dataset_for_visualization = AsyncMock(return_value=MagicMock())
        mock_mindsdb.load_dataset_for_visualization.return_value.empty = False
        mock_mindsdb.api_key = "test_key"

        with patch("app.services.data_visualization.get_visualization_service", side_effect=Exception("Viz service down")):
            result = await svc._attach_shared_chat_visualizations(
                chat_response=chat_response,
                dataset=shared_dataset,
                message="Show me a chart",
                mindsdb_service=mock_mindsdb,
                max_visualizations=3,
            )

        assert result["has_visualizations"] is False
        assert result["visualization_count"] == 0
        assert "visualization_message" in result

    async def test_respects_max_visualizations(self, svc, shared_dataset):
        """Should pass max_visualizations to the viz service."""
        chat_response = {"answer": "Here are the trends"}
        mock_mindsdb = Mock()
        mock_mindsdb.load_dataset_for_visualization = AsyncMock(return_value=MagicMock())
        mock_mindsdb.load_dataset_for_visualization.return_value.empty = False
        mock_mindsdb.api_key = "test_key"

        mock_viz_service = Mock()
        mock_viz_service.analyze_dataset.return_value = {}
        mock_viz_service.generate_chat_visualizations.return_value = []

        with (
            patch("app.services.data_visualization.get_visualization_service", return_value=mock_viz_service),
            patch("app.services.data_visualization.sanitize_visualization_payload", side_effect=lambda x: x),
        ):
            await svc._attach_shared_chat_visualizations(
                chat_response=chat_response,
                dataset=shared_dataset,
                message="Show me a chart",
                mindsdb_service=mock_mindsdb,
                max_visualizations=5,
            )

            mock_viz_service.generate_chat_visualizations.assert_called_once()
            _, kwargs = mock_viz_service.generate_chat_visualizations.call_args
            assert kwargs["max_visualizations"] == 5


# ── analyze_shared_dataset_with_anton ──────────────────────────────────

class TestAnalyzeSharedDatasetWithAnton:
    """DataSharingService.analyze_shared_dataset_with_anton()"""

    async def test_returns_analysis_with_visualizations(self, svc, db_session, shared_dataset, mock_analyze_request):
        """Should return analysis with visualizations for a valid shared dataset."""
        db_session.first.return_value = shared_dataset

        mock_chat_response = {
            "answer": "This dataset contains sales data...",
            "agent_name": "Anton",
            "model": "gemini-2.0-flash",
        }

        mock_app_config = MagicMock()
        mock_app_config.integrations.GOOGLE_API_KEY = "test_google_key"

        mock_viz_service = Mock()
        mock_viz_service.analyze_dataset.return_value = {"summary": "good", "columns": ["a", "b"]}
        mock_viz_service.generate_chat_visualizations.return_value = [
            {"type": "bar", "title": "Sales by Region"},
            {"type": "line", "title": "Trend Over Time"},
        ]

        with (
            patch("app.services.mindsdb.MindsDBService") as MockMindsDB,
            patch("app.core.app_config.get_app_config", return_value=mock_app_config),
            patch("app.services.data_visualization.get_visualization_service", return_value=mock_viz_service),
            patch("app.services.data_visualization.sanitize_visualization_payload", side_effect=lambda x: x),
            patch.object(svc.sharing, 'require_password', Mock()),
        ):
            mock_mindsdb_instance = MockMindsDB.return_value
            mock_mindsdb_instance.chat_with_dataset_agent = AsyncMock(return_value=mock_chat_response)
            mock_mindsdb_instance.load_dataset_for_visualization = AsyncMock(return_value=MagicMock())
            mock_mindsdb_instance.load_dataset_for_visualization.return_value.empty = False

            result = await svc.analyze_shared_dataset_with_anton(
                share_token=shared_dataset.share_token,
                analyze_request=mock_analyze_request,
                request=None,
            )

        assert result["success"] is True
        assert result["dataset_id"] == shared_dataset.id
        assert result["answer"] == "This dataset contains sales data..."
        assert result["has_visualizations"] is True
        assert result["visualization_count"] == 2
        assert result["source"] == "anton_shared_analysis"
        assert result["agent_name"] == "Anton"
        assert result["model"] == "gemini-2.0-flash"
        assert "timestamp" in result
        # Verify share_view_count was incremented
        assert shared_dataset.share_view_count == 11  # was 10, incremented to 11
        db_session.commit.assert_called()

    async def test_handles_missing_dataset_gracefully(self, svc, db_session, mock_analyze_request):
        """Should raise 404 when shared dataset not found."""
        db_session.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await svc.analyze_shared_dataset_with_anton(
                share_token="nonexistent",
                analyze_request=mock_analyze_request,
            )
        assert exc.value.status_code == 404

    async def test_handles_visualization_failure_gracefully(self, svc, db_session, shared_dataset, mock_analyze_request):
        """Should return analysis even when visualization generation fails."""
        db_session.first.return_value = shared_dataset

        mock_chat_response = {
            "answer": "Basic analysis without charts",
            "agent_name": "Anton",
        }

        with (
            patch("app.services.mindsdb.MindsDBService") as MockMindsDB,
            patch("app.core.app_config.get_app_config"),
            patch.object(svc.sharing, 'require_password', Mock()),
        ):
            mock_mindsdb_instance = MockMindsDB.return_value
            mock_mindsdb_instance.chat_with_dataset_agent = AsyncMock(return_value=mock_chat_response)
            # Make visualization loading fail
            mock_mindsdb_instance.load_dataset_for_visualization = AsyncMock(
                side_effect=Exception("Storage unavailable")
            )

            result = await svc.analyze_shared_dataset_with_anton(
                share_token=shared_dataset.share_token,
                analyze_request=mock_analyze_request,
            )

        assert result["success"] is True
        assert result["answer"] == "Basic analysis without charts"
        assert result["has_visualizations"] is False
        assert result["visualization_count"] == 0

    async def test_handles_chat_failure_gracefully(self, svc, db_session, shared_dataset, mock_analyze_request):
        """Should return a default answer when the AI chat fails."""
        db_session.first.return_value = shared_dataset

        with (
            patch("app.services.mindsdb.MindsDBService") as MockMindsDB,
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.core.app_config.get_app_config"),
            patch("app.services.data_visualization.get_visualization_service"),
            patch("app.services.data_visualization.sanitize_visualization_payload", side_effect=lambda x: x),
        ):
            mock_mindsdb_instance = MockMindsDB.return_value
            mock_mindsdb_instance.chat_with_dataset_agent = AsyncMock(
                side_effect=RuntimeError("AI service down")
            )
            mock_mindsdb_instance.load_dataset_for_visualization = AsyncMock(return_value=MagicMock())
            mock_mindsdb_instance.load_dataset_for_visualization.return_value.empty = False

            result = await svc.analyze_shared_dataset_with_anton(
                share_token=shared_dataset.share_token,
                analyze_request=mock_analyze_request,
            )

        assert result["success"] is True
        # Should have default answer
        assert "Anton analyzed" in result["answer"]
        assert result["agent_name"] == "Anton"
        # Visualizations should still be generated since dataset loading succeeded
        assert "visualizations" in result

    async def test_raises_403_when_chat_disabled(self, svc, db_session, shared_dataset, mock_analyze_request):
        """Should raise 403 when allow_ai_chat is False."""
        shared_dataset.allow_ai_chat = False
        db_session.first.return_value = shared_dataset

        with patch.object(svc.sharing, 'require_password', Mock()):
            with pytest.raises(HTTPException) as exc:
                await svc.analyze_shared_dataset_with_anton(
                    share_token=shared_dataset.share_token,
                    analyze_request=mock_analyze_request,
                )
            assert exc.value.status_code == 403

    async def test_raises_413_when_query_too_long(self, svc, db_session, shared_dataset, mock_analyze_request):
        """Should raise 413 when query exceeds 4000 characters."""
        mock_analyze_request.query = "A" * 4001
        db_session.first.return_value = shared_dataset

        with patch.object(svc.sharing, 'require_password', Mock()):
            with pytest.raises(HTTPException) as exc:
                await svc.analyze_shared_dataset_with_anton(
                    share_token=shared_dataset.share_token,
                    analyze_request=mock_analyze_request,
                )
            assert exc.value.status_code == 413

    async def test_default_query_when_none(self, svc, db_session, shared_dataset):
        """Should use default analysis query when none provided."""
        analyze_request = Mock()
        analyze_request.query = None
        analyze_request.password = None
        analyze_request.max_visualizations = 3

        db_session.first.return_value = shared_dataset

        mock_chat_response = {"answer": "Default analysis answer", "agent_name": "Anton"}

        with (
            patch("app.services.mindsdb.MindsDBService") as MockMindsDB,
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.core.app_config.get_app_config"),
            patch("app.services.data_visualization.get_visualization_service"),
            patch("app.services.data_visualization.sanitize_visualization_payload", side_effect=lambda x: x),
        ):
            mock_mindsdb_instance = MockMindsDB.return_value
            mock_mindsdb_instance.chat_with_dataset_agent = AsyncMock(return_value=mock_chat_response)
            mock_mindsdb_instance.load_dataset_for_visualization = AsyncMock(return_value=MagicMock())
            mock_mindsdb_instance.load_dataset_for_visualization.return_value.empty = False

            result = await svc.analyze_shared_dataset_with_anton(
                share_token=shared_dataset.share_token,
                analyze_request=analyze_request,
            )

        assert result["success"] is True
        assert result["answer"] == "Default analysis answer"

    async def test_clamps_max_visualizations(self, svc, db_session, shared_dataset):
        """Should clamp max_visualizations between 1 and 5."""
        analyze_request = Mock()
        analyze_request.query = "Analyze"
        analyze_request.password = None
        analyze_request.max_visualizations = 100  # Exceeds max

        db_session.first.return_value = shared_dataset

        with (
            patch("app.services.mindsdb.MindsDBService") as MockMindsDB,
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.core.app_config.get_app_config"),
            patch("app.services.data_visualization.get_visualization_service"),
            patch("app.services.data_visualization.sanitize_visualization_payload", side_effect=lambda x: x),
        ):
            mock_mindsdb_instance = MockMindsDB.return_value
            mock_mindsdb_instance.chat_with_dataset_agent = AsyncMock(
                return_value={"answer": "Analysis", "agent_name": "Anton"}
            )
            mock_mindsdb_instance.load_dataset_for_visualization = AsyncMock(return_value=MagicMock())
            mock_mindsdb_instance.load_dataset_for_visualization.return_value.empty = False

            mock_viz_service = Mock()
            mock_viz_service.analyze_dataset.return_value = {}
            mock_viz_service.generate_chat_visualizations.return_value = []

            with (
                patch("app.services.data_visualization.get_visualization_service", return_value=mock_viz_service),
            ):
                result = await svc.analyze_shared_dataset_with_anton(
                    share_token=shared_dataset.share_token,
                    analyze_request=analyze_request,
                )

            # Should have clamped to 5
            _, kwargs = mock_viz_service.generate_chat_visualizations.call_args
            assert kwargs["max_visualizations"] == 5

    async def test_increments_share_view_count(self, svc, db_session, shared_dataset, mock_analyze_request):
        """Should increment share_view_count after analysis."""
        initial_count = shared_dataset.share_view_count
        db_session.first.return_value = shared_dataset

        with (
            patch("app.services.mindsdb.MindsDBService") as MockMindsDB,
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.core.app_config.get_app_config"),
            patch("app.services.data_visualization.get_visualization_service"),
            patch("app.services.data_visualization.sanitize_visualization_payload", side_effect=lambda x: x),
        ):
            mock_mindsdb_instance = MockMindsDB.return_value
            mock_mindsdb_instance.chat_with_dataset_agent = AsyncMock(
                return_value={"answer": "Analysis", "agent_name": "Anton"}
            )
            mock_mindsdb_instance.load_dataset_for_visualization = AsyncMock(return_value=MagicMock())
            mock_mindsdb_instance.load_dataset_for_visualization.return_value.empty = False

            result = await svc.analyze_shared_dataset_with_anton(
                share_token=shared_dataset.share_token,
                analyze_request=mock_analyze_request,
            )

        assert shared_dataset.share_view_count == initial_count + 1
        assert result["dataset_id"] == shared_dataset.id


# ── download_shared_dataset ────────────────────────────────────────────

class TestDownloadSharedDataset:
    """DataSharingService.download_shared_dataset()"""

    async def test_downloads_single_file(self, svc, db_session, shared_dataset, mock_dataset_file):
        """Should download a single file dataset."""
        shared_dataset.source_url = None
        db_session.first.return_value = shared_dataset

        with (
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.services.storage.storage_service") as mock_storage,
            patch("fastapi.responses.FileResponse") as MockFileResponse,
        ):
            mock_storage.retrieve_dataset_file = AsyncMock(return_value=b"file content")
            mock_response = Mock()
            MockFileResponse.return_value = mock_response

            # The multi-file path: dataset_files query returns one file
            db_session.all.return_value = [mock_dataset_file]

            result = await svc.download_shared_dataset(
                share_token=shared_dataset.share_token,
            )

            assert result == mock_response
            mock_storage.retrieve_dataset_file.assert_awaited_once_with(mock_dataset_file.relative_path)
            MockFileResponse.assert_called_once()
            # Check filename in kwargs
            assert MockFileResponse.call_args[1]["filename"] == mock_dataset_file.filename

    async def test_downloads_multi_file_as_zip(self, svc, db_session, multi_file_dataset):
        """Should download multi-file dataset as zip."""
        db_session.first.return_value = multi_file_dataset

        dataset_files = []
        for i, name in enumerate(["file1.csv", "file2.csv", "file3.csv"]):
            f = Mock(spec=DatasetFile)
            f.id = i + 1
            f.dataset_id = multi_file_dataset.id
            f.filename = name
            f.file_path = f"/storage/{name}"
            f.relative_path = name
            f.file_size = 100 * (i + 1)
            f.file_type = "csv"
            f.is_primary = (i == 0)
            f.file_order = i
            f.is_deleted = False
            dataset_files.append(f)

        db_session.all.return_value = dataset_files

        with (
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.services.storage.storage_service") as mock_storage,
            patch("fastapi.responses.FileResponse") as MockFileResponse,
            patch("tempfile.NamedTemporaryFile") as MockTemp,
            patch("zipfile.ZipFile") as MockZip,
        ):
            mock_storage.retrieve_dataset_file = AsyncMock(return_value=b"file content")
            mock_temp = Mock()
            mock_temp.name = "/tmp/test_zip.zip"
            MockTemp.return_value = mock_temp
            mock_zip_instance = Mock()
            MockZip.return_value.__enter__.return_value = mock_zip_instance

            mock_response = Mock()
            MockFileResponse.return_value = mock_response

            result = await svc.download_shared_dataset(
                share_token=multi_file_dataset.share_token,
            )

            assert result == mock_response
            # Should have retrieved all three files
            assert mock_storage.retrieve_dataset_file.await_count == 3
            # Should have added all three to zip
            assert mock_zip_instance.writestr.call_count == 3
            mock_temp.close.assert_called_once()
            MockFileResponse.assert_called_once()
            args, kwargs = MockFileResponse.call_args
            assert kwargs["filename"] == f"{multi_file_dataset.name}_all_files.zip"
            assert kwargs["media_type"] == "application/zip"

    async def test_downloads_legacy_file_path(self, svc, db_session, shared_dataset):
        """Should handle legacy file_path downloads."""
        shared_dataset.is_multi_file_dataset = False
        shared_dataset.file_path = "/legacy/storage/file.csv"
        shared_dataset.source_url = "file.csv"
        # No DatasetFile records — triggers legacy path
        db_session.first.return_value = shared_dataset
        db_session.all.return_value = []  # No DatasetFile records

        with (
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.services.storage.storage_service") as mock_storage,
            patch("fastapi.responses.FileResponse") as MockFileResponse,
            patch("app.utils.file_utils.sanitize_filename", return_value="Test_Dataset"),
        ):
            mock_storage.retrieve_dataset_file = AsyncMock(return_value=b"legacy file content")
            mock_response = Mock()
            MockFileResponse.return_value = mock_response

            result = await svc.download_shared_dataset(
                share_token=shared_dataset.share_token,
            )

            assert result == mock_response
            mock_storage.retrieve_dataset_file.assert_awaited_once_with(shared_dataset.file_path)

    async def test_raises_404_when_no_files_found(self, svc, db_session, shared_dataset):
        """Should raise 404 when no downloadable files exist."""
        db_session.first.return_value = shared_dataset
        # No DatasetFile records and no file_path
        shared_dataset.file_path = None
        shared_dataset.source_url = None
        shared_dataset.is_multi_file_dataset = False
        db_session.all.return_value = []

        with (
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.services.storage.storage_service") as mock_storage,
        ):
            mock_storage.retrieve_dataset_file = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc:
                await svc.download_shared_dataset(
                    share_token=shared_dataset.share_token,
                )
            assert exc.value.status_code == 404
            assert "no downloadable files" in str(exc.value.detail).lower()

    async def test_raises_404_when_dataset_not_found(self, svc, db_session):
        """Should raise 404 when shared dataset not found."""
        db_session.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await svc.download_shared_dataset(share_token="nonexistent")
        assert exc.value.status_code == 404

    async def test_raises_400_for_external_url_dataset(self, svc, db_session, shared_dataset):
        """Should raise 400 when dataset has external URL source."""
        shared_dataset.source_url = "https://external-storage.example.com/data.csv"
        db_session.first.return_value = shared_dataset

        with patch.object(svc.sharing, 'require_password', Mock()):
            with pytest.raises(HTTPException) as exc:
                await svc.download_shared_dataset(
                    share_token=shared_dataset.share_token,
                )
            assert exc.value.status_code == 400
            assert "external" in str(exc.value.detail).lower()

    async def test_requires_password(self, svc, db_session, password_protected_dataset):
        """Should call require_password for password-protected dataset."""
        db_session.first.return_value = password_protected_dataset

        with patch.object(svc.sharing, 'require_password', Mock(side_effect=HTTPException(401))):
            with pytest.raises(HTTPException) as exc:
                await svc.download_shared_dataset(
                    share_token=password_protected_dataset.share_token,
                    password="wrong",
                )
            assert exc.value.status_code == 401
            svc.sharing.require_password.assert_called_once_with(
                password_protected_dataset, "wrong",
            )

    async def test_updates_session_download_count(self, svc, db_session, shared_dataset, mock_dataset_file):
        """Should update ShareAccessSession download count when session_token provided."""
        db_session.first.return_value = shared_dataset
        db_session.all.return_value = [mock_dataset_file]

        mock_session = Mock()
        mock_session.files_downloaded = 0
        mock_session.is_active = True
        mock_session.dataset_id = shared_dataset.id

        def first_side_effect(arg=None):
            # First call for dataset query returns dataset
            # If called with ShareAccessSession filter, return mock_session
            if hasattr(first_side_effect, 'call_count') and first_side_effect.call_count > 0:
                return mock_session
            first_side_effect.call_count = 1
            return shared_dataset

        db_session.first.side_effect = first_side_effect

        with (
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.services.storage.storage_service") as mock_storage,
            patch("fastapi.responses.FileResponse") as MockFileResponse,
        ):
            mock_storage.retrieve_dataset_file = AsyncMock(return_value=b"content")
            MockFileResponse.return_value = Mock()

            await svc.download_shared_dataset(
                share_token=shared_dataset.share_token,
                session_token="valid_session",
            )

            assert mock_session.files_downloaded == 1
            assert mock_session.last_activity_at is not None
            db_session.commit.assert_called()

    async def test_single_file_storage_failure(self, svc, db_session, shared_dataset, mock_dataset_file):
        """Should handle storage retrieval failure for single file download gracefully."""
        db_session.first.return_value = shared_dataset
        db_session.all.return_value = [mock_dataset_file]

        with (
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.services.storage.storage_service") as mock_storage,
        ):
            mock_storage.retrieve_dataset_file = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc:
                await svc.download_shared_dataset(
                    share_token=shared_dataset.share_token,
                )
            assert exc.value.status_code == 404

    async def test_zip_creation_failure(self, svc, db_session, multi_file_dataset):
        """Should raise 500 when zip creation fails."""
        db_session.first.return_value = multi_file_dataset

        dataset_files = []
        for i in range(2):
            f = Mock(spec=DatasetFile)
            f.id = i + 1
            f.dataset_id = multi_file_dataset.id
            f.filename = f"file{i}.csv"
            f.file_path = f"/storage/file{i}.csv"
            f.relative_path = f"file{i}.csv"
            f.file_type = "csv"
            f.is_primary = (i == 0)
            f.file_order = i
            f.is_deleted = False
            dataset_files.append(f)

        db_session.all.return_value = dataset_files

        with (
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.services.storage.storage_service") as mock_storage,
            patch("tempfile.NamedTemporaryFile") as MockTemp,
            patch("zipfile.ZipFile") as MockZip,
        ):
            mock_storage.retrieve_dataset_file = AsyncMock(return_value=b"content")
            mock_temp = Mock()
            mock_temp.name = "/tmp/fail.zip"
            MockTemp.return_value = mock_temp
            # Simulate zip creation failure
            MockZip.side_effect = Exception("Disk full")

            with pytest.raises(HTTPException) as exc:
                await svc.download_shared_dataset(
                    share_token=multi_file_dataset.share_token,
                )
            assert exc.value.status_code == 500
            assert "zip" in str(exc.value.detail).lower()

    async def test_single_file_with_multi_file_flag_but_one_file(self, svc, db_session, shared_dataset, mock_dataset_file):
        """Should download single file when is_multi_file_dataset is True but only one file exists."""
        shared_dataset.is_multi_file_dataset = True
        shared_dataset.source_url = None
        db_session.first.return_value = shared_dataset
        db_session.all.return_value = [mock_dataset_file]

        with (
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.services.storage.storage_service") as mock_storage,
            patch("fastapi.responses.FileResponse") as MockFileResponse,
        ):
            mock_storage.retrieve_dataset_file = AsyncMock(return_value=b"content")
            MockFileResponse.return_value = Mock()

            result = await svc.download_shared_dataset(
                share_token=shared_dataset.share_token,
            )

            assert result is not None
            # Single file path should be taken (not zip)
            mock_storage.retrieve_dataset_file.assert_awaited_once_with(mock_dataset_file.relative_path)


# ── Edge cases ─────────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases for DataSharingService."""

    def test_log_download_attempt(self, svc, owner, dataset):
        """Should delegate download logging to AccessControlService."""
        with patch.object(svc.access, 'log_download_attempt', return_value=True):
            result = svc.log_download_attempt(
                user=owner, dataset=dataset, success=True,
            )
            assert result is True
            svc.access.log_download_attempt.assert_called_once_with(
                owner, dataset, True, None, None,
            )

    def test_check_download_rate_limit(self, svc, owner):
        """Should delegate rate limit check to AccessControlService."""
        expected = {"allowed": True, "daily_limit": 100, "daily_used": 0}
        with patch.object(svc.access, 'check_download_rate_limit', return_value=expected):
            result = svc.check_download_rate_limit(owner)
            assert result["allowed"] is True

    def test_log_access(self, svc, owner, dataset):
        """Should delegate access logging to AccessControlService."""
        with patch.object(svc.access, 'log_access', return_value=True):
            result = svc.log_access(
                user=owner, dataset=dataset, access_type="view",
            )
            assert result is True

    def test_get_organization_stats(self, svc, superuser):
        """Should delegate org stats to AccessControlService."""
        expected = {"total_datasets": 5, "total_size_bytes": 10240}
        with patch.object(svc.access, 'get_organization_stats', return_value=expected):
            result = svc.get_organization_stats(org_id=10, user=superuser)
            assert result["total_datasets"] == 5

    def test_get_organization_datasets(self, svc, superuser):
        """Should delegate org datasets to AccessControlService."""
        with patch.object(svc.access, 'get_organization_datasets', return_value=[]):
            result = svc.get_organization_datasets(org_id=10, user=superuser)
            assert result == []

    def test_validate_dataset_creation(self, svc, owner):
        """Should delegate validation to AccessControlService."""
        with patch.object(svc.access, 'validate_dataset_creation', return_value=True):
            result = svc.validate_dataset_creation(owner, org_id=10)
            assert result is True

    def test_get_sharing_stats(self, svc, superuser):
        """Should delegate sharing stats to SharingService."""
        expected = {"total_datasets": 5, "by_sharing_level": {"private": 3, "public": 2}}
        with patch.object(svc.sharing, 'get_sharing_stats', return_value=expected):
            result = svc.get_sharing_stats(org_id=10, user=superuser)
            assert result["total_datasets"] == 5

    def test_get_organization_shared_datasets(self, svc, superuser):
        """Should delegate org shared datasets to SharingService."""
        with patch.object(svc.sharing, 'get_org_shared_datasets', return_value=[]):
            result = svc.get_organization_shared_datasets(org_id=10, user=superuser)
            assert result == []

    def test_get_dataset_analytics(self, svc, owner, dataset):
        """Should delegate analytics to SharingService."""
        expected = {"dataset_id": 42, "view_count": 5}
        with patch.object(svc.sharing, 'get_dataset_analytics', return_value=expected):
            result = svc.get_dataset_analytics(dataset_id=42, user_id=owner.id)
            assert result["view_count"] == 5

    async def test_empty_message_passes_length_check(self, svc, db_session, shared_dataset):
        """Empty message should pass the 4000-char limit check."""
        chat_request = Mock()
        chat_request.message = ""
        chat_request.password = None
        chat_request.session_token = "valid_token"
        db_session.first.return_value = shared_dataset
        shared_dataset.allow_ai_chat = True

        # The empty message should not raise 413, but will raise 401
        # because there's no session (or continue to the next check)
        with patch.object(svc.sharing, 'require_password', Mock()):
            # The first query returns dataset, the session query returns None
            db_session.first.side_effect = [shared_dataset, None]

            with pytest.raises(HTTPException) as exc_info:
                await svc.chat_with_shared_dataset(
                    share_token=shared_dataset.share_token,
                    chat_request=chat_request,
                )
            # Should be 401 for missing/expired session, NOT 413
            assert exc_info.value.status_code == 401
            assert exc_info.value.status_code != 413

    async def test_download_with_non_ascii_filename(self, svc, db_session, shared_dataset, mock_dataset_file):
        """Should handle non-ASCII filenames in download."""
        mock_dataset_file.filename = "dados_2024.csv"
        shared_dataset.source_url = None
        db_session.first.return_value = shared_dataset
        db_session.all.return_value = [mock_dataset_file]

        with (
            patch.object(svc.sharing, 'require_password', Mock()),
            patch("app.services.storage.storage_service") as mock_storage,
            patch("fastapi.responses.FileResponse") as MockFileResponse,
        ):
            mock_storage.retrieve_dataset_file = AsyncMock(return_value=b"content")
            MockFileResponse.return_value = Mock()

            result = await svc.download_shared_dataset(
                share_token=shared_dataset.share_token,
            )

            assert result is not None
            MockFileResponse.assert_called_once()
            assert MockFileResponse.call_args[1]["filename"] == "dados_2024.csv"
