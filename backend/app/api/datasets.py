from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Body
import json
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.dataset import Dataset, DatasetType, DatabaseConnector


from app.models.organization import DataSharingLevel
from app.schemas.dataset import (
    DatasetUpdate, DatasetResponse
)
from app.services.data_sharing import DataSharingService
from app.services.mindsdb import mindsdb_service
from app.services.storage import storage_service
from app.services.dataset_service import DatasetService
from app.utils.file_utils import sanitize_filename
import logging

logger = logging.getLogger(__name__)

# Helper functions for JSON metadata analysis

router = APIRouter()

@router.get("/", response_model=List[DatasetResponse])
async def get_datasets(
    skip: int = 0,
    limit: int = 100,
    sharing_level: Optional[DataSharingLevel] = None,
    dataset_type: Optional[DatasetType] = None,
    include_inactive: bool = False,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get datasets accessible to the current user within their organization."""
    logger.info(f"get_datasets called by user {current_user.id} ({current_user.email})")
    logger.info(f"Parameters: skip={skip}, limit={limit}, include_deleted={include_deleted}, include_inactive={include_inactive}")
    
    if not current_user.organization_id:
        logger.info(f"User {current_user.id} has no organization, returning empty list")
        # Return empty list for users without organizations
        return []
    
    data_service = DataSharingService(db)
    datasets = data_service.get_accessible_datasets(
        user=current_user,
        sharing_level=sharing_level,
        include_inactive=include_inactive,
        include_deleted=include_deleted,
        dataset_type=dataset_type,
        skip=skip,
        limit=limit
    )

    logger.info(f"Returning {len(datasets)} datasets after SQL filtering and pagination")

    return datasets

@router.post("/", response_model=DatasetResponse, status_code=201)
async def create_dataset(
    dataset_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new dataset within the user's organization."""
    svc = DatasetService(db)
    try:
        dataset = await svc.create_dataset(dataset_data=dataset_data, user=current_user)
        return dataset
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY if "name" in str(e).lower()
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

@router.get("/{dataset_id}")
async def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific dataset if accessible to the user."""
    svc = DatasetService(db)
    try:
        result = await svc.get_dataset_details(dataset_id=dataset_id, user=current_user)
        logger.info(f"📤 Returning dataset {dataset_id} with {len(result.get('files', []))} files to user {current_user.id}")
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

@router.put("/{dataset_id}/metadata", response_model=DatasetResponse)
async def update_dataset_metadata(
    dataset_id: int,
    metadata_update: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update dataset metadata including schema, description, and custom fields."""
    svc = DatasetService(db)
    try:
        return await svc.update_dataset_metadata(
            dataset_id=dataset_id, metadata_update=metadata_update, user=current_user
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN, detail=str(e),
        )

@router.get("/{dataset_id}/metadata/detailed", response_model=Dict[str, Any])
async def get_detailed_dataset_metadata(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive dataset metadata including schema, statistics, and AI insights."""
    svc = DatasetService(db)
    try:
        result = await svc.get_detailed_metadata(dataset_id=dataset_id, user=current_user)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

@router.put("/{dataset_id}/edit", response_model=Dict[str, Any])
async def edit_dataset_content(
    dataset_id: int,
    edit_request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Edit dataset content and structure (for supported dataset types)."""
    svc = DatasetService(db)
    try:
        result = await svc.edit_content(
            dataset_id=dataset_id, edit_request=edit_request, user=current_user,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.put("/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: int,
    dataset_update: DatasetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a dataset (only owner can update)."""
    svc = DatasetService(db)
    try:
        return await svc.update_dataset(
            dataset_id=dataset_id, dataset_update=dataset_update, user=current_user
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN, detail=str(e),
        )

@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: int,
    force_delete: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Soft delete a dataset (only owner can delete). Use force_delete=true for hard delete."""
    svc = DatasetService(db)
    try:
        result = await svc.delete(
            dataset_id=dataset_id,
            force=force_delete,
            user=current_user,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.patch("/{dataset_id}/activate")
async def activate_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Activate a dataset."""
    svc = DatasetService(db)
    try:
        dataset = await svc.activate(dataset_id=dataset_id, user=current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    return {
        "message": "Dataset activated successfully",
        "dataset_id": dataset_id,
        "status": dataset.status
    }


@router.patch("/{dataset_id}/deactivate")
async def deactivate_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deactivate a dataset."""
    svc = DatasetService(db)
    try:
        dataset = await svc.deactivate(dataset_id=dataset_id, user=current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    return {
        "message": "Dataset deactivated successfully",
        "dataset_id": dataset_id,
        "status": dataset.status
    }

@router.post("/upload")
async def upload_dataset_file(
    file: UploadFile = File(None),
    files: List[UploadFile] = File(None),
    name: str = None,
    description: str = None,
    sharing_level: str = "private",
    agri_tags: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload single or multiple dataset files.

    agri_tags (optional): JSON object with region_id, crop_id, season,
    yield_column — see AgriDataService.validate_upload_tags.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must be part of an organization to upload datasets"
        )

    # Parse optional agri tags
    parsed_agri_tags = None
    if agri_tags:
        try:
            candidate = json.loads(agri_tags)
        except (json.JSONDecodeError, TypeError):
            candidate = None
        if not isinstance(candidate, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="agri_tags must be a valid JSON object",
            )
        parsed_agri_tags = candidate

    # Normalise files list (supports both `file` and `files` params)
    upload_files = []
    if files:
        upload_files = list(files)
        if file:
            upload_files.append(file)
    elif file:
        upload_files = [file]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )

    svc = DatasetService(db)
    try:
        dataset = await svc.create_from_files(
            files=upload_files,
            name=name,
            description=description,
            sharing_level=sharing_level,
            user=current_user,
            organization_id=current_user.organization_id,
            agri_tags=parsed_agri_tags,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {
        "message": "Dataset uploaded successfully",
        "dataset": dataset,
        "agent_based_chat": True,
        "ai_chat_available": True,
        "ai_features": {
            "chat_enabled": True,
            "model_ready": True,
            "architecture": "agent_based",
            "chat_endpoint": f"/api/datasets/{dataset.id}/chat",
            "supports_multi_file": dataset.is_multi_file_dataset,
        },
    }

@router.get("/{dataset_id}/download")
async def download_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download a dataset file with secure token-based access."""
    from app.services.download import DownloadService

    download_service = DownloadService(db)

    # Initiate download and get secure token
    download_info = await download_service.initiate_download(
        dataset_id=dataset_id,
        user=current_user
    )

    return download_info

@router.get("/{dataset_id}/download-all")
async def download_all_files(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Download all files from a multi-file dataset as a ZIP archive.

    For single-file datasets, returns the single file.
    For multi-file datasets, creates a ZIP archive containing all files.
    """
    from app.services.data_sharing import DataSharingService
    from app.services.zip_service import ZipService

    # Get dataset and check permissions
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )

    # Check permissions using data sharing service
    data_sharing_service = DataSharingService(db)
    if not data_sharing_service.can_download_dataset(current_user, dataset):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to download this dataset"
        )

    # Log download access
    data_sharing_service.log_access(
        user=current_user,
        dataset=dataset,
        access_type="download_all"
    )

    svc = ZipService(db)
    return await svc.download_all_files(dataset=dataset, user=current_user)

@router.get("/{dataset_id}/files/{file_id}/download")
async def download_individual_file(
    dataset_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Download a specific file from a multi-file dataset.

    Args:
        dataset_id: ID of the dataset
        file_id: ID of the specific file to download
    """
    from app.models.dataset import DatasetFile
    from app.services.data_sharing import DataSharingService

    # Get dataset and check permissions
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )

    # Check permissions using data sharing service
    data_sharing_service = DataSharingService(db)
    if not data_sharing_service.can_download_dataset(current_user, dataset):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to download this file"
        )

    # Try to get file from DatasetFile table first
    dataset_file = db.query(DatasetFile).filter(
        DatasetFile.id == file_id,
        DatasetFile.dataset_id == dataset_id,
        DatasetFile.is_deleted == False
    ).first()

    # If not found, try FileUpload table (MindsDB agent files)
    if not dataset_file:
        from app.models.file_handler import FileUpload
        dataset_file = db.query(FileUpload).filter(
            FileUpload.id == file_id,
            FileUpload.dataset_id == dataset_id
        ).first()

    if not dataset_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in this dataset"
        )

    # Get filename (handle both DatasetFile.filename and FileUpload.original_filename)
    filename = getattr(dataset_file, 'filename', None) or getattr(dataset_file, 'original_filename', 'download')

    # Log download access
    data_sharing_service.log_access(
        user=current_user,
        dataset=dataset,
        access_type=f"download_file_{file_id}"
    )

    try:
        # Get file from storage
        file_response = await storage_service.get_file_stream(dataset_file.file_path)

        # Set proper filename
        safe_filename = sanitize_filename(filename)
        file_response.headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'

        # Update dataset download statistics
        dataset.download_count = (dataset.download_count or 0) + 1
        dataset.last_downloaded_at = datetime.utcnow()
        db.commit()

        logger.info(f"✅ Downloaded file {dataset_file.filename} (ID: {file_id}) from dataset {dataset_id}")

        return file_response

    except Exception as e:
        logger.error(f"Failed to download file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}"
        )

@router.get("/download/{download_token}")
async def execute_download(
    download_token: str,
    range: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Execute the actual file download using a secure token with resumable download support.
    
    The Range header can be used for resumable downloads (e.g., "bytes=1024-").
    """
    from app.services.download import DownloadService
    
    download_service = DownloadService(db)
    
    # Execute the download with range support for resumable downloads
    return await download_service.execute_download(
        download_token=download_token,
        use_streaming=True,
        range_header=range
    )

@router.get("/download/{download_token}/progress")
async def get_download_progress(
    download_token: str,
    db: Session = Depends(get_db)
):
    """
    Get download progress information.
    
    Returns detailed progress information including status, percentage, 
    transfer rate, and estimated time remaining.
    """
    from app.services.download import DownloadService
    
    download_service = DownloadService(db)
    
    return download_service.get_download_progress(download_token)

@router.post("/download/{download_token}/retry")
async def retry_download(
    download_token: str,
    db: Session = Depends(get_db)
):
    """
    Retry a failed or interrupted download.
    
    This endpoint allows resuming downloads that were interrupted due to network issues
    or retrying downloads that failed for other reasons.
    """
    from app.services.download import DownloadService
    
    download_service = DownloadService(db)
    download_info = download_service.get_download_progress(download_token)
    
    # Check if download can be retried
    if download_info["status"] not in ["failed", "interrupted", "expired"]:
        return {
            "message": "Download is already in progress or completed",
            "status": download_info["status"],
            "can_retry": False,
            "download_info": download_info
        }
    
    # Reset download status for retry
    download_record = db.query(DatasetDownload).filter(
        DatasetDownload.download_token == download_token
    ).first()
    
    if not download_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Download not found"
        )
    
    # Update download record for retry
    download_record.download_status = "pending"
    download_record.error_message = None
    download_record.expires_at = datetime.utcnow() + timedelta(hours=24)
    db.commit()
    
    return {
        "message": "Download ready for retry",
        "download_token": download_token,
        "status": "pending",
        "can_retry": True,
        "expires_at": download_record.expires_at.isoformat()
    }

@router.get("/{dataset_id}/download-history")
async def get_download_history(
    dataset_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get download history for a dataset (owner only)."""
    from app.services.download import DownloadService
    
    download_service = DownloadService(db)
    
    return download_service.get_download_history(
        dataset_id=dataset_id,
        user=current_user,
        limit=limit
    )

@router.get("/{dataset_id}/stats")
async def get_dataset_stats(
    dataset_id: int,
    include_downloads: bool = True,
    include_access_logs: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive statistics for a dataset."""
    svc = DatasetService(db)
    try:
        return await svc.get_stats(
            dataset_id=dataset_id, user=current_user,
            include_downloads=include_downloads,
            include_access_logs=include_access_logs,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"❌ Failed to get stats for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dataset statistics: {str(e)}"
        )

@router.post("/{dataset_id}/chat")
async def chat_with_dataset(
    dataset_id: int,
    message: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Chat with the AI model specifically trained for this dataset."""
    svc = DatasetService(db)
    try:
        return await svc.chat_with_dataset(
            dataset_id=dataset_id, message=message, user=current_user
        )
    except ValueError as e:
        msg = str(e)
        if "Chat is disabled" in msg:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
        if "Message is required" in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in msg
            else status.HTTP_403_FORBIDDEN,
            detail=msg,
        )
    except Exception as e:
        logger.error(f"Dataset chat failed for dataset {dataset_id}: {e}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat with dataset failed: {str(e)}"
        )

@router.get("/{dataset_id}/models")
async def get_dataset_models(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get information about ML models associated with this dataset."""
    svc = DatasetService(db)
    try:
        return await svc.get_dataset_models(dataset_id=dataset_id, user=current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN, detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to get model info for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model information: {str(e)}"
        )

@router.post("/{dataset_id}/recreate-models")
async def recreate_dataset_models(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Recreate ML models for this dataset (owner only)."""
    svc = DatasetService(db)
    try:
        return await svc.recreate_dataset_models(dataset_id=dataset_id, user=current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN, detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to recreate models for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to recreate models: {str(e)}"
        )

# Enhanced Dataset Management API Endpoints

@router.get("/{dataset_id}/metadata")
async def get_dataset_metadata(
    dataset_id: int,
    refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed metadata for a dataset."""
    svc = DatasetService(db)
    try:
        return await svc.get_dataset_metadata(
            dataset_id=dataset_id, user=current_user, refresh=refresh
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN, detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to get metadata for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metadata: {str(e)}"
        )

@router.get("/{dataset_id}/preview")
async def get_dataset_preview(
    dataset_id: int,
    rows: int = 20,
    include_stats: bool = True,
    refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get dataset content preview."""
    svc = DatasetService(db)
    try:
        preview_data = await svc.get_preview(
            dataset_id=dataset_id, user=current_user,
            rows=rows, include_stats=include_stats
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    # Log access
    from app.services.data_sharing import DataSharingService
    data_service = DataSharingService(db)
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if dataset:
        data_service.log_access(user=current_user, dataset=dataset, access_type="preview")

    return {
        **preview_data,
        "request_params": {"rows_requested": rows, "include_stats": include_stats},
    }

@router.post("/{dataset_id}/download-token")
async def generate_download_token(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a secure download token for dataset access."""
    svc = DatasetService(db)
    try:
        download_info = await svc.generate_download_token(
            dataset_id=dataset_id, user=current_user
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    return {
        "message": "Download token generated successfully",
        "download_token": download_info["download_token"],
        "expires_at": download_info["expires_at"],
        "dataset_id": dataset_id,
        "file_format": "original",
    }

@router.post("/{dataset_id}/refresh-metadata")
async def refresh_dataset_metadata(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Refresh and update dataset metadata (owner only)."""
    svc = DatasetService(db)
    try:
        result = await svc.refresh_metadata(
            dataset_id=dataset_id, user=current_user
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    return {
        "message": "Dataset metadata refreshed successfully",
        "dataset_id": dataset_id,
        "status": result.get("status"),
        "updated_at": result.get("generated_at"),
    }

@router.get("/{dataset_id}/schema")
async def get_dataset_schema(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get dataset schema information."""
    svc = DatasetService(db)
    try:
        result = await svc.get_dataset_schema(dataset_id=dataset_id, user=current_user)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

@router.post("/{dataset_id}/transfer-ownership")
async def transfer_dataset_ownership(
    dataset_id: int,
    new_owner_id: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Transfer ownership of a dataset to another user within the same organization."""
    svc = DatasetService(db)
    try:
        result = await svc.transfer_ownership(
            dataset_id=dataset_id, new_owner_id=new_owner_id, user=current_user,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

@router.get("/{dataset_id}/preview/enhanced")
async def get_enhanced_dataset_preview(
    dataset_id: int,
    include_connector_preview: bool = True,
    include_file_preview: bool = True,
    preview_rows: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get enhanced dataset preview including file/connector-specific previews for metadata viewing."""
    data_service = DataSharingService(db)
    
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Check access permissions
    if not data_service.can_access_dataset(current_user, dataset):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this dataset"
        )
    
    try:
        preview_response = {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "type": dataset.type.value if dataset.type else "unknown",
            "preview_metadata": {}
        }
        
        # Base preview data from existing fields
        if dataset.preview_data:
            preview_response["preview_metadata"]["base_preview"] = dataset.preview_data
        elif dataset.content_preview:
            preview_response["preview_metadata"]["base_preview"] = {
                "content_sample": dataset.content_preview,
                "is_sample": True
            }
        
        # Enhanced file preview for different types
        if include_file_preview and dataset.file_path:
            try:
                file_preview = await _get_file_type_preview(dataset)
                preview_response["preview_metadata"]["file_preview"] = file_preview
            except Exception as e:
                logger.warning(f"Could not generate file preview for dataset {dataset_id}: {e}")
                preview_response["preview_metadata"]["file_preview"] = {
                    "error": f"File preview unavailable: {str(e)}",
                    "file_type": dataset.type.value if dataset.type else "unknown"
                }
        
        # Enhanced connector preview if connected via database connector
        if include_connector_preview and dataset.connector_id:
            try:
                connector_preview = await _get_connector_preview(dataset, preview_rows, db)
                preview_response["preview_metadata"]["connector_preview"] = connector_preview
            except Exception as e:
                logger.warning(f"Could not generate connector preview for dataset {dataset_id}: {e}")
                preview_response["preview_metadata"]["connector_preview"] = {
                    "error": f"Connector preview unavailable: {str(e)}",
                    "connector_id": dataset.connector_id
                }
        
        # Schema and structure information
        preview_response["preview_metadata"]["schema_summary"] = {
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
            "size_bytes": dataset.size_bytes,
            "file_metadata": dataset.file_metadata or {},
            "schema_metadata": dataset.schema_metadata or {},
            "quality_score": dataset.quality_metrics.get("overall_score") if dataset.quality_metrics else None
        }
        
        # Column statistics preview
        if dataset.column_statistics:
            preview_response["preview_metadata"]["columns_summary"] = {
                "total_columns": len(dataset.column_statistics),
                "column_types": {},
                "sample_columns": list(dataset.column_statistics.keys())[:10]
            }
            
            # Summarize column types
            for col, stats in dataset.column_statistics.items():
                col_type = stats.get("data_type", "unknown")
                preview_response["preview_metadata"]["columns_summary"]["column_types"][col_type] = \
                    preview_response["preview_metadata"]["columns_summary"]["column_types"].get(col_type, 0) + 1
        
        # Log access
        data_service.log_access(
            user=current_user,
            dataset=dataset,
            access_type="enhanced_preview"
        )
        
        return preview_response
        
    except Exception as e:
        logger.error(f"❌ Failed to get enhanced preview for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get enhanced preview: {str(e)}"
        )


async def _get_file_type_preview(dataset: Dataset) -> Dict[str, Any]:
    """Generate file-type specific preview data."""
    file_preview = {
        "file_type": dataset.type.value if dataset.type else "unknown",
        "file_size": dataset.size_bytes,
        "preview_available": True
    }
    
    if dataset.type == DatasetType.CSV:
        # CSV specific preview
        if dataset.schema_metadata and "columns" in dataset.schema_metadata:
            file_preview.update({
                "columns": dataset.schema_metadata["columns"],
                "delimiter": dataset.file_metadata.get("delimiter", ",") if dataset.file_metadata else ",",
                "encoding": dataset.schema_metadata.get("encoding", "utf-8"),
                "has_header": True  # Assume CSV has header
            })
    
    elif dataset.type == DatasetType.JSON:
        # JSON specific preview
        file_preview.update({
            "structure": dataset.schema_metadata.get("structure", {}) if dataset.schema_metadata else {},
            "is_array": dataset.file_metadata.get("is_array", False) if dataset.file_metadata else False,
            "nested_levels": dataset.file_metadata.get("nested_levels", 0) if dataset.file_metadata else 0
        })
    
    elif dataset.type == DatasetType.EXCEL:
        # Excel specific preview
        file_preview.update({
            "sheets": dataset.file_metadata.get("sheets", []) if dataset.file_metadata else [],
            "active_sheet": dataset.file_metadata.get("active_sheet", "Sheet1") if dataset.file_metadata else "Sheet1",
            "has_formulas": dataset.file_metadata.get("has_formulas", False) if dataset.file_metadata else False
        })
    
    elif dataset.type == DatasetType.PDF:
        # PDF specific preview
        file_preview.update({
            "pages": dataset.file_metadata.get("pages", 0) if dataset.file_metadata else 0,
            "text_content": bool(dataset.content_preview),
            "extractable": dataset.file_metadata.get("extractable", True) if dataset.file_metadata else True
        })
    
    elif dataset.type == DatasetType.IMAGE:
        # Image specific preview
        file_preview.update({
            "dimensions": dataset.file_metadata.get("dimensions", {}) if dataset.file_metadata else {},
            "image_format": dataset.file_metadata.get("image_format", "unknown") if dataset.file_metadata else "unknown",
            "color_mode": dataset.file_metadata.get("color_mode", "unknown") if dataset.file_metadata else "unknown",
            "has_exif": bool(dataset.file_metadata.get("exif_data")) if dataset.file_metadata else False
        })
    
    return file_preview


async def _get_connector_preview(dataset: Dataset, preview_rows: int, db: Session) -> Dict[str, Any]:
    """Generate connector-specific preview data."""
    from app.models.dataset import DatabaseConnector
    
    connector = db.query(DatabaseConnector).filter(
        DatabaseConnector.id == dataset.connector_id
    ).first()
    
    if not connector:
        raise ValueError("Connector not found")
    
    connector_preview = {
        "connector_id": connector.id,
        "connector_name": connector.name,
        "connector_type": connector.type,
        "status": connector.status,
        "connection_info": {
            "host": connector.host,
            "port": connector.port,
            "database": connector.database_name
        }
    }
    
    # Try to get live preview from connector
    try:
        if dataset.mindsdb_table_name and dataset.mindsdb_database:
            query = f"SELECT * FROM {dataset.mindsdb_database}.{dataset.mindsdb_table_name} LIMIT {preview_rows};"
            result = mindsdb_service.execute_query(query)
            
            if result.get('data'):
                connector_preview["live_preview"] = {
                    "sample_data": result['data'][:10],  # Show first 10 rows
                    "total_rows_available": len(result['data']),
                    "is_live": True,
                    "query_timestamp": datetime.utcnow().isoformat()
                }
            else:
                connector_preview["live_preview"] = {
                    "error": "No data available from connector",
                    "is_live": False
                }
    
    except Exception as e:
        connector_preview["live_preview"] = {
            "error": f"Could not fetch live data: {str(e)}",
            "is_live": False
        }
    
    return connector_preview


@router.put("/{dataset_id}/reupload")
async def reupload_dataset_file(
    dataset_id: int,
    file: UploadFile = File(...),
    preserve_metadata: bool = True,
    update_sharing_settings: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reupload/replace the file for an existing dataset while preserving configuration."""
    svc = DatasetService(db)
    try:
        result = await svc.reupload_file(
            dataset_id=dataset_id, file=file, user=current_user,
            preserve_metadata=preserve_metadata,
            update_sharing_settings=update_sharing_settings,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

@router.get("/{dataset_id}/visualize")
async def visualize_dataset(
    dataset_id: int,
    visualization_type: Optional[str] = None,
    max_visualizations: int = 4,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate visualizations for a dataset using LIDA."""
    svc = DatasetService(db)
    try:
        return await svc.visualize_dataset(
            dataset_id=dataset_id, user=current_user,
            visualization_type=visualization_type,
            max_visualizations=max_visualizations
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e)
            else status.HTTP_400_BAD_REQUEST, detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to generate visualizations for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate visualizations: {str(e)}"
        )