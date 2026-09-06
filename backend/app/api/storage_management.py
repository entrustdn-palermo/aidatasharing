"""
Storage Management API
Provides endpoints for managing storage configuration and migration
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging

from app.core.database import get_db
from app.core.auth import get_current_admin_user
from app.models.user import User
from app.utils.storage_migration import migration_service
from app.services.storage import storage_service

logger = logging.getLogger(__name__)
router = APIRouter()

class MigrationRequest(BaseModel):
    target_backend: str  # 's3' or 'local'
    dataset_ids: Optional[List[int]] = None  # If None, migrate all datasets

class StorageStatusResponse(BaseModel):
    current_backend: str
    storage_strategy: str
    local_backend_available: bool
    s3_backend_available: bool
    backend_info: dict

class MigrationStatusResponse(BaseModel):
    migration_id: str
    status: str
    progress: dict

@router.get("/storage/status")
async def get_storage_status(
    current_user: User = Depends(get_current_admin_user)
) -> StorageStatusResponse:
    """Get current storage configuration status"""
    try:
        # Get storage service info
        backend_info = storage_service.get_backend_info()
        
        # Get migration service status
        migration_status = migration_service.get_storage_status()
        
        # Determine storage strategy based on configuration
        storage_type = backend_info.get('storage_type', 'unknown')
        local_available = migration_status['local_backend_available']
        s3_available = migration_status['s3_backend_available']
        
        if storage_type == 'local':
            storage_strategy = 'local_primary'
        elif storage_type == 's3':
            storage_strategy = 's3_primary'
        elif local_available and s3_available:
            storage_strategy = 'hybrid'
        else:
            storage_strategy = 'local_primary'  # default fallback
        
        return StorageStatusResponse(
            current_backend=storage_type,
            storage_strategy=storage_strategy,
            local_backend_available=local_available,
            s3_backend_available=s3_available,
            backend_info={
                **backend_info,
                'local_storage_dir': migration_status.get('local_storage_dir'),
                's3_bucket': migration_status.get('s3_bucket'),
                's3_endpoint': migration_status.get('s3_endpoint')
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get storage status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get storage status: {str(e)}"
        )

@router.post("/storage/migrate")
async def migrate_storage(
    request: MigrationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Initiate storage migration"""
    try:
        # Validate target backend
        if request.target_backend.lower() not in ['s3', 'local']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target backend must be 's3' or 'local'"
            )
        
        # Check if target backend is available
        storage_status = migration_service.get_storage_status()
        
        if request.target_backend.lower() == 's3' and not storage_status['s3_backend_available']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="S3 backend is not configured or available"
            )
        
        if request.target_backend.lower() == 'local' and not storage_status['local_backend_available']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Local backend is not available"
            )
        
        # Start migration
        if request.dataset_ids:
            # Migrate specific datasets
            migration_results = []
            for dataset_id in request.dataset_ids:
                result = await migration_service.migrate_dataset_files(
                    dataset_id, request.target_backend, db
                )
                migration_results.append(result)
            
            return {
                "message": f"Migration to {request.target_backend} completed",
                "results": migration_results
            }
        else:
            # Migrate all datasets
            result = await migration_service.migrate_all_datasets(request.target_backend, db)
            
            return {
                "message": f"Bulk migration to {request.target_backend} completed",
                "result": result
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Migration failed: {str(e)}"
        )

@router.get("/storage/migration-status/{migration_id}")
async def get_migration_status(
    migration_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Get status of a running migration (placeholder for future implementation)"""
    # This would be implemented with a background task queue like Celery
    # For now, return a simple response
    return {
        "migration_id": migration_id,
        "status": "completed",
        "message": "Migration tracking not yet implemented. Use the migrate endpoint for synchronous migration."
    }

@router.post("/storage/verify")
async def verify_storage_integrity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Verify storage integrity - check if all database file references exist"""
    try:
        from app.models.dataset import Dataset, DatasetFile
        
        verification_result = {
            'datasets_checked': 0,
            'files_checked': 0,
            'missing_files': [],
            'orphaned_files': [],
            'integrity_issues': 0
        }
        
        # Check all datasets
        datasets = db.query(Dataset).filter(Dataset.is_deleted == False).all()
        verification_result['datasets_checked'] = len(datasets)
        
        for dataset in datasets:
            # Check single-file datasets
            if dataset.file_path and not dataset.is_multi_file_dataset:
                verification_result['files_checked'] += 1
                if not await storage_service.dataset_file_exists(dataset.file_path):
                    verification_result['missing_files'].append({
                        'type': 'dataset',
                        'dataset_id': dataset.id,
                        'dataset_name': dataset.name,
                        'file_path': dataset.file_path
                    })
                    verification_result['integrity_issues'] += 1
            
            # Check multi-file datasets
            if dataset.is_multi_file_dataset:
                dataset_files = db.query(DatasetFile).filter(
                    DatasetFile.dataset_id == dataset.id,
                    DatasetFile.is_deleted == False
                ).all()
                
                for df in dataset_files:
                    verification_result['files_checked'] += 1
                    if not await storage_service.dataset_file_exists(df.relative_path or df.file_path):
                        verification_result['missing_files'].append({
                            'type': 'dataset_file',
                            'dataset_id': dataset.id,
                            'dataset_name': dataset.name,
                            'file_id': df.id,
                            'filename': df.filename,
                            'file_path': df.file_path
                        })
                        verification_result['integrity_issues'] += 1
        
        # Run cleanup for orphaned files
        cleanup_result = await storage_service.cleanup_orphaned_files(db)
        verification_result['orphaned_files'] = cleanup_result.get('deleted_files', [])
        
        logger.info(f"Storage verification completed: {verification_result['integrity_issues']} issues found")
        
        return {
            "message": "Storage integrity verification completed",
            "result": verification_result
        }
        
    except Exception as e:
        logger.error(f"Storage verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage verification failed: {str(e)}"
        )

@router.get("/storage/recommendations")
async def get_storage_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get storage strategy recommendations based on current usage patterns"""
    try:
        from app.models.dataset import Dataset, DatasetFile
        
        # Analyze current storage usage
        datasets = db.query(Dataset).filter(Dataset.is_deleted == False).all()
        
        analysis = {
            'total_datasets': len(datasets),
            'total_size_mb': 0,
            'large_files_count': 0,  # >10MB
            'small_files_count': 0,  # <10MB
            'multi_file_datasets': 0,
            'single_file_datasets': 0,
            'recommendations': []
        }
        
        large_file_threshold = 10 * 1024 * 1024  # 10MB
        
        for dataset in datasets:
            if dataset.is_multi_file_dataset:
                analysis['multi_file_datasets'] += 1
                dataset_files = db.query(DatasetFile).filter(
                    DatasetFile.dataset_id == dataset.id,
                    DatasetFile.is_deleted == False
                ).all()
                
                for df in dataset_files:
                    if df.file_size:
                        analysis['total_size_mb'] += df.file_size / (1024 * 1024)
                        if df.file_size > large_file_threshold:
                            analysis['large_files_count'] += 1
                        else:
                            analysis['small_files_count'] += 1
            else:
                analysis['single_file_datasets'] += 1
                if dataset.size_bytes:
                    analysis['total_size_mb'] += dataset.size_bytes / (1024 * 1024)
                    if dataset.size_bytes > large_file_threshold:
                        analysis['large_files_count'] += 1
                    else:
                        analysis['small_files_count'] += 1
        
        analysis['total_size_mb'] = round(analysis['total_size_mb'], 2)
        
        # Generate recommendations
        if analysis['total_size_mb'] > 1000:  # >1GB total
            analysis['recommendations'].append({
                'strategy': 's3',
                'reason': 'High volume of data detected. S3 provides better scalability and cost-effectiveness for large datasets.',
                'priority': 'high'
            })
        elif analysis['total_size_mb'] > 100:  # 100MB-1GB
            analysis['recommendations'].append({
                'strategy': 's3',
                'reason': 'Moderate storage usage. S3 provides good scalability and backup benefits.',
                'priority': 'medium'
            })
        else:  # <100MB total
            analysis['recommendations'].append({
                'strategy': 'local',
                'reason': 'Small storage footprint detected. Local storage is sufficient and provides faster access.',
                'priority': 'low'
            })
        
        if analysis['total_datasets'] > 100:
            analysis['recommendations'].append({
                'strategy': 's3',
                'reason': 'Large number of datasets detected. S3 provides better data protection and availability.',
                'priority': 'medium'
            })
        
        return {
            "message": "Storage recommendations generated",
            "analysis": analysis
        }
        
    except Exception as e:
        logger.error(f"Failed to generate storage recommendations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate recommendations: {str(e)}"
        )