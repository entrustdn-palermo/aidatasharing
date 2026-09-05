"""
Storage Migration Utilities
Helps migrate files between different storage backends (local <-> S3)
"""

import os
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.dataset import Dataset, DatasetFile
from app.services.storage import LocalStorageBackend, S3StorageBackend, storage_service

logger = logging.getLogger(__name__)

class StorageMigrationService:
    """Service for migrating files between storage backends"""
    
    def __init__(self):
        self.local_backend = None
        self.s3_backend = None
        self._initialize_backends()
    
    def _initialize_backends(self):
        """Initialize both storage backends for migration"""
        # Initialize local backend
        try:
            from app.core.config import settings
            storage_dir = settings.DATASET_STORAGE_PATH
        except ImportError:
            storage_dir = os.getenv('STORAGE_DIR', 
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage"))
        
        self.local_backend = LocalStorageBackend(storage_dir)
        
        # Initialize S3 backend if configured
        bucket_name = os.getenv('S3_BUCKET_NAME')
        access_key = os.getenv('S3_ACCESS_KEY_ID') or os.getenv('AWS_ACCESS_KEY_ID')
        secret_key = os.getenv('S3_SECRET_ACCESS_KEY') or os.getenv('AWS_SECRET_ACCESS_KEY')
        endpoint_url = os.getenv('S3_ENDPOINT_URL')
        region = os.getenv('S3_REGION') or os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        use_ssl = os.getenv('S3_USE_SSL', 'true').lower() == 'true'
        addressing_style = os.getenv('S3_ADDRESSING_STYLE', 'path')
        
        if all([bucket_name, access_key, secret_key]):
            try:
                self.s3_backend = S3StorageBackend(
                    bucket_name=bucket_name,
                    access_key=access_key,
                    secret_key=secret_key,
                    endpoint_url=endpoint_url,
                    region=region,
                    use_ssl=use_ssl,
                    addressing_style=addressing_style
                )
                logger.info("S3 backend initialized for migration")
            except Exception as e:
                logger.error(f"Failed to initialize S3 backend for migration: {str(e)}")
        else:
            logger.warning("S3 backend not configured for migration")
    
    async def migrate_file_local_to_s3(self, file_path: str, metadata: Dict[str, Any]) -> bool:
        """Migrate a single file from local storage to S3"""
        if not self.s3_backend:
            logger.error("S3 backend not available for migration")
            return False
        
        try:
            # Read file from local storage
            file_content = await self.local_backend.retrieve_file(file_path)
            if file_content is None:
                logger.error(f"File not found in local storage: {file_path}")
                return False
            
            # Store in S3
            result = await self.s3_backend.store_file(file_content, file_path, metadata)
            
            if result.get('success'):
                logger.info(f"Successfully migrated file to S3: {file_path}")
                return True
            else:
                logger.error(f"Failed to store file in S3: {file_path}")
                return False
                
        except Exception as e:
            logger.error(f"Migration failed for {file_path}: {str(e)}")
            return False
    
    async def migrate_file_s3_to_local(self, file_path: str, metadata: Dict[str, Any]) -> bool:
        """Migrate a single file from S3 to local storage"""
        if not self.s3_backend:
            logger.error("S3 backend not available for migration")
            return False
        
        try:
            # Read file from S3
            file_content = await self.s3_backend.retrieve_file(file_path)
            if file_content is None:
                logger.error(f"File not found in S3: {file_path}")
                return False
            
            # Store locally
            result = await self.local_backend.store_file(file_content, file_path, metadata)
            
            if result.get('success'):
                logger.info(f"Successfully migrated file to local: {file_path}")
                return True
            else:
                logger.error(f"Failed to store file locally: {file_path}")
                return False
                
        except Exception as e:
            logger.error(f"Migration failed for {file_path}: {str(e)}")
            return False
    
    async def migrate_dataset_files(self, dataset_id: int, target_backend: str, db: Session) -> Dict[str, Any]:
        """Migrate all files for a specific dataset"""
        migration_result = {
            'dataset_id': dataset_id,
            'target_backend': target_backend,
            'migrated_files': [],
            'failed_files': [],
            'total_files': 0,
            'success_count': 0,
            'error_count': 0
        }
        
        try:
            # Get dataset and its files
            dataset = db.query(Dataset).filter(
                Dataset.id == dataset_id,
                Dataset.is_deleted == False
            ).first()
            
            if not dataset:
                migration_result['error'] = f"Dataset {dataset_id} not found"
                return migration_result
            
            # Get all files for this dataset
            if dataset.is_multi_file_dataset:
                dataset_files = db.query(DatasetFile).filter(
                    DatasetFile.dataset_id == dataset_id,
                    DatasetFile.is_deleted == False
                ).all()
                
                files_to_migrate = [
                    {
                        'file_path': df.file_path,
                        'relative_path': df.relative_path or df.file_path,
                        'metadata': {
                            'dataset_id': dataset_id,
                            'filename': df.filename,
                            'file_type': df.file_type,
                            'is_primary': df.is_primary
                        }
                    }
                    for df in dataset_files if df.file_path
                ]
            else:
                # Single file dataset
                if dataset.file_path:
                    files_to_migrate = [
                        {
                            'file_path': dataset.file_path,
                            'relative_path': dataset.file_path,
                            'metadata': {
                                'dataset_id': dataset_id,
                                'filename': dataset.name,
                                'file_type': dataset.file_type
                            }
                        }
                    ]
                else:
                    migration_result['error'] = "No files to migrate for this dataset"
                    return migration_result
            
            migration_result['total_files'] = len(files_to_migrate)
            
            # Migrate each file
            for file_info in files_to_migrate:
                try:
                    if target_backend.lower() == 's3':
                        success = await self.migrate_file_local_to_s3(
                            file_info['relative_path'], 
                            file_info['metadata']
                        )
                    elif target_backend.lower() == 'local':
                        success = await self.migrate_file_s3_to_local(
                            file_info['relative_path'],
                            file_info['metadata']
                        )
                    else:
                        logger.error(f"Unsupported target backend: {target_backend}")
                        success = False
                    
                    if success:
                        migration_result['migrated_files'].append(file_info['relative_path'])
                        migration_result['success_count'] += 1
                    else:
                        migration_result['failed_files'].append(file_info['relative_path'])
                        migration_result['error_count'] += 1
                        
                except Exception as e:
                    logger.error(f"Failed to migrate file {file_info['relative_path']}: {str(e)}")
                    migration_result['failed_files'].append(file_info['relative_path'])
                    migration_result['error_count'] += 1
            
            logger.info(f"Dataset {dataset_id} migration completed: {migration_result['success_count']} success, {migration_result['error_count']} failed")
            return migration_result
            
        except Exception as e:
            logger.error(f"Dataset migration failed: {str(e)}")
            migration_result['error'] = str(e)
            return migration_result
    
    async def migrate_all_datasets(self, target_backend: str, db: Session) -> Dict[str, Any]:
        """Migrate all datasets to the target backend"""
        migration_result = {
            'target_backend': target_backend,
            'datasets_processed': [],
            'datasets_failed': [],
            'total_datasets': 0,
            'total_files': 0,
            'success_files': 0,
            'failed_files': 0
        }
        
        try:
            # Get all datasets with files
            datasets = db.query(Dataset).filter(
                Dataset.is_deleted == False,
                Dataset.file_path.isnot(None)
            ).all()
            
            migration_result['total_datasets'] = len(datasets)
            
            for dataset in datasets:
                dataset_result = await self.migrate_dataset_files(dataset.id, target_backend, db)
                
                migration_result['total_files'] += dataset_result.get('total_files', 0)
                migration_result['success_files'] += dataset_result.get('success_count', 0)
                migration_result['failed_files'] += dataset_result.get('error_count', 0)
                
                if dataset_result.get('error_count', 0) == 0:
                    migration_result['datasets_processed'].append({
                        'dataset_id': dataset.id,
                        'dataset_name': dataset.name,
                        'files_migrated': dataset_result.get('success_count', 0)
                    })
                else:
                    migration_result['datasets_failed'].append({
                        'dataset_id': dataset.id,
                        'dataset_name': dataset.name,
                        'error': dataset_result.get('error', 'Migration failed'),
                        'files_migrated': dataset_result.get('success_count', 0),
                        'files_failed': dataset_result.get('error_count', 0)
                    })
            
            logger.info(f"All datasets migration completed: {len(migration_result['datasets_processed'])} success, {len(migration_result['datasets_failed'])} failed")
            return migration_result
            
        except Exception as e:
            logger.error(f"Bulk migration failed: {str(e)}")
            migration_result['error'] = str(e)
            return migration_result
    
    def get_storage_status(self) -> Dict[str, Any]:
        """Get current storage configuration status"""
        return {
            'local_backend_available': self.local_backend is not None,
            'local_storage_dir': self.local_backend.storage_dir if self.local_backend else None,
            's3_backend_available': self.s3_backend is not None,
            's3_bucket': self.s3_backend.bucket_name if self.s3_backend else None,
            's3_endpoint': self.s3_backend.endpoint_url if self.s3_backend else None,
            'current_type': os.getenv('STORAGE_TYPE', 'local')
        }

# Global migration service instance
migration_service = StorageMigrationService()