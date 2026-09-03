"""
MindsDB File Handler Service
Handles file uploads, processing, and integration with MindsDB
Enhanced with permanent storage capabilities
"""

import os
import hashlib
import mimetypes
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from fastapi import UploadFile
import logging
from datetime import datetime

from app.models.file_handler import FileUpload, MindsDBHandler, FileProcessingLog, UploadStatus, ProcessingStatus, FileType
from app.models.dataset import Dataset
from app.models.user import User
from app.services.mindsdb import MindsDBService
from app.services.file_handler_permanent import PermanentFileHandlerService
from app.services.image_processing import ImageProcessingService
from app.services.pdf_processing import PDFProcessingService
from app.services.universal_file_processor import UniversalFileProcessor
from app.core.config import settings

logger = logging.getLogger(__name__)


class FileHandlerService:
    """Service for handling file uploads and MindsDB integration with permanent storage support"""
    
    def __init__(self, db: Session, use_permanent_storage: bool = True):
        self.db = db
        self.mindsdb_service = MindsDBService()
        self.use_permanent_storage = use_permanent_storage
        
        # Initialize services
        if self.use_permanent_storage:
            self.permanent_service = PermanentFileHandlerService(db)
        
        self.image_service = ImageProcessingService(db)
        self.pdf_service = PDFProcessingService(db)
        self.universal_processor = UniversalFileProcessor(db)
    
    def calculate_file_hash(self, file_content: bytes) -> str:
        """Calculate SHA-256 hash of file content"""
        return hashlib.sha256(file_content).hexdigest()
    
    def get_file_mime_type(self, filename: str) -> Optional[str]:
        """Get MIME type for file"""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type
    def determine_file_type(self, filename: str, mime_type: str = None) -> str:
        """Determine file type based on filename and MIME type"""
        # Check for images first
        if self.image_service.is_supported_image(filename, mime_type):
            return FileType.IMAGE.value
        
        # Check for PDFs
        if self.pdf_service.is_supported_pdf(filename, mime_type):
            return FileType.DOCUMENT.value
        
        # Check for documents
        document_extensions = ['.pdf', '.docx', '.doc', '.txt', '.rtf', '.odt']
        file_ext = os.path.splitext(filename.lower())[1]
        if file_ext in document_extensions:
            return FileType.DOCUMENT.value
        
        # Check for spreadsheets
        spreadsheet_extensions = ['.csv', '.xlsx', '.xls', '.ods']
        if file_ext in spreadsheet_extensions:
            return FileType.SPREADSHEET.value
        
        # Check for archives
        archive_extensions = ['.zip', '.tar', '.gz', '.rar', '.7z']
        if file_ext in archive_extensions:
            return FileType.ARCHIVE.value
        
        return FileType.OTHER.value
    
    async def save_uploaded_file(self, file: UploadFile, user: User, dataset: Dataset) -> FileUpload:
        """Save uploaded file via universal processor"""
        try:
            logger.info(f"Processing file with universal processor: {file.filename}")
            return await self.universal_processor.process_file(file, user, dataset)
        except Exception as e:
            logger.error(f"File upload failed: {str(e)}")
            raise
    
    def process_file_with_mindsdb(self, file_upload: FileUpload) -> Dict[str, Any]:
        """Process uploaded file with MindsDB (supports both permanent and local storage)"""
        try:
            # Check if file is in permanent storage
            if file_upload.file_path.startswith("mindsdb://permanent_storage/"):
                logger.info(f"File is already in permanent storage: {file_upload.original_filename}")
                # File is already processed during upload for permanent storage
                return {
                    "success": True,
                    "message": "File already processed in permanent storage",
                    "file_id": file_upload.mindsdb_file_id,
                    "storage_type": "permanent"
                }
            
            # Handle image files specially
            if file_upload.file_type == FileType.IMAGE.value:
                logger.info(f"Processing image file with AI: {file_upload.original_filename}")
                return self.image_service.process_image_with_ai(file_upload)
            
            # Handle PDF files specially
            if file_upload.file_type == FileType.DOCUMENT.value and file_upload.mime_type == "application/pdf":
                logger.info(f"Processing PDF file with AI: {file_upload.original_filename}")
                return self.pdf_service.process_pdf_with_ai(file_upload)
            
            # Legacy processing for other local files
            logger.info(f"Processing local file with MindsDB: {file_upload.original_filename}")
            
            # Update status to processing
            file_upload.upload_status = UploadStatus.PROCESSING
            file_upload.processing_started_at = datetime.utcnow()
            self.db.commit()
            
            self.log_processing_step(
                file_upload.id,
                "mindsdb_processing",
                "started",
                f"Starting MindsDB file processing for local {file_upload.file_type} file"
            )
            
            # Create file handler in MindsDB
            handler_result = self.create_mindsdb_file_handler(file_upload)
            
            if handler_result["success"]:
                # Upload file to MindsDB
                upload_result = self.upload_file_to_mindsdb(file_upload)
                
                if upload_result["success"]:
                    # Update status to completed
                    file_upload.upload_status = UploadStatus.COMPLETED
                    file_upload.processing_completed_at = datetime.utcnow()
                    file_upload.mindsdb_file_id = upload_result.get("file_id")
                    
                    self.log_processing_step(
                        file_upload.id,
                        "mindsdb_processing",
                        "completed",
                        "File processing completed successfully",
                        upload_result
                    )
                    
                    result = {
                        "success": True,
                        "message": "File processed successfully",
                        "file_id": upload_result.get("file_id"),
                        "mindsdb_handler": handler_result.get("handler_name"),
                        "storage_type": "local",
                        "file_type": file_upload.file_type
                    }
                else:
                    # Processing failed
                    file_upload.upload_status = UploadStatus.FAILED
                    file_upload.error_message = upload_result.get("error", "Unknown error")
                    
                    self.log_processing_step(
                        file_upload.id,
                        "mindsdb_processing",
                        "failed",
                        f"File processing failed: {upload_result.get('error')}",
                        upload_result
                    )
                    
                    result = {
                        "success": False,
                        "error": upload_result.get("error", "File processing failed")
                    }
            else:
                # Handler creation failed
                file_upload.upload_status = UploadStatus.FAILED
                file_upload.error_message = handler_result.get("error", "Handler creation failed")
                
                self.log_processing_step(
                    file_upload.id,
                    "handler_creation",
                    "failed",
                    f"Handler creation failed: {handler_result.get('error')}",
                    handler_result
                )
                
                result = {
                    "success": False,
                    "error": handler_result.get("error", "Handler creation failed")
                }
            
            self.db.commit()
            return result
            
        except Exception as e:
            # Processing failed with exception
            file_upload.upload_status = UploadStatus.FAILED
            file_upload.error_message = str(e)
            self.db.commit()
            
            self.log_processing_step(
                file_upload.id,
                "mindsdb_processing",
                "failed",
                f"Processing failed with exception: {str(e)}"
            )
            
            logger.error(f"MindsDB file processing failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def migrate_to_permanent_storage(self, file_upload_id: int) -> Dict[str, Any]:
        """Migrate existing local file to permanent storage"""
        if not self.use_permanent_storage:
            return {
                "success": False,
                "error": "Permanent storage is not enabled"
            }
        
        return self.permanent_service.migrate_local_file_to_permanent_storage(file_upload_id)
    
    def query_file_data(
        self,
        file_upload_id: int,
        query: str = "",
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Query data from uploaded file (supports both storage types)"""
        file_upload = self.db.query(FileUpload).filter(
            FileUpload.id == file_upload_id
        ).first()
        
        if not file_upload:
            return {
                "success": False,
                "error": "File upload not found"
            }
        
        if file_upload.file_path.startswith("mindsdb://permanent_storage/"):
            # Query permanent storage file
            if self.use_permanent_storage:
                return self.permanent_service.query_permanent_storage_file(file_upload, query, limit)
            else:
                return {
                    "success": False,
                    "error": "File is in permanent storage but permanent storage service is not enabled"
                }
        else:
            # Query local file through MindsDB
            try:
                handler_name = f"file_handler_{file_upload.id}"
                table_name = f"uploaded_file_{file_upload.id}"
                
                if limit:
                    full_query = f"SELECT * FROM {handler_name}.{table_name} {query} LIMIT {limit}"
                else:
                    full_query = f"SELECT * FROM {handler_name}.{table_name} {query}"
                
                result = self.mindsdb_service.execute_query(full_query)
                
                if result.get("error"):
                    return {
                        "success": False,
                        "error": f"Query failed: {result.get('error')}"
                    }
                
                return {
                    "success": True,
                    "data": result.get("data", []),
                    "query": full_query,
                    "storage_type": "local",
                    "message": "Query executed successfully"
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e)
                }
    
    def get_file_metadata(self, file_upload_id: int) -> Dict[str, Any]:
        """Get comprehensive file metadata"""
        file_upload = self.db.query(FileUpload).filter(
            FileUpload.id == file_upload_id
        ).first()
        
        if not file_upload:
            return {
                "success": False,
                "error": "File upload not found"
            }
        
        if file_upload.file_path.startswith("mindsdb://permanent_storage/"):
            # Get permanent storage metadata
            if self.use_permanent_storage:
                metadata = self.permanent_service.get_file_metadata(file_upload)
                metadata["success"] = True
                return metadata
            else:
                return {
                    "success": False,
                    "error": "File is in permanent storage but permanent storage service is not enabled"
                }
        else:
            # Get local file metadata
            return {
                "success": True,
                "file_id": file_upload.id,
                "original_filename": file_upload.original_filename,
                "file_size": file_upload.file_size,
                "file_hash": file_upload.file_hash,
                "mime_type": file_upload.mime_type,
                "upload_status": file_upload.upload_status,
                "file_path": file_upload.file_path,
                "created_at": file_upload.created_at,
                "storage_type": "local"
            }
    
    def delete_file_upload(self, file_upload_id: int) -> Dict[str, Any]:
        """Delete file upload and cleanup resources"""
        file_upload = self.db.query(FileUpload).filter(
            FileUpload.id == file_upload_id
        ).first()
        
        if not file_upload:
            return {
                "success": False,
                "error": "File upload not found"
            }
        
        if file_upload.file_path.startswith("mindsdb://permanent_storage/"):
            # Delete from permanent storage
            if self.use_permanent_storage:
                return self.permanent_service.delete_permanent_storage_file(file_upload)
            else:
                return {
                    "success": False,
                    "error": "File is in permanent storage but permanent storage service is not enabled"
                }
        else:
            # Delete local file
            try:
                # Delete physical file
                if os.path.exists(file_upload.file_path):
                    os.remove(file_upload.file_path)
                
                # Delete MindsDB handler
                handler_name = f"file_handler_{file_upload.id}"
                drop_handler_query = f"DROP DATABASE IF EXISTS {handler_name}"
                self.mindsdb_service.execute_query(drop_handler_query)
                
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
                    "message": "Local file deleted successfully"
                }
                
            except Exception as e:
                logger.error(f"Failed to delete local file: {str(e)}")
                self.db.rollback()
                return {
                    "success": False,
                    "error": str(e)
                }
    
    def create_mindsdb_file_handler(self, file_upload: FileUpload) -> Dict[str, Any]:
        """Create file handler in MindsDB"""
        try:
            handler_name = f"file_handler_{file_upload.id}"
            
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
            
            # Create file handler in MindsDB
            create_query = f"""
            CREATE DATABASE {handler_name}
            WITH ENGINE = 'files'
            """
            
            result = self.mindsdb_service.execute_query(create_query)
            
            if result.get("error"):
                return {
                    "success": False,
                    "error": f"Failed to create MindsDB handler: {result.get('error')}"
                }
            
            # Save handler configuration
            handler_config = MindsDBHandler(
                organization_id=file_upload.organization_id,
                handler_name=handler_name,
                handler_type="file",
                configuration={
                    "engine": "files",
                    "file_upload_id": file_upload.id,
                    "original_filename": file_upload.original_filename
                }
            )
            
            self.db.add(handler_config)
            self.db.commit()
            
            return {
                "success": True,
                "handler_name": handler_name,
                "message": "Handler created successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to create MindsDB file handler: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def upload_file_to_mindsdb(self, file_upload: FileUpload) -> Dict[str, Any]:
        """Upload file to MindsDB for processing"""
        try:
            # For now, we'll create a table reference to the file
            # In a full implementation, you'd use MindsDB's file upload API
            
            handler_name = f"file_handler_{file_upload.id}"
            table_name = f"uploaded_file_{file_upload.id}"
            
            # Create table reference to the uploaded file
            create_table_query = f"""
            CREATE TABLE {handler_name}.{table_name} (
                file_path '{file_upload.file_path}'
            )
            """
            
            result = self.mindsdb_service.execute_query(create_table_query)
            
            if result.get("error"):
                return {
                    "success": False,
                    "error": f"Failed to create file table: {result.get('error')}"
                }
            
            return {
                "success": True,
                "file_id": table_name,
                "handler": handler_name,
                "message": "File uploaded to MindsDB successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to upload file to MindsDB: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def log_processing_step(
        self,
        file_upload_id: int,
        step: str,
        status: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        processing_time_ms: Optional[int] = None
    ):
        """Log a processing step"""
        try:
            log_entry = FileProcessingLog(
                file_upload_id=file_upload_id,
                step=step,
                status=status,
                message=message,
                details=details,
                processing_time_ms=processing_time_ms
            )
            
            self.db.add(log_entry)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to log processing step: {str(e)}")
    
    def get_file_upload_status(self, file_upload_id: int) -> Optional[Dict[str, Any]]:
        """Get file upload status and processing logs (supports both storage types)"""
        file_upload = self.db.query(FileUpload).filter(
            FileUpload.id == file_upload_id
        ).first()
        
        if not file_upload:
            return None
        
        # Get processing logs
        logs = self.db.query(FileProcessingLog).filter(
            FileProcessingLog.file_upload_id == file_upload_id
        ).order_by(FileProcessingLog.created_at).all()
        
        # Determine storage type
        storage_type = "permanent" if file_upload.file_path.startswith("mindsdb://permanent_storage/") else "local"
        
        status_info = {
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
                    "created_at": log.created_at
                }
                for log in logs
            ]
        }
        
        # Add storage-specific information
        if storage_type == "permanent":
            status_info["storage_path"] = getattr(file_upload, 'mindsdb_storage_path', None)
        else:
            status_info["file_path"] = file_upload.file_path
        
        return status_info
    
    def get_organization_handlers(self, organization_id: int) -> List[Dict[str, Any]]:
        """Get all MindsDB handlers for an organization (both storage types)"""
        handlers = self.db.query(MindsDBHandler).filter(
            MindsDBHandler.organization_id == organization_id,
            MindsDBHandler.is_active == True
        ).all()
        
        handler_list = []
        for handler in handlers:
            handler_info = {
                "id": handler.id,
                "handler_name": handler.handler_name,
                "handler_type": handler.handler_type,
                "configuration": handler.configuration,
                "created_at": handler.created_at,
                "updated_at": handler.updated_at
            }
            
            # Determine storage type from handler type or configuration
            if handler.handler_type == "permanent_file":
                handler_info["storage_type"] = "permanent"
            elif handler.handler_type == "file":
                handler_info["storage_type"] = "local"
            else:
                # Check configuration for storage type
                config = handler.configuration or {}
                if config.get("storage_type") == "permanent":
                    handler_info["storage_type"] = "permanent"
                else:
                    handler_info["storage_type"] = "local"
            
            handler_list.append(handler_info)
        
        return handler_list
    def execute_query(self, query: str) -> Dict[str, Any]:
        """Execute a query using MindsDB service"""
        try:
            if not self.mindsdb_service._ensure_connection():
                return {
                    "error": "MindsDB connection not available"
                }
            
            result = self.mindsdb_service.connection.query(query)
            
            if result:
                try:
                    if hasattr(result, 'fetch'):
                        data = result.fetch()
                        if hasattr(data, 'to_dict'):
                            return {"data": [data.to_dict()]}
                        elif hasattr(data, 'to_records'):
                            return {"data": data.to_records()}
                        else:
                            return {"data": data}
                    else:
                        return {"data": result}
                except Exception as e:
                    return {"error": f"Failed to fetch query result: {str(e)}"}
            else:
                return {"data": []}
                
        except Exception as e:
            logger.error(f"Query execution failed: {str(e)}")
            return {"error": str(e)} 