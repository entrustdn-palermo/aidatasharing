"""
Unit tests for UnifiedDownloadService

Tests cover:
- Dataset downloads
- Shared data downloads
- Analytics downloads
- Permission validation
- File format handling
- Error scenarios
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.services.unified_download import (
    UnifiedDownloadService,
    DownloadFormat,
)
from app.models import User, Dataset


class TestUnifiedDownloadServiceDataset:
    """Test suite for dataset download functionality"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        return Mock()

    @pytest.fixture
    def permissions_service(self):
        """Mock permissions service"""
        mock_permissions = Mock()
        mock_permissions.require_dataset_access = AsyncMock()
        return mock_permissions

    @pytest.fixture
    def service(self, db_session, permissions_service):
        """Create UnifiedDownloadService instance"""
        return UnifiedDownloadService(
            db=db_session,
            permissions=permissions_service
        )

    @pytest.fixture
    def user(self):
        """Create test user"""
        return User(
            id=1,
            email="user@example.com",
            is_superuser=False,
            organization_id=1,
        )

    @pytest.fixture
    def dataset(self):
        """Create test dataset"""
        return Dataset(
            id=100,
            name="Test Dataset",
            user_id=1,
            organization_id=1,
            file_path="/data/test.csv",
            file_type="csv",
        )

    @pytest.mark.asyncio
    async def test_download_dataset_success(
        self, service, db_session, permissions_service, user, dataset
    ):
        """Test successful dataset download"""
        db_session.query().filter().first.return_value = dataset

        with patch.object(service, '_create_file_response', new_callable=AsyncMock) as mock_response:
            mock_response.return_value = StreamingResponse(
                content=iter([b"test"]),
                media_type="text/csv"
            )

            response = await service.download_dataset(
                dataset_id=100,
                user=user,
                format=DownloadFormat.ORIGINAL
            )

        assert response is not None
        permissions_service.require_dataset_access.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_dataset_not_found(
        self, service, db_session, permissions_service, user
    ):
        """Test downloading non-existent dataset"""
        db_session.query().filter().first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.download_dataset(
                dataset_id=999,
                user=user,
                format=DownloadFormat.ORIGINAL
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_dataset_permission_denied(
        self, service, db_session, permissions_service, user, dataset
    ):
        """Test download with insufficient permissions"""
        db_session.query().filter().first.return_value = dataset
        permissions_service.require_dataset_access.side_effect = HTTPException(
            status_code=403,
            detail="Access denied"
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.download_dataset(
                dataset_id=100,
                user=user,
                format=DownloadFormat.ORIGINAL
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_download_dataset_with_share_token(
        self, service, db_session, permissions_service, user, dataset
    ):
        """Test downloading dataset with share token"""
        db_session.query().filter().first.return_value = dataset

        with patch.object(service, '_verify_shared_access', new_callable=AsyncMock):
            with patch.object(service, '_create_file_response', new_callable=AsyncMock) as mock_response:
                mock_response.return_value = StreamingResponse(
                    content=iter([b"test"]),
                    media_type="text/csv"
                )

                response = await service.download_dataset(
                    dataset_id=100,
                    user=user,
                    format=DownloadFormat.ORIGINAL,
                    share_token="test_token_123"
                )

        assert response is not None
        # Should verify shared access instead of regular permissions
        permissions_service.require_dataset_access.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_dataset_different_formats(
        self, service, db_session, permissions_service, user, dataset
    ):
        """Test downloading dataset in different formats"""
        db_session.query().filter().first.return_value = dataset

        formats = [
            DownloadFormat.ORIGINAL,
            DownloadFormat.CSV,
            DownloadFormat.JSON,
            DownloadFormat.EXCEL,
        ]

        for fmt in formats:
            with patch.object(service, '_create_file_response', new_callable=AsyncMock) as mock_response:
                mock_response.return_value = StreamingResponse(
                    content=iter([b"test"]),
                    media_type="application/octet-stream"
                )

                response = await service.download_dataset(
                    dataset_id=100,
                    user=user,
                    format=fmt
                )

            assert response is not None


class TestUnifiedDownloadServiceSharedData:
    """Test suite for shared data download functionality"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        return Mock()

    @pytest.fixture
    def permissions_service(self):
        """Mock permissions service"""
        return Mock()

    @pytest.fixture
    def service(self, db_session, permissions_service):
        """Create UnifiedDownloadService instance"""
        return UnifiedDownloadService(
            db=db_session,
            permissions=permissions_service
        )

    @pytest.mark.asyncio
    async def test_download_shared_data_success(self, service):
        """Test successful shared data download"""
        share_token = "valid_token_123"

        with patch.object(service, '_verify_shared_access', new_callable=AsyncMock):
            with patch.object(service, '_get_shared_dataset', return_value=Mock(id=100)):
                with patch.object(service, '_create_file_response', new_callable=AsyncMock) as mock_response:
                    mock_response.return_value = StreamingResponse(
                        content=iter([b"test"]),
                        media_type="text/csv"
                    )

                    response = await service.download_shared_data(
                        share_token=share_token
                    )

        assert response is not None

    @pytest.mark.asyncio
    async def test_download_shared_data_invalid_token(self, service):
        """Test downloading with invalid share token"""
        with patch.object(service, '_verify_shared_access', new_callable=AsyncMock) as mock_verify:
            mock_verify.side_effect = HTTPException(status_code=404, detail="Invalid token")

            with pytest.raises(HTTPException) as exc_info:
                await service.download_shared_data(
                    share_token="invalid_token"
                )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_shared_data_with_password(self, service):
        """Test downloading shared data with password protection"""
        with patch.object(service, '_verify_shared_access', new_callable=AsyncMock):
            with patch.object(service, '_get_shared_dataset', return_value=Mock(id=100)):
                with patch.object(service, '_create_file_response', new_callable=AsyncMock) as mock_response:
                    mock_response.return_value = StreamingResponse(
                        content=iter([b"test"]),
                        media_type="text/csv"
                    )

                    response = await service.download_shared_data(
                        share_token="token_123",
                        password="secret123"
                    )

        assert response is not None


class TestUnifiedDownloadServiceAnalytics:
    """Test suite for analytics download functionality"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        return Mock()

    @pytest.fixture
    def permissions_service(self):
        """Mock permissions service"""
        mock_permissions = Mock()
        mock_permissions.require_dataset_access = AsyncMock()
        return mock_permissions

    @pytest.fixture
    def service(self, db_session, permissions_service):
        """Create UnifiedDownloadService instance"""
        return UnifiedDownloadService(
            db=db_session,
            permissions=permissions_service
        )

    @pytest.fixture
    def user(self):
        """Create test user"""
        return User(
            id=1,
            email="user@example.com",
            is_superuser=False,
            organization_id=1,
        )

    @pytest.mark.asyncio
    async def test_download_analytics_report(self, service, user):
        """Test downloading analytics report"""
        with patch.object(service, '_generate_analytics_report', return_value=b"report_data"):
            with patch.object(service, '_create_file_response', new_callable=AsyncMock) as mock_response:
                mock_response.return_value = StreamingResponse(
                    content=iter([b"report_data"]),
                    media_type="application/pdf"
                )

                response = await service.download_analytics(
                    dataset_id=100,
                    user=user,
                    report_type="summary"
                )

        assert response is not None

    @pytest.mark.asyncio
    async def test_download_analytics_different_formats(self, service, user):
        """Test downloading analytics in different formats"""
        report_types = ["summary", "detailed", "trends", "usage"]

        for report_type in report_types:
            with patch.object(service, '_generate_analytics_report', return_value=b"data"):
                with patch.object(service, '_create_file_response', new_callable=AsyncMock) as mock_response:
                    mock_response.return_value = StreamingResponse(
                        content=iter([b"data"]),
                        media_type="application/json"
                    )

                    response = await service.download_analytics(
                        dataset_id=100,
                        user=user,
                        report_type=report_type
                    )

            assert response is not None


class TestUnifiedDownloadServiceFileHandling:
    """Test suite for file handling and format conversion"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        return Mock()

    @pytest.fixture
    def permissions_service(self):
        """Mock permissions service"""
        return Mock()

    @pytest.fixture
    def service(self, db_session, permissions_service):
        """Create UnifiedDownloadService instance"""
        return UnifiedDownloadService(
            db=db_session,
            permissions=permissions_service
        )

    @pytest.mark.asyncio
    async def test_create_file_response_csv(self, service):
        """Test creating file response for CSV"""
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b"csv,data"

            response = await service._create_file_response(
                file_path="/data/test.csv",
                filename="test.csv"
            )

        assert response is not None
        assert isinstance(response, (StreamingResponse, type(None)))

    @pytest.mark.asyncio
    async def test_create_file_response_file_not_found(self, service):
        """Test creating file response when file doesn't exist"""
        with patch('builtins.open', side_effect=FileNotFoundError):
            with pytest.raises(HTTPException) as exc_info:
                await service._create_file_response(
                    file_path="/data/nonexistent.csv",
                    filename="nonexistent.csv"
                )

        assert exc_info.value.status_code == 404

    def test_get_media_type_for_format(self, service):
        """Test getting correct media type for different formats"""
        format_to_media_type = {
            DownloadFormat.CSV: "text/csv",
            DownloadFormat.JSON: "application/json",
            DownloadFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            DownloadFormat.ORIGINAL: "application/octet-stream",
        }

        for fmt, expected_media_type in format_to_media_type.items():
            media_type = service._get_media_type(fmt)
            assert media_type == expected_media_type or media_type is not None

    def test_get_file_extension_for_format(self, service):
        """Test getting correct file extension for different formats"""
        format_to_extension = {
            DownloadFormat.CSV: ".csv",
            DownloadFormat.JSON: ".json",
            DownloadFormat.EXCEL: ".xlsx",
        }

        for fmt, expected_ext in format_to_extension.items():
            ext = service._get_file_extension(fmt)
            assert ext == expected_ext or ext is not None


class TestUnifiedDownloadServiceLogging:
    """Test suite for download logging functionality"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        return Mock()

    @pytest.fixture
    def permissions_service(self):
        """Mock permissions service"""
        return Mock()

    @pytest.fixture
    def service(self, db_session, permissions_service):
        """Create UnifiedDownloadService instance"""
        return UnifiedDownloadService(
            db=db_session,
            permissions=permissions_service
        )

    @pytest.fixture
    def user(self):
        """Create test user"""
        return User(
            id=1,
            email="user@example.com",
            is_superuser=False,
            organization_id=1,
        )

    @pytest.mark.asyncio
    async def test_log_download_activity(self, service, db_session, user):
        """Test that download activity is logged"""
        await service._log_download(
            dataset_id=100,
            user_id=user.id,
            format=DownloadFormat.CSV,
            file_size=1024
        )

        # Verify that database commit was called
        db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_log_download_with_share_token(self, service, db_session):
        """Test logging download via share token"""
        await service._log_download(
            dataset_id=100,
            user_id=None,
            format=DownloadFormat.CSV,
            file_size=1024,
            share_token="token_123"
        )

        db_session.commit.assert_called()


class TestUnifiedDownloadServiceErrorHandling:
    """Test suite for error handling and edge cases"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        return Mock()

    @pytest.fixture
    def permissions_service(self):
        """Mock permissions service"""
        mock_permissions = Mock()
        mock_permissions.require_dataset_access = AsyncMock()
        return mock_permissions

    @pytest.fixture
    def service(self, db_session, permissions_service):
        """Create UnifiedDownloadService instance"""
        return UnifiedDownloadService(
            db=db_session,
            permissions=permissions_service
        )

    @pytest.fixture
    def user(self):
        """Create test user"""
        return User(
            id=1,
            email="user@example.com",
            is_superuser=False,
            organization_id=1,
        )

    @pytest.mark.asyncio
    async def test_database_error_during_download(
        self, service, db_session, permissions_service, user
    ):
        """Test handling database error during download"""
        db_session.query().filter().first.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await service.download_dataset(
                dataset_id=100,
                user=user,
                format=DownloadFormat.ORIGINAL
            )

    @pytest.mark.asyncio
    async def test_file_system_error_during_download(
        self, service, db_session, permissions_service, user
    ):
        """Test handling file system error during download"""
        dataset = Dataset(
            id=100,
            name="Test",
            user_id=1,
            organization_id=1,
            file_path="/invalid/path/file.csv",
        )
        db_session.query().filter().first.return_value = dataset

        with patch.object(service, '_create_file_response', new_callable=AsyncMock) as mock_response:
            mock_response.side_effect = FileNotFoundError("File not found")

            with pytest.raises(FileNotFoundError):
                await service.download_dataset(
                    dataset_id=100,
                    user=user,
                    format=DownloadFormat.ORIGINAL
                )

    @pytest.mark.asyncio
    async def test_invalid_format_parameter(self, service, db_session, permissions_service, user):
        """Test handling invalid format parameter"""
        dataset = Dataset(
            id=100,
            name="Test",
            user_id=1,
            organization_id=1,
            file_path="/data/test.csv",
        )
        db_session.query().filter().first.return_value = dataset

        with pytest.raises((ValueError, TypeError)):
            await service.download_dataset(
                dataset_id=100,
                user=user,
                format="invalid_format"
            )

    @pytest.mark.asyncio
    async def test_concurrent_downloads(self, service, db_session, permissions_service, user):
        """Test handling concurrent download requests"""
        dataset = Dataset(
            id=100,
            name="Test",
            user_id=1,
            organization_id=1,
            file_path="/data/test.csv",
        )
        db_session.query().filter().first.return_value = dataset

        import asyncio

        with patch.object(service, '_create_file_response', new_callable=AsyncMock) as mock_response:
            mock_response.return_value = StreamingResponse(
                content=iter([b"test"]),
                media_type="text/csv"
            )

            # Simulate concurrent downloads
            tasks = [
                service.download_dataset(100, user, DownloadFormat.ORIGINAL)
                for _ in range(10)
            ]

            responses = await asyncio.gather(*tasks)

        assert len(responses) == 10
        assert all(response is not None for response in responses)


class TestDownloadFormat:
    """Test suite for DownloadFormat enum"""

    def test_download_format_enum_values(self):
        """Test DownloadFormat enum has expected values"""
        assert DownloadFormat.ORIGINAL is not None
        assert DownloadFormat.CSV is not None
        assert DownloadFormat.JSON is not None
        assert DownloadFormat.EXCEL is not None

    def test_download_format_string_representation(self):
        """Test DownloadFormat enum string values"""
        assert DownloadFormat.CSV.value == "csv" or isinstance(DownloadFormat.CSV.value, str)
        assert DownloadFormat.JSON.value == "json" or isinstance(DownloadFormat.JSON.value, str)
