"""
File Handler Base — shared utilities for MindsDB file handler services.

Consolidates methods that were duplicated between FileHandlerService
and PermanentFileHandlerService into one seam.
"""

import hashlib
import mimetypes
import logging
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from app.models.file_handler import FileUpload, MindsDBHandler, FileProcessingLog

logger = logging.getLogger(__name__)


class FileHandlerBase:
    """Base class with shared file-handler utility methods.

    Subclasses inherit ``calculate_file_hash``, ``get_file_mime_type``,
    ``log_processing_step``, ``get_file_upload_status``, and
    ``get_organization_handlers``.
    """

    def __init__(self, db: Session):
        self.db = db

    # ── Shared utilities ─────────────────────────────────────────

    @staticmethod
    def calculate_file_hash(file_content: bytes) -> str:
        """Calculate SHA-256 hash of file content."""
        return hashlib.sha256(file_content).hexdigest()

    @staticmethod
    def get_file_mime_type(filename: str) -> Optional[str]:
        """Get MIME type for file."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type

    def log_processing_step(
        self,
        file_upload_id: int,
        step: str,
        status: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        processing_time_ms: Optional[int] = None,
    ):
        """Log a processing step."""
        try:
            log_entry = FileProcessingLog(
                file_upload_id=file_upload_id,
                step=step,
                status=status,
                message=message,
                details=details,
                processing_time_ms=processing_time_ms,
            )
            self.db.add(log_entry)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log processing step: {str(e)}")

    def get_file_upload_status(self, file_upload_id: int) -> Optional[Dict[str, Any]]:
        """Get file upload status and processing logs.

        Subclasses may override to add storage-type-specific fields.
        """
        file_upload = (
            self.db.query(FileUpload)
            .filter(FileUpload.id == file_upload_id)
            .first()
        )
        if not file_upload:
            return None

        logs = (
            self.db.query(FileProcessingLog)
            .filter(FileProcessingLog.file_upload_id == file_upload_id)
            .order_by(FileProcessingLog.created_at)
            .all()
        )

        storage_type = (
            "permanent"
            if file_upload.file_path
            and file_upload.file_path.startswith("mindsdb://permanent_storage/")
            else "local"
        )

        status_info: Dict[str, Any] = {
            "id": file_upload.id,
            "original_filename": file_upload.original_filename,
            "file_size": file_upload.file_size,
            "upload_status": file_upload.upload_status,
            "mindsdb_file_id": file_upload.mindsdb_file_id,
            "storage_type": storage_type,
            "processing_started_at": file_upload.processing_started_at,
            "processing_completed_at": file_upload.processing_completed_at,
            "error_message": file_upload.error_message,
            "created_at": file_upload.created_at,
            "processing_logs": [
                {
                    "step": log.step,
                    "status": log.status,
                    "message": log.message,
                    "details": log.details,
                    "processing_time_ms": log.processing_time_ms,
                    "created_at": log.created_at,
                }
                for log in logs
            ],
        }

        if storage_type == "permanent":
            status_info["storage_path"] = getattr(
                file_upload, "mindsdb_storage_path", None
            )
        else:
            status_info["file_path"] = file_upload.file_path

        return status_info

    def get_organization_handlers(
        self, organization_id: int
    ) -> List[Dict[str, Any]]:
        """Get all active MindsDB handlers for an organization.

        Subclasses may override to filter by handler type.
        """
        handlers = (
            self.db.query(MindsDBHandler)
            .filter(
                MindsDBHandler.organization_id == organization_id,
                MindsDBHandler.is_active == True,
            )
            .all()
        )

        handler_list = []
        for handler in handlers:
            handler_info: Dict[str, Any] = {
                "id": handler.id,
                "handler_name": handler.handler_name,
                "handler_type": handler.handler_type,
                "configuration": handler.configuration,
                "created_at": handler.created_at,
                "updated_at": handler.updated_at,
            }

            if handler.handler_type == "permanent_file":
                handler_info["storage_type"] = "permanent"
            elif handler.handler_type == "file":
                handler_info["storage_type"] = "local"
            else:
                config = handler.configuration or {}
                handler_info["storage_type"] = (
                    "permanent"
                    if config.get("storage_type") == "permanent"
                    else "local"
                )

            handler_list.append(handler_info)

        return handler_list
