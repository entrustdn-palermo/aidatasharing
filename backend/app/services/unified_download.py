"""
Unified Download Service
Centralizes all file download logic across the platform
"""

import os
import io
import logging
from typing import Optional, Dict, Any, BinaryIO
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse, FileResponse

from app.models.user import User
from app.models.dataset import Dataset
from app.models.data_sharing import SharedDataset
from app.services.permissions import PermissionService, AccessLevel
from app.services.storage import StorageService
from app.core.config import settings

logger = logging.getLogger(__name__)


class DownloadFormat:
    """Supported download formats"""
    ORIGINAL = "original"
    CSV = "csv"
    JSON = "json"
    EXCEL = "excel"
    PARQUET = "parquet"


class UnifiedDownloadService:
    """
    Centralized download service for all file types

    Features:
    - Permission checking
    - Format conversion
    - Download tracking
    - Storage abstraction
    - Streaming support
    """

    def __init__(self, db: Session):
        self.db = db
        self.permissions = PermissionService(db)
        self.storage = StorageService()

    # ========================================================================
    # Main Download Methods
    # ========================================================================

    async def download_dataset(
        self,
        dataset_id: int,
        user: User,
        format: str = DownloadFormat.ORIGINAL,
        share_token: Optional[str] = None
    ) -> StreamingResponse:
        """
        Download a dataset file

        Args:
            dataset_id: Dataset ID
            user: User requesting download
            format: Desired download format
            share_token: Optional share token for shared access

        Returns:
            StreamingResponse with file data

        Raises:
            HTTPException: If access denied or file not found
        """
        try:
            # Get dataset
            dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if not dataset:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Dataset {dataset_id} not found"
                )

            # Check permissions
            if share_token:
                await self._verify_shared_access(share_token, dataset_id)
            else:
                await self.permissions.require_dataset_access(
                    dataset_id, user, AccessLevel.READ
                )

            # Get file path
            file_path = self._get_dataset_file_path(dataset)
            if not file_path or not os.path.exists(file_path):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Dataset file not found"
                )

            # Convert format if needed
            if format != DownloadFormat.ORIGINAL:
                file_path = await self._convert_format(file_path, format)

            # Log download
            await self._log_download(
                resource_type="dataset",
                resource_id=dataset_id,
                user_id=user.id if user else None,
                format=format,
                share_token=share_token
            )

            # Return file
            return await self._create_file_response(
                file_path,
                filename=self._get_download_filename(dataset, format)
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error downloading dataset {dataset_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Download failed: {str(e)}"
            )

    async def download_shared_data(
        self,
        share_token: str,
        format: str = DownloadFormat.ORIGINAL
    ) -> StreamingResponse:
        """
        Download shared dataset via share token

        Args:
            share_token: Share token
            format: Desired download format

        Returns:
            StreamingResponse with file data
        """
        try:
            # Verify share access
            shared = await self._verify_shared_access(share_token)

            # Download dataset
            return await self.download_dataset(
                dataset_id=shared.dataset_id,
                user=None,  # Anonymous access via share token
                format=format,
                share_token=share_token
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error downloading shared data {share_token}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Download failed: {str(e)}"
            )

    async def download_analytics_export(
        self,
        dataset_id: int,
        user: User,
        analysis_type: str,
        format: str = DownloadFormat.CSV
    ) -> StreamingResponse:
        """
        Download analytics export

        Args:
            dataset_id: Dataset ID
            user: User requesting download
            analysis_type: Type of analysis (summary, detailed, etc.)
            format: Export format

        Returns:
            StreamingResponse with analytics data
        """
        try:
            # Check permissions
            await self.permissions.require_dataset_access(
                dataset_id, user, AccessLevel.READ
            )

            # Generate analytics export
            export_data = await self._generate_analytics_export(
                dataset_id, analysis_type
            )

            # Log download
            await self._log_download(
                resource_type="analytics",
                resource_id=dataset_id,
                user_id=user.id,
                format=format,
                metadata={"analysis_type": analysis_type}
            )

            # Return export
            return await self._create_stream_response(
                export_data,
                filename=f"analytics_{analysis_type}_{dataset_id}.{format}",
                media_type=self._get_media_type(format)
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error downloading analytics for {dataset_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Analytics export failed: {str(e)}"
            )

    # ========================================================================
    # Permission & Access Control
    # ========================================================================

    async def _verify_shared_access(
        self,
        share_token: str,
        dataset_id: Optional[int] = None
    ) -> SharedDataset:
        """Verify shared access via token"""
        shared = self.db.query(SharedDataset).filter(
            SharedDataset.share_token == share_token
        ).first()

        if not shared:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Share link not found"
            )

        if not shared.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Share link is inactive"
            )

        if shared.expires_at and datetime.utcnow() > shared.expires_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Share link has expired"
            )

        if dataset_id and shared.dataset_id != dataset_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Share token not valid for this dataset"
            )

        return shared

    # ========================================================================
    # File Operations
    # ========================================================================

    def _get_dataset_file_path(self, dataset: Dataset) -> Optional[str]:
        """Get file path for dataset"""
        if dataset.file_path:
            # Use absolute path if provided
            if os.path.isabs(dataset.file_path):
                return dataset.file_path
            # Otherwise construct from storage path
            return os.path.join(settings.DATASET_STORAGE_PATH, dataset.file_path)
        return None

    async def _convert_format(self, file_path: str, target_format: str) -> str:
        """
        Convert file to target format

        Note: Basic implementation - expand as needed
        """
        # For now, return original if conversion not supported
        logger.info(f"Format conversion to {target_format} requested but not implemented")
        return file_path

    def _get_download_filename(self, dataset: Dataset, format: str) -> str:
        """Generate download filename"""
        base_name = dataset.name or f"dataset_{dataset.id}"
        # Clean filename
        safe_name = "".join(c for c in base_name if c.isalnum() or c in (' ', '-', '_'))

        # Add extension based on format
        if format == DownloadFormat.ORIGINAL:
            # Keep original extension
            return safe_name
        elif format == DownloadFormat.CSV:
            return f"{safe_name}.csv"
        elif format == DownloadFormat.JSON:
            return f"{safe_name}.json"
        elif format == DownloadFormat.EXCEL:
            return f"{safe_name}.xlsx"
        elif format == DownloadFormat.PARQUET:
            return f"{safe_name}.parquet"
        else:
            return safe_name

    async def _create_file_response(
        self,
        file_path: str,
        filename: str
    ) -> FileResponse:
        """Create file response for download"""
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/octet-stream"
        )

    async def _create_stream_response(
        self,
        data: bytes,
        filename: str,
        media_type: str
    ) -> StreamingResponse:
        """Create streaming response for download"""
        return StreamingResponse(
            io.BytesIO(data),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    def _get_media_type(self, format: str) -> str:
        """Get media type for format"""
        media_types = {
            DownloadFormat.CSV: "text/csv",
            DownloadFormat.JSON: "application/json",
            DownloadFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            DownloadFormat.PARQUET: "application/octet-stream"
        }
        return media_types.get(format, "application/octet-stream")

    # ========================================================================
    # Analytics & Logging
    # ========================================================================

    async def _generate_analytics_export(
        self,
        dataset_id: int,
        analysis_type: str
    ) -> bytes:
        """
        Generate analytics export data

        Note: Placeholder - implement actual analytics generation
        """
        # TODO: Implement actual analytics generation
        import json
        data = {
            "dataset_id": dataset_id,
            "analysis_type": analysis_type,
            "generated_at": datetime.utcnow().isoformat(),
            "data": []
        }
        return json.dumps(data, indent=2).encode()

    async def _log_download(
        self,
        resource_type: str,
        resource_id: int,
        user_id: Optional[int] = None,
        format: str = DownloadFormat.ORIGINAL,
        share_token: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log download activity"""
        try:
            # TODO: Implement actual logging to database table
            logger.info(
                f"Download: type={resource_type}, id={resource_id}, "
                f"user={user_id}, format={format}, share_token={share_token}"
            )
        except Exception as e:
            logger.error(f"Error logging download: {e}")
            # Don't fail download if logging fails

    # ========================================================================
    # Statistics & Analytics
    # ========================================================================

    async def get_download_stats(
        self,
        dataset_id: int,
        user: User
    ) -> Dict[str, Any]:
        """
        Get download statistics for a dataset

        Args:
            dataset_id: Dataset ID
            user: User requesting stats

        Returns:
            Dictionary with download statistics
        """
        try:
            # Check permissions
            await self.permissions.require_dataset_access(
                dataset_id, user, AccessLevel.READ
            )

            # TODO: Implement actual stats from download logs
            return {
                "dataset_id": dataset_id,
                "total_downloads": 0,
                "unique_users": 0,
                "formats": {},
                "recent_downloads": []
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting download stats: {e}")
            return {}


# ========================================================================
# Dependency Injection Helper
# ========================================================================

def get_download_service(db: Session) -> UnifiedDownloadService:
    """
    Dependency injection helper for FastAPI routes

    Usage:
        @router.get("/datasets/{dataset_id}/download")
        async def download_dataset(
            dataset_id: int,
            user: User = Depends(get_current_user),
            downloads: UnifiedDownloadService = Depends(get_download_service)
        ):
            return await downloads.download_dataset(dataset_id, user)
    """
    return UnifiedDownloadService(db)
