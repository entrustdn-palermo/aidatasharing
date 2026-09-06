"""
Individual file download endpoints for shared datasets
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import os
import mimetypes
import zipfile
import tempfile
import logging

from app.core.database import get_db
from app.models.dataset import Dataset, DatasetFile
from app.services.data_sharing import DataSharingService

logger = logging.getLogger(__name__)
router = APIRouter()


class DownloadSelectedFilesRequest(BaseModel):
    file_ids: List[int]


@router.get("/public/shared/{share_token}/files")
async def get_shared_dataset_files(
    share_token: str,
    password: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get list of files in a shared multi-file dataset (public endpoint)."""
    # Verify dataset and access
    dataset = db.query(Dataset).filter(
        Dataset.share_token == share_token,
        Dataset.public_share_enabled == True,
        Dataset.is_deleted == False
    ).first()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared dataset not found"
        )
    
    service = DataSharingService(db)
    service.require_share_password(dataset, password)
    
    # Check if it's a multi-file dataset
    if not dataset.is_multi_file_dataset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This dataset does not contain multiple files"
        )
    
    # Get files for this dataset
    dataset_files = db.query(DatasetFile).filter(
        DatasetFile.dataset_id == dataset.id,
        DatasetFile.is_deleted == False
    ).order_by(DatasetFile.is_primary.desc(), DatasetFile.file_order.asc()).all()
    
    # Format file information
    files = []
    for file_record in dataset_files:
        files.append({
            "id": file_record.id,
            "filename": file_record.filename,
            "file_type": file_record.file_type,
            "file_size": file_record.file_size,
            "mime_type": file_record.mime_type,
            "is_primary": file_record.is_primary,
            "file_order": file_record.file_order,
            "created_at": file_record.created_at.isoformat() if file_record.created_at else None
        })
    
    return {
        "files": files,
        "total_count": len(files),
        "dataset_name": dataset.name,
        "dataset_id": dataset.id
    }


@router.get("/public/shared/{share_token}/files/{file_id}/download")
async def download_individual_file(
    share_token: str,
    file_id: int,
    password: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Download an individual file from a shared multi-file dataset (public endpoint)."""
    # Verify dataset and access
    dataset = db.query(Dataset).filter(
        Dataset.share_token == share_token,
        Dataset.public_share_enabled == True,
        Dataset.allow_download == True,
        Dataset.is_deleted == False
    ).first()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared dataset not found or download not allowed"
        )
    
    service = DataSharingService(db)
    service.require_share_password(dataset, password)
    
    # Get the specific file
    dataset_file = db.query(DatasetFile).filter(
        DatasetFile.id == file_id,
        DatasetFile.dataset_id == dataset.id,
        DatasetFile.is_deleted == False
    ).first()
    
    if not dataset_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or not accessible"
        )
    
    # Log the download
    logger.info(f"Individual file download: {dataset_file.filename} from dataset {dataset.id} via token {share_token[:8]}...")

    # Use storage service to get file stream (works with both S3 and local storage)
    try:
        from app.services.storage import storage_service

        # Use relative_path if available, otherwise use file_path
        file_path_to_retrieve = dataset_file.relative_path or dataset_file.file_path

        # Get file stream from storage service
        return await storage_service.get_file_stream(file_path_to_retrieve)

    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        logger.error(f"File download failed for {dataset_file.filename}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}"
        )


@router.post("/public/shared/{share_token}/files/download-selected")
async def download_selected_files(
    share_token: str,
    request_data: DownloadSelectedFilesRequest,
    password: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Download selected files from a shared multi-file dataset as a zip (public endpoint)."""
    # Verify dataset and access
    dataset = db.query(Dataset).filter(
        Dataset.share_token == share_token,
        Dataset.public_share_enabled == True,
        Dataset.allow_download == True,
        Dataset.is_deleted == False
    ).first()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared dataset not found or download not allowed"
        )
    
    service = DataSharingService(db)
    service.require_share_password(dataset, password)
    
    # Get the selected files
    dataset_files = db.query(DatasetFile).filter(
        DatasetFile.id.in_(request_data.file_ids),
        DatasetFile.dataset_id == dataset.id,
        DatasetFile.is_deleted == False
    ).all()
    
    if not dataset_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No valid files found for download"
        )
    
    # If only one file, return it directly
    if len(dataset_files) == 1:
        dataset_file = dataset_files[0]
        
        if not os.path.exists(dataset_file.file_path):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="File is no longer available"
            )
        
        logger.info(f"Single file download: {dataset_file.filename} from dataset {dataset.id} via token {share_token[:8]}...")
        
        mime_type = dataset_file.mime_type or 'application/octet-stream'
        
        return FileResponse(
            path=dataset_file.file_path,
            filename=dataset_file.filename,
            media_type=mime_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{dataset_file.filename}\"",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    
    # Multiple files - create zip
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    
    try:
        with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for dataset_file in dataset_files:
                if os.path.exists(dataset_file.file_path):
                    zip_file.write(dataset_file.file_path, dataset_file.filename)
        
        temp_zip.close()
        
        logger.info(f"Multi-file zip download: {len(dataset_files)} files from dataset {dataset.id} via token {share_token[:8]}...")
        
        download_name = f"{dataset.name}_selected_files.zip"
        
        return FileResponse(
            path=temp_zip.name,
            filename=download_name,
            media_type='application/zip',
            headers={
                "Content-Disposition": f"attachment; filename=\"{download_name}\"",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except Exception as e:
        # Clean up temp file on error
        if os.path.exists(temp_zip.name):
            os.unlink(temp_zip.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create zip file: {str(e)}"
        )