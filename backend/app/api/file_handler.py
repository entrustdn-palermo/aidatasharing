"""
File Handler API endpoints
Provides endpoints for file upload and MindsDB integration
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks, Form
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.core.config import settings
from app.models.user import User
from app.models.dataset import Dataset, DatasetType, DatasetStatus, DatabaseConnector
from app.models.organization import DataSharingLevel
from app.models.file_handler import FileUpload, MindsDBHandler, FileType
from app.services.file_handler import FileHandlerService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/upload", operation_id="upload_file_to_mindsdb")
async def upload_file(
    background_tasks: BackgroundTasks,
    dataset_id: int,
    file: UploadFile = File(...),
    process_with_mindsdb: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload a file and optionally process it with MindsDB
    """
    # Validate dataset access
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.organization_id == current_user.organization_id
    ).first()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found or access denied"
        )
    
    # Check if user can upload to this dataset
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        # Check organization-level permissions
        if dataset.organization_id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot upload files to datasets outside your organization"
            )
    
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    # Check file size (100MB limit)
    max_file_size = 100 * 1024 * 1024
    file_size = 0
    while chunk := await file.read(1024 * 1024):
        file_size += len(chunk)
        if file_size > max_file_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds 100MB limit"
            )
    await file.seek(0)
    
    try:
        # Initialize file handler service
        file_service = FileHandlerService(db)
        
        # Save uploaded file
        file_upload = await file_service.save_uploaded_file(file, current_user, dataset)
        
        # Process with MindsDB in background if requested
        if process_with_mindsdb:
            background_tasks.add_task(
                process_file_background,
                db,
                file_upload.id
            )
        
        return {
            "success": True,
            "message": "File uploaded successfully",
            "file_upload_id": file_upload.id,
            "original_filename": file_upload.original_filename,
            "file_size": file_upload.file_size,
            "processing_status": "queued" if process_with_mindsdb else "uploaded"
        }
        
    except Exception as e:
        logger.error(f"File upload failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}"
        )


async def process_file_background(db: Session, file_upload_id: int):
    """Background task to process file with MindsDB"""
    try:
        file_service = FileHandlerService(db)
        file_upload = db.query(FileUpload).filter(FileUpload.id == file_upload_id).first()
        
        if file_upload:
            result = file_service.process_file_with_mindsdb(file_upload)
            logger.info(f"Background processing completed for file {file_upload_id}: {result}")
        else:
            logger.error(f"File upload {file_upload_id} not found for background processing")
            
    except Exception as e:
        logger.error(f"Background file processing failed for {file_upload_id}: {str(e)}")


@router.get("/uploads/{file_upload_id}")
async def get_file_upload_status(
    file_upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get file upload status and processing logs"""
    file_service = FileHandlerService(db)
    
    # Get file upload with organization check
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File upload not found"
        )
    
    status_info = file_service.get_file_upload_status(file_upload_id)
    
    if not status_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File upload status not found"
        )
    
    return status_info


@router.get("/uploads")
async def list_file_uploads(
    dataset_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List file uploads for the current user's organization"""
    query = db.query(FileUpload).filter(
        FileUpload.organization_id == current_user.organization_id
    )
    
    if dataset_id:
        # Verify dataset access
        dataset = db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.organization_id == current_user.organization_id
        ).first()
        
        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dataset not found"
            )
        
        query = query.filter(FileUpload.dataset_id == dataset_id)
    
    file_uploads = query.order_by(FileUpload.created_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "file_uploads": [
            {
                "id": upload.id,
                "dataset_id": upload.dataset_id,
                "original_filename": upload.original_filename,
                "file_size": upload.file_size,
                "upload_status": upload.upload_status,
                "mindsdb_file_id": upload.mindsdb_file_id,
                "created_at": upload.created_at,
                "processing_started_at": upload.processing_started_at,
                "processing_completed_at": upload.processing_completed_at,
                "error_message": upload.error_message
            }
            for upload in file_uploads
        ],
        "total": query.count(),
        "limit": limit,
        "offset": offset
    }


@router.post("/uploads/{file_upload_id}/reprocess")
async def reprocess_file(
    file_upload_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Reprocess a file with MindsDB"""
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File upload not found"
        )
    
    # Reset processing status
    file_upload.upload_status = "uploaded"
    file_upload.processing_started_at = None
    file_upload.processing_completed_at = None
    file_upload.error_message = None
    file_upload.mindsdb_file_id = None
    db.commit()
    
    # Queue for reprocessing
    background_tasks.add_task(
        process_file_background,
        db,
        file_upload_id
    )
    
    return {
        "success": True,
        "message": "File queued for reprocessing",
        "file_upload_id": file_upload_id
    }


@router.get("/handlers")
async def list_mindsdb_handlers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List MindsDB handlers for the current organization"""
    file_service = FileHandlerService(db)
    handlers = file_service.get_organization_handlers(current_user.organization_id)
    
    return {
        "handlers": handlers,
        "count": len(handlers)
    }


@router.delete("/uploads/{file_upload_id}")
async def delete_file_upload(
    file_upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a file upload and its associated data"""
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File upload not found"
        )
    
    # Only allow deletion by file owner or admin
    if file_upload.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only delete your own file uploads"
        )
    
    try:
        file_service = FileHandlerService(db)
        result = file_service.delete_file_upload(file_upload_id)
        
        if result["success"]:
            return {
                "success": True,
                "message": result["message"]
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"]
            )
        
    except Exception as e:
        logger.error(f"Failed to delete file upload {file_upload_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file upload: {str(e)}"
        )
@router.post("/migrate/{file_upload_id}")
async def migrate_file_to_permanent_storage(
    file_upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Migrate existing local file to permanent storage"""
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File upload not found"
        )
    
    # Only allow migration by file owner or admin
    if file_upload.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only migrate your own file uploads"
        )
    
    try:
        file_service = FileHandlerService(db)
        result = file_service.migrate_to_permanent_storage(file_upload_id)
        
        if result["success"]:
            return {
                "success": True,
                "message": result["message"],
                "file_upload_id": file_upload_id,
                "new_file_id": result.get("new_file_id"),
                "handler_name": result.get("handler_name")
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"]
            )
            
    except Exception as e:
        logger.error(f"Migration failed for file {file_upload_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Migration failed: {str(e)}"
        )


@router.get("/uploads/{file_upload_id}/query")
async def query_file_data(
    file_upload_id: int,
    query: str = "",
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Query data from uploaded file"""
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File upload not found"
        )
    
    try:
        file_service = FileHandlerService(db)
        result = file_service.query_file_data(file_upload_id, query, limit)
        
        if result["success"]:
            return result
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"]
            )
            
    except Exception as e:
        logger.error(f"Query failed for file {file_upload_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(e)}"
        )


@router.get("/uploads/{file_upload_id}/metadata")
async def get_file_metadata(
    file_upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get comprehensive file metadata"""
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File upload not found"
        )
    
    try:
        file_service = FileHandlerService(db)
        result = file_service.get_file_metadata(file_upload_id)
        
        if result["success"]:
            return result
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"]
            )
            
    except Exception as e:
        logger.error(f"Metadata retrieval failed for file {file_upload_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Metadata retrieval failed: {str(e)}"
        ) 
@router.post("/upload/universal")
async def upload_universal_file(
    file: UploadFile = File(...),
    dataset_name: str = Form(...),
    description: str = Form(""),
    sharing_level: str = Form("PRIVATE"),
    process_with_ai: bool = Form(True),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Upload any supported file type with metadata extraction and preview"""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization to upload files"
        )
    
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    # Check file size (100MB limit)
    file_content = await file.read()
    file_size = len(file_content)
    
    if file_size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds {settings.MAX_FILE_SIZE_MB}MB limit"
        )
    
    # Reset file pointer
    await file.seek(0)
    
    try:
        # Create dataset
        sharing_level_enum = getattr(DataSharingLevel, sharing_level.upper(), DataSharingLevel.PRIVATE)
        
        # Determine dataset type based on file
        from app.services.universal_file_processor import UniversalFileProcessor
        processor = UniversalFileProcessor(db)
        file_type = processor.determine_file_type(file.filename)
        
        dataset_type_mapping = {
            FileType.SPREADSHEET: DatasetType.CSV,  # Default CSV for spreadsheets
            FileType.DOCUMENT: DatasetType.PDF,     # Default PDF for documents
            FileType.IMAGE: DatasetType.IMAGE,      # Now we have IMAGE type
            FileType.ARCHIVE: DatasetType.TXT,      # No ARCHIVE type, use TXT as fallback
            FileType.OTHER: DatasetType.TXT         # Use TXT as fallback for other types
        }
        
        dataset_type = dataset_type_mapping.get(file_type, DatasetType.TXT)
        
        dataset = Dataset(
            name=dataset_name,
            description=description,
            type=dataset_type,
            status=DatasetStatus.ACTIVE,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
            sharing_level=sharing_level_enum,
            allow_download=True,
            allow_api_access=True,
            allow_ai_chat=True
        )
        
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        
        # Process file with universal processor
        file_service = FileHandlerService(db)
        file_upload = await file_service.save_uploaded_file(file, current_user, dataset)
        
        # Update dataset with file metadata
        dataset.size_bytes = file_upload.file_size
        dataset.source_url = file_upload.file_path
        
        # Extract additional metadata from file_upload.file_metadata
        if file_upload.file_metadata:
            metadata = file_upload.file_metadata
            
            # For spreadsheet files
            if metadata.get('type') == 'spreadsheet':
                if 'rows' in metadata:
                    dataset.row_count = metadata['rows']
                if 'columns' in metadata:
                    dataset.column_count = len(metadata['columns']) if isinstance(metadata['columns'], list) else metadata['columns']
                    
            # For other files, try to extract row/column info
            elif 'data_rows' in metadata:
                dataset.row_count = metadata['data_rows']
            elif 'rows' in metadata:
                dataset.row_count = metadata['rows']
                
            if 'headers' in metadata and isinstance(metadata['headers'], list):
                dataset.column_count = len(metadata['headers'])
        
        # Commit dataset updates
        db.commit()
        db.refresh(dataset)
        
        # Process with AI in background if requested
        if process_with_ai:
            background_tasks.add_task(
                process_universal_file_background,
                db,
                file_upload.id
            )
        
        return {
            "success": True,
            "message": f"{file_type.value.title()} file uploaded successfully",
            "dataset_id": dataset.id,
            "file_upload_id": file_upload.id,
            "original_filename": file_upload.original_filename,
            "file_size": file_upload.file_size,
            "file_type": file_upload.file_type,
            "metadata": file_upload.file_metadata,
            "processing_status": "queued" if process_with_ai else "uploaded"
        }
        
    except Exception as e:
        logger.error(f"Universal file upload failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}"
        )


async def process_universal_file_background(db: Session, file_upload_id: int):
    """Background task to process any file type with AI"""
    try:
        file_service = FileHandlerService(db)
        file_upload = db.query(FileUpload).filter(FileUpload.id == file_upload_id).first()
        
        if file_upload:
            result = file_service.process_file_with_mindsdb(file_upload)
            logger.info(f"Background file processing completed for file {file_upload_id}: {result}")
        else:
            logger.error(f"File upload {file_upload_id} not found for background processing")
            
    except Exception as e:
        logger.error(f"Background file processing failed for {file_upload_id}: {str(e)}")


@router.get("/uploads/{file_upload_id}/preview")
async def get_file_preview(
    file_upload_id: int,
    preview_type: str = "metadata",  # metadata, content
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get preview for any uploaded file"""
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    try:
        from app.services.universal_file_processor import UniversalFileProcessor
        processor = UniversalFileProcessor(db)
        preview = processor.generate_preview(file_upload, preview_type)
        
        if preview["success"]:
            return preview
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=preview["error"]
            )
            
    except Exception as e:
        logger.error(f"File preview failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preview generation failed: {str(e)}"
        )


@router.get("/connectors/{connector_id}/preview")
async def get_connector_preview(
    connector_id: int,
    table_or_path: str,
    preview_type: str = "data",  # data, list, content
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get preview for connector data"""
    connector = db.query(DatabaseConnector).filter(
        DatabaseConnector.id == connector_id,
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found"
        )
    
    try:
        from app.services.connector_preview import ConnectorPreviewService
        preview_service = ConnectorPreviewService(db)
        preview = await preview_service.generate_connector_preview(
            connector, table_or_path, preview_type
        )
        
        if preview["success"]:
            return preview
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=preview["error"]
            )
            
    except Exception as e:
        logger.error(f"Connector preview failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connector preview failed: {str(e)}"
        )


@router.post("/upload/pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    dataset_name: str = Form(...),
    description: str = Form(""),
    sharing_level: str = Form("PRIVATE"),
    process_with_ai: bool = Form(True),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Upload a PDF file with metadata extraction and AI processing"""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization to upload files"
        )
    
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    # Check if it's a PDF file
    file_service = FileHandlerService(db)
    mime_type = file_service.get_file_mime_type(file.filename)
    if not file_service.pdf_service.is_supported_pdf(file.filename, mime_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a supported PDF format"
        )
    
    # Check file size (50MB limit for PDFs)
    file_content = await file.read()
    file_size = len(file_content)
    
    if file_size > 50 * 1024 * 1024:  # 50MB
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF size exceeds 50MB limit"
        )
    
    # Reset file pointer
    await file.seek(0)
    
    try:
        # Create or get dataset
        sharing_level_enum = getattr(DataSharingLevel, sharing_level.upper(), DataSharingLevel.PRIVATE)
        
        dataset = Dataset(
            name=dataset_name,
            description=description,
            type=DatasetType.DOCUMENT,
            status=DatasetStatus.ACTIVE,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
            sharing_level=sharing_level_enum,
            allow_download=True,
            allow_api_access=True,
            allow_ai_chat=True
        )
        
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        
        # Save uploaded PDF
        file_upload = await file_service.save_uploaded_file(file, current_user, dataset)
        
        # Process with AI in background if requested
        if process_with_ai:
            background_tasks.add_task(
                process_pdf_background,
                db,
                file_upload.id
            )
        
        return {
            "success": True,
            "message": "PDF uploaded successfully",
            "dataset_id": dataset.id,
            "file_upload_id": file_upload.id,
            "original_filename": file_upload.original_filename,
            "file_size": file_upload.file_size,
            "file_type": "pdf",
            "pdf_metadata": file_upload.file_metadata,
            "processing_status": "queued" if process_with_ai else "uploaded"
        }
        
    except Exception as e:
        logger.error(f"PDF upload failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF upload failed: {str(e)}"
        )


async def process_pdf_background(db: Session, file_upload_id: int):
    """Background task to process PDF with AI"""
    try:
        file_service = FileHandlerService(db)
        file_upload = db.query(FileUpload).filter(FileUpload.id == file_upload_id).first()
        
        if file_upload and file_upload.file_type == "document" and file_upload.mime_type == "application/pdf":
            result = file_service.process_file_with_mindsdb(file_upload)
            logger.info(f"Background PDF processing completed for file {file_upload_id}: {result}")
        else:
            logger.error(f"PDF file upload {file_upload_id} not found for background processing")
            
    except Exception as e:
        logger.error(f"Background PDF processing failed for {file_upload_id}: {str(e)}")


@router.get("/uploads/{file_upload_id}/pdf-analysis")
async def get_pdf_analysis(
    file_upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get analysis results for a PDF"""
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id,
        FileUpload.file_type == "document",
        FileUpload.mime_type == "application/pdf"
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF not found"
        )
    
    try:
        file_service = FileHandlerService(db)
        analysis = file_service.pdf_service.get_pdf_analysis(file_upload_id)
        
        if analysis["success"]:
            return analysis
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=analysis["error"]
            )
            
    except Exception as e:
        logger.error(f"PDF analysis retrieval failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF analysis retrieval failed: {str(e)}"
        )


@router.post("/upload/image")
async def upload_image(
    background_tasks: BackgroundTasks,
    dataset_id: int,
    file: UploadFile = File(...),
    process_with_ai: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload an image file and optionally process it with AI
    """
    # Validate dataset access
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.organization_id == current_user.organization_id
    ).first()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found or access denied"
        )
    
    # Check if user can upload to this dataset
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        # Check organization-level permissions
        if dataset.organization_id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot upload files to datasets outside your organization"
            )
    
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    # Check if it's an image file
    file_service = FileHandlerService(db)
    mime_type = file_service.get_file_mime_type(file.filename)
    if not file_service.image_service.is_supported_image(file.filename, mime_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a supported image format. Supported: JPG, PNG, GIF, BMP, TIFF, WebP, SVG"
        )
    
    # Check file size (50MB limit for images)
    file_content = await file.read()
    file_size = len(file_content)
    
    if file_size > 50 * 1024 * 1024:  # 50MB
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image size exceeds 50MB limit"
        )
    
    # Reset file pointer
    await file.seek(0)
    
    try:
        # Save uploaded image
        file_upload = await file_service.save_uploaded_file(file, current_user, dataset)
        
        # Process with AI in background if requested
        if process_with_ai:
            background_tasks.add_task(
                process_image_background,
                db,
                file_upload.id
            )
        
        return {
            "success": True,
            "message": "Image uploaded successfully",
            "file_upload_id": file_upload.id,
            "original_filename": file_upload.original_filename,
            "file_size": file_upload.file_size,
            "file_type": "image",
            "image_metadata": {
                "width": file_upload.image_width,
                "height": file_upload.image_height,
                "format": file_upload.image_format,
                "color_mode": file_upload.color_mode
            },
            "processing_status": "queued" if process_with_ai else "uploaded"
        }
        
    except Exception as e:
        logger.error(f"Image upload failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image upload failed: {str(e)}"
        )


async def process_image_background(db: Session, file_upload_id: int):
    """Background task to process image with AI"""
    try:
        file_service = FileHandlerService(db)
        file_upload = db.query(FileUpload).filter(FileUpload.id == file_upload_id).first()
        
        if file_upload and file_upload.file_type == "image":
            result = file_service.process_file_with_mindsdb(file_upload)
            logger.info(f"Background image processing completed for file {file_upload_id}: {result}")
        else:
            logger.error(f"Image file upload {file_upload_id} not found for background processing")
            
    except Exception as e:
        logger.error(f"Background image processing failed for {file_upload_id}: {str(e)}")


@router.get("/uploads/{file_upload_id}/image-analysis")
async def get_image_analysis(
    file_upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get AI analysis results for an image"""
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id,
        FileUpload.file_type == "image"
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    try:
        file_service = FileHandlerService(db)
        analysis = file_service.image_service.get_image_analysis(file_upload_id)
        
        if analysis["success"]:
            return analysis
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=analysis["error"]
            )
            
    except Exception as e:
        logger.error(f"Image analysis retrieval failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image analysis retrieval failed: {str(e)}"
        )


@router.post("/connectors/remote-image")
async def create_remote_image_connector(
    connector_config: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a remote image connector (S3, URL, etc.)"""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    try:
        file_service = FileHandlerService(db)
        result = file_service.image_service.create_remote_image_connector(connector_config)
        
        if result["success"]:
            return {
                "success": True,
                "message": result["message"],
                "connector_name": result["connector_name"],
                "source_type": result["source_type"]
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
            
    except Exception as e:
        logger.error(f"Remote image connector creation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Remote image connector creation failed: {str(e)}"
        )

@router.get("/{file_upload_id}/preview/enhanced")
async def get_enhanced_image_preview(
    file_upload_id: int,
    include_metadata: bool = True,
    include_ai_analysis: bool = True,
    include_technical_details: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get enhanced image preview with comprehensive metadata and AI analysis."""
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id,
        FileUpload.file_type == "image"
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    try:
        preview_response = {
            "file_upload_id": file_upload_id,
            "filename": file_upload.original_filename,
            "file_type": "image",
            "preview_metadata": {}
        }
        
        # Basic image information
        preview_response["preview_metadata"]["basic_info"] = {
            "file_size": file_upload.file_size,
            "upload_date": file_upload.created_at.isoformat() if file_upload.created_at else None,
            "processing_status": file_upload.upload_status,
            "mime_type": file_upload.mime_type
        }
        
        # Technical image details
        if include_technical_details:
            try:
                technical_details = await _get_image_technical_details(file_upload)
                preview_response["preview_metadata"]["technical_details"] = technical_details
            except Exception as e:
                logger.warning(f"Could not get technical details for image {file_upload_id}: {e}")
                preview_response["preview_metadata"]["technical_details"] = {
                    "error": f"Technical details unavailable: {str(e)}"
                }
        
        # Enhanced metadata from file metadata
        if include_metadata and file_upload.file_metadata:
            preview_response["preview_metadata"]["image_metadata"] = {
                "dimensions": {
                    "width": file_upload.image_width,
                    "height": file_upload.image_height,
                    "aspect_ratio": f"{file_upload.image_width}:{file_upload.image_height}" if file_upload.image_width and file_upload.image_height else None
                },
                "format_info": {
                    "format": file_upload.image_format,
                    "color_mode": file_upload.color_mode,
                    "has_transparency": file_upload.file_metadata.get("has_transparency", False),
                    "compression": file_upload.file_metadata.get("compression_type")
                },
                "quality_metrics": {
                    "estimated_quality": file_upload.file_metadata.get("estimated_quality"),
                    "color_depth": file_upload.file_metadata.get("color_depth"),
                    "file_size_efficiency": file_upload.file_metadata.get("size_efficiency")
                }
            }
        
        # AI analysis results
        if include_ai_analysis:
            try:
                ai_analysis = await _get_image_ai_analysis(file_upload, db)
                preview_response["preview_metadata"]["ai_analysis"] = ai_analysis
            except Exception as e:
                logger.warning(f"Could not get AI analysis for image {file_upload_id}: {e}")
                preview_response["preview_metadata"]["ai_analysis"] = {
                    "error": f"AI analysis unavailable: {str(e)}"
                }
        
        # Usage and sharing information
        preview_response["preview_metadata"]["usage_info"] = {
            "dataset_id": file_upload.dataset_id,
            "can_download": True,
            "processing_completed": file_upload.processing_completed_at is not None,
            "mindsdb_file_id": file_upload.mindsdb_file_id
        }
        
        return preview_response
        
    except Exception as e:
        logger.error(f"❌ Failed to get enhanced preview for image {file_upload_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get enhanced preview: {str(e)}"
        )


async def _get_image_technical_details(file_upload: FileUpload) -> Dict[str, Any]:
    """Get technical details for an image file."""
    technical_details = {
        "format": file_upload.image_format,
        "dimensions": {
            "width": file_upload.image_width,
            "height": file_upload.image_height,
            "total_pixels": file_upload.image_width * file_upload.image_height if file_upload.image_width and file_upload.image_height else None
        },
        "color_info": {
            "mode": file_upload.color_mode,
            "channels": file_upload.file_metadata.get("channels") if file_upload.file_metadata else None,
            "bit_depth": file_upload.file_metadata.get("bit_depth") if file_upload.file_metadata else None
        },
        "compression": {
            "type": file_upload.file_metadata.get("compression_type") if file_upload.file_metadata else None,
            "quality": file_upload.file_metadata.get("compression_quality") if file_upload.file_metadata else None
        }
    }
    
    # Add EXIF data if available
    if file_upload.file_metadata and "exif" in file_upload.file_metadata:
        technical_details["exif_data"] = file_upload.file_metadata["exif"]
    
    return technical_details


async def _get_image_ai_analysis(file_upload: FileUpload, db: Session) -> Dict[str, Any]:
    """Get AI analysis results for an image."""
    ai_analysis = {
        "analysis_available": file_upload.processing_completed_at is not None,
        "analysis_date": file_upload.processing_completed_at.isoformat() if file_upload.processing_completed_at else None
    }
    
    # Get AI analysis from MindsDB if available
    if file_upload.mindsdb_file_id:
        try:
            from app.services.mindsdb import mindsdb_service
            
            # Query for AI analysis results
            analysis_query = f"""
                SELECT * FROM mindsdb.image_analysis_{file_upload.id} 
                WHERE file_id = '{file_upload.mindsdb_file_id}' 
                LIMIT 1;
            """
            
            result = mindsdb_service.execute_query(analysis_query)
            
            if result.get('data') and len(result['data']) > 0:
                analysis_data = result['data'][0]
                ai_analysis["content_description"] = analysis_data.get('description')
                ai_analysis["detected_objects"] = analysis_data.get('objects', [])
                ai_analysis["scene_classification"] = analysis_data.get('scene_type')
                ai_analysis["visual_features"] = analysis_data.get('features', {})
                ai_analysis["confidence_score"] = analysis_data.get('confidence')
            else:
                ai_analysis["status"] = "No analysis results available"
        
        except Exception as e:
            ai_analysis["error"] = f"Could not retrieve AI analysis: {str(e)}"
    else:
        ai_analysis["status"] = "AI analysis not processed"
    
    return ai_analysis


@router.post("/{file_upload_id}/reupload")
async def reupload_image_file(
    file_upload_id: int,
    file: UploadFile = File(...),
    preserve_metadata: bool = True,
    reprocess_with_ai: bool = True,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Reupload/replace an image file while preserving configuration."""
    file_upload = db.query(FileUpload).filter(
        FileUpload.id == file_upload_id,
        FileUpload.organization_id == current_user.organization_id,
        FileUpload.file_type == "image"
    ).first()
    
    if not file_upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    # Check permissions - only owner or admin can reupload
    if file_upload.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only file owner or organization admin can reupload images"
        )
    
    # Validate new file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    # Check if it's an image file
    file_service = FileHandlerService(db)
    mime_type = file_service.get_file_mime_type(file.filename)
    if not file_service.image_service.is_supported_image(file.filename, mime_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a supported image format. Supported: JPG, PNG, GIF, BMP, TIFF, WebP, SVG"
        )
    
    # Check file size (50MB limit for images)
    file_content = await file.read()
    file_size = len(file_content)
    
    if file_size > 50 * 1024 * 1024:  # 50MB
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image size exceeds 50MB limit"
        )
    
    # Reset file pointer
    await file.seek(0)
    
    try:
        # Store original metadata if preserving
        original_metadata = {}
        if preserve_metadata:
            original_metadata = {
                "original_filename": file_upload.original_filename,
                "description": getattr(file_upload, 'description', ''),
                "tags": getattr(file_upload, 'tags', []),
                "custom_metadata": getattr(file_upload, 'custom_metadata', {})
            }
        
        # Backup old file information
        old_file_path = file_upload.file_path
        old_mindsdb_file_id = file_upload.mindsdb_file_id
        
        # Update file upload record with new file
        file_upload.original_filename = file.filename if not preserve_metadata else original_metadata.get("original_filename", file.filename)
        file_upload.file_size = file_size
        file_upload.mime_type = mime_type
        file_upload.upload_status = "uploaded"
        file_upload.processing_started_at = None
        file_upload.processing_completed_at = None
        file_upload.error_message = None
        
        # Clear old AI processing results
        file_upload.mindsdb_file_id = None
        
        # Save new file content
        import tempfile
        import os
        from PIL import Image
        
        # Create temporary file to analyze new image
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        try:
            # Extract new image metadata
            with Image.open(temp_file_path) as img:
                file_upload.image_width = img.width
                file_upload.image_height = img.height
                file_upload.image_format = img.format
                file_upload.color_mode = img.mode
                
                # Enhanced metadata extraction
                enhanced_metadata = {
                    "format": img.format,
                    "mode": img.mode,
                    "size": img.size,
                    "has_transparency": img.mode in ('RGBA', 'LA') or 'transparency' in img.info,
                    "reupload_timestamp": datetime.utcnow().isoformat()
                }
                
                # Extract EXIF data if available
                if hasattr(img, '_getexif') and img._getexif():
                    enhanced_metadata["exif"] = dict(img._getexif())
                
                file_upload.file_metadata = enhanced_metadata
        
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        
        # Save file to storage
        await file.seek(0)
        new_file_upload = await file_service.save_uploaded_file(file, current_user, file_upload.dataset)
        
        # Update the original record with new file path
        file_upload.file_path = new_file_upload.file_path
        file_upload.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(file_upload)
        
        # Clean up old MindsDB file if it exists
        if old_mindsdb_file_id:
            try:
                from app.services.mindsdb import mindsdb_service
                cleanup_result = mindsdb_service.delete_file(old_mindsdb_file_id)
                logger.info(f"Cleaned up old MindsDB file {old_mindsdb_file_id}: {cleanup_result}")
            except Exception as e:
                logger.warning(f"Could not clean up old MindsDB file {old_mindsdb_file_id}: {e}")
        
        # Process with AI in background if requested
        if reprocess_with_ai:
            background_tasks.add_task(
                process_image_background,
                db,
                file_upload.id
            )
        
        # Prepare response
        response_data = {
            "success": True,
            "message": "Image file reuploaded successfully",
            "file_upload_id": file_upload.id,
            "original_filename": file_upload.original_filename,
            "file_changes": {
                "new_filename": file.filename,
                "new_size_bytes": file_size,
                "new_format": file_upload.image_format,
                "new_dimensions": {
                    "width": file_upload.image_width,
                    "height": file_upload.image_height
                }
            },
            "metadata_preserved": preserve_metadata,
            "ai_processing": {
                "reprocess_queued": reprocess_with_ai,
                "status": "queued" if reprocess_with_ai else "not_requested"
            },
            "updated_at": file_upload.updated_at.isoformat()
        }
        
        logger.info(f"✅ Image {file_upload_id} reuploaded successfully by user {current_user.id}")
        
        return response_data
        
    except Exception as e:
        logger.error(f"❌ Failed to reupload image {file_upload_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reupload image: {str(e)}"
        )