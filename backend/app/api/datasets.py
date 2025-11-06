from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.dataset import Dataset, DatasetType, DatasetStatus, AIProcessingStatus, DatabaseConnector
from app.models.organization import DataSharingLevel
from app.schemas.dataset import (
    DatasetCreate, DatasetUpdate, DatasetResponse, 
    DatasetUpload, DatasetStats, DatasetAccessLog
)
from app.services.data_sharing import DataSharingService
from app.services.mindsdb import mindsdb_service
from app.services.storage import storage_service
from app.services.metadata import MetadataService
from app.services.preview import PreviewService
import json
import logging
import time
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Helper functions for JSON metadata analysis
def _count_json_nesting(obj, level=0):
    """Count the maximum nesting level in a JSON object"""
    if isinstance(obj, dict):
        if not obj:
            return level
        return max(_count_json_nesting(v, level + 1) for v in obj.values())
    elif isinstance(obj, list):
        if not obj:
            return level
        return max(_count_json_nesting(item, level + 1) for item in obj)
    else:
        return level

def _count_json_elements(obj):
    """Count total elements in a JSON structure"""
    if isinstance(obj, dict):
        return sum(_count_json_elements(v) for v in obj.values()) + len(obj)
    elif isinstance(obj, list):
        return sum(_count_json_elements(item) for item in obj) + len(obj)
    else:
        return 1

def _analyze_json_types(obj, max_depth=3, current_depth=0):
    """Analyze data types in JSON structure"""
    if current_depth >= max_depth:
        return type(obj).__name__
        
    if isinstance(obj, dict):
        return {k: _analyze_json_types(v, max_depth, current_depth + 1) for k, v in list(obj.items())[:5]}  # Limit to first 5 keys
    elif isinstance(obj, list):
        if obj:
            return [_analyze_json_types(obj[0], max_depth, current_depth + 1)]  # Analyze first element as example
        else:
            return []
    else:
        return type(obj).__name__

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
        include_deleted=include_deleted
    )
    
    logger.info(f"DataSharingService returned {len(datasets)} datasets")
    
    # Filter out deleted datasets unless explicitly requested
    if not include_deleted:
        original_count = len(datasets)
        datasets = [d for d in datasets if not d.is_deleted]
        filtered_count = len(datasets)
        logger.info(f"Filtered out deleted datasets: {original_count} -> {filtered_count}")
    
    # Apply additional filters
    filtered_datasets = []
    for dataset in datasets:
        # Filter by type if specified
        if dataset_type and dataset.type != dataset_type:
            continue
        filtered_datasets.append(dataset)
    
    logger.info(f"Final result: {len(filtered_datasets)} datasets after all filtering")
    
    # Apply pagination
    result = filtered_datasets[skip:skip + limit]
    logger.info(f"Returning {len(result)} datasets after pagination (skip={skip}, limit={limit})")
    
    return result

@router.post("/", response_model=DatasetResponse, status_code=201)
async def create_dataset(
    dataset_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new dataset within the user's organization."""
    # First validate the input data (422 errors)
    name = dataset_data.get("name")
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dataset name is required"
        )
    
    # Then check authorization (403 errors)
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must be part of an organization to create datasets"
        )
    
    # Map data_format to type if provided
    data_format = dataset_data.get("data_format", "CSV")
    dataset_type = DatasetType.CSV if data_format.upper() == "CSV" else DatasetType.JSON
    
    # Extract sharing level
    sharing_level_str = dataset_data.get("sharing_level", "private")
    try:
        # Handle both 'private' and 'PRIVATE' formats
        normalized_level = sharing_level_str.lower() if isinstance(sharing_level_str, str) else "private"
        sharing_level = DataSharingLevel(normalized_level)
    except ValueError:
        sharing_level = DataSharingLevel.PRIVATE
    
    # Build schema info from test data
    schema_info = {}
    if "columns" in dataset_data:
        schema_info["columns"] = dataset_data["columns"]
    if "row_count" in dataset_data:
        schema_info["row_count"] = dataset_data["row_count"]
    
    # Generate basic metadata for programmatically created datasets
    columns = dataset_data.get("columns", [])
    row_count = dataset_data.get("row_count", 0)
    
    schema_metadata = {
        "columns": columns,
        "data_types": {},
        "programmatically_created": True,
        "created_at": datetime.utcnow().isoformat()
    }
    
    quality_metrics = {
        "overall_score": 0.9,  # Default good score for programmatic creation
        "completeness": 1.0,
        "consistency": 1.0,
        "accuracy": 0.9,
        "issues": [],
        "last_analyzed": datetime.utcnow().isoformat()
    }
    
    column_statistics = {}
    for col in columns:
        column_statistics[col] = {
            "data_type": "unknown",
            "non_null_count": row_count,
            "null_count": 0,
            "unique_count": "unknown"
        }
    
    preview_data = {
        "headers": columns,
        "sample_rows": [],
        "total_rows": row_count,
        "is_sample": False,
        "preview_generated_at": datetime.utcnow().isoformat()
    }

    # Create dataset with organization context
    db_dataset = Dataset(
        name=name,
        description=dataset_data.get("description"),
        type=dataset_type,
        status=DatasetStatus.ACTIVE,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
        sharing_level=sharing_level,
        source_url=dataset_data.get("source_url"),
        connector_id=dataset_data.get("connector_id"),
        schema_info=schema_info if schema_info else None,
        allow_download=True,
        allow_api_access=True,
        row_count=row_count,
        column_count=len(columns),
        # Enhanced metadata fields
        schema_metadata=schema_metadata,
        quality_metrics=quality_metrics,
        column_statistics=column_statistics,
        preview_data=preview_data,
        download_count=0,
        last_downloaded_at=None
    )
    
    db.add(db_dataset)
    db.commit()
    db.refresh(db_dataset)
    
    return db_dataset

@router.get("/{dataset_id}")
async def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific dataset if accessible to the user."""
    logger.info(f"🔍 GET dataset {dataset_id} called by user {current_user.id}")
    data_service = DataSharingService(db)

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        logger.warning(f"❌ Dataset {dataset_id} not found in database")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )

    logger.info(f"✅ Found dataset {dataset_id}: name='{dataset.name}', type={dataset.type}, status={dataset.status}")

    # Check access permissions
    if not data_service.can_access_dataset(current_user, dataset):
        logger.warning(f"❌ User {current_user.id} denied access to dataset {dataset_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this dataset"
        )

    # Log access
    data_service.log_access(
        user=current_user,
        dataset=dataset,
        access_type="view"
    )

    # Build response with files included
    from app.models.dataset import DatasetFile
    from app.models.file_handler import FileUpload

    # Get files from both DatasetFile and FileUpload tables
    dataset_files = db.query(DatasetFile).filter(
        DatasetFile.dataset_id == dataset_id,
        DatasetFile.is_deleted == False
    ).all()

    # If no DatasetFile records, check FileUpload (MindsDB agent files)
    if not dataset_files:
        file_uploads = db.query(FileUpload).filter(
            FileUpload.dataset_id == dataset_id
        ).all()
        dataset_files = file_uploads

    # Convert dataset to dict and add files
    from sqlalchemy.inspection import inspect
    dataset_dict = {c.key: getattr(dataset, c.key) for c in inspect(dataset).mapper.column_attrs}

    # Add files with proper field mapping
    dataset_dict['files'] = []
    for f in dataset_files:
        file_dict = {
            'id': f.id,
            'filename': getattr(f, 'filename', None) or getattr(f, 'original_filename', 'unknown'),
            'file_path': f.file_path,
            'file_size': getattr(f, 'file_size', 0),
            'file_type': getattr(f, 'file_type', None),
            'mime_type': getattr(f, 'mime_type', None),
            'created_at': getattr(f, 'created_at', None).isoformat() if hasattr(f, 'created_at') and getattr(f, 'created_at') else None
        }
        dataset_dict['files'].append(file_dict)

    # Add computed fields
    dataset_dict['is_multi_file'] = len(dataset_files) > 1
    dataset_dict['total_files_count'] = len(dataset_files)

    # Convert datetime objects to ISO format
    for key in ['created_at', 'updated_at', 'last_accessed', 'deleted_at', 'last_downloaded_at', 'ai_processed_at', 'share_expires_at', 'agent_created_at', 'agent_last_updated']:
        if key in dataset_dict and dataset_dict[key]:
            dataset_dict[key] = dataset_dict[key].isoformat()

    logger.info(f"📤 Returning dataset {dataset_id} with {len(dataset_files)} files to user {current_user.id}")
    return dataset_dict

@router.put("/{dataset_id}", response_model=DatasetResponse)
@router.put("/{dataset_id}/metadata", response_model=DatasetResponse)
async def update_dataset_metadata(
    dataset_id: int,
    metadata_update: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update dataset metadata including schema, description, and custom fields."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Check permissions
    data_service = DataSharingService(db)
    if not data_service.can_access_dataset(current_user, dataset):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this dataset"
        )
    
    # Only owner or admin can update metadata
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        if current_user.role not in ["owner", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only dataset owner or organization admin can update metadata"
            )
    
    # Update allowed metadata fields
    allowed_fields = [
        'name', 'description', 'schema_info', 'file_metadata', 'content_preview',
        'ai_summary', 'ai_insights', 'ai_recommendations', 'sharing_level',
        'public_share_enabled', 'ai_chat_enabled', 'allow_download'
    ]
    
    updated_fields = []
    for field, value in metadata_update.items():
        if field in allowed_fields:
            if field == 'sharing_level':
                # Convert string to enum properly
                try:
                    if isinstance(value, str):
                        # Handle both 'private' and 'PRIVATE' formats
                        normalized_value = value.lower()
                        value = DataSharingLevel(normalized_value)
                    elif not isinstance(value, DataSharingLevel):
                        continue
                except ValueError:
                    continue
            
            setattr(dataset, field, value)
            updated_fields.append(field)
    
    # Update timestamp
    dataset.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(dataset)
    
    # Log the metadata update
    data_service.log_access(
        user=current_user,
        dataset=dataset,
        access_type="metadata_update"
    )
    
    return dataset

@router.get("/{dataset_id}/metadata/detailed", response_model=Dict[str, Any])
async def get_detailed_dataset_metadata(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive dataset metadata including schema, statistics, and AI insights."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Check access permissions
    data_service = DataSharingService(db)
    if not data_service.can_access_dataset(current_user, dataset):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this dataset"
        )
    
    # Compile comprehensive metadata
    metadata = {
        "basic_info": {
            "id": dataset.id,
            "name": dataset.name,
            "description": dataset.description,
            "type": dataset.type,
            "status": dataset.status,
            "created_at": dataset.created_at,
            "updated_at": dataset.updated_at
        },
        "ownership": {
            "owner_id": dataset.owner_id,
            "owner_name": dataset.owner.full_name if dataset.owner else None,
            "organization_id": dataset.organization_id,
            "organization_name": dataset.organization.name if dataset.organization else None
        },
        "data_structure": {
            "size_bytes": dataset.size_bytes,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
            "schema_info": dataset.schema_info,
            "file_metadata": dataset.file_metadata
        },
        "ai_processing": {
            "ai_processing_status": dataset.ai_processing_status,
            "ai_summary": dataset.ai_summary,
            "ai_insights": dataset.ai_insights,
            "ai_recommendations": dataset.ai_recommendations,
            "ai_chat_enabled": dataset.ai_chat_enabled,
            "chat_model_name": dataset.chat_model_name,
            "chat_context": dataset.chat_context
        },
        "sharing_settings": {
            "sharing_level": dataset.sharing_level,
            "public_share_enabled": dataset.public_share_enabled,
            "share_token": dataset.share_token if dataset.public_share_enabled else None,
            # Expiration functionality removed
            "share_view_count": dataset.share_view_count,
            "allow_download": dataset.allow_download
        },
        "data_source": {
            "source_url": dataset.source_url,
            "connection_params": dataset.connection_params,
            "connector_id": dataset.connector_id,
            "mindsdb_table_name": dataset.mindsdb_table_name,
            "mindsdb_database": dataset.mindsdb_database
        },
        "content_preview": dataset.content_preview[:500] if dataset.content_preview else None,
        "statistics": {
            "access_count": getattr(dataset, 'access_count', 0),
            "download_count": getattr(dataset, 'download_count', 0),
            "last_accessed": getattr(dataset, 'last_accessed_at', None),
            "last_downloaded": getattr(dataset, 'last_downloaded_at', None)
        }
    }
    
    # Add connector information if available
    if dataset.connector_id:
        connector = db.query(DatabaseConnector).filter(
            DatabaseConnector.id == dataset.connector_id
        ).first()
        if connector:
            metadata["connector_info"] = {
                "name": connector.name,
                "description": connector.description,
                "type": connector.type,
                "host": connector.host,
                "port": connector.port,
                "status": connector.status
            }
    
    # Log the metadata access
    data_service.log_access(
        user=current_user,
        dataset=dataset,
        access_type="metadata_view"
    )
    
    return metadata

@router.post("/{dataset_id}/edit", response_model=Dict[str, Any])
async def edit_dataset_content(
    dataset_id: int,
    edit_request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Edit dataset content and structure (for supported dataset types)."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Check permissions - only owner or admin can edit
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        if current_user.role not in ["owner", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only dataset owner or organization admin can edit content"
            )
    
    # Check if dataset type supports editing
    editable_types = [DatasetType.CSV, DatasetType.JSON, DatasetType.TXT]
    if dataset.type not in editable_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset type {dataset.type} does not support content editing"
        )
    
    edit_type = edit_request.get("edit_type")
    
    if edit_type == "update_content":
        # Update entire content
        new_content = edit_request.get("content")
        if not new_content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Content is required for content update"
            )
        
        # Update content preview and metadata
        dataset.content_preview = new_content[:1000] + "..." if len(new_content) > 1000 else new_content
        dataset.size_bytes = len(new_content.encode('utf-8'))
        
        # Update schema info based on type
        if dataset.type == DatasetType.CSV:
            lines = new_content.strip().split('\n')
            dataset.row_count = len(lines) - 1 if lines else 0
            dataset.column_count = len(lines[0].split(',')) if lines else 0
        elif dataset.type == DatasetType.JSON:
            try:
                json_data = json.loads(new_content)
                if isinstance(json_data, list):
                    dataset.row_count = len(json_data)
                dataset.schema_info = {"type": "json", "structure": type(json_data).__name__}
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON content"
                )
        elif dataset.type == DatasetType.TXT:
            lines = new_content.split('\n')
            dataset.schema_info = {
                "type": "text",
                "line_count": len(lines),
                "word_count": len(new_content.split()),
                "character_count": len(new_content)
            }
    
    elif edit_type == "update_schema":
        # Update schema information
        new_schema = edit_request.get("schema_info")
        if new_schema:
            dataset.schema_info = new_schema
    
    elif edit_type == "update_metadata":
        # Update file metadata
        new_metadata = edit_request.get("file_metadata")
        if new_metadata:
            dataset.file_metadata = new_metadata
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid edit_type. Supported types: update_content, update_schema, update_metadata"
        )
    
    # Update timestamp
    dataset.updated_at = datetime.utcnow()
    
    # Reset AI processing status to trigger re-analysis
    dataset.ai_processing_status = AIProcessingStatus.NOT_PROCESSED
    
    db.commit()
    db.refresh(dataset)
    
    # Log the edit action
    data_service = DataSharingService(db)
    data_service.log_access(
        user=current_user,
        dataset=dataset,
        access_type="content_edit",
        details={"edit_type": edit_type}
    )
    
    return {
        "success": True,
        "message": f"Dataset {edit_type} completed successfully",
        "updated_at": dataset.updated_at,
        "ai_processing_status": dataset.ai_processing_status
    }


@router.put("/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: int,
    dataset_update: DatasetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a dataset (only owner can update)."""
    logger.info(f"Update dataset {dataset_id} called by user {current_user.id} with data: {dataset_update}")
    
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Only owner or org admin can update
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        if current_user.role not in ["owner", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only dataset owner or organization admin can update"
            )
    
    # Update fields with proper type conversion
    updated_fields = []
    for field, value in dataset_update.dict(exclude_unset=True).items():
        if field == 'sharing_level':
            # Convert string to enum properly
            try:
                if isinstance(value, str):
                    # Handle both 'private' and 'PRIVATE' formats
                    normalized_value = value.lower()
                    value = DataSharingLevel(normalized_value)
                    logger.info(f"Converted sharing_level '{value}' to enum {value}")
                elif not isinstance(value, DataSharingLevel):
                    logger.warning(f"Invalid sharing level type: {type(value)}")
                    continue
            except ValueError:
                logger.warning(f"Invalid sharing level value: {value}")
                continue
        setattr(dataset, field, value)
        updated_fields.append(field)
    
    # Update timestamp
    dataset.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(dataset)
    
    logger.info(f"Successfully updated dataset {dataset_id} fields: {updated_fields}")
    
    return dataset

@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: int,
    force_delete: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Soft delete a dataset (only owner can delete). Use force_delete=true for hard delete."""
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.is_deleted == False
    ).first()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found or already deleted"
        )
    
    # Check if user is owner or admin
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only delete your own datasets"
        )
    
    # Clean up associated MindsDB agents first
    try:
        if dataset.agent_name:
            mindsdb_service.delete_agent(dataset.agent_name)
            logger.info(f"Agent {dataset.agent_name} deleted")
    except Exception as e:
        logger.warning(f"Agent cleanup failed: {e}")

    # Clean up MindsDB uploaded files, database connectors, and S3 files
    try:
        from app.models.file_handler import FileUpload
        file_uploads = db.query(FileUpload).filter(
            FileUpload.dataset_id == dataset_id
        ).all()

        for file_upload in file_uploads:
            # Delete file from MindsDB files database
            mindsdb_file_name = f"dataset_{file_upload.dataset_id}_file_{file_upload.id}"
            mindsdb_service.delete_file_from_mindsdb(mindsdb_file_name)

            # Delete database connector
            connector_name = f"file_db_{file_upload.id}"
            mindsdb_service.delete_database_connector(connector_name)

            # Delete file from S3/MinIO storage
            if file_upload.file_path:
                try:
                    success = await storage_service.delete_dataset_file(file_upload.file_path)
                    if success:
                        logger.info(f"✅ Deleted file from S3: {file_upload.file_path}")
                    else:
                        logger.warning(f"⚠️  Failed to delete from S3: {file_upload.file_path}")
                except Exception as s3_error:
                    logger.warning(f"⚠️  S3 deletion error for {file_upload.file_path}: {s3_error}")

        logger.info(f"✅ Cleaned up {len(file_uploads)} MindsDB files, connectors, and S3 files")
    except Exception as e:
        logger.warning(f"MindsDB and S3 file cleanup failed: {e}")
    
    # Clean up all associated files (for both single and multi-file datasets)
    file_deletion_results = []
    
    # First, check if this dataset has files in the DatasetFile table
    from app.models.dataset import DatasetFile
    dataset_files = db.query(DatasetFile).filter(
        DatasetFile.dataset_id == dataset_id,
        DatasetFile.is_deleted == False
    ).all()
    
    if dataset_files:
        # Delete all files from DatasetFile records (both S3 and local)
        logger.info(f"Found {len(dataset_files)} files in DatasetFile table for dataset {dataset_id}")
        for dataset_file in dataset_files:
            try:
                deleted_from_storage = False

                # Try to delete from S3/MinIO storage first
                if dataset_file.file_path:
                    try:
                        success = await storage_service.delete_dataset_file(dataset_file.file_path)
                        if success:
                            logger.info(f"✅ Deleted file from S3/storage: {dataset_file.file_path}")
                            deleted_from_storage = True
                            file_deletion_results.append({
                                "file": dataset_file.filename,
                                "success": True,
                                "method": "storage_service_s3"
                            })
                        else:
                            logger.warning(f"⚠️  Failed to delete from storage: {dataset_file.file_path}")
                    except Exception as storage_error:
                        logger.warning(f"⚠️  Storage deletion error: {storage_error}")

                # Fallback to local file deletion if storage deletion failed
                if not deleted_from_storage and dataset_file.file_path and os.path.exists(dataset_file.file_path):
                    os.remove(dataset_file.file_path)
                    logger.info(f"✅ Deleted local file: {dataset_file.file_path}")
                    file_deletion_results.append({
                        "file": dataset_file.filename,
                        "success": True,
                        "method": "local_file_deletion"
                    })
                elif not deleted_from_storage:
                    logger.warning(f"⚠️  File not found in storage or locally: {dataset_file.file_path}")
                    file_deletion_results.append({
                        "file": dataset_file.filename,
                        "success": False,
                        "error": "File not found in storage or locally"
                    })

                # Mark the DatasetFile record as deleted
                dataset_file.is_deleted = True
                dataset_file.deleted_at = datetime.utcnow()

            except Exception as e:
                logger.error(f"❌ Error deleting file {dataset_file.filename}: {e}")
                file_deletion_results.append({
                    "file": dataset_file.filename,
                    "success": False,
                    "error": str(e)
                })
    
    # Also check legacy file_path and source_url fields for backward compatibility
    elif dataset.file_path or dataset.source_url:
        try:
            file_path_to_delete = None
            
            # Determine which file path to use for deletion
            if dataset.file_path and os.path.exists(dataset.file_path):
                # Use absolute file path if it exists
                file_path_to_delete = dataset.file_path
                logger.info(f"Deleting legacy file using absolute path: {file_path_to_delete}")
                os.remove(file_path_to_delete)
                file_deletion_results.append({
                    "file": os.path.basename(file_path_to_delete),
                    "success": True,
                    "method": "direct_file_deletion"
                })
            elif dataset.source_url and not dataset.source_url.startswith('http'):
                # Use relative path through storage service for uploaded files
                file_path_to_delete = dataset.source_url
                logger.info(f"Deleting legacy file using storage service: {file_path_to_delete}")
                success = await storage_service.delete_dataset_file(file_path_to_delete)
                file_deletion_results.append({
                    "file": file_path_to_delete,
                    "success": success,
                    "method": "storage_service"
                })
            else:
                logger.info(f"Dataset {dataset_id} has no local file to delete (connector-based or external URL)")
                file_deletion_results.append({
                    "message": "No local file to delete",
                    "success": True,
                    "method": "no_file"
                })
                
        except Exception as e:
            logger.error(f"Error deleting legacy file for dataset {dataset_id}: {e}")
            file_deletion_results.append({
                "file": "legacy_file",
                "success": False,
                "error": str(e)
            })
    else:
        logger.info(f"Dataset {dataset_id} has no files to delete")
        file_deletion_results.append({
            "message": "No files to delete",
            "success": True,
            "method": "no_file"
        })
    
    # Summarize file deletion results
    successful_deletions = sum(1 for r in file_deletion_results if r.get("success"))
    failed_deletions = len(file_deletion_results) - successful_deletions
    
    file_deletion_result = {
        "total_files": len(file_deletion_results),
        "successful": successful_deletions,
        "failed": failed_deletions,
        "details": file_deletion_results
    }
    
    if force_delete and current_user.is_superuser:
        # Hard delete (only for superusers) - need to clean up related records first
        logger.info(f"Performing hard delete of dataset {dataset_id}")
        
        # Delete related records that have NOT NULL foreign keys
        from app.models.dataset import DatasetAccessLog, DatasetDownload, DatasetModel, DatasetChatSession, ChatMessage, DatasetShareAccess, DatasetFile
        
        # Delete chat messages first (they reference chat sessions)
        chat_sessions = db.query(DatasetChatSession).filter(DatasetChatSession.dataset_id == dataset_id).all()
        for session in chat_sessions:
            db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
        
        # Delete chat sessions
        db.query(DatasetChatSession).filter(DatasetChatSession.dataset_id == dataset_id).delete()
        
        # Delete access logs
        db.query(DatasetAccessLog).filter(DatasetAccessLog.dataset_id == dataset_id).delete()
        
        # Delete downloads
        db.query(DatasetDownload).filter(DatasetDownload.dataset_id == dataset_id).delete()
        
        # Delete models
        db.query(DatasetModel).filter(DatasetModel.dataset_id == dataset_id).delete()
        
        # Delete share accesses
        db.query(DatasetShareAccess).filter(DatasetShareAccess.dataset_id == dataset_id).delete()
        
        # Delete DatasetFile records (for multi-file datasets)
        db.query(DatasetFile).filter(DatasetFile.dataset_id == dataset_id).delete()
        
        # Now delete the dataset itself
        db.delete(dataset)
        db.commit()
        
        logger.info(f"Successfully hard deleted dataset {dataset_id} and all related records")
        return {
            "message": "Dataset permanently deleted",
            "dataset_id": dataset_id,
            "deletion_type": "hard",
            "file_deletion": file_deletion_result
        }
    else:
        # Soft delete
        # Disable sharing when dataset is deleted
        if dataset.public_share_enabled:
            dataset.public_share_enabled = False
            dataset.share_token = None
            # Expiration functionality removed - share links no longer expire
            dataset.share_password = None
            dataset.ai_chat_enabled = False
            logger.info(f"Disabled sharing for deleted dataset {dataset_id}")
        
        dataset.soft_delete(current_user.id)
        
        # Also disable any related proxy connectors
        try:
            from app.models.proxy_connector import ProxyConnector
            proxy_connectors = db.query(ProxyConnector).filter(
                ProxyConnector.name == dataset.name,
                ProxyConnector.organization_id == dataset.organization_id,
                ProxyConnector.is_active == True
            ).all()
            
            for proxy_connector in proxy_connectors:
                proxy_connector.is_active = False
                logger.info(f"Disabled proxy connector {proxy_connector.proxy_id} for deleted dataset {dataset_id}")
                
        except Exception as e:
            logger.warning(f"Failed to disable proxy connectors for dataset {dataset_id}: {e}")
        
        db.commit()
        return {
            "message": "Dataset deleted successfully",
            "dataset_id": dataset_id,
            "deletion_type": "soft",
            "deleted_at": dataset.deleted_at,
            "file_deletion": file_deletion_result
        }


@router.patch("/{dataset_id}/activate")
async def activate_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Activate a dataset."""
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.is_deleted == False
    ).first()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found or deleted"
        )
    
    # Check permissions
    data_service = DataSharingService(db)
    if not data_service.can_access_dataset(current_user, dataset) and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this dataset"
        )
    
    dataset.activate()
    db.commit()
    
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
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.is_deleted == False
    ).first()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found or deleted"
        )
    
    # Check if user is owner or admin
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only deactivate your own datasets"
        )
    
    dataset.deactivate()
    db.commit()
    
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload single or multiple dataset files."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must be part of an organization to upload datasets"
        )
    
    # Determine if single or multiple file upload
    upload_files = []
    if files:  # Multiple files
        upload_files = files
        if file:  # Also include single file if provided
            upload_files.append(file)
    elif file:  # Single file only
        upload_files = [file]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )
    
    is_multi_file = len(upload_files) > 1
    
    # Convert sharing level string to enum
    try:
        # Handle both 'private' and 'PRIVATE' formats
        normalized_level = sharing_level.lower() if isinstance(sharing_level, str) else "private"
        sharing_level_enum = DataSharingLevel(normalized_level)
    except ValueError:
        sharing_level_enum = DataSharingLevel.PRIVATE
    
    # Validate all files
    total_size = 0
    for upload_file in upload_files:
        if not upload_file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All files must have valid names"
            )
        
        file_extension = upload_file.filename.split('.')[-1].lower()
        from app.core.config import settings
        allowed_extensions = settings.get_allowed_file_types()
        
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type '{file_extension}' in '{upload_file.filename}'. Supported formats: {', '.join(allowed_extensions).upper()}"
            )
        
        # Get file size (will be read later)
        content = await upload_file.read()
        await upload_file.seek(0)  # Reset file pointer
        total_size += len(content)
    
    # Determine dataset name and primary file info
    primary_file = upload_files[0]
    dataset_name = name or (
        primary_file.filename.rsplit('.', 1)[0] if len(upload_files) == 1 
        else f"Multi-file dataset ({len(upload_files)} files)"
    )
    
    # Determine dataset type from primary file
    primary_extension = primary_file.filename.split('.')[-1].lower()
    if primary_extension == 'csv':
        dataset_type = DatasetType.CSV
    elif primary_extension == 'json':
        dataset_type = DatasetType.JSON
    elif primary_extension in ['xlsx', 'xls']:
        dataset_type = DatasetType.EXCEL
    elif primary_extension == 'pdf':
        dataset_type = DatasetType.PDF
    elif primary_extension.lower() in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'svg']:
        dataset_type = DatasetType.IMAGE
    else:
        dataset_type = DatasetType.TXT
    
    # Create dataset record first to get ID for storage
    temp_dataset = Dataset(
        name=dataset_name,
        description=description,
        type=dataset_type,
        status=DatasetStatus.PROCESSING,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
        sharing_level=sharing_level_enum,
        size_bytes=total_size,
        allow_download=True,
        allow_api_access=True,
        is_multi_file_dataset=is_multi_file,
        total_files_count=len(upload_files)
    )
    
    db.add(temp_dataset)
    db.commit()
    db.refresh(temp_dataset)
    
    # Store files using storage service
    stored_files = []
    try:
        from app.models.dataset import DatasetFile
        
        for i, upload_file in enumerate(upload_files):
            # Read file content
            content = await upload_file.read()
            file_size = len(content)
            
            # Store file
            storage_result = await storage_service.store_dataset_file(
                file_content=content,
                original_filename=upload_file.filename,
                dataset_id=temp_dataset.id,
                organization_id=current_user.organization_id
            )
            
            # Create DatasetFile record
            file_extension = upload_file.filename.split('.')[-1].lower()
            dataset_file = DatasetFile(
                dataset_id=temp_dataset.id,
                filename=upload_file.filename,
                file_path=storage_result['file_path'],
                relative_path=storage_result['relative_path'],
                file_size=file_size,
                file_type=file_extension,
                mime_type=upload_file.content_type,
                is_primary=(i == 0),  # First file is primary
                file_order=i,
                is_processed=False
            )
            
            db.add(dataset_file)
            stored_files.append({
                'file_record': dataset_file,
                'storage_result': storage_result,
                'content': content,
                'upload_file': upload_file
            })
        
        # Commit file records
        db.commit()

        # Create FileUpload records for MindsDB agent compatibility
        from app.models.file_handler import FileUpload
        import hashlib

        for stored_file_info in stored_files:
            dataset_file = stored_file_info['file_record']

            # Generate file hash
            file_hash = hashlib.md5(dataset_file.filename.encode()).hexdigest()

            # Create FileUpload record
            file_upload = FileUpload(
                dataset_id=temp_dataset.id,
                user_id=current_user.id,
                organization_id=current_user.organization_id,
                original_filename=dataset_file.filename,
                file_path=dataset_file.file_path,
                file_size=dataset_file.file_size,
                file_hash=file_hash,
                mime_type=dataset_file.mime_type,
                file_type=dataset_file.file_type,
                upload_status='completed',
                mindsdb_file_id=None,
                created_at=datetime.utcnow()
            )
            db.add(file_upload)

        # Commit FileUpload records
        db.commit()

        logger.info(f"✅ {len(stored_files)} files stored successfully for dataset {temp_dataset.id}")
        logger.info(f"✅ Created {len(stored_files)} FileUpload records for MindsDB integration")
        
    except Exception as e:
        # Clean up dataset record if storage fails
        try:
            db.rollback()  # Rollback any pending transaction
            db.delete(temp_dataset)
            db.commit()
        except Exception as cleanup_error:
            logger.error(f"❌ Error during cleanup: {cleanup_error}")
            db.rollback()  # Ensure we rollback the failed cleanup transaction
        
        logger.error(f"❌ File storage failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store files: {str(e)}"
        )
    
    # Process primary file for metadata (if it's processable)
    primary_file_info = stored_files[0]
    primary_content = primary_file_info['content']
    primary_upload_file = primary_file_info['upload_file']
    primary_extension = primary_file_info['file_record'].file_type
    
    # Process file content and extract metadata
    file_metadata = {}
    content_preview = None
    row_count = None
    column_count = None
    
    # Initialize enhanced metadata fields for all file types
    schema_metadata = {}
    quality_metrics = {}
    column_statistics = {}
    preview_data = {}
    
    # Save file temporarily for processing
    import tempfile
    import os
    
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        # Process different file types
        if file_extension in ["pdf", "json"]:
            try:
                content_result = mindsdb_service.process_file_content(temp_file_path, file_extension)
                if content_result.get("success"):
                    file_metadata = content_result.get("metadata", {})
                    content_preview = content_result["content"][:500] + "..." if len(content_result["content"]) > 500 else content_result["content"]
                    
                    # Extract counts for metadata
                    if file_extension == "json":
                        row_count = file_metadata.get("element_count")
                        column_count = 1  # JSON treated as single complex column
                        
                        # Generate enhanced metadata for JSON
                        try:
                            import json as json_module
                            with open(temp_file_path, 'r', encoding='utf-8') as f:
                                json_data = json_module.load(f)
                            
                            # Enhanced schema metadata for JSON
                            schema_metadata = {
                                'file_type': 'json',
                                'original_filename': file.filename,
                                'encoding': 'utf-8',
                                'structure': {
                                    'type': type(json_data).__name__,
                                    'is_array': isinstance(json_data, list),
                                    'nested_levels': _count_json_nesting(json_data),
                                    'total_elements': _count_json_elements(json_data)
                                },
                                'data_types': _analyze_json_types(json_data),
                                'sample_data': str(json_data)[:200] + "..." if len(str(json_data)) > 200 else str(json_data)
                            }
                            
                            # Enhanced quality metrics for JSON
                            quality_metrics = {
                                'overall_score': 95,  # JSON files are typically well-structured
                                'completeness': 100,  # JSON files don't have missing values in the same way
                                'consistency': 95,
                                'accuracy': 90,
                                'issues': [],
                                'last_analyzed': datetime.utcnow().isoformat()
                            }
                            
                            # Enhanced preview data for JSON
                            preview_data = {
                                'type': 'json',
                                'structure_preview': str(json_data)[:500] + "..." if len(str(json_data)) > 500 else str(json_data),
                                'total_elements': _count_json_elements(json_data),
                                'is_sample': len(str(json_data)) > 500,
                                'preview_generated_at': datetime.utcnow().isoformat()
                            }
                            
                        except Exception as json_e:
                            logger.warning(f"Could not generate enhanced JSON metadata: {json_e}")
                            # Fallback metadata
                            schema_metadata = {'file_type': 'json', 'error': 'Could not parse JSON structure'}
                            quality_metrics = {'overall_score': 50, 'issues': ['JSON parsing failed']}
                            preview_data = {'type': 'json', 'error': 'Preview generation failed'}
                    
                    logger.info(f"Successfully processed {file_extension} file: {file_metadata}")
            except Exception as e:
                logger.warning(f"Could not process {file_extension} file content: {e}")
        
        # For CSV files, try to get basic info
        elif file_extension == "csv":
            try:
                import pandas as pd
                df = pd.read_csv(temp_file_path)
                file_metadata = {
                    "row_count": len(df),
                    "column_count": len(df.columns),
                    "columns": df.columns.tolist(),
                    "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()}
                }
                content_preview = df.head(3).to_string()
                row_count = len(df)
                column_count = len(df.columns)
                logger.info(f"Successfully analyzed CSV file: {file_metadata}")
            except Exception as e:
                logger.warning(f"Could not analyze CSV file: {e}")
    
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

    # Generate enhanced metadata for files that haven't been processed yet
    # (CSV files and JSON files are already processed above)
    if not schema_metadata and file_metadata:
        # Enhanced schema metadata
        schema_metadata = {
            "file_type": file_extension,
            "original_filename": primary_upload_file.filename,
            "encoding": "utf-8",  # Default assumption
            "structure": file_metadata.get("structure", {}),
            "columns": file_metadata.get("columns", []),
            "data_types": file_metadata.get("dtypes", {}),
            "sample_data": file_metadata.get("sample_data", [])
        }
        
        # Basic quality metrics
        quality_metrics = {
            "overall_score": 0.85,  # Default good score
            "completeness": 1.0 if row_count and row_count > 0 else 0.0,
            "consistency": 0.9,  # Default assumption
            "accuracy": 0.8,  # Default assumption
            "issues": [],
            "last_analyzed": datetime.utcnow().isoformat()
        }
        
        # Column statistics from file metadata
        if "column_stats" in file_metadata:
            column_statistics = file_metadata["column_stats"]
        elif "dtypes" in file_metadata:
            # Generate basic column stats
            column_statistics = {}
            for col, dtype in file_metadata["dtypes"].items():
                column_statistics[col] = {
                    "data_type": dtype,
                    "non_null_count": row_count or 0,
                    "null_count": 0,
                    "unique_count": "unknown"
                }
        
        # Preview data structure
        preview_data = {
            "headers": file_metadata.get("columns", []),
            "sample_rows": file_metadata.get("sample_data", [])[:10],  # First 10 rows
            "total_rows": row_count or 0,
            "is_sample": True,
            "preview_generated_at": datetime.utcnow().isoformat()
        }

    # Update the temporary dataset with complete information
    temp_dataset.name = dataset_name
    temp_dataset.description = description
    temp_dataset.type = dataset_type
    temp_dataset.status = DatasetStatus.ACTIVE
    temp_dataset.size_bytes = file_size
    temp_dataset.source_url = storage_result['relative_path']  # Storage service path
    temp_dataset.file_path = storage_result['file_path']  # Actual file storage path
    temp_dataset.row_count = row_count
    temp_dataset.column_count = column_count
    temp_dataset.file_metadata = file_metadata
    temp_dataset.content_preview = content_preview
    # New enhanced metadata fields
    temp_dataset.schema_metadata = schema_metadata
    temp_dataset.quality_metrics = quality_metrics
    temp_dataset.column_statistics = column_statistics
    temp_dataset.preview_data = preview_data
    temp_dataset.download_count = 0  # Initialize download count
    temp_dataset.last_downloaded_at = None
    
    # Use the updated dataset
    db_dataset = temp_dataset
    
    db.add(db_dataset)
    db.commit()
    db.refresh(db_dataset)

    # No longer creating ML models automatically - agent-based chat works directly with files
    # Agent-based architecture uses MindsDB agents that query files directly via databases
    logger.info(f"✅ Dataset {db_dataset.id} created successfully. Agent-based chat will handle queries on-demand.")
    
    # Automatically create share link if sharing level is not private
    if sharing_level_enum != DataSharingLevel.PRIVATE:
        try:
            from app.services.data_sharing import DataSharingService
            sharing_service = DataSharingService(db)
            
            # Create share link with chat enabled by default
            share_result = sharing_service.create_share_link(
                dataset_id=db_dataset.id,
                user_id=current_user.id,
                password=None,  # No password by default
                enable_chat=True  # Enable chat by default
            )
            
            logger.info(f"Auto-created share link for dataset {db_dataset.id} with sharing level {sharing_level_enum.value}")
            
            # Refresh dataset to get updated share info
            db.refresh(db_dataset)
            
        except Exception as e:
            logger.warning(f"Could not auto-create share link for dataset {db_dataset.id}: {e}")
            # Don't fail the upload if share link creation fails
    
    # Prepare comprehensive response
    response_data = {
        "message": "Dataset uploaded successfully",
        "dataset": db_dataset,
        "agent_based_chat": True  # Using agent-based architecture
    }

    # AI chat is always available with agent-based architecture
    response_data["ai_chat_available"] = True
    response_data["ai_features"] = {
        "chat_enabled": True,
        "model_ready": True,  # Agent creates resources on-demand
        "architecture": "agent_based",
        "chat_endpoint": f"/api/datasets/{db_dataset.id}/chat",
        "supports_multi_file": db_dataset.is_multi_file_dataset
        }
    
    return response_data

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
    import io
    import zipfile
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
    has_access = data_sharing_service.can_access_dataset(current_user, dataset)

    if not has_access:
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

    # Get all files for this dataset from DatasetFile table
    dataset_files = db.query(DatasetFile).filter(
        DatasetFile.dataset_id == dataset_id,
        DatasetFile.is_deleted == False
    ).order_by(DatasetFile.file_order).all()

    # If no DatasetFile records, try FileUpload records (MindsDB agent files)
    if not dataset_files:
        from app.models.file_handler import FileUpload
        file_uploads = db.query(FileUpload).filter(
            FileUpload.dataset_id == dataset_id
        ).all()

        if file_uploads:
            # Use FileUpload records - they have the same fields we need
            logger.info(f"Found {len(file_uploads)} files in FileUpload table for dataset {dataset_id}")
            dataset_files = file_uploads
        elif dataset.file_path:
            # No multi-file records, try legacy single file download
            from app.services.download import DownloadService
            download_service = DownloadService(db)
            download_info = await download_service.initiate_download(
                dataset_id=dataset_id,
                user=current_user
            )
            return download_info
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No files found for this dataset"
            )

    # If only one file, download it directly
    if len(dataset_files) == 1:
        single_file = dataset_files[0]
        try:
            # Get file from storage
            file_response = await storage_service.get_file_stream(single_file.file_path)

            # Set proper filename (handle both DatasetFile.filename and FileUpload.original_filename)
            filename = getattr(single_file, 'filename', None) or getattr(single_file, 'original_filename', 'download')
            file_response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

            # Update dataset download statistics
            dataset.download_count = (dataset.download_count or 0) + 1
            dataset.last_downloaded_at = datetime.utcnow()
            db.commit()

            return file_response
        except Exception as e:
            logger.error(f"Failed to download single file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to download file: {str(e)}"
            )

    # Multiple files - create ZIP archive
    try:
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for dataset_file in dataset_files:
                try:
                    # Download file from storage
                    file_content = await storage_service.get_file_content(dataset_file.file_path)

                    # Get filename (handle both DatasetFile.filename and FileUpload.original_filename)
                    filename = getattr(dataset_file, 'filename', None) or getattr(dataset_file, 'original_filename', f'file_{dataset_file.id}')

                    # Add file to ZIP with original filename
                    zip_file.writestr(filename, file_content)
                    logger.info(f"Added {filename} to ZIP")

                except Exception as file_error:
                    filename = getattr(dataset_file, 'filename', None) or getattr(dataset_file, 'original_filename', 'unknown')
                    logger.error(f"Failed to add file {filename} to ZIP: {file_error}")
                    # Continue with other files
                    continue

        # Prepare ZIP for download
        zip_buffer.seek(0)

        # Update dataset download statistics
        dataset.download_count = (dataset.download_count or 0) + 1
        dataset.last_downloaded_at = datetime.utcnow()
        db.commit()

        # Create safe filename for ZIP
        safe_dataset_name = "".join(c for c in dataset.name if c.isalnum() or c in (' ', '-', '_')).strip()
        zip_filename = f"{safe_dataset_name}_files.zip"

        logger.info(f"✅ Created ZIP archive with {len(dataset_files)} files for dataset {dataset_id}")

        return StreamingResponse(
            io.BytesIO(zip_buffer.read()),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{zip_filename}"'
            }
        )

    except Exception as e:
        logger.error(f"Failed to create ZIP archive: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create ZIP archive: {str(e)}"
        )

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
    has_access = data_sharing_service.can_access_dataset(current_user, dataset)

    if not has_access:
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
        file_response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

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
        stats_response = {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "basic_stats": {
                "total_size_bytes": dataset.size_bytes,
                "row_count": dataset.row_count,
                "column_count": dataset.column_count,
                "file_type": dataset.type.value if dataset.type else "unknown",
                "sharing_level": dataset.sharing_level.value if dataset.sharing_level else "private",
                "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
                "updated_at": dataset.updated_at.isoformat() if dataset.updated_at else None,
                "last_accessed": dataset.last_accessed.isoformat() if dataset.last_accessed else None
            },
            "usage_stats": {
                "download_count": dataset.download_count or 0,
                "last_downloaded_at": dataset.last_downloaded_at.isoformat() if dataset.last_downloaded_at else None,
                "is_downloadable": dataset.allow_download,
                "api_access_enabled": dataset.allow_api_access,
                "ai_chat_enabled": dataset.allow_ai_chat
            }
        }
        
        # Include download statistics if requested and user is owner
        if include_downloads and (dataset.owner_id == current_user.id or current_user.is_superuser):
            from app.models.dataset import DatasetDownload
            
            # Get download statistics
            download_stats = db.query(DatasetDownload).filter(
                DatasetDownload.dataset_id == dataset_id
            ).all()
            
            successful_downloads = [d for d in download_stats if d.download_status == "completed"]
            failed_downloads = [d for d in download_stats if d.download_status == "failed"]
            
            stats_response["download_analytics"] = {
                "total_download_attempts": len(download_stats),
                "successful_downloads": len(successful_downloads),
                "failed_downloads": len(failed_downloads),
                "success_rate": len(successful_downloads) / len(download_stats) if download_stats else 0,
                "average_download_time": sum(d.download_duration_seconds or 0 for d in successful_downloads) / len(successful_downloads) if successful_downloads else 0,
                "popular_formats": {}
            }
            
            # Format popularity
            format_counts = {}
            for download in download_stats:
                format_counts[download.file_format] = format_counts.get(download.file_format, 0) + 1
            stats_response["download_analytics"]["popular_formats"] = format_counts
        
        # Include access logs if requested and user is owner
        if include_access_logs and (dataset.owner_id == current_user.id or current_user.is_superuser):
            from app.models.dataset import DatasetAccessLog
            
            recent_access = db.query(DatasetAccessLog).filter(
                DatasetAccessLog.dataset_id == dataset_id
            ).order_by(DatasetAccessLog.created_at.desc()).limit(10).all()
            
            stats_response["recent_access"] = [
                {
                    "access_type": log.access_type,
                    "user_id": log.user_id,
                    "ip_address": log.ip_address,
                    "created_at": log.created_at.isoformat() if log.created_at else None
                }
                for log in recent_access
            ]
        
        # Include quality metrics if available
        if dataset.quality_metrics:
            stats_response["quality_summary"] = {
                "overall_score": dataset.quality_metrics.get("overall_score"),
                "completeness": dataset.quality_metrics.get("completeness"),
                "consistency": dataset.quality_metrics.get("consistency"),
                "accuracy": dataset.quality_metrics.get("accuracy"),
                "last_analyzed": dataset.quality_metrics.get("last_analyzed")
            }
        
        # Log access
        data_service.log_access(
            user=current_user,
            dataset=dataset,
            access_type="stats"
        )
        
        return stats_response
        
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
    # Check if dataset exists and user has access
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

    # Extract message and agent preference
    user_message = message.get("message", "")
    agent_name = message.get("agent_name")  # Optional agent specification like '@preprocessing_agent'
    use_agents = message.get("use_agents", True)  # Default to using agents

    if not user_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is required"
        )

    try:
        # Use MindsDB agent-based chat directly (with agent creation and SQL capabilities)
        # Skip DSPy agents as per user requirement: "turn all into chat_with_dataset_agent()"
        response = await mindsdb_service.chat_with_dataset_agent(
            dataset_id=dataset_id,
            message=user_message,
            db=db,
            session_id=message.get("session_id"),
            stream=True
        )

        # Log the interaction
        data_service.log_access(
            user=current_user,
            dataset=dataset,
            access_type="ai_chat"
        )

        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "question": user_message,
            "model_type": "agent_chat",
            "agent_system": True,
            **response
        }

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
    # Check if dataset exists and user has access
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
        # Get model information from MindsDB
        models_info = []
        
        # Check chat model
        chat_model_name = f"dataset_{dataset_id}_chat_model"
        
        # Query MindsDB for model status
        try:
            models_query = f"SHOW MODELS WHERE name LIKE 'dataset_{dataset_id}_%';"
            result = mindsdb_service.execute_query(models_query)
            
            if result.get('data'):
                for model_data in result['data']:
                    model_info = {
                        "name": model_data[0] if len(model_data) > 0 else "unknown",
                        "engine": model_data[1] if len(model_data) > 1 else "unknown",
                        "status": model_data[5] if len(model_data) > 5 else "unknown",
                        "predict": model_data[7] if len(model_data) > 7 else "unknown",
                    }
                    models_info.append(model_info)
            
        except Exception as e:
            logger.warning(f"Could not fetch model status for dataset {dataset_id}: {e}")
        
        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "models": models_info,
            "available_models": {
                "chat_model": chat_model_name
            },
            "endpoints": {
                "chat": f"/api/datasets/{dataset_id}/chat"
            }
        }
        
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
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Only owner or superuser can recreate models
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only dataset owner can recreate models"
        )
    
    try:
        # Recreate agent for the dataset
        logger.info(f"Recreating agent for dataset {dataset_id}")

        # Delete old agent if exists
        if dataset.agent_name:
            mindsdb_service.delete_agent(dataset.agent_name)
            logger.info(f"Deleted old agent: {dataset.agent_name}")

        # Create new agent based on dataset type
        if dataset.is_multi_file_dataset:
            agent_result = mindsdb_service.setup_multi_file_agent(dataset, db)
        else:
            agent_result = mindsdb_service.setup_single_file_agent(dataset, db)

        if not agent_result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create agent: {agent_result.get('error')}"
            )

        return {
            "message": "Dataset agent recreated successfully",
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "agent_name": agent_result.get("agent_name"),
            "agent_status": agent_result.get("status")
        }
        
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
        metadata_service = MetadataService(db)
        
        # Check cache first (unless refresh is requested)
        cached_metadata = None
        if not refresh and cached_metadata:
            logger.info(f"📋 Returning cached metadata for dataset {dataset_id}")
            return cached_metadata["data"]
        
        # Generate fresh metadata
        logger.info(f"📋 Generating fresh metadata for dataset {dataset_id}")
        
        schema_metadata = await metadata_service.analyze_dataset_schema(dataset)
        quality_metrics = await metadata_service.get_data_quality_metrics(dataset)
        column_statistics = await metadata_service.generate_column_statistics(dataset)
        
        metadata_response = {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "schema_metadata": schema_metadata,
            "quality_metrics": quality_metrics,
            "column_statistics": column_statistics,
            "basic_info": {
                "type": dataset.type.value if dataset.type else "unknown",
                "size_bytes": dataset.size_bytes,
                "row_count": dataset.row_count,
                "column_count": dataset.column_count,
                "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
                "updated_at": dataset.updated_at.isoformat() if dataset.updated_at else None
            },
            "generated_at": schema_metadata.get("analysis_timestamp")
        }
        
        # Log access
        data_service.log_access(
            user=current_user,
            dataset=dataset,
            access_type="metadata"
        )
        
        return metadata_response
        
    except Exception as e:
        logger.error(f"❌ Failed to get metadata for dataset {dataset_id}: {e}")
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
        preview_service = PreviewService(db)
        
        # Check cache first (unless refresh is requested)
        cached_preview = None
        cache_key_params = {"rows": rows, "include_stats": include_stats}
        if not refresh and cached_preview:
            logger.info(f"👁️ Returning cached preview for dataset {dataset_id}")
            return cached_preview["data"]
        
        # Generate fresh preview
        logger.info(f"👁️ Generating fresh preview for dataset {dataset_id}")
        
        preview_data = await preview_service.generate_preview_data(
            dataset=dataset,
            rows=rows,
            include_stats=include_stats
        )
        
        preview_response = {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "preview": preview_data,
            "request_params": {
                "rows_requested": rows,
                "include_stats": include_stats
            }
        }
        
        # Log access
        data_service.log_access(
            user=current_user,
            dataset=dataset,
            access_type="preview"
        )
        
        return preview_response
        
    except Exception as e:
        logger.error(f"❌ Failed to get preview for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get preview: {str(e)}"
        )

@router.post("/{dataset_id}/download-token")
async def generate_download_token(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a secure download token for dataset access."""
    from app.services.download import DownloadService
    
    download_service = DownloadService(db)
    
    # Generate download token with custom expiration
    download_info = await download_service.initiate_download(
        dataset_id=dataset_id,
        user=current_user
    )
    
    return {
        "message": "Download token generated successfully",
        "download_token": download_info["download_token"],
        "expires_at": download_info["expires_at"],
        "dataset_id": dataset_id,
        "file_format": "original"
    }

@router.post("/{dataset_id}/refresh-metadata")
async def refresh_dataset_metadata(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Refresh and update dataset metadata (owner only)."""
    
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Only owner or superuser can refresh metadata
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only dataset owner can refresh metadata"
        )
    
    try:
        metadata_service = MetadataService(db)
        
        # Update metadata in database
        result = await metadata_service.update_dataset_metadata(dataset_id)
        
        logger.info(f"🔄 Metadata refreshed for dataset {dataset_id}")
        
        return {
            "message": "Dataset metadata refreshed successfully",
            "dataset_id": dataset_id,
            "status": result.get("status"),
            "updated_at": result.get("updated_at")
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to refresh metadata for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh metadata: {str(e)}"
        )

@router.get("/{dataset_id}/schema")
async def get_dataset_schema(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get dataset schema information."""
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
        # Return schema from cached metadata or database
        schema_info = dataset.schema_metadata or dataset.schema_info or {}
        
        schema_response = {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "schema": schema_info,
            "basic_info": {
                "type": dataset.type.value if dataset.type else "unknown",
                "row_count": dataset.row_count,
                "column_count": dataset.column_count
            }
        }
        
        # Log access
        data_service.log_access(
            user=current_user,
            dataset=dataset,
            access_type="schema"
        )
        
        return schema_response
        
    except Exception as e:
        logger.error(f"❌ Failed to get schema for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get schema: {str(e)}"
        )

@router.post("/{dataset_id}/transfer-ownership")
async def transfer_dataset_ownership(
    dataset_id: int,
    new_owner_id: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Transfer ownership of a dataset to another user within the same organization."""
    from app.models.user import User
    
    # Get the dataset
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Check if current user is the owner or admin
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        # Check if user is organization admin
        if not (current_user.organization_id == dataset.organization_id and 
                current_user.role in ["owner", "admin"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only dataset owner or organization admin can transfer ownership"
            )
    
    # Get the new owner
    new_owner = db.query(User).filter(User.id == new_owner_id).first()
    if not new_owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="New owner user not found"
        )
    
    # Check if new owner is in the same organization
    if new_owner.organization_id != dataset.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New owner must be in the same organization as the dataset"
        )
    
    # Check if new owner is different from current owner
    if new_owner_id == dataset.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset is already owned by this user"
        )
    
    try:
        # Store old owner info for logging
        old_owner_id = dataset.owner_id
        
        # Transfer ownership
        dataset.owner_id = new_owner_id
        dataset.updated_at = datetime.utcnow()
        
        # Log the ownership transfer
        from app.models.dataset import DatasetAccessLog
        access_log = DatasetAccessLog(
            dataset_id=dataset_id,
            user_id=current_user.id,
            access_type="ownership_transfer",
            ip_address=None,
            user_agent=None,
            details={
                "old_owner_id": old_owner_id,
                "new_owner_id": new_owner_id,
                "transferred_by": current_user.id
            }
        )
        db.add(access_log)
        
        db.commit()
        db.refresh(dataset)
        
        logger.info(f"📋 Dataset {dataset_id} ownership transferred from user {old_owner_id} to user {new_owner_id} by user {current_user.id}")
        
        return {
            "message": "Dataset ownership transferred successfully",
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "old_owner_id": old_owner_id,
            "new_owner_id": new_owner_id,
            "transferred_by": current_user.id,
            "transferred_at": dataset.updated_at.isoformat()
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to transfer ownership for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to transfer ownership: {str(e)}"
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


@router.post("/{dataset_id}/reupload")
async def reupload_dataset_file(
    dataset_id: int,
    file: UploadFile = File(...),
    preserve_metadata: bool = True,
    update_sharing_settings: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reupload/replace the file for an existing dataset while preserving configuration."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Check permissions - only owner or admin can reupload
    if dataset.owner_id != current_user.id and not current_user.is_superuser:
        if current_user.role not in ["owner", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only dataset owner or organization admin can reupload files"
            )
    
    # Validate file type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    file_extension = file.filename.split('.')[-1].lower()
    from app.core.config import settings
    allowed_extensions = settings.get_allowed_file_types()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Supported formats: {', '.join(allowed_extensions).upper()}"
        )
    
    try:
        # Store original metadata if preserving
        original_metadata = {}
        if preserve_metadata:
            original_metadata = {
                "name": dataset.name,
                "description": dataset.description,
                "sharing_level": dataset.sharing_level,
                "ai_summary": dataset.ai_summary,
                "ai_insights": dataset.ai_insights,
                "ai_recommendations": dataset.ai_recommendations,
                "custom_metadata": getattr(dataset, 'custom_metadata', {}),
                "tags": getattr(dataset, 'tags', [])
            }
        
        # Read new file content
        content = await file.read()
        file_size = len(content)
        
        # Backup old file path (in case rollback is needed)
        old_file_path = dataset.file_path
        
        # Store new file using storage service
        storage_result = await storage_service.store_dataset_file(
            file_content=content,
            original_filename=file.filename,
            dataset_id=dataset_id,
            organization_id=current_user.organization_id
        )
        
        # Determine new dataset type
        if file_extension == 'csv':
            new_dataset_type = DatasetType.CSV
        elif file_extension == 'json':
            new_dataset_type = DatasetType.JSON
        elif file_extension in ['xlsx', 'xls']:
            new_dataset_type = DatasetType.EXCEL
        elif file_extension == 'pdf':
            new_dataset_type = DatasetType.PDF
        elif file_extension.lower() in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'svg']:
            new_dataset_type = DatasetType.IMAGE
        else:
            new_dataset_type = DatasetType.TXT  # Better fallback for unknown types
        
        # Process new file content and extract metadata
        file_metadata = {}
        content_preview = None
        row_count = None
        column_count = None
        
        # Save file temporarily for processing
        import tempfile
        import os
        
        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            # Process different file types
            if file_extension in ["pdf", "json"]:
                try:
                    content_result = mindsdb_service.process_file_content(temp_file_path, file_extension)
                    if content_result.get("success"):
                        file_metadata = content_result.get("metadata", {})
                        content_preview = content_result["content"][:500] + "..." if len(content_result["content"]) > 500 else content_result["content"]
                        
                        if file_extension == "json":
                            row_count = file_metadata.get("element_count")
                            column_count = 1
                        
                        logger.info(f"Successfully processed reuploaded {file_extension} file: {file_metadata}")
                except Exception as e:
                    logger.warning(f"Could not process reuploaded {file_extension} file content: {e}")
            
            # For CSV files, try to get basic info
            elif file_extension == "csv":
                try:
                    import pandas as pd
                    df = pd.read_csv(temp_file_path)
                    file_metadata = {
                        "row_count": len(df),
                        "column_count": len(df.columns),
                        "columns": df.columns.tolist(),
                        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()}
                    }
                    content_preview = df.head(3).to_string()
                    row_count = len(df)
                    column_count = len(df.columns)
                    logger.info(f"Successfully analyzed reuploaded CSV file: {file_metadata}")
                except Exception as e:
                    logger.warning(f"Could not analyze reuploaded CSV file: {e}")
        
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        
        # Generate enhanced metadata for new file
        schema_metadata = {}
        quality_metrics = {}
        column_statistics = {}
        preview_data = {}
        
        if file_metadata:
            # Enhanced schema metadata
            schema_metadata = {
                "file_type": file_extension,
                "original_filename": file.filename,
                "encoding": "utf-8",
                "structure": file_metadata.get("structure", {}),
                "columns": file_metadata.get("columns", []),
                "data_types": file_metadata.get("dtypes", {}),
                "sample_data": file_metadata.get("sample_data", []),
                "reupload_timestamp": datetime.utcnow().isoformat()
            }
            
            # Basic quality metrics
            quality_metrics = {
                "overall_score": 0.85,
                "completeness": 1.0 if row_count and row_count > 0 else 0.0,
                "consistency": 0.9,
                "accuracy": 0.8,
                "issues": [],
                "last_analyzed": datetime.utcnow().isoformat(),
                "reupload_analysis": True
            }
            
            # Column statistics
            if "column_stats" in file_metadata:
                column_statistics = file_metadata["column_stats"]
            elif "dtypes" in file_metadata:
                column_statistics = {}
                for col, dtype in file_metadata["dtypes"].items():
                    column_statistics[col] = {
                        "data_type": dtype,
                        "non_null_count": row_count or 0,
                        "null_count": 0,
                        "unique_count": "unknown"
                    }
            
            # Preview data structure
            preview_data = {
                "headers": file_metadata.get("columns", []),
                "sample_rows": file_metadata.get("sample_data", [])[:10],
                "total_rows": row_count or 0,
                "is_sample": True,
                "preview_generated_at": datetime.utcnow().isoformat(),
                "from_reupload": True
            }
        
        # Update dataset with new file information
        dataset.type = new_dataset_type
        dataset.size_bytes = file_size
        dataset.source_url = storage_result['relative_path']
        dataset.file_path = storage_result['file_path']
        dataset.row_count = row_count
        dataset.column_count = column_count
        dataset.file_metadata = file_metadata
        dataset.content_preview = content_preview
        dataset.schema_metadata = schema_metadata
        dataset.quality_metrics = quality_metrics
        dataset.column_statistics = column_statistics
        dataset.preview_data = preview_data
        dataset.updated_at = datetime.utcnow()
        
        # Preserve original metadata if requested
        if preserve_metadata and not update_sharing_settings:
            dataset.name = original_metadata.get("name", dataset.name)
            dataset.description = original_metadata.get("description", dataset.description)
            dataset.sharing_level = original_metadata.get("sharing_level", dataset.sharing_level)
            dataset.ai_summary = original_metadata.get("ai_summary", dataset.ai_summary)
            dataset.ai_insights = original_metadata.get("ai_insights", dataset.ai_insights)
            dataset.ai_recommendations = original_metadata.get("ai_recommendations", dataset.ai_recommendations)
        
        # Reset AI processing status to trigger re-analysis
        dataset.ai_processing_status = AIProcessingStatus.NOT_PROCESSED
        
        db.commit()
        db.refresh(dataset)
        
        # Try to recreate agent for the new file
        agent_result = None
        try:
            # Clean up old agent first
            if dataset.agent_name:
                mindsdb_service.delete_agent(dataset.agent_name)
                logger.info(f"Deleted old agent for reuploaded dataset {dataset_id}")

            # Create new agent based on dataset type
            if dataset.is_multi_file_dataset:
                agent_result = mindsdb_service.setup_multi_file_agent(dataset, db)
            else:
                agent_result = mindsdb_service.setup_single_file_agent(dataset, db)

            if agent_result and agent_result.get("success"):
                logger.info(f"Successfully created new agent for reuploaded dataset {dataset_id}")
            else:
                logger.warning(f"Agent creation failed for reuploaded dataset {dataset_id}: {agent_result.get('error') if agent_result else 'Unknown error'}")
        
        except Exception as e:
            logger.error(f"Error recreating ML models for reuploaded dataset {dataset_id}: {e}")
            ml_model_result = {
                "success": False,
                "error": str(e),
                "message": "ML model recreation failed but file reupload was successful"
            }
        
        # Log the reupload action
        data_service = DataSharingService(db)
        data_service.log_access(
            user=current_user,
            dataset=dataset,
            access_type="file_reupload"
        )
        
        # Prepare response
        response_data = {
            "message": "Dataset file reuploaded successfully",
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "file_changes": {
                "new_file_type": new_dataset_type.value,
                "new_filename": file.filename,
                "new_size_bytes": file_size,
                "new_row_count": row_count,
                "new_column_count": column_count
            },
            "metadata_preserved": preserve_metadata,
            "ml_models": ml_model_result,
            "updated_at": dataset.updated_at.isoformat()
        }
        
        # Add AI chat availability info
        if ml_model_result and ml_model_result.get("success"):
            response_data["ai_features"] = {
                "chat_enabled": True,
                "model_ready": True,
                "chat_endpoint": f"/api/datasets/{dataset_id}/chat"
            }
        else:
            response_data["ai_features"] = {
                "chat_enabled": False,
                "model_ready": False,
                "error": ml_model_result.get("error") if ml_model_result else "Unknown error"
            }
        
        logger.info(f"✅ Dataset {dataset_id} file reuploaded successfully by user {current_user.id}")
        
        return response_data
        
    except Exception as e:
        logger.error(f"❌ Failed to reupload file for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reupload file: {str(e)}"
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
    try:
        # Get dataset
        dataset = db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.is_deleted == False
        ).first()
        
        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dataset not found"
            )
        
        # Check permissions
        data_service = DataSharingService(db)
        if not data_service.can_access_dataset(current_user, dataset):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to visualize this dataset"
            )
        
        # Load dataset data
        dataset_df = await mindsdb_service._load_dataset_for_visualization(dataset, db)
        
        if dataset_df is None or dataset_df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to load dataset data for visualization"
            )
        
        # Get visualization service
        from app.services.data_visualization import get_visualization_service
        from app.core.app_config import get_app_config
        
        app_config = get_app_config()
        api_key = app_config.integrations.GOOGLE_API_KEY
        viz_service = get_visualization_service(api_key)
        
        # Analyze dataset
        data_analysis = viz_service.analyze_dataset(dataset_df, dataset.name)
        
        # Generate visualizations
        if visualization_type:
            query = f"Generate {visualization_type} visualizations for this dataset"
        else:
            query = "Generate useful visualizations for this dataset"
        
        visualizations = viz_service.generate_visualizations_with_lida(
            dataset_df,
            query=query,
            max_visualizations=max_visualizations
        )
        
        # Log access
        data_service.log_access(
            user=current_user,
            dataset=dataset,
            access_type="visualization"
        )
        
        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "data_analysis": data_analysis,
            "visualizations": visualizations,
            "visualization_count": len(visualizations),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate visualizations for dataset {dataset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate visualizations: {str(e)}"
        )