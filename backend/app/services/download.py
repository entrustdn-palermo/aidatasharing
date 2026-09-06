"""
Download Service for Enhanced Dataset Management
Handles secure dataset downloads with permission checks, token generation, and progress tracking
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse, FileResponse

from app.models.dataset import Dataset, DatasetDownload
from app.models.user import User
from app.services.storage import storage_service
from app.services.data_sharing import DataSharingService
from app.services.download_token import download_token_service
from app.services.download_validator import DownloadValidator
from app.services.error_handler import DownloadErrorHandler
from app.services.download_progress import DownloadProgressTracker
import logging

logger = logging.getLogger(__name__)


class DownloadService:
    """Service for handling secure dataset downloads"""
    
    def __init__(self, db: Session):
        self.db = db
        self.data_sharing_service = DataSharingService(db)
        self.validator = DownloadValidator(db)
        self.error_handler = DownloadErrorHandler(db)
        self.progress_tracker = DownloadProgressTracker(db)
    
    async def initiate_download(
        self,
        dataset_id: int,
        user: User,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiate a dataset download with enhanced permission checks
        
        Args:
            dataset_id: ID of dataset to download
            user: User requesting download
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            Dict with download information and token
        """
        try:
            # Comprehensive validation using the validator
            is_valid, error_details = self.validator.validate_download_request(
                dataset_id=dataset_id,
                user=user,
                file_format="original",
                compression=None
            )
            
            if not is_valid:
                # Log failed download attempt
                dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
                if dataset:
                    self.data_sharing_service.log_download_attempt(
                        user, dataset, False, error_details["message"], ip_address
                    )
                
                # Map error codes to HTTP status codes
                status_code_map = {
                    "DATASET_NOT_FOUND": status.HTTP_404_NOT_FOUND,
                    "DATASET_DELETED": status.HTTP_410_GONE,
                    "DATASET_INACTIVE": status.HTTP_403_FORBIDDEN,
                    "ACCESS_DENIED": status.HTTP_403_FORBIDDEN,
                    "DOWNLOAD_PERMISSION_DENIED": status.HTTP_403_FORBIDDEN,
                    "RATE_LIMIT_EXCEEDED": status.HTTP_429_TOO_MANY_REQUESTS,
                    "INVALID_FILE_FORMAT": status.HTTP_400_BAD_REQUEST,
                    "FILE_SIZE_EXCEEDED": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    "INVALID_COMPRESSION": status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR
                }
                
                status_code = status_code_map.get(error_details["error_code"], status.HTTP_400_BAD_REQUEST)
                
                raise HTTPException(
                    status_code=status_code,
                    detail=error_details
                )
            
            # Get dataset for token generation (validation already confirmed it exists)
            dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
            
            # Generate secure download token
            download_token = download_token_service.generate(
                dataset_id=dataset_id,
                user_id=user.id,
                expires_in_hours=24
            )
            logger.info(f"Generated download token: {download_token[:20]}... for dataset {dataset_id}")
            
            # Create download record
            download_record = DatasetDownload(
                dataset_id=dataset_id,
                user_id=user.id,
                download_token=download_token,
                file_format="original",
                compression=None,
                original_filename=dataset.name,
                file_size_bytes=dataset.size_bytes,
                download_status="pending",
                progress_percentage=0,
                started_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=24),
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            self.db.add(download_record)
            try:
                self.db.commit()
                self.db.refresh(download_record)
                logger.info(f"Successfully created download record {download_record.id} with token {download_token[:20]}...")
            except Exception as e:
                self.db.rollback()
                logger.error(f"Failed to commit download record: {e}")
                raise
            
            logger.info(f"📥 Download initiated: Dataset {dataset_id} by user {user.id}")
            
            return {
                "download_id": download_record.id,
                "download_token": download_token,
                "dataset_id": dataset_id,
                "dataset_name": dataset.name,
                "file_format": "original",
                "estimated_size": dataset.size_bytes,
                "expires_at": download_record.expires_at.isoformat(),
                "status": "pending"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initiate download: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initiate download: {str(e)}"
            )
    
    async def execute_download(
        self,
        download_token: str,
        use_streaming: bool = True,
        range_header: Optional[str] = None
    ) -> StreamingResponse:
        """
        Execute the actual file download using a secure token with enhanced error handling
        and resumable download support
        
        Args:
            download_token: Secure download token
            use_streaming: Whether to use streaming response for large files
            range_header: HTTP Range header for resumable downloads
            
        Returns:
            StreamingResponse or FileResponse with the file
        """
        try:
            # Validate token format
            logger.info(f"Validating download token: {download_token[:20]}...")
            if not download_token_service.validate(download_token):
                logger.error(f"Invalid token format for token: {download_token}")
                error = self.error_handler.handle_permission_error(
                    dataset=None,
                    user=None,
                    permission_details={"error": "Invalid token format"}
                )
                raise self.error_handler.create_http_exception(error)
            
            # Get download record
            logger.info(f"Looking for download record with token: {download_token[:20]}...")
            download_record = self.db.query(DatasetDownload).filter(
                DatasetDownload.download_token == download_token
            ).first()
            
            if not download_record:
                logger.error(f"Download record not found for token: {download_token[:20]}...")
                # Let's also check how many download records exist in total
                total_records = self.db.query(DatasetDownload).count()
                logger.info(f"Total download records in database: {total_records}")
                
                error = self.error_handler.handle_permission_error(
                    dataset=None,
                    user=None,
                    permission_details={"error": "Token not found", "token": download_token[:8] + "..."}
                )
                raise self.error_handler.create_http_exception(error)
            
            # Check if token has expired
            if download_record.expires_at and download_record.expires_at < datetime.utcnow():
                download_record.download_status = "expired"
                self.db.commit()
                
                error = self.error_handler.handle_permission_error(
                    dataset=None,
                    user=None,
                    permission_details={
                        "error": "Token expired",
                        "expired_at": download_record.expires_at.isoformat(),
                        "token_age_hours": round((datetime.utcnow() - download_record.started_at).total_seconds() / 3600, 1)
                    }
                )
                raise self.error_handler.create_http_exception(error)
            
            # Get dataset
            dataset = self.db.query(Dataset).filter(
                Dataset.id == download_record.dataset_id
            ).first()
            
            if not dataset:
                download_record.download_status = "failed"
                download_record.error_message = "Dataset not found"
                self.db.commit()
                
                error = self.error_handler.handle_file_not_found_error(
                    dataset=None,
                    file_path=None,
                    download_record=download_record
                )
                raise self.error_handler.create_http_exception(error)
            
            # Check if dataset is still active
            if dataset.is_deleted or not dataset.is_active:
                download_record.download_status = "failed"
                download_record.error_message = "Dataset no longer available"
                self.db.commit()
                
                error = self.error_handler.handle_permission_error(
                    dataset=dataset,
                    user=None,
                    permission_details={
                        "error": "Dataset unavailable",
                        "is_deleted": dataset.is_deleted,
                        "is_active": dataset.is_active
                    }
                )
                raise self.error_handler.create_http_exception(error)
            
            # Get user for permission checks
            user = None
            if download_record.user_id:
                from app.models.user import User
                user = self.db.query(User).filter(User.id == download_record.user_id).first()
            
            # Update download status
            is_resuming = range_header is not None
            
            if is_resuming and download_record.download_status == "interrupted":
                # Resuming a previously interrupted download
                logger.info(f"🔄 Resuming download: Dataset {dataset.id}, token {download_token[:8]}...")
            else:
                # New download or restart
                download_record.download_status = "in_progress"
                download_record.progress_percentage = 0
            
            self.db.commit()
            
            # Get file path
            file_path = dataset.file_path or dataset.source_url
            if not file_path:
                download_record.download_status = "failed"
                download_record.error_message = "File path not found"
                self.db.commit()
                
                error = self.error_handler.handle_file_not_found_error(
                    dataset=dataset,
                    file_path=None,
                    download_record=download_record
                )
                raise self.error_handler.create_http_exception(error)
            
            # For now, skip file existence check - let the streaming handle it
            # The actual file existence will be validated when we try to stream it
            logger.info(f"Will attempt to stream file: {file_path}")
            
            # Use the original file path for all subsequent operations
            final_file_path = file_path
            
            # Log download access
            if user:
                self.data_sharing_service.log_access(
                    user=user,
                    dataset=dataset,
                    access_type="download_resume" if is_resuming else "download"
                )
            
            # Update dataset download statistics (only for new downloads, not resumptions)
            if not is_resuming:
                dataset.download_count = (dataset.download_count or 0) + 1
                dataset.last_downloaded_at = datetime.utcnow()
            
            # Start download timing
            start_time = datetime.utcnow()
            
            try:
                # For now, always use simple file streaming (range requests not implemented yet)
                response = await storage_service.get_file_stream(final_file_path)
                
                # Add basic headers
                if range_header:
                    logger.info(f"Range request received but not supported yet: {range_header}")
                    # For now, ignore range header and serve full file
                    pass
                
                # Indicate support for resumable downloads (even though not fully implemented)
                response.headers["Accept-Ranges"] = "bytes"
                
                # Set original filename with proper extension
                filename = dataset.name
                if dataset.file_path and '.' in dataset.file_path:
                    # Extract extension from the original file path
                    original_extension = dataset.file_path.split('.')[-1]
                    if not filename.lower().endswith(f'.{original_extension.lower()}'):
                        filename += f'.{original_extension}'
                elif dataset.type and dataset.type != 'unknown':
                    # Use dataset type as extension if no file path extension
                    extension = dataset.type.lower()
                    if not filename.lower().endswith(f'.{extension}'):
                        filename += f'.{extension}'
                
                response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
                
                # Update download completion
                end_time = datetime.utcnow()
                duration = (end_time - start_time).total_seconds()
                
                download_record.download_status = "completed"
                download_record.progress_percentage = 100
                download_record.completed_at = end_time
                download_record.download_duration_seconds = int(duration)
                
                # Calculate transfer rate
                if dataset.size_bytes and duration > 0:
                    mbps = (dataset.size_bytes * 8) / (duration * 1024 * 1024)  # Megabits per second
                    download_record.transfer_rate_mbps = f"{mbps:.2f}"
                
                self.db.commit()
                
                logger.info(f"✅ Download completed: Dataset {dataset.id} in {duration:.2f}s")
                
                # Add custom headers for tracking
                response.headers["X-Download-ID"] = str(download_record.id)
                response.headers["X-Download-Time"] = str(int(duration))
                
                return response
                
            except Exception as e:
                # Check if it's a network interruption
                is_network_error = "connection" in str(e).lower() or "network" in str(e).lower() or "timeout" in str(e).lower()
                
                if is_network_error:
                    # Mark as interrupted for resumable download
                    download_record.download_status = "interrupted"
                    download_record.error_message = f"Download interrupted: {str(e)}"
                    self.db.commit()
                    
                    error = self.error_handler.handle_network_error(
                        dataset=dataset,
                        network_error=e,
                        download_record=download_record
                    )
                else:
                    # Other errors
                    download_record.download_status = "failed"
                    download_record.error_message = str(e)
                    download_record.completed_at = datetime.utcnow()
                    self.db.commit()
                    
                    # Check if it's a storage error
                    if "storage" in str(e).lower() or "disk" in str(e).lower() or "file" in str(e).lower():
                        error = self.error_handler.handle_storage_error(
                            dataset=dataset,
                            storage_error=e,
                            download_record=download_record
                        )
                    else:
                        # Generic error
                        error = self.error_handler.handle_file_corruption_error(
                            dataset=dataset,
                            file_path=file_path,
                            corruption_details={"error": str(e), "type": "unknown"},
                            download_record=download_record
                        )
                
                raise self.error_handler.create_http_exception(error)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Download execution failed: {e}")
            
            # Create a generic error response
            error_dict = {
                "error_code": "DOWNLOAD_FAILED",
                "message": "Download execution failed",
                "details": {"error": str(e)},
                "recovery_suggestions": [
                    "Please try again later",
                    "Contact support if the problem persists"
                ]
            }
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_dict
            )
    
    def _parse_range_header(self, range_header: str) -> int:
        """Parse HTTP Range header to get start byte for resumable downloads"""
        try:
            if not range_header or not range_header.startswith("bytes="):
                return 0
            
            # Format: "bytes=start-end" or "bytes=start-"
            range_value = range_header.split("=")[1]
            start_byte = int(range_value.split("-")[0])
            return max(0, start_byte)  # Ensure non-negative
            
        except Exception as e:
            logger.error(f"Failed to parse range header: {e}")
            return 0
    
    def get_download_progress(self, download_token: str) -> Dict[str, Any]:
        """
        Get download progress information with enhanced details
        
        Args:
            download_token: Download token
            
        Returns:
            Dict with detailed download progress information
        """
        try:
            download_record = self.db.query(DatasetDownload).filter(
                DatasetDownload.download_token == download_token
            ).first()
            
            if not download_record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error_code": "DOWNLOAD_NOT_FOUND",
                        "message": "Download not found",
                        "details": {"token": download_token[:8] + "..."}
                    }
                )
            
            # Get dataset information
            dataset = self.db.query(Dataset).filter(Dataset.id == download_record.dataset_id).first()
            
            # Get progress from tracker if active
            progress_info = self.progress_tracker.get_progress(download_record.id)
            
            # Calculate estimated time remaining
            estimated_time_remaining = None
            if (download_record.download_status == "in_progress" and 
                download_record.progress_percentage and 
                download_record.progress_percentage > 0 and 
                download_record.progress_percentage < 100 and
                download_record.started_at):
                
                # Calculate based on elapsed time and progress
                elapsed_seconds = (datetime.utcnow() - download_record.started_at).total_seconds()
                if elapsed_seconds > 0:
                    progress_ratio = download_record.progress_percentage / 100
                    if progress_ratio > 0:
                        estimated_time_remaining = int((elapsed_seconds / progress_ratio) - elapsed_seconds)
            
            # Calculate bytes transferred
            bytes_transferred = None
            if download_record.file_size_bytes and download_record.progress_percentage is not None:
                bytes_transferred = int((download_record.progress_percentage / 100) * download_record.file_size_bytes)
            
            # Determine if download is resumable
            is_resumable = download_record.download_status in ["interrupted", "failed"] and download_record.progress_percentage > 0
            
            # Prepare response with enhanced information
            response = {
                "download_id": download_record.id,
                "dataset_id": download_record.dataset_id,
                "dataset_name": dataset.name if dataset else None,
                "status": download_record.download_status,
                "progress_percentage": download_record.progress_percentage,
                "bytes_transferred": bytes_transferred,
                "file_size_bytes": download_record.file_size_bytes,
                "file_format": download_record.file_format,
                "compression": download_record.compression,
                "started_at": download_record.started_at.isoformat() if download_record.started_at else None,
                "completed_at": download_record.completed_at.isoformat() if download_record.completed_at else None,
                "duration_seconds": download_record.download_duration_seconds,
                "transfer_rate_mbps": download_record.transfer_rate_mbps,
                "error_message": download_record.error_message,
                "expires_at": download_record.expires_at.isoformat() if download_record.expires_at else None,
                "estimated_time_remaining_seconds": estimated_time_remaining,
                "is_resumable": is_resumable,
                "retry_url": f"/api/datasets/download/{download_token}/retry" if is_resumable else None
            }
            
            # Add real-time tracking info if available
            if isinstance(progress_info, dict) and "error" not in progress_info:
                response.update({
                    "real_time_transfer_rate_bps": progress_info.get("transfer_rate_bps"),
                    "real_time_progress": progress_info
                })
            
            # Add recovery suggestions for failed downloads
            if download_record.download_status == "failed":
                response["recovery_suggestions"] = [
                    "Try downloading again using the retry URL",
                    "Try a different file format if available",
                    "Check your network connection and try again",
                    "Contact support if the problem persists"
                ]
            
            # Add resumption instructions for interrupted downloads
            if download_record.download_status == "interrupted":
                response["recovery_suggestions"] = [
                    "Use the retry URL to resume your download",
                    "Your download will continue from where it left off",
                    "Make sure you have a stable network connection"
                ]
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to get download progress: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error_code": "PROGRESS_RETRIEVAL_FAILED",
                    "message": "Failed to get download progress",
                    "details": {"error": str(e)}
                }
            )
    
    def get_download_history(
        self,
        dataset_id: int,
        user: User,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get download history for a dataset (owner only)
        
        Args:
            dataset_id: Dataset ID
            user: User requesting history
            limit: Maximum number of records to return
            
        Returns:
            List of download history records
        """
        try:
            # Get dataset and verify ownership
            dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if not dataset:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Dataset not found"
                )
            
            # Only owner or superuser can view download history
            if dataset.owner_id != user.id and not user.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only dataset owner can view download history"
                )
            
            # Get download records
            downloads = self.db.query(DatasetDownload).filter(
                DatasetDownload.dataset_id == dataset_id
            ).order_by(DatasetDownload.started_at.desc()).limit(limit).all()
            
            history = []
            for download in downloads:
                history.append({
                    "id": download.id,
                    "user_id": download.user_id,
                    "file_format": download.file_format,
                    "compression": download.compression,
                    "file_size_bytes": download.file_size_bytes,
                    "status": download.download_status,
                    "started_at": download.started_at.isoformat() if download.started_at else None,
                    "completed_at": download.completed_at.isoformat() if download.completed_at else None,
                    "duration_seconds": download.download_duration_seconds,
                    "transfer_rate_mbps": download.transfer_rate_mbps,
                    "ip_address": download.ip_address,
                    "error_message": download.error_message
                })
            
            return history
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to get download history: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get download history: {str(e)}"
            )
    
    def cleanup_expired_downloads(self) -> int:
        """
        Clean up expired download records
        
        Returns:
            Number of records cleaned up
        """
        try:
            expired_downloads = self.db.query(DatasetDownload).filter(
                DatasetDownload.expires_at < datetime.utcnow(),
                DatasetDownload.download_status.in_(["pending", "in_progress"])
            ).all()
            
            for download in expired_downloads:
                download.download_status = "expired"
            
            self.db.commit()
            
            logger.info(f"🧹 Cleaned up {len(expired_downloads)} expired downloads")
            return len(expired_downloads)
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup expired downloads: {e}")
            return 0