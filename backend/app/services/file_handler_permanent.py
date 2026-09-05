"""
MindsDB Permanent Storage File Handler Service
Handles file uploads, processing, and integration with MindsDB permanent storage
Replaces local file storage with MindsDB's permanent storage capabilities
"""

import os
import hashlib
import mimetypes
import tempfile
import json
import requests
from typing import Dict, List, Optional, Any, BinaryIO
from sqlalchemy.orm import Session
from fastapi import UploadFile
import logging
from datetime import datetime

from app.models.file_handler import FileUpload, MindsDBHandler, FileProcessingLog, UploadStatus, ProcessingStatus
from app.models.dataset import Dataset
from app.models.user import User
from app.services.agent_gateway import AgentGateway
from app.services.mindsdb import MindsDBService, mindsdb_service as _default_mindsdb
from app.services.file_handler_base import FileHandlerBase
from app.core.config import settings

logger = logging.getLogger(__name__)


class PermanentFileHandlerService(FileHandlerBase):
    """Service for handling file uploads using MindsDB permanent storage"""

    def __init__(self, db: Session, mindsdb_service: Optional[AgentGateway] = None):
        super().__init__(db)
        self.mindsdb_service: AgentGateway = mindsdb_service or _default_mindsdb
        self.mindsdb_base_url = settings.MINDSDB_URL

        # Supported file formats for MindsDB permanent storage
        self.supported_formats = {
            'csv': ['text/csv', 'application/csv'],
            'xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
            'xls': ['application/vnd.ms-excel'],
            'json': ['application/json', 'text/json'],
            'txt': ['text/plain'],
            'pdf': ['application/pdf'],
            'parquet': ['application/octet-stream'],
        }
    
    def validate_file_format(self, filename: str, mime_type: Optional[str]) -> Dict[str, Any]:
        """Validate if file format is supported by MindsDB permanent storage"""
        file_extension = os.path.splitext(filename)[1].lower().lstrip('.')
        
        # Check by extension first
        if file_extension in self.supported_formats:
            return {
                "valid": True,
                "format": file_extension,
                "message": f"File format '{file_extension}' is supported"
            }
        
        # Check by MIME type
        if mime_type:
            for format_name, mime_types in self.supported_formats.items():
                if mime_type in mime_types:
                    return {
                        "valid": True,
                        "format": format_name,
                        "message": f"File format '{format_name}' detected by MIME type"
                    }
        
        return {
            "valid": False,
            "format": None,
            "message": f"File format '{file_extension}' is not supported. Supported formats: {', '.join(self.supported_formats.keys())}"
        }
    
    def upload_file_to_permanent_storage(self, file: UploadFile, user: User, dataset: Dataset) -> Dict[str, Any]:
        """Upload file directly to MindsDB permanent storage"""
        try:
            # Read file content
            file_content = file.file.read()
            file_size = len(file_content)
            file_hash = self.calculate_file_hash(file_content)
            mime_type = self.get_file_mime_type(file.filename)
            
            # Validate file format
            validation = self.validate_file_format(file.filename, mime_type)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": validation["message"]
                }
            
            # Generate unique file identifier for MindsDB
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_file_id = f"org_{user.organization_id}_user_{user.id}_dataset_{dataset.id}_{timestamp}_{file_hash[:8]}"
            
            # Create file upload record
            file_upload = FileUpload(
                dataset_id=dataset.id,
                user_id=user.id,
                organization_id=user.organization_id,
                original_filename=file.filename,
                file_path=f"mindsdb://permanent_storage/{unique_file_id}",  # Virtual path for permanent storage
                file_size=file_size,
                file_hash=file_hash,
                mime_type=mime_type,
                upload_status=UploadStatus.UPLOADING,
                mindsdb_file_id=unique_file_id
            )
            
            self.db.add(file_upload)
            self.db.commit()
            self.db.refresh(file_upload)
            
            # Log upload start
            self.log_processing_step(
                file_upload.id,
                "permanent_storage_upload",
                "started",
                f"Starting upload to MindsDB permanent storage: {file.filename}",
                {
                    "file_size": file_size,
                    "file_hash": file_hash,
                    "format": validation["format"],
                    "unique_file_id": unique_file_id
                }
            )
            
            # Upload to MindsDB permanent storage using HTTP API
            upload_result = self._upload_to_mindsdb_storage(
                file_content=file_content,
                filename=file.filename,
                unique_file_id=unique_file_id,
                file_format=validation["format"]
            )
            
            if upload_result["success"]:
                # Update status to uploaded
                file_upload.upload_status = UploadStatus.UPLOADED
                file_upload.mindsdb_storage_path = upload_result.get("storage_path")
                
                self.log_processing_step(
                    file_upload.id,
                    "permanent_storage_upload",
                    "completed",
                    "File uploaded to MindsDB permanent storage successfully",
                    upload_result
                )
                
                # Create file handler in MindsDB
                handler_result = self.create_permanent_storage_handler(file_upload)
                
                if handler_result["success"]:
                    file_upload.upload_status = UploadStatus.COMPLETED
                    file_upload.processing_completed_at = datetime.utcnow()
                    
                    self.log_processing_step(
                        file_upload.id,
                        "handler_creation",
                        "completed",
                        "MindsDB handler created successfully",
                        handler_result
                    )
                    
                    result = {
                        "success": True,
                        "message": "File uploaded to permanent storage successfully",
                        "file_upload_id": file_upload.id,
                        "mindsdb_file_id": unique_file_id,
                        "handler_name": handler_result.get("handler_name"),
                        "storage_path": upload_result.get("storage_path")
                    }
                else:
                    file_upload.upload_status = UploadStatus.FAILED
                    file_upload.error_message = handler_result.get("error")
                    
                    result = {
                        "success": False,
                        "error": f"File uploaded but handler creation failed: {handler_result.get('error')}"
                    }
            else:
                # Upload failed
                file_upload.upload_status = UploadStatus.FAILED
                file_upload.error_message = upload_result.get("error")
                
                self.log_processing_step(
                    file_upload.id,
                    "permanent_storage_upload",
                    "failed",
                    f"Upload to permanent storage failed: {upload_result.get('error')}",
                    upload_result
                )
                
                result = {
                    "success": False,
                    "error": upload_result.get("error")
                }
            
            self.db.commit()
            return result
            
        except Exception as e:
            # Upload failed with exception
            if 'file_upload' in locals():
                file_upload.upload_status = UploadStatus.FAILED
                file_upload.error_message = str(e)
                self.db.commit()
                
                self.log_processing_step(
                    file_upload.id,
                    "permanent_storage_upload",
                    "failed",
                    f"Upload failed with exception: {str(e)}"
                )
            
            logger.error(f"Permanent storage upload failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _upload_to_mindsdb_storage(
        self,
        file_content: bytes,
        filename: str,
        unique_file_id: str,
        file_format: str
    ) -> Dict[str, Any]:
        """Upload file content to MindsDB permanent storage via HTTP API"""
        try:
            # MindsDB file upload endpoint
            upload_url = f"{self.mindsdb_base_url}/api/files"
            
            # Prepare multipart form data
            files = {
                'file': (filename, file_content, self.get_file_mime_type(filename))
            }
            
            # Additional metadata
            data = {
                'file_id': unique_file_id,
                'format': file_format,
                'permanent': 'true'  # Request permanent storage
            }
            
            # Make upload request
            response = requests.post(
                upload_url,
                files=files,
                data=data,
                timeout=300  # 5 minute timeout for large files
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "storage_path": result.get("path", f"permanent_storage/{unique_file_id}"),
                    "file_id": result.get("file_id", unique_file_id),
                    "message": "File uploaded to permanent storage successfully"
                }
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"MindsDB upload failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during MindsDB upload: {str(e)}")
            return {
                "success": False,
                "error": f"Network error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error during MindsDB upload: {str(e)}")
            return {
                "success": False,
                "error": f"Upload error: {str(e)}"
            }
    
    def create_permanent_storage_handler(self, file_upload: FileUpload) -> Dict[str, Any]:
        """Create file handler in MindsDB for permanent storage file"""
        try:
            handler_name = f"permanent_file_{file_upload.id}"
            
            # Check if handler already exists
            existing_handler = self.db.query(MindsDBHandler).filter(
                MindsDBHandler.organization_id == file_upload.organization_id,
                MindsDBHandler.handler_name == handler_name
            ).first()
            
            if existing_handler:
                return {
                    "success": True,
                    "handler_name": handler_name,
                    "message": "Handler already exists"
                }
            
            # Create file handler in MindsDB using permanent storage
            create_query = f"""
            CREATE DATABASE {handler_name}
            WITH ENGINE = 'files',
            PARAMETERS = {{
                "location": "permanent_storage",
                "file_id": "{file_upload.mindsdb_file_id}"
            }}
            """
            
            result = self.mindsdb_service.execute_query(create_query)
            
            if result.get("status") == "error":
                return {
                    "success": False,
                    "error": f"Failed to create MindsDB permanent storage handler: {result.get('message')}"
                }
            
            # Save handler configuration
            handler_config = MindsDBHandler(
                organization_id=file_upload.organization_id,
                handler_name=handler_name,
                handler_type="permanent_file",
                configuration={
                    "engine": "files",
                    "location": "permanent_storage",
                    "file_upload_id": file_upload.id,
                    "file_id": file_upload.mindsdb_file_id,
                    "original_filename": file_upload.original_filename,
                    "storage_type": "permanent"
                }
            )
            
            self.db.add(handler_config)
            self.db.commit()
            
            return {
                "success": True,
                "handler_name": handler_name,
                "message": "Permanent storage handler created successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to create MindsDB permanent storage handler: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_file_table_reference(self, file_upload: FileUpload) -> Dict[str, Any]:
        """Create table reference to permanent storage file"""
        try:
            handler_name = f"permanent_file_{file_upload.id}"
            table_name = f"file_data_{file_upload.id}"
            
            # Create table reference to the permanent storage file
            create_table_query = f"""
            CREATE TABLE {handler_name}.{table_name}
            FROM permanent_storage
            WHERE file_id = '{file_upload.mindsdb_file_id}'
            """
            
            result = self.mindsdb_service.execute_query(create_table_query)
            
            if result.get("status") == "error":
                return {
                    "success": False,
                    "error": f"Failed to create file table reference: {result.get('message')}"
                }
            
            return {
                "success": True,
                "table_name": table_name,
                "handler": handler_name,
                "message": "File table reference created successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to create file table reference: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def query_permanent_storage_file(
        self,
        file_upload: FileUpload,
        query: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Query data from permanent storage file"""
        try:
            handler_name = f"permanent_file_{file_upload.id}"
            table_name = f"file_data_{file_upload.id}"
            
            # Construct full query
            if limit:
                full_query = f"SELECT * FROM {handler_name}.{table_name} {query} LIMIT {limit}"
            else:
                full_query = f"SELECT * FROM {handler_name}.{table_name} {query}"
            
            result = self.mindsdb_service.execute_query(full_query)
            
            if result.get("status") == "error":
                return {
                    "success": False,
                    "error": f"Query failed: {result.get('message')}"
                }
            
            return {
                "success": True,
                "data": result.get("rows", []),
                "query": full_query,
                "message": "Query executed successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to query permanent storage file: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_file_metadata(self, file_upload: FileUpload) -> Dict[str, Any]:
        """Get metadata about permanent storage file"""
        try:
            # Query MindsDB for file metadata
            metadata_query = f"""
            SELECT 
                COUNT(*) as row_count,
                COUNT(DISTINCT *) as unique_rows
            FROM permanent_file_{file_upload.id}.file_data_{file_upload.id}
            """
            
            result = self.mindsdb_service.execute_query(metadata_query)
            
            if result.get("status") == "error":
                # Return basic metadata from database record
                return {
                    "file_id": file_upload.mindsdb_file_id,
                    "original_filename": file_upload.original_filename,
                    "file_size": file_upload.file_size,
                    "file_hash": file_upload.file_hash,
                    "mime_type": file_upload.mime_type,
                    "upload_status": file_upload.upload_status,
                    "created_at": file_upload.created_at,
                    "storage_type": "permanent",
                    "error": "Could not retrieve detailed metadata from MindsDB"
                }
            
            # Combine database metadata with MindsDB metadata
            metadata = {
                "file_id": file_upload.mindsdb_file_id,
                "original_filename": file_upload.original_filename,
                "file_size": file_upload.file_size,
                "file_hash": file_upload.file_hash,
                "mime_type": file_upload.mime_type,
                "upload_status": file_upload.upload_status,
                "created_at": file_upload.created_at,
                "storage_type": "permanent",
                "storage_path": file_upload.mindsdb_storage_path
            }
            
            # Add MindsDB metadata if available
            if result.get("rows"):
                metadata.update(result["rows"][0])
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to get file metadata: {str(e)}")
            return {
                "file_id": file_upload.mindsdb_file_id,
                "original_filename": file_upload.original_filename,
                "error": str(e)
            }
    
    def delete_permanent_storage_file(self, file_upload: FileUpload) -> Dict[str, Any]:
        """Delete file from permanent storage and cleanup handlers"""
        try:
            handler_name = f"permanent_file_{file_upload.id}"
            
            # Delete MindsDB handler
            drop_handler_query = f"DROP DATABASE IF EXISTS {handler_name}"
            handler_result = self.mindsdb_service.execute_query(drop_handler_query)
            
            # Delete file from permanent storage via API
            delete_url = f"{self.mindsdb_base_url}/api/files/{file_upload.mindsdb_file_id}"
            
            try:
                response = requests.delete(delete_url, timeout=30)
                storage_deleted = response.status_code in [200, 204, 404]  # 404 means already deleted
            except Exception as e:
                logger.warning(f"Could not delete from permanent storage: {e}")
                storage_deleted = False
            
            # Delete database records
            # Delete handler configuration
            handler_config = self.db.query(MindsDBHandler).filter(
                MindsDBHandler.handler_name == handler_name,
                MindsDBHandler.organization_id == file_upload.organization_id
            ).first()
            
            if handler_config:
                self.db.delete(handler_config)
            
            # Delete file upload record (cascade will handle logs)
            self.db.delete(file_upload)
            self.db.commit()
            
            return {
                "success": True,
                "message": "File deleted from permanent storage",
                "handler_deleted": not handler_result.get("error"),
                "storage_deleted": storage_deleted
            }
            
        except Exception as e:
            logger.error(f"Failed to delete permanent storage file: {str(e)}")
            self.db.rollback()
            return {
                "success": False,
                "error": str(e)
            }
    
    def migrate_local_file_to_permanent_storage(self, file_upload_id: int) -> Dict[str, Any]:
        """Migrate existing local file to permanent storage"""
        try:
            file_upload = self.db.query(FileUpload).filter(
                FileUpload.id == file_upload_id
            ).first()
            
            if not file_upload:
                return {
                    "success": False,
                    "error": "File upload not found"
                }
            
            # Check if file is already in permanent storage
            if file_upload.file_path.startswith("mindsdb://permanent_storage/"):
                return {
                    "success": True,
                    "message": "File is already in permanent storage",
                    "already_migrated": True
                }
            
            # Read local file
            if not os.path.exists(file_upload.file_path):
                return {
                    "success": False,
                    "error": "Local file not found"
                }
            
            with open(file_upload.file_path, 'rb') as f:
                file_content = f.read()
            
            # Generate new unique file ID
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_file_id = f"migrated_org_{file_upload.organization_id}_file_{file_upload.id}_{timestamp}"
            
            # Validate file format
            validation = self.validate_file_format(file_upload.original_filename, file_upload.mime_type)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": f"File format not supported for permanent storage: {validation['message']}"
                }
            
            # Upload to permanent storage
            upload_result = self._upload_to_mindsdb_storage(
                file_content=file_content,
                filename=file_upload.original_filename,
                unique_file_id=unique_file_id,
                file_format=validation["format"]
            )
            
            if upload_result["success"]:
                # Update file upload record
                old_file_path = file_upload.file_path
                file_upload.file_path = f"mindsdb://permanent_storage/{unique_file_id}"
                file_upload.mindsdb_file_id = unique_file_id
                file_upload.mindsdb_storage_path = upload_result.get("storage_path")
                
                # Create new permanent storage handler
                handler_result = self.create_permanent_storage_handler(file_upload)
                
                if handler_result["success"]:
                    # Delete old local file
                    try:
                        os.remove(old_file_path)
                    except Exception as e:
                        logger.warning(f"Could not delete old local file {old_file_path}: {e}")
                    
                    self.db.commit()
                    
                    self.log_processing_step(
                        file_upload.id,
                        "migration_to_permanent_storage",
                        "completed",
                        "File migrated from local storage to permanent storage successfully",
                        {
                            "old_path": old_file_path,
                            "new_file_id": unique_file_id,
                            "handler_name": handler_result.get("handler_name")
                        }
                    )
                    
                    return {
                        "success": True,
                        "message": "File migrated to permanent storage successfully",
                        "old_path": old_file_path,
                        "new_file_id": unique_file_id,
                        "handler_name": handler_result.get("handler_name")
                    }
                else:
                    # Rollback file upload changes
                    file_upload.file_path = old_file_path
                    file_upload.mindsdb_file_id = None
                    file_upload.mindsdb_storage_path = None
                    self.db.commit()
                    
                    return {
                        "success": False,
                        "error": f"File uploaded but handler creation failed: {handler_result.get('error')}"
                    }
            else:
                return {
                    "success": False,
                    "error": f"Failed to upload to permanent storage: {upload_result.get('error')}"
                }
                
        except Exception as e:
            logger.error(f"Migration to permanent storage failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }