"""
Permission Service for Centralized Access Control
Handles all authorization checks across the platform
"""

import logging
from typing import Optional, List
from enum import Enum
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.user import User
from app.models.dataset import Dataset
from app.models.organization import Organization
from app.models.data_connector import DataConnector

logger = logging.getLogger(__name__)


class AccessLevel(str, Enum):
    """Access level enumeration"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SHARE = "share"
    ADMIN = "admin"


class ResourceType(str, Enum):
    """Resource type enumeration"""
    DATASET = "dataset"
    CONNECTOR = "connector"
    ORGANIZATION = "organization"
    SHARED_DATA = "shared_data"
    FILE = "file"


class PermissionService:
    """Centralized permission and authorization service"""

    def __init__(self, db: Session):
        self.db = db

    # ========================================================================
    # Dataset Permissions
    # ========================================================================

    async def check_dataset_access(
        self,
        dataset_id: int,
        user: User,
        required_level: AccessLevel = AccessLevel.READ
    ) -> bool:
        """
        Check if user has access to dataset

        Args:
            dataset_id: Dataset ID
            user: User object
            required_level: Required access level

        Returns:
            True if user has access, False otherwise
        """
        try:
            dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if not dataset:
                logger.warning(f"Dataset {dataset_id} not found")
                return False

            # Superuser always has access
            if user.is_superuser:
                logger.debug(f"Superuser {user.email} granted access to dataset {dataset_id}")
                return True

            # Owner has full access
            if dataset.owner_id == user.id:
                logger.debug(f"Owner {user.email} granted access to dataset {dataset_id}")
                return True

            # Check organization access
            if dataset.organization_id and dataset.organization_id == user.organization_id:
                # Check if user has required permission level in organization
                org_access = await self._check_org_permission(user, required_level)
                if org_access:
                    logger.debug(f"Organization member {user.email} granted {required_level} access to dataset {dataset_id}")
                    return True

            # Check shared access
            shared_access = await self._check_shared_dataset_access(dataset_id, user, required_level)
            if shared_access:
                logger.debug(f"Shared access granted to {user.email} for dataset {dataset_id}")
                return True

            logger.warning(f"Access denied for user {user.email} to dataset {dataset_id}")
            return False

        except Exception as e:
            logger.error(f"Error checking dataset access: {e}")
            return False

    async def require_dataset_access(
        self,
        dataset_id: int,
        user: User,
        required_level: AccessLevel = AccessLevel.READ
    ):
        """
        Require dataset access or raise HTTPException

        Args:
            dataset_id: Dataset ID
            user: User object
            required_level: Required access level

        Raises:
            HTTPException: If access is denied
        """
        has_access = await self.check_dataset_access(dataset_id, user, required_level)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to dataset {dataset_id}"
            )

    def check_dataset_ownership(self, dataset: Dataset, user: User) -> bool:
        """
        Check if user owns the dataset

        Args:
            dataset: Dataset object
            user: User object

        Returns:
            True if user owns dataset
        """
        return user.is_superuser or dataset.owner_id == user.id

    def require_dataset_ownership(self, dataset: Dataset, user: User):
        """
        Require dataset ownership or raise HTTPException

        Args:
            dataset: Dataset object
            user: User object

        Raises:
            HTTPException: If user doesn't own dataset
        """
        if not self.check_dataset_ownership(dataset, user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only dataset owner can perform this action"
            )

    # ========================================================================
    # Connector Permissions
    # ========================================================================

    async def check_connector_access(
        self,
        connector_id: int,
        user: User,
        required_level: AccessLevel = AccessLevel.READ
    ) -> bool:
        """
        Check if user has access to data connector

        Args:
            connector_id: Connector ID
            user: User object
            required_level: Required access level

        Returns:
            True if user has access
        """
        try:
            connector = self.db.query(DataConnector).filter(
                DataConnector.id == connector_id
            ).first()

            if not connector:
                logger.warning(f"Connector {connector_id} not found")
                return False

            # Superuser always has access
            if user.is_superuser:
                return True

            # Owner has full access
            if connector.created_by == user.id:
                return True

            # Check organization access
            if connector.organization_id and connector.organization_id == user.organization_id:
                return await self._check_org_permission(user, required_level)

            return False

        except Exception as e:
            logger.error(f"Error checking connector access: {e}")
            return False

    async def require_connector_access(
        self,
        connector_id: int,
        user: User,
        required_level: AccessLevel = AccessLevel.READ
    ):
        """
        Require connector access or raise HTTPException

        Args:
            connector_id: Connector ID
            user: User object
            required_level: Required access level

        Raises:
            HTTPException: If access is denied
        """
        has_access = await self.check_connector_access(connector_id, user, required_level)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to connector {connector_id}"
            )

    # ========================================================================
    # Organization Permissions
    # ========================================================================

    async def check_organization_access(
        self,
        organization_id: int,
        user: User,
        required_level: AccessLevel = AccessLevel.READ
    ) -> bool:
        """
        Check if user has access to organization

        Args:
            organization_id: Organization ID
            user: User object
            required_level: Required access level

        Returns:
            True if user has access
        """
        try:
            # Superuser always has access
            if user.is_superuser:
                return True

            # Check if user belongs to organization
            if user.organization_id == organization_id:
                return await self._check_org_permission(user, required_level)

            return False

        except Exception as e:
            logger.error(f"Error checking organization access: {e}")
            return False

    async def require_organization_access(
        self,
        organization_id: int,
        user: User,
        required_level: AccessLevel = AccessLevel.READ
    ):
        """
        Require organization access or raise HTTPException

        Args:
            organization_id: Organization ID
            user: User object
            required_level: Required access level

        Raises:
            HTTPException: If access is denied
        """
        has_access = await self.check_organization_access(organization_id, user, required_level)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to organization {organization_id}"
            )

    def check_organization_admin(self, user: User, organization_id: int) -> bool:
        """
        Check if user is admin of organization

        Args:
            user: User object
            organization_id: Organization ID

        Returns:
            True if user is org admin
        """
        if user.is_superuser:
            return True

        if user.organization_id != organization_id:
            return False

        # Check if user has admin role
        return user.role in ["admin", "owner"]

    def require_organization_admin(self, user: User, organization_id: int):
        """
        Require organization admin or raise HTTPException

        Args:
            user: User object
            organization_id: Organization ID

        Raises:
            HTTPException: If user is not org admin
        """
        if not self.check_organization_admin(user, organization_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization admin access required"
            )

    # ========================================================================
    # Shared Data Permissions
    # ========================================================================

    async def check_shared_data_access(
        self,
        share_token: str,
        user: Optional[User] = None
    ) -> bool:
        """
        Check if user/guest has access to shared data

        Args:
            share_token: Share token
            user: Optional user object (None for anonymous)

        Returns:
            True if access is granted
        """
        try:
            # Sharing lives on the Dataset itself: a share link is a dataset
            # with share_token set and public_share_enabled turned on.
            dataset = self.db.query(Dataset).filter(
                Dataset.share_token == share_token,
                Dataset.public_share_enabled == True,
                Dataset.is_deleted == False,
                Dataset.is_active == True,
            ).first()

            if not dataset:
                logger.warning(f"Shared data with token {share_token} not found")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking shared data access: {e}")
            return False

    async def require_shared_data_access(
        self,
        share_token: str,
        user: Optional[User] = None
    ):
        """
        Require shared data access or raise HTTPException

        Args:
            share_token: Share token
            user: Optional user object

        Raises:
            HTTPException: If access is denied
        """
        has_access = await self.check_shared_data_access(share_token, user)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to shared data"
            )

    # ========================================================================
    # Admin Permissions
    # ========================================================================

    def check_superuser(self, user: User) -> bool:
        """Check if user is superuser"""
        return user.is_superuser

    def require_superuser(self, user: User):
        """
        Require superuser or raise HTTPException

        Args:
            user: User object

        Raises:
            HTTPException: If user is not superuser
        """
        if not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superuser access required"
            )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _check_org_permission(
        self,
        user: User,
        required_level: AccessLevel
    ) -> bool:
        """
        Check if user has required permission level in their organization

        Args:
            user: User object
            required_level: Required access level

        Returns:
            True if user has permission
        """
        # Map access levels to roles
        role_hierarchy = {
            AccessLevel.READ: ["member", "analyst", "contributor", "admin", "owner"],
            AccessLevel.WRITE: ["contributor", "analyst", "admin", "owner"],
            AccessLevel.DELETE: ["admin", "owner"],
            AccessLevel.SHARE: ["contributor", "admin", "owner"],
            AccessLevel.ADMIN: ["admin", "owner"]
        }

        allowed_roles = role_hierarchy.get(required_level, [])
        return user.role in allowed_roles

    async def _check_shared_dataset_access(
        self,
        dataset_id: int,
        user: User,
        required_level: AccessLevel
    ) -> bool:
        """
        Check if dataset is shared with user

        Args:
            dataset_id: Dataset ID
            user: User object
            required_level: Required access level

        Returns:
            True if user has shared access
        """
        try:
            # A dataset is "shared" when its public share link is enabled
            # (Dataset.public_share_enabled + share_token) — there is no
            # separate share-grant table.
            dataset = self.db.query(Dataset).filter(
                Dataset.id == dataset_id
            ).first()

            if not dataset:
                return False

            if not dataset.public_share_enabled or dataset.is_deleted or not dataset.is_active:
                return False

            # For now, shared datasets are read-only
            if required_level in [AccessLevel.READ]:
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking shared dataset access: {e}")
            return False

    # ========================================================================
    # Bulk Permission Checks
    # ========================================================================

    async def filter_accessible_datasets(
        self,
        user: User,
        datasets: List[Dataset],
        required_level: AccessLevel = AccessLevel.READ
    ) -> List[Dataset]:
        """
        Filter list of datasets to only those user can access

        Args:
            user: User object
            datasets: List of datasets
            required_level: Required access level

        Returns:
            Filtered list of accessible datasets
        """
        accessible = []
        for dataset in datasets:
            has_access = await self.check_dataset_access(dataset.id, user, required_level)
            if has_access:
                accessible.append(dataset)
        return accessible

    async def filter_accessible_connectors(
        self,
        user: User,
        connectors: List[DataConnector],
        required_level: AccessLevel = AccessLevel.READ
    ) -> List[DataConnector]:
        """
        Filter list of connectors to only those user can access

        Args:
            user: User object
            connectors: List of connectors
            required_level: Required access level

        Returns:
            Filtered list of accessible connectors
        """
        accessible = []
        for connector in connectors:
            has_access = await self.check_connector_access(connector.id, user, required_level)
            if has_access:
                accessible.append(connector)
        return accessible


# ========================================================================
# Dependency Injection Helper
# ========================================================================

def get_permission_service(db: Session) -> PermissionService:
    """
    Dependency injection helper for FastAPI routes

    Usage:
        @router.get("/datasets/{dataset_id}")
        async def get_dataset(
            dataset_id: int,
            user: User = Depends(get_current_user),
            perms: PermissionService = Depends(get_permission_service)
        ):
            await perms.require_dataset_access(dataset_id, user)
            ...
    """
    return PermissionService(db)
