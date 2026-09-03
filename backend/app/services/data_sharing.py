from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_
from app.models.user import User
from app.models.dataset import Dataset, DatasetAccessLog, DatasetChatSession, ChatMessage, DatasetShareAccess, DatabaseConnector, DatasetType
from app.models.organization import Organization, DataSharingLevel, UserRole
from datetime import datetime, timedelta
import logging
import secrets
import hashlib
import os
import pandas as pd
import numpy as np
from fastapi import HTTPException, status
from app.core.config import settings
from app.core.auth import get_password_hash, verify_password
from app.services.mindsdb import MindsDBService

logger = logging.getLogger(__name__)


class DataSharingService:
    """Service for managing organization-scoped data sharing and access control"""
    
    def __init__(self, db: Session):
        self.db = db
        self.mindsdb_service = MindsDBService()
    
    def can_access_dataset(self, user: User, dataset: Dataset) -> bool:
        """
        Check if a user can access a dataset based on sharing level.
        PUBLIC datasets are accessible to all users.
        ORGANIZATION datasets are accessible within the same organization.
        PRIVATE datasets are only accessible to owners.
        """
        # Check if dataset is deleted
        if dataset.is_deleted:
            return False
        
        # Owner can always access their own datasets (even if private)
        if dataset.owner_id == user.id:
            return True
        
        # Normalize sharing level to DataSharingLevel enum
        if isinstance(dataset.sharing_level, str):
            try:
                sharing_level = DataSharingLevel(dataset.sharing_level.lower())
            except ValueError:
                sharing_level = DataSharingLevel.PRIVATE
        else:
            sharing_level = dataset.sharing_level or DataSharingLevel.PRIVATE
        
        if sharing_level == DataSharingLevel.PUBLIC:
            # PUBLIC datasets are accessible to all users
            return True
        
        elif sharing_level == DataSharingLevel.ORGANIZATION:
            # ORGANIZATION datasets are accessible within the same organization
            return user.organization_id and user.organization_id == dataset.organization_id
        
        elif sharing_level == DataSharingLevel.PRIVATE:
            # PRIVATE datasets are only accessible to owners (already checked above)
            return False
        
        return False
    
    def can_download_dataset(self, user: User, dataset: Dataset) -> bool:
        """
        Check if a user can download a dataset.
        Download permissions are separate from view permissions.
        Handles both uploaded files and connector-based datasets.
        """
        # First check basic access permissions
        if not self.can_access_dataset(user, dataset):
            return False
        
        # Check if downloads are globally disabled for this dataset
        if not dataset.allow_download:
            return False
        
        # Owner can always download their own datasets
        if dataset.owner_id == user.id:
            return True
        
        # Check the dataset owner's organization policy because it controls data egress.
        org_download_policy = self._get_organization_download_policy(dataset.organization_id)
        
        # If organization has strict download policy, only owners and admins can download
        if org_download_policy.get("restrict_downloads", False):
            return user.role in ["owner", "admin"] or user.is_superuser
        
        # Check user role-based download permissions
        user_download_permissions = self._get_user_download_permissions(user)
        
        # If user has download restrictions, check them
        if user_download_permissions.get("download_restricted", False):
            allowed_sharing_levels = user_download_permissions.get("allowed_sharing_levels", [])
            return dataset.sharing_level.value in allowed_sharing_levels
        
        # Check dataset-specific download restrictions
        if hasattr(dataset, 'download_restrictions') and dataset.download_restrictions:
            restrictions = dataset.download_restrictions
            
            # Check role-based restrictions
            if "allowed_roles" in restrictions:
                if user.role not in restrictions["allowed_roles"]:
                    return False
        
        # Special handling for connector-based datasets
        is_connector_dataset = dataset.connector_id is not None
        if is_connector_dataset:
            # Check if connector-based downloads are restricted by organization policy
            if org_download_policy.get("restrict_connector_downloads", False):
                # Only admins and owners can download connector-based datasets if restricted
                if not (user.role in ["owner", "admin"] or user.is_superuser):
                    return False
            
            # Check if connector is active
            if dataset.connector and not dataset.connector.is_active:
                return False
            
            # Check connector-specific permissions
            connector_permissions = self._get_connector_download_permissions(user, dataset.connector_id)
            if not connector_permissions.get("can_download", True):
                return False
        else:
            # Check if uploaded file downloads are restricted by organization policy
            if org_download_policy.get("restrict_file_downloads", False):
                # Check user role against allowed roles for file downloads
                allowed_roles = org_download_policy.get("file_download_roles", ["owner", "admin", "manager", "member"])
                if user.role not in allowed_roles:
                    return False
        
        # Default: if user can access, they can download (unless restricted above)
        return True
        
    def _get_connector_download_permissions(self, user: User, connector_id: int) -> Dict[str, Any]:
        """Get connector-specific download permissions"""
        try:
            connector = self.db.query(DatabaseConnector).filter(
                DatabaseConnector.id == connector_id
            ).first()
            
            if not connector:
                return {"can_download": False}
            
            # Check if connector belongs to user's organization
            if connector.organization_id != user.organization_id:
                return {"can_download": False}
            
            # Default permissions
            permissions = {
                "can_download": True,
                "allowed_formats": ["csv", "json"],
                "max_rows": 100000
            }
            
            # Role-based connector permissions
            if user.role == "viewer":
                permissions.update({
                    "max_rows": 1000,
                    "allowed_formats": ["csv"]
                })
            elif user.role == "member":
                permissions.update({
                    "max_rows": 10000
                })
            elif user.role in ["admin", "owner"]:
                permissions.update({
                    "max_rows": None  # No limit
                })
            
            # Check connector type-specific restrictions
            connector_type = connector.connector_type
            if connector_type == "api":
                # API connectors might have special restrictions
                permissions.update({
                    "allowed_formats": ["json", "csv"],
                    "require_api_key": True
                })
            elif connector_type in ["mysql", "postgresql", "snowflake"]:
                # Database connectors
                permissions.update({
                    "allowed_formats": ["csv", "json", "excel"],
                    "allow_query_download": user.role in ["admin", "owner", "manager"]
                })
            
            return permissions
            
        except Exception as e:
            logger.error(f"Failed to get connector download permissions: {e}")
            return {"can_download": False}
    
    def _get_organization_download_policy(self, organization_id: int) -> Dict[str, Any]:
        """Get organization-level download policy"""
        try:
            organization = self.db.query(Organization).filter(
                Organization.id == organization_id
            ).first()
            
            if organization and hasattr(organization, 'download_policy'):
                return organization.download_policy or {}
            
            # Default policy with separate settings for uploaded files and connectors
            return {
                # General download settings
                "restrict_downloads": False,
                "require_approval": False,
                "allowed_file_types": ["csv", "json", "excel", "pdf", "parquet"],
                "max_file_size_mb": 1000,
                "rate_limit_per_hour": 50,
                "allow_compression": True,
                "allowed_compression_types": ["none", "zip", "gzip"],
                
                # Uploaded file specific settings
                "restrict_file_downloads": False,
                "file_download_roles": ["owner", "admin", "manager", "member", "viewer"],
                "file_max_size_mb": 1000,
                
                # Connector specific settings
                "restrict_connector_downloads": False,
                "connector_download_roles": ["owner", "admin", "manager"],
                "connector_max_rows": 100000,
                "connector_allowed_types": ["mysql", "postgresql", "s3", "api", "mongodb", "snowflake", "bigquery", "redshift"]
            }
            
        except Exception as e:
            logger.error(f"Failed to get organization download policy: {e}")
            return {"restrict_downloads": False}
    
    def _get_user_download_permissions(self, user: User) -> Dict[str, Any]:
        """Get user-specific download permissions"""
        try:
            # Check if user has specific download restrictions
            user_permissions = {
                "download_restricted": False,
                "allowed_sharing_levels": ["private", "department", "organization"],
                "max_downloads_per_day": 100,
                "allowed_file_types": ["csv", "json", "excel", "pdf"]
            }
            
            # Role-based permissions
            if user.role == "viewer":
                user_permissions.update({
                    "download_restricted": True,
                    "allowed_sharing_levels": ["organization"],
                    "max_downloads_per_day": 10
                })
            elif user.role == "member":
                user_permissions.update({
                    "max_downloads_per_day": 50
                })
            elif user.role in ["admin", "owner"]:
                user_permissions.update({
                    "max_downloads_per_day": 1000
                })
            
            return user_permissions
            
        except Exception as e:
            logger.error(f"Failed to get user download permissions: {e}")
            return {"download_restricted": False}
    
    def check_download_rate_limit(self, user: User) -> Dict[str, Any]:
        """Check if user has exceeded download rate limits"""
        try:
            from app.models.dataset import DatasetDownload
            from datetime import datetime, timedelta
            
            # Get user's download permissions
            permissions = self._get_user_download_permissions(user)
            max_downloads = permissions.get("max_downloads_per_day", 100)
            
            # Count downloads in the last 24 hours
            since_time = datetime.utcnow() - timedelta(hours=24)
            recent_downloads = self.db.query(DatasetDownload).filter(
                DatasetDownload.user_id == user.id,
                DatasetDownload.started_at >= since_time,
                DatasetDownload.download_status == "completed"
            ).count()
            
            # Check organization-level rate limits
            org_policy = self._get_organization_download_policy(user.organization_id)
            org_rate_limit = org_policy.get("rate_limit_per_hour", 50)
            
            # Count downloads in the last hour
            since_hour = datetime.utcnow() - timedelta(hours=1)
            recent_hour_downloads = self.db.query(DatasetDownload).filter(
                DatasetDownload.user_id == user.id,
                DatasetDownload.started_at >= since_hour,
                DatasetDownload.download_status == "completed"
            ).count()
            
            return {
                "allowed": recent_downloads < max_downloads and recent_hour_downloads < org_rate_limit,
                "daily_limit": max_downloads,
                "daily_used": recent_downloads,
                "hourly_limit": org_rate_limit,
                "hourly_used": recent_hour_downloads,
                "reset_time": (datetime.utcnow() + timedelta(hours=24 - datetime.utcnow().hour)).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to check download rate limit: {e}")
            return {"allowed": True, "error": str(e)}
    
    def log_download_attempt(
        self, 
        user: User, 
        dataset: Dataset, 
        success: bool,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """Log download attempt for audit and rate limiting"""
        try:
            # Log as access log
            access_type = "download_success" if success else "download_failed"
            self.log_access(user, dataset, access_type, ip_address)
            
            # Additional download-specific logging could be added here
            if not success and error_message:
                logger.warning(f"Download failed for user {user.id}, dataset {dataset.id}: {error_message}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to log download attempt: {e}")
            return False
    
    def get_accessible_datasets(self, user: User,
                              sharing_level: Optional[DataSharingLevel] = None,
                              include_inactive: bool = False,
                              include_deleted: bool = False,
                              dataset_type: Optional[DatasetType] = None,
                              skip: Optional[int] = None,
                              limit: Optional[int] = None) -> List[Dataset]:
        """
        Get datasets accessible to a user.
        """
        query = self.db.query(Dataset).options(selectinload(Dataset.owner))

        if not include_deleted:
            query = query.filter(Dataset.is_deleted == False)

        if not include_inactive:
            query = query.filter(Dataset.is_active == True)

        if sharing_level:
            query = query.filter(Dataset.sharing_level == sharing_level)

        if dataset_type:
            query = query.filter(Dataset.type == dataset_type)

        public_levels = [DataSharingLevel.PUBLIC, DataSharingLevel.PUBLIC.value]
        organization_levels = [DataSharingLevel.ORGANIZATION, DataSharingLevel.ORGANIZATION.value]
        query = query.filter(or_(
            Dataset.owner_id == user.id,
            Dataset.sharing_level.in_(public_levels),
            and_(
                Dataset.organization_id == user.organization_id,
                Dataset.sharing_level.in_(organization_levels)
            )
        ))

        query = query.order_by(Dataset.created_at.desc(), Dataset.id.desc())

        if skip is not None:
            query = query.offset(skip)

        if limit is not None:
            query = query.limit(limit)

        return query.all()

    def get_organization_datasets(self, organization_id: int,
                                user: User) -> List[Dataset]:
        """
        Get all datasets for an organization (admin/manager view).
        Only organization admins/owners can see all datasets.
        """
        if (not user.organization_id or 
            user.organization_id != organization_id or
            user.role not in ["owner", "admin"]):
            return []
        
        return self.db.query(Dataset).filter(
            Dataset.organization_id == organization_id
        ).all()
    
    def log_access(self, user: User, dataset: Dataset, access_type: str,
                   ip_address: Optional[str] = None, 
                   user_agent: Optional[str] = None) -> bool:
        """Log dataset access for audit purposes"""
        if not self.can_access_dataset(user, dataset):
            return False
        
        access_log = DatasetAccessLog(
            dataset_id=dataset.id,
            user_id=user.id,
            access_type=access_type,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.db.add(access_log)
        self.db.commit()
        
        # Update last accessed timestamp
        dataset.last_accessed = access_log.created_at
        self.db.commit()
        
        return True
    
    def get_organization_stats(self, organization_id: int, user: User) -> dict:
        """
        Get organization data usage statistics.
        Only available to organization admins/owners.
        """
        if (not user.organization_id or 
            user.organization_id != organization_id or
            user.role not in ["owner", "admin"]):
            return {}
        
        datasets = self.db.query(Dataset).filter(
            Dataset.organization_id == organization_id
        ).all()
        
        total_datasets = len(datasets)
        
        # Count by sharing level
        sharing_stats = {
            DataSharingLevel.PRIVATE: 0,
            DataSharingLevel.ORGANIZATION: 0,
            DataSharingLevel.PUBLIC: 0
        }
        
        total_size = 0
        for dataset in datasets:
            # Normalize sharing level
            if isinstance(dataset.sharing_level, str):
                try:
                    level = DataSharingLevel(dataset.sharing_level.lower())
                except ValueError:
                    level = DataSharingLevel.PRIVATE
            else:
                level = dataset.sharing_level or DataSharingLevel.PRIVATE
            
            sharing_stats[level] += 1
            if dataset.size_bytes:
                total_size += dataset.size_bytes
        
        # Recent access count
        recent_accesses = self.db.query(DatasetAccessLog).join(Dataset).filter(
            Dataset.organization_id == organization_id
        ).count()
        
        return {
            "total_datasets": total_datasets,
            "total_size_bytes": total_size,
            "sharing_levels": sharing_stats,
            "recent_accesses": recent_accesses,
            "organization_id": organization_id
        }
    
    def validate_dataset_creation(self, user: User, organization_id: int) -> bool:
        """
        Validate if user can create dataset in the organization.
        Users can only create datasets in their own organization.
        """
        return (user.organization_id == organization_id and
               user.role in ["owner", "admin", "manager", "member"])
    
    def update_sharing_level(self, user: User, dataset: Dataset, 
                           new_sharing_level: DataSharingLevel) -> bool:
        """
        Update dataset sharing level within organization.
        Only owner and admins can change sharing levels.
        """
        # Check permissions
        if not (dataset.owner_id == user.id or 
               (user.organization_id == dataset.organization_id and 
                user.role in ["owner", "admin"])):
            return False
        
        dataset.sharing_level = new_sharing_level
        self.db.commit()
        
        logger.info(f"Dataset {dataset.id} sharing level updated to {new_sharing_level} by user {user.id}")
        return True
    
    def get_sharing_stats(self, organization_id: int, user: User) -> dict:
        """
        Get data sharing statistics for an organization (organization-scoped only)
        """
        if (not user.organization_id or 
            user.organization_id != organization_id or
            user.role not in ["owner", "admin"]):
            return {}
        
        # Get datasets by sharing level
        datasets = self.db.query(Dataset).filter(
            Dataset.organization_id == organization_id
        ).all()
        
        stats = {
            "total_datasets": len(datasets),
            "by_sharing_level": {
                "private": 0,
                "organization": 0,
                "public": 0
            },
            "by_type": {},
            "total_access_logs": 0,
            "unique_users_accessed": 0
        }
        
        # Count by sharing level
        for dataset in datasets:
            # Normalize sharing level to string value
            if isinstance(dataset.sharing_level, str):
                level = dataset.sharing_level.lower()
            elif dataset.sharing_level:
                level = dataset.sharing_level.value
            else:
                level = "private"
            
            if level in stats["by_sharing_level"]:
                stats["by_sharing_level"][level] += 1
            
            # Count by type
            dataset_type = dataset.type.value if dataset.type else "unknown"
            stats["by_type"][dataset_type] = stats["by_type"].get(dataset_type, 0) + 1
        
        # Get access statistics
        access_logs = self.db.query(DatasetAccessLog).join(Dataset).filter(
            Dataset.organization_id == organization_id
        ).all()
        
        stats["total_access_logs"] = len(access_logs)
        stats["unique_users_accessed"] = len(set(log.user_id for log in access_logs))
        
        return stats
    
    def get_organization_shared_datasets(
        self, 
        organization_id: int, 
        user: User
    ) -> List[Dataset]:
        """
        Get all datasets shared at organization level (organization-scoped only)
        """
        # Check if user has access to this organization
        if (not user.organization_id or 
            user.organization_id != organization_id):
            return []
        
        return self.db.query(Dataset).filter(
            Dataset.organization_id == organization_id,
            Dataset.sharing_level == DataSharingLevel.ORGANIZATION
        ).all()

    def verify_share_password(self, dataset: Dataset, password: Optional[str]) -> bool:
        if not dataset.share_password:
            return True
        if not password:
            return False
        try:
            return verify_password(password, dataset.share_password)
        except Exception:
            return password == dataset.share_password

    def require_share_password(self, dataset: Dataset, password: Optional[str]) -> None:
        if not self.verify_share_password(dataset, password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )

    def create_share_link(
        self,
        dataset_id: int,
        user_id: int,
        password: Optional[str] = None,
        enable_chat: bool = True
    ) -> Dict[str, Any]:
        """Create a shareable link for a dataset."""
        dataset = self.db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.owner_id == user_id
        ).first()

        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dataset not found or access denied"
            )

        if not dataset.organization or not dataset.organization.allow_external_sharing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="External sharing is disabled for this organization"
            )

        # Generate unique share token
        share_token = self._generate_share_token(dataset_id, user_id)

        # Update dataset with sharing information
        dataset.public_share_enabled = True
        dataset.share_token = share_token
        dataset.share_password = get_password_hash(password) if password else None
        dataset.ai_chat_enabled = enable_chat and dataset.allow_ai_chat and settings.ENABLE_AI_CHAT
        
        # Only create proxy connector for connector-based datasets, not uploaded files
        if dataset.connector_id:
            self._create_dataset_proxy_connector_sync(dataset, share_token)
            logger.info(f"Created proxy connector for connector-based dataset: {dataset.name}")
        else:
            logger.info(f"Skipping proxy connector creation for uploaded file: {dataset.name}")
        
        self.db.commit()
        self.db.refresh(dataset)
        
        # Initialize AI context if chat is enabled
        if dataset.ai_chat_enabled:
            self._initialize_ai_context(dataset)
        
        share_url = f"/shared/{share_token}"
        
        return {
            "share_token": share_token,
            "share_url": share_url,
            "chat_enabled": dataset.ai_chat_enabled,
            "password_protected": bool(password),
            "dataset_name": dataset.name
        }

    async def get_shared_dataset(
        self,
        share_token: str,
        password: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get dataset information via share token."""
        dataset = self.db.query(Dataset).filter(
            Dataset.share_token == share_token,
            Dataset.public_share_enabled == True,
            Dataset.is_deleted == False,
            Dataset.is_active == True
        ).first()
        
        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared dataset not found or no longer available"
            )
        
        self.require_share_password(dataset, password)

        # Check if dataset depends on a connector and validate connector status
        if dataset.connector_id:
            connector = self.db.query(DatabaseConnector).filter(
                DatabaseConnector.id == dataset.connector_id,
                DatabaseConnector.is_deleted == False,
                DatabaseConnector.is_active == True
            ).first()
            
            if not connector:
                # Disable sharing if connector is gone
                dataset.public_share_enabled = False
                self.db.commit()
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="Dataset source is no longer available"
                )
        
        # Check if uploaded file(s) still exist (for non-connector datasets)
        elif dataset.file_path or dataset.is_multi_file_dataset:
            file_exists = False
            
            if dataset.is_multi_file_dataset:
                # Check if any files exist for multi-file dataset
                from app.models.dataset import DatasetFile
                existing_files = self.db.query(DatasetFile).filter(
                    DatasetFile.dataset_id == dataset.id,
                    DatasetFile.is_deleted == False
                ).all()
                
                # Use storage service to check file existence properly
                from app.services.storage import storage_service
                
                file_exists = False
                for f in existing_files:
                    if f.file_path:
                        # Check if file exists using storage service (works for both S3 and local)
                        try:
                            file_path = f.relative_path or f.file_path
                            if await storage_service.dataset_file_exists(file_path):
                                file_exists = True
                                break
                        except Exception as e:
                            logger.debug(f"File check failed for {f.file_path}: {e}")
                            continue
                
                if not file_exists:
                    # Disable sharing if no files exist
                    dataset.public_share_enabled = False
                    self.db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_410_GONE,
                        detail="Dataset files are no longer available"
                    )
            elif dataset.file_path:
                # Single file check - use proper path resolution
                from app.services.storage import storage_service
                try:
                    # Use storage service to check file existence (works for both S3 and local)
                    file_exists = await storage_service.dataset_file_exists(dataset.file_path)
                except Exception:
                    file_exists = False
                
                if not file_exists:
                    # Disable sharing if file doesn't exist
                    dataset.public_share_enabled = False
                    self.db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_410_GONE,
                        detail="Dataset file is no longer available"
                    )
        
        # Log access
        self._log_share_access(dataset, share_token, ip_address, user_agent)
        
        # Update view count
        dataset.share_view_count += 1
        dataset.last_accessed = datetime.utcnow()
        self.db.commit()
        
        # Get preview data if available
        preview_data = None
        try:
            import pandas as pd
            
            # Handle multi-file datasets
            if dataset.is_multi_file_dataset:
                from app.models.dataset import DatasetFile
                
                # Get primary file or first file for preview
                dataset_files = self.db.query(DatasetFile).filter(
                    DatasetFile.dataset_id == dataset.id,
                    DatasetFile.is_deleted == False
                ).order_by(DatasetFile.is_primary.desc(), DatasetFile.file_order.asc()).all()
                
                if dataset_files:
                    primary_file = dataset_files[0]  # First file (primary or first by order)
                    
                    preview_data = {
                        "type": "multi_file",
                        "total_files": len(dataset_files),
                        "files_list": [{
                            "filename": f.filename,
                            "file_type": f.file_type,
                            "file_size": f.file_size,
                            "is_primary": f.is_primary
                        } for f in dataset_files[:5]],  # Show first 5 files
                        "primary_file": {
                            "filename": primary_file.filename,
                            "file_type": primary_file.file_type
                        }
                    }
                    
                    # Try to preview primary file if it's CSV (only for local storage for now)
                    if (primary_file.file_type and primary_file.file_type.lower() == 'csv'
                        and primary_file.file_path and hasattr(storage_service.backend, 'storage_dir')):
                        try:
                            # Resolve full path for local storage
                            full_file_path = os.path.join(storage_service.backend.storage_dir, primary_file.file_path)
                            if os.path.exists(full_file_path):
                                df = pd.read_csv(full_file_path, nrows=10)
                            else:
                                raise FileNotFoundError(f"File not found: {full_file_path}")  # Skip preview if file doesn't exist
                            headers = df.columns.tolist()
                            rows = []
                            for row in df.values:
                                converted_row = []
                                for val in row:
                                    if pd.isna(val):
                                        converted_row.append(None)
                                    elif isinstance(val, (np.integer, int)):
                                        converted_row.append(int(val))
                                    elif isinstance(val, (np.floating, float)):
                                        converted_row.append(float(val))
                                    elif isinstance(val, np.bool_):
                                        converted_row.append(bool(val))
                                    else:
                                        converted_row.append(str(val))
                                rows.append(converted_row)
                            
                            preview_data.update({
                                "headers": headers,
                                "rows": rows,
                                "total_rows": len(rows),
                                "preview_source": "primary_file"
                            })
                        except Exception as e:
                            logger.warning(f"Failed to preview primary file {primary_file.filename}: {e}")
                            
            # Handle single file datasets
            elif dataset.file_path:
                # Check file existence using storage service (works for both S3 and local)
                file_exists = False
                actual_file_path = None
                from app.services.storage import storage_service
                try:
                    file_exists = await storage_service.dataset_file_exists(dataset.file_path)
                    # For local storage, set actual file path for CSV preview
                    if file_exists and hasattr(storage_service.backend, 'storage_dir'):
                        actual_file_path = os.path.join(storage_service.backend.storage_dir, dataset.file_path)
                except Exception:
                    file_exists = False

                if file_exists and actual_file_path:
                    if dataset.type.value.lower() == 'csv':
                        df = pd.read_csv(actual_file_path, nrows=10)
                        headers = df.columns.tolist()

                        # Convert to native Python types
                        rows = []
                        for row in df.values:
                            converted_row = []
                            for val in row:
                                if pd.isna(val):
                                    converted_row.append(None)
                                elif isinstance(val, (np.integer, int)):
                                    converted_row.append(int(val))
                                elif isinstance(val, (np.floating, float)):
                                    converted_row.append(float(val))
                                elif isinstance(val, np.bool_):
                                    converted_row.append(bool(val))
                                else:
                                    converted_row.append(str(val))
                            rows.append(converted_row)

                        preview_data = {
                            "headers": headers,
                            "rows": rows,
                            "total_rows": len(rows),
                            "type": "csv",
                            "preview_source": "single_file"
                        }
                    
            if preview_data and preview_data.get('rows'):
                logger.info(f"Generated preview data for shared dataset {dataset.id}: {len(preview_data.get('rows', []))} rows of {preview_data.get('type', 'unknown')} data")
            else:
                logger.debug(f"No preview data available for shared dataset {dataset.id} (file not found or unsupported format)")
        except Exception as e:
            logger.warning(f"Failed to generate preview for shared dataset {dataset.id}: {e}")
            
        # Determine if this is an uploaded file or a connector dataset
        # Check if there are files in dataset_files table (for new upload system)
        has_dataset_files = False
        if dataset.id:
            from app.models.dataset import DatasetFile
            dataset_files_count = self.db.query(DatasetFile).filter(
                DatasetFile.dataset_id == dataset.id,
                DatasetFile.is_deleted == False
            ).count()
            has_dataset_files = dataset_files_count > 0
        
        is_uploaded_file = bool(
            (dataset.source_url and not dataset.source_url.startswith('http')) or
            dataset.is_multi_file_dataset or
            dataset.file_path or
            has_dataset_files or
            # Fallback: if no connector_id and it's a file type, assume uploaded
            (not dataset.connector_id and dataset.type.value.lower() in [
                'pdf', 'csv', 'json', 'excel', 'txt', 'docx', 'doc', 'rtf', 'odt', 'image'
            ])
        )
        
        # Only include proxy connection info for connector-based datasets, not uploaded files
        proxy_connection_info = None
        if dataset.connector_id:
            # For connector datasets, provide connection info only
            # Get base URL dynamically
            base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
            proxy_connection_info = {
                "connection_type": dataset.type.value,
                "proxy_url": f"{base_url}/api/proxy",
                "access_token": share_token,
                "database_name": dataset.name,
                "supports_sql": dataset.type.value in ['csv', 'database', 'api']
            }

        return {
            "dataset_id": dataset.id,
            "dataset_name": dataset.name,
            "description": dataset.description,
            "file_type": dataset.type.value if hasattr(dataset.type, 'value') else str(dataset.type),
            "size_bytes": dataset.size_bytes,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
            "schema_info": dataset.schema_info,
            "ai_summary": dataset.ai_summary,
            "ai_insights": dataset.ai_insights,
            "enable_chat": dataset.ai_chat_enabled,
            "allow_download": dataset.allow_download,
            "created_at": dataset.created_at,
            "share_token": share_token,
            "access_allowed": True,
            "requires_password": bool(dataset.share_password),
            "owner_name": dataset.owner.full_name if dataset.owner else None,
            "organization_name": dataset.organization.name if dataset.organization else None,
            "shared_at": dataset.created_at,
            "preview_data": preview_data,
            "is_uploaded_file": is_uploaded_file,
            "is_connector_dataset": bool(dataset.connector_id),
            "has_proxy_connection": bool(proxy_connection_info),
            "proxy_connection_info": proxy_connection_info
        }

    def create_chat_session(
        self,
        share_token: str,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new chat session for a shared dataset."""
        dataset = self.db.query(Dataset).filter(
            Dataset.share_token == share_token,
            Dataset.public_share_enabled == True,
            Dataset.ai_chat_enabled == True,
            Dataset.is_deleted == False,
            Dataset.is_active == True
        ).first()
        
        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dataset not found or chat not enabled"
            )
        
        # Check session limits
        active_sessions = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.dataset_id == dataset.id,
            DatasetChatSession.is_active == True
        ).count()
        
        if active_sessions >= settings.MAX_CHAT_SESSIONS_PER_DATASET:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum chat sessions reached for this dataset"
            )
        
        # Create session
        session_token = self._generate_session_token()
        system_prompt = self._generate_system_prompt(dataset)
        
        chat_session = DatasetChatSession(
            dataset_id=dataset.id,
            user_id=user_id,
            session_token=session_token,
            share_token=share_token,
            ip_address=ip_address,
            user_agent=user_agent,
            ai_model_name=dataset.chat_model_name or settings.DEFAULT_GEMINI_MODEL,
            system_prompt=system_prompt,
            context_data=dataset.chat_context
        )
        
        self.db.add(chat_session)
        self.db.commit()
        self.db.refresh(chat_session)
        
        return {
            "session_token": session_token,
                            "model_name": chat_session.ai_model_name,
            "dataset_name": dataset.name,
            "system_prompt": system_prompt
        }

    def send_chat_message(
        self,
        session_token: str,
        message: str,
        message_type: str = "user"
    ) -> Dict[str, Any]:
        """Send a message in a chat session."""
        session = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.session_token == session_token,
            DatasetChatSession.is_active == True
        ).first()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found"
            )
        
        dataset = session.dataset

        # Verify dataset is still accessible for chat
        if not dataset or dataset.is_deleted or not dataset.is_active or not dataset.ai_chat_enabled:
            session.is_active = False
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Dataset is no longer available for chat"
            )

        # Save user message
        user_message = ChatMessage(
            session_id=session.id,
            message_type=message_type,
            content=message,
            created_at=datetime.utcnow()
        )
        self.db.add(user_message)
        
        try:
            # Get AI response
            start_time = datetime.utcnow()
            ai_response = self._get_ai_response(dataset, session, message)
            processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Save AI response
            ai_message = ChatMessage(
                session_id=session.id,
                message_type="assistant",
                content=ai_response["content"],
                message_metadata=ai_response.get("metadata"),
                tokens_used=ai_response.get("tokens_used"),
                processing_time_ms=processing_time,
                model_version=session.ai_model_name,
                created_at=datetime.utcnow()
            )
            self.db.add(ai_message)
            
            # Update session stats
            session.message_count += 2  # user + assistant
            session.total_tokens_used += ai_response.get("tokens_used", 0)
            session.updated_at = datetime.utcnow()
            
            self.db.commit()
            
            return {
                "user_message": {
                    "id": user_message.id,
                    "content": user_message.content,
                    "type": user_message.message_type,
                    "created_at": user_message.created_at
                },
                "ai_response": {
                    "id": ai_message.id,
                    "content": ai_message.content,
                    "type": ai_message.message_type,
                    "tokens_used": ai_message.tokens_used,
                    "processing_time_ms": ai_message.processing_time_ms,
                    "created_at": ai_message.created_at
                }
            }
            
        except Exception as e:
            self.db.rollback()
            # Save error message
            error_message = ChatMessage(
                session_id=session.id,
                message_type="system",
                content=f"Error processing message: {str(e)}",
                created_at=datetime.utcnow()
            )
            self.db.add(error_message)
            self.db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error processing chat message"
            )

    def get_chat_history(self, session_token: str) -> List[Dict[str, Any]]:
        """Get chat history for a session."""
        session = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.session_token == session_token
        ).first()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found"
            )
        
        # Verify dataset is still accessible
        dataset = session.dataset
        if not dataset or dataset.is_deleted or not dataset.is_active:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Dataset is no longer available"
            )

        messages = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at).all()
        
        return [
            {
                "id": msg.id,
                "type": msg.message_type,
                "content": msg.content,
                "metadata": msg.message_metadata,
                "tokens_used": msg.tokens_used,
                "processing_time_ms": msg.processing_time_ms,
                "created_at": msg.created_at
            }
            for msg in messages
        ]

    def end_chat_session(self, session_token: str) -> bool:
        """End a chat session."""
        session = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.session_token == session_token
        ).first()
        
        if not session:
            return False
        
        session.is_active = False
        session.ended_at = datetime.utcnow()
        self.db.commit()
        
        return True

    def get_dataset_analytics(self, dataset_id: int, user_id: int) -> Dict[str, Any]:
        """Get analytics for a shared dataset."""
        dataset = self.db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.owner_id == user_id
        ).first()
        
        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dataset not found"
            )
        
        # Get access statistics
        total_accesses = self.db.query(DatasetShareAccess).filter(
            DatasetShareAccess.dataset_id == dataset_id
        ).count()
        
        chat_sessions = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.dataset_id == dataset_id
        ).count()
        
        total_messages = self.db.query(ChatMessage).join(DatasetChatSession).filter(
            DatasetChatSession.dataset_id == dataset_id
        ).count()
        
        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "share_enabled": dataset.public_share_enabled,
            "view_count": dataset.share_view_count,
            "total_accesses": total_accesses,
            "chat_sessions": chat_sessions,
            "total_chat_messages": total_messages,
            "created_at": dataset.created_at,
            "last_accessed": dataset.last_accessed
        }

    def _generate_share_token(self, dataset_id: int, user_id: int) -> str:
        """Generate a unique share token."""
        data = f"{dataset_id}-{user_id}-{datetime.utcnow().isoformat()}-{secrets.token_hex(16)}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _generate_session_token(self) -> str:
        """Generate a unique session token."""
        return secrets.token_urlsafe(32)

    def _log_share_access(
        self,
        dataset: Dataset,
        share_token: str,
        ip_address: Optional[str],
        user_agent: Optional[str]
    ):
        """Log access to a shared dataset."""
        access_log = DatasetShareAccess(
            dataset_id=dataset.id,
            share_token=share_token,
            ip_address=ip_address,
            user_agent=user_agent
        )
        self.db.add(access_log)
        self.db.commit()

    def _initialize_ai_context(self, dataset: Dataset):
        """Initialize AI context for dataset chat with file access."""
        if not dataset.chat_context:
            # Get file URL for MindsDB access
            file_url = None
            if dataset.file_path or dataset.source_url:
                from app.services.storage import storage_service
                try:
                    file_path = dataset.file_path or dataset.source_url
                    file_url = storage_service.get_dataset_file_url(file_path, expires_in=86400)  # 24 hours
                    if file_url and not file_url.startswith('http'):
                        # Convert relative URL to absolute for external access
                        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
                        file_url = f"{base_url}{file_url}"
                except Exception as e:
                    logger.warning(f"Failed to generate file URL for dataset {dataset.id}: {str(e)}")
            
            # Create MindsDB dataset connection if file URL is available
            mindsdb_datasource = None
            if file_url and dataset.type in ["csv", "json"]:
                try:
                    logger.info(f"Creating MindsDB dataset connection for {dataset.name}")
                    connection_result = self.mindsdb_service.create_dataset_connection(
                        dataset_name=dataset.name,
                        file_url=file_url,
                        file_type=dataset.type.value if hasattr(dataset.type, 'value') else str(dataset.type)
                    )
                    if connection_result.get("status") == "success":
                        mindsdb_datasource = connection_result.get("datasource_name")
                        logger.info(f"✅ MindsDB datasource created: {mindsdb_datasource}")
                    else:
                        logger.warning(f"⚠️ MindsDB datasource creation failed: {connection_result.get('message')}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to create MindsDB datasource: {str(e)}")

            context = {
                "dataset_name": dataset.name,
                "description": dataset.description,
                "type": dataset.type,
                "columns": dataset.schema_info.get("columns", []) if dataset.schema_info else [],
                "row_count": dataset.row_count,
                "summary": dataset.ai_summary,
                "file_url": file_url,
                "file_path": dataset.file_path,
                "accessible_via_url": bool(file_url),
                "mindsdb_datasource": mindsdb_datasource,
                "mindsdb_available": bool(mindsdb_datasource)
            }
            dataset.chat_context = context
            dataset.chat_model_name = settings.DEFAULT_GEMINI_MODEL
            self.db.commit()

    def _generate_system_prompt(self, dataset: Dataset) -> str:
        """Generate system prompt for AI chat."""
        # Handle dataset type properly
        dataset_type = dataset.type.value if hasattr(dataset.type, 'value') else str(dataset.type)
        
        prompt = f"""You are an AI assistant helping users understand and analyze the dataset "{dataset.name}".

Dataset Information:
- Name: {dataset.name}
- Description: {dataset.description or 'No description provided'}
- Type: {dataset_type}
- Rows: {dataset.row_count or 'Unknown'}
- Columns: {dataset.column_count or 'Unknown'}

"""
        
        if dataset.schema_info and "columns" in dataset.schema_info:
            prompt += "Dataset Schema:\n"
            for col in dataset.schema_info["columns"]:
                prompt += f"- {col.get('name', 'Unknown')}: {col.get('type', 'Unknown')}\n"
            prompt += "\n"
        
        if dataset.ai_summary:
            prompt += f"Dataset Summary: {dataset.ai_summary}\n\n"
        
        # Add file access information if available
        if dataset.chat_context and dataset.chat_context.get('file_url'):
            file_url = dataset.chat_context.get('file_url')
            prompt += f"""File Access:
- Dataset is accessible via URL: {file_url}
- You can reference this URL for analysis or suggest how users can access the data
- File format: {dataset_type}

"""
        else:
            prompt += """File Access:
- Dataset file is not directly accessible via URL
- Analysis is based on metadata and schema information only

"""
        
        prompt += """You can help users:
1. Understand the dataset structure and content
2. Answer questions about the data
3. Suggest analysis approaches and SQL queries when file is accessible
4. Explain data patterns and insights
5. Help with data interpretation
6. Provide guidance on accessing and analyzing the data

Please provide helpful, accurate, and concise responses. If you're unsure about something, let the user know."""
        
        return prompt

    def _get_ai_response(
        self,
        dataset: Dataset,
        session: DatasetChatSession,
        user_message: str
    ) -> Dict[str, Any]:
        """Get AI response using MindsDB Gemini integration."""
        try:
            # Prepare enhanced context for AI with file access info
            file_access_info = ""
            if dataset.chat_context and dataset.chat_context.get('file_url'):
                file_url = dataset.chat_context.get('file_url')
                file_access_info = f"""
File Access Available: YES
File URL: {file_url}
File Type: {dataset.type}
Note: The AI can reference this URL for data analysis suggestions."""
            else:
                file_access_info = """
File Access Available: NO
Note: Analysis limited to metadata and schema information."""

            context = f"""Dataset: {dataset.name}
User Question: {user_message}

Dataset Context: {dataset.chat_context}
{file_access_info}

Instructions: When answering, consider whether the dataset file is accessible via URL. If accessible, you can suggest specific analysis methods, SQL queries, or data manipulation techniques that work with the actual file. If not accessible, focus on insights from metadata and schema."""
            
            # Use MindsDB service to get response
            response = self.mindsdb_service.ai_chat(
                message=context,
                model_name=session.ai_model_name
            )
            
            return {
                "content": response.get("answer", "I'm sorry, I couldn't process your request.") if response else "I'm sorry, I couldn't process your request.",
                "metadata": response.get("metadata") if response else None,
                "tokens_used": response.get("tokens_used", 0) if response else 0
            }
            
        except Exception as e:
            return {
                "content": f"I encountered an error while processing your request: {str(e)}",
                "metadata": {"error": True},
                "tokens_used": 0
            }

    async def _create_dataset_proxy_connector(self, dataset: Dataset, share_token: str):
        """Create a proxy connector for dataset API access"""
        try:
            from app.models.proxy_connector import ProxyConnector
            from app.services.proxy_service import ProxyService
            import json
            from urllib.parse import quote
            
            # Check if proxy connector already exists for this dataset
            # Try both original name and URL-safe name to handle existing connectors
            existing_connector = self.db.query(ProxyConnector).filter(
                or_(
                    ProxyConnector.name == dataset.name,
                    ProxyConnector.name == quote(dataset.name, safe='')
                ),
                ProxyConnector.organization_id == dataset.organization_id,
                ProxyConnector.is_active == True
            ).first()
            
            if existing_connector:
                logger.info(f"Proxy connector already exists for dataset {dataset.name}")
                return existing_connector
            
            # Create proxy connector configuration for external API access
            # Use port 8000 for data sharing endpoints
            connection_config = {
                "base_url": f"http://localhost:8000/api/data-sharing/public/shared/{share_token}",
                "dataset_id": dataset.id,
                "share_token": share_token,
                "type": "dataset_api"
            }
            
            credentials = {
                "token": share_token,
                "auth_type": "share_token"
            }
            
            # Create proxy connector
            proxy_service = ProxyService()
            proxy_connector = await proxy_service.create_proxy_connector(
                db=self.db,
                name=dataset.name,
                connector_type="api",
                real_connection_config=connection_config,
                real_credentials=credentials,
                organization_id=dataset.organization_id,
                user_id=dataset.owner_id,
                description=f"API access for shared dataset: {dataset.description or dataset.name}",
                is_public=True,
                allowed_operations=["GET", "POST"]
            )
            
            logger.info(f"Created proxy connector for dataset {dataset.name}")
            return proxy_connector
            
        except Exception as e:
            logger.error(f"Failed to create proxy connector for dataset {dataset.name}: {e}")
            # Don't fail the sharing process if proxy connector creation fails
            return None

    def _create_dataset_proxy_connector_sync(self, dataset: Dataset, share_token: str):
        """Create a proxy connector for dataset API access (synchronous version)"""
        try:
            from app.models.proxy_connector import ProxyConnector
            import json
            import uuid
            from urllib.parse import quote
            
            # Check if proxy connector already exists for this dataset
            # Try both original name and URL-safe name to handle existing connectors
            existing_connector = self.db.query(ProxyConnector).filter(
                or_(
                    ProxyConnector.name == dataset.name,
                    ProxyConnector.name == quote(dataset.name, safe='')
                ),
                ProxyConnector.organization_id == dataset.organization_id,
                ProxyConnector.is_active == True
            ).first()
            
            if existing_connector:
                logger.info(f"Proxy connector already exists for dataset {dataset.name}")
                return existing_connector
            
            # Create proxy connector configuration based on dataset's connector
            if dataset.connector_id:
                # Get the original connector configuration
                original_connector = self.db.query(DatabaseConnector).filter(
                    DatabaseConnector.id == dataset.connector_id
                ).first()
                
                if original_connector and original_connector.connection_config:
                    # Use the original connector's configuration
                    original_config = original_connector.connection_config
                    connection_config = {
                        "base_url": original_config.get("base_url", "https://jsonplaceholder.typicode.com"),
                        "endpoint": original_config.get("endpoint", "/"),
                        "dataset_id": dataset.id,
                        "share_token": share_token,
                        "type": "dataset_api"
                    }
                else:
                    connection_config = {
                        "base_url": "https://jsonplaceholder.typicode.com",  # Default fallback
                        "dataset_id": dataset.id,
                        "share_token": share_token,
                        "type": "dataset_api"
                    }
            else:
                # Use dataset's source_url if available
                source_url = dataset.source_url or "https://jsonplaceholder.typicode.com/comments"
                if source_url.count('/') > 2:  # Has path component
                    base_url = '/'.join(source_url.split('/')[:3])  # protocol://host:port
                    endpoint = '/' + '/'.join(source_url.split('/')[3:])  # /path/to/endpoint
                else:
                    base_url = source_url
                    endpoint = "/"
                
                connection_config = {
                    "base_url": base_url,
                    "endpoint": endpoint,
                    "dataset_id": dataset.id,
                    "share_token": share_token,
                    "type": "dataset_api"
                }
            
            credentials = {
                "api_key": None,
                "auth_type": "none"
            }
            
            # Create proxy connector directly
            proxy_connector = ProxyConnector(
                proxy_id=str(uuid.uuid4()),
                name=dataset.name,
                connector_type="api",
                description=f"API access for shared dataset: {dataset.description or dataset.name}",
                proxy_url=f"http://localhost:8000/api/proxy/api/{quote(dataset.name)}",
                real_connection_config=json.dumps(connection_config),
                real_credentials=json.dumps(credentials),
                organization_id=dataset.organization_id,
                created_by=dataset.owner_id,
                is_public=True,
                allowed_operations=["GET", "POST"],
                is_active=True
            )
            
            self.db.add(proxy_connector)
            self.db.commit()
            
            logger.info(f"Created proxy connector for dataset {dataset.name}")
            return proxy_connector
            
        except Exception as e:
            logger.error(f"Failed to create proxy connector for dataset {dataset.name}: {e}")
            # Don't fail the sharing process if proxy connector creation fails
            return None 