"""
Access Control Service — dataset access, download permissions, rate limiting.

Deep module: a small interface over organization-scoped permission logic.
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_

from app.models.user import User
from app.models.dataset import (
    Dataset, DatasetType, DatasetAccessLog, DatasetDownload,
    DatabaseConnector,
)
from app.models.organization import Organization, DataSharingLevel

logger = logging.getLogger(__name__)


class AccessControlService:
    """Dataset access and download permissions.

    Construct per-request with a DB session.
    Does NOT depend on MindsDBService — no hard-coded external dependency.
    """

    def __init__(self, db: Session):
        self.db = db

    # ── Access checks ──────────────────────────────────────────────────

    def can_access_dataset(self, user: User, dataset: Dataset) -> bool:
        """Check if a user can view a dataset based on its sharing level."""
        if dataset.is_deleted:
            return False
        if dataset.owner_id == user.id:
            return True

        sharing_level = self._normalize_level(dataset.sharing_level)

        if sharing_level == DataSharingLevel.PUBLIC:
            return True
        if sharing_level == DataSharingLevel.ORGANIZATION:
            return bool(user.organization_id and user.organization_id == dataset.organization_id)
        # PRIVATE
        return False

    def can_download_dataset(self, user: User, dataset: Dataset) -> bool:
        """Check if a user can download a dataset (stricter than view)."""
        if not self.can_access_dataset(user, dataset):
            return False
        if not dataset.allow_download:
            return False
        if dataset.owner_id == user.id:
            return True

        org_policy = self._get_org_download_policy(dataset.organization_id)
        if org_policy.get("restrict_downloads", False):
            return user.role in ("owner", "admin") or user.is_superuser

        user_perms = self._get_user_download_permissions(user)
        if user_perms.get("download_restricted", False):
            allowed = user_perms.get("allowed_sharing_levels", [])
            return dataset.sharing_level.value in allowed

        return True

    def check_download_rate_limit(self, user: User) -> Dict[str, Any]:
        """Check if user has exceeded download rate limits."""
        try:
            perms = self._get_user_download_permissions(user)
            max_daily = perms.get("max_downloads_per_day", 100)

            since = datetime.utcnow() - timedelta(hours=24)
            daily_used = self.db.query(DatasetDownload).filter(
                DatasetDownload.user_id == user.id,
                DatasetDownload.started_at >= since,
                DatasetDownload.download_status == "completed",
            ).count()

            org_policy = self._get_org_download_policy(user.organization_id)
            hourly_limit = org_policy.get("rate_limit_per_hour", 50)
            since_hour = datetime.utcnow() - timedelta(hours=1)
            hourly_used = self.db.query(DatasetDownload).filter(
                DatasetDownload.user_id == user.id,
                DatasetDownload.started_at >= since_hour,
                DatasetDownload.download_status == "completed",
            ).count()

            return {
                "allowed": daily_used < max_daily and hourly_used < hourly_limit,
                "daily_limit": max_daily,
                "daily_used": daily_used,
                "hourly_limit": hourly_limit,
                "hourly_used": hourly_used,
                "reset_time": (datetime.utcnow() + timedelta(hours=24 - datetime.utcnow().hour)).isoformat(),
            }
        except Exception as e:
            logger.error("Rate-limit check failed: %s", e)
            return {"allowed": True}

    def log_download_attempt(
        self, user: User, dataset: Dataset, success: bool,
        error_message: Optional[str] = None, ip_address: Optional[str] = None,
    ) -> bool:
        """Log a download attempt for audit."""
        try:
            access_type = "download_success" if success else "download_failed"
            self.log_access(user, dataset, access_type, ip_address)
            if not success and error_message:
                logger.warning("Download failed user=%s dataset=%s: %s", user.id, dataset.id, error_message)
            return True
        except Exception as e:
            logger.error("Failed to log download attempt: %s", e)
            return False

    # ── Dataset listing ────────────────────────────────────────────────

    def get_accessible_datasets(
        self, user: User,
        sharing_level: Optional[DataSharingLevel] = None,
        include_inactive: bool = False,
        include_deleted: bool = False,
        dataset_type: Optional[DatasetType] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dataset]:
        """Return datasets the user can see, filtered and paginated."""
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
        org_levels = [DataSharingLevel.ORGANIZATION, DataSharingLevel.ORGANIZATION.value]
        query = query.filter(or_(
            Dataset.owner_id == user.id,
            Dataset.sharing_level.in_(public_levels),
            and_(
                Dataset.organization_id == user.organization_id,
                Dataset.sharing_level.in_(org_levels),
            ),
        ))
        query = query.order_by(Dataset.created_at.desc(), Dataset.id.desc())
        if skip is not None:
            query = query.offset(skip)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def get_organization_datasets(self, org_id: int, user: User) -> List[Dataset]:
        """All datasets for an org (admin/owner view)."""
        if (not user.organization_id or user.organization_id != org_id
                or user.role not in ("owner", "admin")):
            return []
        return self.db.query(Dataset).filter(Dataset.organization_id == org_id).all()

    def validate_dataset_creation(self, user: User, org_id: int) -> bool:
        """Can this user create a dataset in the given org?"""
        return user.organization_id == org_id and user.role in ("owner", "admin", "manager", "member")

    # ── Audit logging ──────────────────────────────────────────────────

    def log_access(
        self, user: User, dataset: Dataset, access_type: str,
        ip_address: Optional[str] = None, user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Log a dataset access event."""
        if not self.can_access_dataset(user, dataset):
            return False
        log = DatasetAccessLog(
            dataset_id=dataset.id, user_id=user.id, access_type=access_type,
            ip_address=ip_address, user_agent=user_agent, details=details,
        )
        self.db.add(log)
        self.db.commit()
        dataset.last_accessed = log.created_at
        self.db.commit()
        return True

    # ── Organization stats ─────────────────────────────────────────────

    def get_organization_stats(self, org_id: int, user: User) -> dict:
        """Aggregate data-usage stats for an org (admin/owner only)."""
        if (not user.organization_id or user.organization_id != org_id
                or user.role not in ("owner", "admin")):
            return {}

        datasets = self.db.query(Dataset).filter(Dataset.organization_id == org_id).all()
        sharing_stats = {level: 0 for level in DataSharingLevel}
        total_size = 0
        for ds in datasets:
            level = self._normalize_level(ds.sharing_level)
            sharing_stats[level] = sharing_stats.get(level, 0) + 1
            if ds.size_bytes:
                total_size += ds.size_bytes

        recent = self.db.query(DatasetAccessLog).join(Dataset).filter(
            Dataset.organization_id == org_id,
        ).count()

        return {
            "total_datasets": len(datasets),
            "total_size_bytes": total_size,
            "sharing_levels": {k.value if hasattr(k, 'value') else k: v for k, v in sharing_stats.items()},
            "recent_accesses": recent,
            "organization_id": org_id,
        }

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _normalize_level(level) -> DataSharingLevel:
        if isinstance(level, str):
            try:
                return DataSharingLevel(level.lower())
            except ValueError:
                return DataSharingLevel.PRIVATE
        return level or DataSharingLevel.PRIVATE

    def _get_org_download_policy(self, org_id: int) -> Dict[str, Any]:
        try:
            org = self.db.query(Organization).filter(Organization.id == org_id).first()
            if org and hasattr(org, 'download_policy'):
                return org.download_policy or {}
        except Exception:
            pass
        return {
            "restrict_downloads": False,
            "rate_limit_per_hour": 50,
            "restrict_file_downloads": False,
            "file_download_roles": ["owner", "admin", "manager", "member", "viewer"],
            "restrict_connector_downloads": False,
            "connector_download_roles": ["owner", "admin", "manager"],
        }

    def _get_user_download_permissions(self, user: User) -> Dict[str, Any]:
        perms = {
            "download_restricted": False,
            "allowed_sharing_levels": ["private", "department", "organization"],
            "max_downloads_per_day": 100,
        }
        if user.role == "viewer":
            perms.update(download_restricted=True, allowed_sharing_levels=["organization"], max_downloads_per_day=10)
        elif user.role == "member":
            perms["max_downloads_per_day"] = 50
        elif user.role in ("admin", "owner"):
            perms["max_downloads_per_day"] = 1000
        return perms
