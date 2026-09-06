"""
ZipService — create ZIP archives from dataset files for download.

Deep module: hides ZIP creation, file-fetching, and single-file fallback
behind a small interface so the route handler stays thin.
"""
import io
import logging
import zipfile
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models.dataset import Dataset, DatasetFile
from app.models.file_handler import FileUpload
from app.services.storage import storage_service

logger = logging.getLogger(__name__)


def _sanitize_filename(filename: str, default: str = "download") -> str:
    """Sanitize a filename for use in Content-Disposition headers."""
    import re
    if not filename:
        return default
    filename = filename.replace("/", "_").replace("\\", "_")
    filename = re.sub(r'[\x00-\x1f\x7f-\x9f"]', "", filename)
    if len(filename) > 255:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = name[:250] + ("." + ext if ext else "")
    return filename or default


class ZipService:
    """Create ZIP archives from dataset files.

    Construct per-request with a DB session.
    """

    def __init__(self, db: Session):
        self.db = db

    async def download_all_files(
        self, dataset: Dataset, user: Any,
    ) -> Union[StreamingResponse, Dict[str, Any]]:
        """Download all files as ZIP, or a single file if only one exists.

        Returns a StreamingResponse for the ZIP/file, or raises HTTPException.
        """
        # Get all files for this dataset from DatasetFile table
        dataset_files = self.db.query(DatasetFile).filter(
            DatasetFile.dataset_id == dataset.id,
            DatasetFile.is_deleted == False,
        ).order_by(DatasetFile.file_order).all()

        # If no DatasetFile records, try FileUpload records (MindsDB agent files)
        if not dataset_files:
            file_uploads = self.db.query(FileUpload).filter(
                FileUpload.dataset_id == dataset.id,
            ).all()

            if file_uploads:
                logger.info(
                    f"Found {len(file_uploads)} files in FileUpload table for dataset {dataset.id}"
                )
                dataset_files = file_uploads
            elif dataset.file_path:
                # No multi-file records, try legacy single file download
                from app.services.download import DownloadService
                download_service = DownloadService(self.db)
                download_info = await download_service.initiate_download(
                    dataset_id=dataset.id, user=user,
                )
                return download_info
            else:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail="No files found for this dataset",
                )

        # If only one file, download it directly
        if len(dataset_files) == 1:
            return await self._download_single_file(dataset, dataset_files[0])

        # Multiple files — create ZIP archive
        return await self._create_zip_archive(dataset, dataset_files)

    async def _download_single_file(
        self, dataset: Dataset, file_record,
    ) -> StreamingResponse:
        """Stream a single file directly."""
        try:
            file_response = await storage_service.get_file_stream(file_record.file_path)

            filename = (
                getattr(file_record, "filename", None)
                or getattr(file_record, "original_filename", "download")
            )
            safe_filename = _sanitize_filename(filename)
            file_response.headers["Content-Disposition"] = (
                f'attachment; filename="{safe_filename}"'
            )

            dataset.download_count = (dataset.download_count or 0) + 1
            dataset.last_downloaded_at = __import__("datetime").datetime.utcnow()
            self.db.commit()

            return file_response
        except Exception as e:
            logger.error(f"Failed to download single file: {e}")
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to download file: {str(e)}",
            )

    async def _create_zip_archive(
        self, dataset: Dataset, dataset_files: List,
    ) -> StreamingResponse:
        """Build a ZIP archive in memory and return it as a StreamingResponse."""
        try:
            zip_buffer = io.BytesIO()

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for dataset_file in dataset_files:
                    try:
                        file_content = await storage_service.get_file_content(
                            dataset_file.file_path,
                        )
                        filename = (
                            getattr(dataset_file, "filename", None)
                            or getattr(dataset_file, "original_filename", f"file_{dataset_file.id}")
                        )
                        zip_file.writestr(filename, file_content)
                    except Exception as file_error:
                        fname = getattr(dataset_file, "filename", None) or getattr(dataset_file, "original_filename", "unknown")
                        logger.error(f"Failed to add file {fname} to ZIP: {file_error}")
                        continue

            zip_buffer.seek(0)

            dataset.download_count = (dataset.download_count or 0) + 1
            dataset.last_downloaded_at = __import__("datetime").datetime.utcnow()
            self.db.commit()

            safe_name = "".join(
                c for c in dataset.name if c.isalnum() or c in (" ", "-", "_")
            ).strip()
            zip_filename = f"{safe_name}_files.zip"

            logger.info(
                f"Created ZIP archive with {len(dataset_files)} files for dataset {dataset.id}"
            )

            return StreamingResponse(
                io.BytesIO(zip_buffer.read()),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{zip_filename}"',
                },
            )
        except Exception as e:
            logger.error(f"Failed to create ZIP archive: {e}")
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create ZIP archive: {str(e)}",
            )