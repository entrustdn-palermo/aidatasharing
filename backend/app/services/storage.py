"""
Storage Service
Handles file storage operations for datasets with multiple backend support
"""

import os
import hashlib
import uuid
import secrets
import mimetypes
from typing import Dict, Any, Optional, BinaryIO, AsyncGenerator
from datetime import datetime, timedelta
import logging
from fastapi import UploadFile, HTTPException, status
from fastapi.responses import StreamingResponse, FileResponse
import aiofiles
import asyncio

# Optional S3 imports
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

logger = logging.getLogger(__name__)

class BaseStorageBackend:
    """Base class for storage backends"""
    
    async def store_file(self, file_content: bytes, file_path: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
    
    async def retrieve_file(self, file_path: str) -> Optional[bytes]:
        raise NotImplementedError
    
    async def delete_file(self, file_path: str) -> bool:
        raise NotImplementedError
    
    async def get_file_stream(self, file_path: str) -> StreamingResponse:
        raise NotImplementedError
    
    def get_file_url(self, file_path: str, expires_in: int = 3600) -> Optional[str]:
        """Get a temporary URL for file access (local files served via API)"""
        try:
            from app.core.config import settings
            # For local storage, return an API endpoint URL
            # This will be served by a dedicated file serving endpoint
            base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
            return f"{base_url}/api/files/serve/{file_path}"
        except Exception as e:
            logger.error(f"Failed to generate local file URL: {str(e)}")
            return None

class LocalStorageBackend(BaseStorageBackend):
    """Local file system storage backend"""
    
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.chunk_size = 8 * 1024 * 1024  # 8MB chunks
    
    async def store_file(self, file_content: bytes, file_path: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Store file in local filesystem"""
        try:
            full_path = os.path.join(self.storage_dir, file_path)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Save the file
            with open(full_path, "wb") as f:
                f.write(file_content)
            
            logger.info(f"File stored locally: {file_path}")
            
            return {
                "success": True,
                "backend": "local",
                "file_path": file_path,
                "full_path": full_path,
                "file_size": len(file_content)
            }
            
        except Exception as e:
            logger.error(f"Local storage failed: {str(e)}")
            raise
    
    async def retrieve_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file from local filesystem"""
        try:
            full_path = os.path.join(self.storage_dir, file_path)
            
            if os.path.exists(full_path):
                with open(full_path, "rb") as f:
                    return f.read()
            
            return None
            
        except Exception as e:
            logger.error(f"Local file retrieval failed: {str(e)}")
            return None
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from local filesystem"""
        try:
            full_path = os.path.join(self.storage_dir, file_path)
            
            if os.path.exists(full_path):
                os.remove(full_path)
                logger.info(f"File deleted locally: {file_path}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Local file deletion failed: {str(e)}")
            return False
    
    async def get_file_stream(self, file_path: str) -> StreamingResponse:
        """Get file as streaming response from local filesystem"""
        full_path = os.path.join(self.storage_dir, file_path)
        
        if not os.path.exists(full_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "FILE_NOT_FOUND", "message": "File not found"}
            )
        
        # Get file info
        file_size = os.path.getsize(full_path)
        filename = os.path.basename(full_path)
        content_type, _ = mimetypes.guess_type(full_path)
        if not content_type:
            content_type = "application/octet-stream"
        
        # Stream file
        async def file_stream():
            async with aiofiles.open(full_path, "rb") as f:
                while chunk := await f.read(self.chunk_size):
                    yield chunk
        
        response = StreamingResponse(file_stream(), media_type=content_type)
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.headers["Content-Length"] = str(file_size)
        
        return response
    
    def get_file_url(self, file_path: str, expires_in: int = 3600) -> Optional[str]:
        """Generate URL for local file access via API endpoint"""
        try:
            # For local storage, return an API endpoint URL that can serve the file
            # This will be handled by a dedicated file serving endpoint
            from urllib.parse import quote
            encoded_path = quote(file_path, safe='/')
            return f"/api/files/serve/{encoded_path}"
        except Exception as e:
            logger.error(f"Failed to generate local file URL: {str(e)}")
            return None

class S3StorageBackend(BaseStorageBackend):
    """S3-compatible storage backend"""
    
    def __init__(self, bucket_name: str, access_key: str, secret_key: str, 
                 endpoint_url: Optional[str] = None, region: str = "us-east-1",
                 use_ssl: bool = True, addressing_style: str = "path"):
        if not S3_AVAILABLE:
            raise ImportError("boto3 is required for S3 storage backend")
        
        self.bucket_name = bucket_name
        self.region = region
        self.endpoint_url = endpoint_url
        self.use_ssl = use_ssl
        self.addressing_style = addressing_style
        
        # Configure S3 client with advanced options
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        # Prepare S3 client configuration
        client_config = {
            'config': boto3.session.Config(
                s3={
                    'addressing_style': addressing_style
                },
                signature_version='s3v4',
                retries={'max_attempts': 3}
            )
        }
        
        # Add SSL configuration
        if not use_ssl:
            client_config['use_ssl'] = False
        
        # Use custom endpoint if provided (for MinIO, IDrive, etc.)
        if endpoint_url:
            client_config['endpoint_url'] = endpoint_url
            
        self.s3_client = session.client('s3', **client_config)
        
        # Verify bucket access
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.warning(f"Bucket {bucket_name} not found, attempting to create...")
                try:
                    self.s3_client.create_bucket(Bucket=bucket_name)
                    logger.info(f"Created bucket {bucket_name}")
                except ClientError as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
                    raise
            else:
                logger.error(f"S3 bucket access error: {e}")
                raise
    
    async def store_file(self, file_content: bytes, file_path: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Store file in S3-compatible storage"""
        try:
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_path,
                Body=file_content,
                Metadata={k: str(v) for k, v in metadata.items()}  # S3 metadata must be strings
            )
            
            logger.info(f"File stored in S3: {file_path}")
            
            return {
                "success": True,
                "backend": "s3",
                "bucket": self.bucket_name,
                "file_path": file_path,
                "file_size": len(file_content)
            }
            
        except Exception as e:
            logger.error(f"S3 storage failed: {str(e)}")
            raise
    
    async def retrieve_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file from S3-compatible storage"""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_path)
            return response['Body'].read()
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            logger.error(f"S3 file retrieval failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"S3 file retrieval failed: {str(e)}")
            return None
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from S3-compatible storage"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_path)
            logger.info(f"File deleted from S3: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"S3 file deletion failed: {str(e)}")
            return False
    
    async def get_file_stream(self, file_path: str) -> StreamingResponse:
        """Get file as streaming response from S3-compatible storage"""
        try:
            # Get object metadata first
            head_response = self.s3_client.head_object(Bucket=self.bucket_name, Key=file_path)
            file_size = head_response['ContentLength']
            content_type = head_response.get('ContentType', 'application/octet-stream')
            filename = os.path.basename(file_path)
            
            # Stream file from S3
            async def s3_file_stream():
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_path)
                body = response['Body']
                
                try:
                    while True:
                        chunk = body.read(8192)  # 8KB chunks
                        if not chunk:
                            break
                        yield chunk
                finally:
                    body.close()
            
            response = StreamingResponse(s3_file_stream(), media_type=content_type)
            response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
            response.headers["Content-Length"] = str(file_size)
            
            return response
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error_code": "FILE_NOT_FOUND", "message": "File not found"}
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error_code": "S3_ERROR", "message": str(e)}
            )
    
    def get_file_url(self, file_path: str, expires_in: int = 3600) -> Optional[str]:
        """Generate presigned URL for direct file access"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': file_path},
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            return None

# Hybrid storage removed for simplicity - user requested S3 only or local only


class StorageService:
    """Main storage service - simple choice between local or S3 storage"""
    
    def __init__(self):
        self.backend = None
        self._initialize_backend()
    
    def _initialize_backend(self):
        """Initialize storage backend - simple choice: local or S3"""
        storage_type = os.getenv('STORAGE_TYPE', 'local').lower()
        
        if storage_type == 'local':
            # Try to get from settings first, then fall back to environment, then default
            try:
                from app.core.config import settings
                storage_dir = settings.STORAGE_BASE_PATH
                logger.info(f"Using storage directory from settings: {storage_dir}")
            except ImportError:
                storage_dir = os.getenv('STORAGE_DIR', 
                    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage"))
                logger.info(f"Using storage directory from environment/default: {storage_dir}")
            
            self.backend = LocalStorageBackend(storage_dir)
            logger.info("Initialized local storage backend")
            
        elif storage_type in ['s3', 's3_compatible']:
            # Unified S3/S3-compatible storage configuration
            bucket_name = os.getenv('S3_BUCKET_NAME')
            access_key = os.getenv('S3_ACCESS_KEY_ID') or os.getenv('AWS_ACCESS_KEY_ID')  # Support both new and legacy
            secret_key = os.getenv('S3_SECRET_ACCESS_KEY') or os.getenv('AWS_SECRET_ACCESS_KEY')  # Support both new and legacy
            endpoint_url = os.getenv('S3_ENDPOINT_URL')  # Custom endpoint for S3-compatible services
            region = os.getenv('S3_REGION') or os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
            use_ssl = os.getenv('S3_USE_SSL', 'true').lower() == 'true'
            addressing_style = os.getenv('S3_ADDRESSING_STYLE', 'path')
            
            # For AWS S3, set endpoint_url to None to use default
            if storage_type == 's3' and not endpoint_url:
                endpoint_url = None
                
            if not all([bucket_name, access_key, secret_key]):
                logger.error("S3 configuration incomplete, falling back to local storage")
                logger.error(f"Missing: bucket_name={bucket_name is not None}, access_key={access_key is not None}, secret_key={secret_key is not None}")
                try:
                    from app.core.config import settings
                    storage_dir = settings.STORAGE_BASE_PATH
                except ImportError:
                    storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage")
                self.backend = LocalStorageBackend(storage_dir)
            else:
                try:
                    if not S3_AVAILABLE:
                        raise ImportError("boto3 not available")
                        
                    self.backend = S3StorageBackend(
                        bucket_name=bucket_name,
                        access_key=access_key,
                        secret_key=secret_key,
                        endpoint_url=endpoint_url,
                        region=region,
                        use_ssl=use_ssl,
                        addressing_style=addressing_style
                    )
                    endpoint_info = f" (endpoint: {endpoint_url})" if endpoint_url else ""
                    logger.info(f"Initialized S3 storage backend (bucket: {bucket_name}){endpoint_info}")
                except Exception as e:
                    logger.error(f"S3 initialization failed: {str(e)}, falling back to local storage")
                    try:
                        from app.core.config import settings
                        storage_dir = settings.STORAGE_BASE_PATH
                    except ImportError:
                        storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage")
                    self.backend = LocalStorageBackend(storage_dir)
        else:
            logger.warning(f"Unknown storage type: {storage_type}, using local storage")
            storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage")
            self.backend = LocalStorageBackend(storage_dir)
    
    async def store_dataset_file(
        self,
        file_content: bytes,
        original_filename: str,
        dataset_id: int,
        organization_id: int
    ) -> Dict[str, Any]:
        """Store a dataset file using the configured backend"""
        try:
            # Generate unique file path
            file_hash = hashlib.sha256(file_content).hexdigest()[:16]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            extension = original_filename.split('.')[-1] if '.' in original_filename else ''
            
            safe_filename = f"dataset_{dataset_id}_{timestamp}_{file_hash}.{extension}"
            file_path = f"org_{organization_id}/{safe_filename}"
            
            # Prepare metadata
            metadata = {
                "original_filename": original_filename,
                "dataset_id": dataset_id,
                "organization_id": organization_id,
                "upload_timestamp": timestamp,
                "file_hash": file_hash
            }
            
            # Store using backend
            result = await self.backend.store_file(file_content, file_path, metadata)
            
            # Add common fields to result
            result.update({
                "filename": safe_filename,
                "original_filename": original_filename,
                "relative_path": file_path,
                "file_size": len(file_content),
                "file_hash": file_hash
            })
            
            logger.info(f"File stored successfully: {original_filename} -> {safe_filename}")
            return result
            
        except Exception as e:
            logger.error(f"File storage failed: {str(e)}")
            raise
    
    async def retrieve_dataset_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve a dataset file using the configured backend"""
        return await self.backend.retrieve_file(file_path)
    
    def get_dataset_file_url(self, file_path: str, expires_in: int = 3600) -> Optional[str]:
        """Get a publicly accessible URL for a dataset file (for MindsDB integration)"""
        return self.backend.get_file_url(file_path, expires_in)
    
    async def get_dataset_file_stream(self, file_path: str):
        """Get a streaming response for a dataset file"""
        return await self.backend.get_file_stream(file_path)
    
    async def delete_dataset_file(self, file_path: str) -> bool:
        """Delete a dataset file using the configured backend"""
        return await self.backend.delete_file(file_path)
    
    async def get_file_stream(self, file_path: str) -> StreamingResponse:
        """Get file as streaming response using the configured backend"""
        return await self.backend.get_file_stream(file_path)

    async def get_file_content(self, file_path: str) -> bytes:
        """Get file content as bytes (for ZIP creation and other operations)"""
        return await self.backend.retrieve_file(file_path)

    def get_file_url(self, file_path: str, expires_in: int = 3600) -> Optional[str]:
        """Get temporary URL for file access (if supported by backend)"""
        return self.backend.get_file_url(file_path, expires_in)
    
    def generate_download_token(self, dataset_id: int, user_id: Optional[int] = None, expires_in_hours: int = 24) -> str:
        """Generate a simple download token for a dataset"""
        # Simple token generation without expiry
        random_part = secrets.token_urlsafe(32)  # Longer random part for security
        
        # Create simple payload
        payload_parts = [
            str(dataset_id),
            str(user_id) if user_id else "anon"
        ]
        payload = "-".join(payload_parts)
        
        # Create hash without secret key dependency
        token_data = f"{payload}-{random_part}"
        token_hash = hashlib.sha256(token_data.encode()).hexdigest()[:16]
        
        # Return simple format: payload.random.hash
        return f"{payload}.{random_part}.{token_hash}"
    
    def validate_download_token(self, token: str) -> bool:
        """Validate simple download token format"""
        if not token or not isinstance(token, str):
            return False
        
        try:
            # Split token: payload.random.hash
            parts = token.split(".")
            if len(parts) != 3:
                return False
                
            payload, random_part, provided_hash = parts
            
            # Validate payload format (dataset_id-user_id or dataset_id-anon)
            if "-" not in payload:
                return False
                
            payload_parts = payload.split("-")
            if len(payload_parts) != 2:
                return False
                
            dataset_id_str, user_id_str = payload_parts
            
            # Validate dataset_id is numeric
            try:
                int(dataset_id_str)
            except ValueError:
                return False
            
            # Validate user_id is numeric or "anon"
            if user_id_str != "anon":
                try:
                    int(user_id_str)
                except ValueError:
                    return False
            
            # Validate random part length (should be ~43 chars for urlsafe_b64encode of 32 bytes)
            if len(random_part) < 40:
                return False
            
            # Validate hash format
            if len(provided_hash) != 16:
                return False
            
            # Verify hash
            token_data = f"{payload}-{random_part}"
            expected_hash = hashlib.sha256(token_data.encode()).hexdigest()[:16]
            
            return provided_hash == expected_hash
            
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return False
    
    async def cleanup_orphaned_files(self, db_session) -> Dict[str, Any]:
        """Clean up files that no longer have corresponding dataset records"""
        try:
            from app.models.dataset import Dataset
            
            cleanup_result = {
                "deleted_files": [],
                "errors": [],
                "total_cleaned": 0,
                "total_errors": 0
            }
            
            # Get all datasets with file paths
            datasets_with_files = db_session.query(Dataset).filter(
                (Dataset.file_path.isnot(None)) | (Dataset.source_url.isnot(None))
            ).all()
            
            # Create a set of valid file paths from existing datasets
            valid_paths = set()
            for dataset in datasets_with_files:
                if dataset.file_path:
                    valid_paths.add(dataset.file_path)
                if dataset.source_url and not dataset.source_url.startswith('http'):
                    valid_paths.add(dataset.source_url)
            
            # For local storage, scan the storage directory
            if isinstance(self.backend, LocalStorageBackend):
                storage_dir = self.backend.storage_dir
                
                if os.path.exists(storage_dir):
                    for root, dirs, files in os.walk(storage_dir):
                        for file in files:
                            full_path = os.path.join(root, file)
                            relative_path = os.path.relpath(full_path, storage_dir)
                            
                            # Check if this file is referenced by any dataset
                            is_orphaned = True
                            for valid_path in valid_paths:
                                if (full_path == valid_path or 
                                    relative_path == valid_path or
                                    file in valid_path):
                                    is_orphaned = False
                                    break
                            
                            if is_orphaned:
                                try:
                                    os.remove(full_path)
                                    cleanup_result["deleted_files"].append(full_path)
                                    cleanup_result["total_cleaned"] += 1
                                    logger.info(f"Deleted orphaned file: {full_path}")
                                except Exception as e:
                                    error_msg = f"Failed to delete {full_path}: {str(e)}"
                                    cleanup_result["errors"].append(error_msg)
                                    cleanup_result["total_errors"] += 1
                                    logger.error(error_msg)
            
            logger.info(f"Cleanup completed: {cleanup_result['total_cleaned']} files deleted, {cleanup_result['total_errors']} errors")
            return cleanup_result
            
        except Exception as e:
            logger.error(f"Orphaned file cleanup failed: {str(e)}")
            return {
                "error": str(e),
                "total_cleaned": 0,
                "total_errors": 1
            }

    def get_backend_info(self) -> Dict[str, Any]:
        """Get information about the current storage backend"""
        backend_type = type(self.backend).__name__
        
        info = {
            "backend_type": backend_type,
            "storage_type": os.getenv('STORAGE_TYPE', 'local')
        }
        
        if isinstance(self.backend, S3StorageBackend):
            info.update({
                "bucket_name": self.backend.bucket_name,
                "region": self.backend.region,
                "supports_presigned_urls": True
            })
        elif isinstance(self.backend, LocalStorageBackend):
            info.update({
                "storage_directory": self.backend.storage_dir,
                "supports_presigned_urls": False
            })
        
        return info

# Create a singleton instance
storage_service = StorageService()