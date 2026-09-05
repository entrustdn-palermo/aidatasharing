"""
Sharing Service — share-link creation, verification, shared-dataset access.

Deep module: hides share-token generation, password hashing, proxy connector
setup, and CSV preview rendering behind a small interface.
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_password_hash, verify_password
from app.core.config import settings
from app.models.dataset import (
    Dataset, DatasetChatSession, ChatMessage, DatasetFile,
    DatasetShareAccess, DatabaseConnector,
)
from app.models.organization import DataSharingLevel
from app.models.user import User
from app.services.storage import storage_service

logger = logging.getLogger(__name__)


class SharingService:
    """Share-link lifecycle: create, verify, access, analytics.

    Construct per-request with a DB session.
    """

    def __init__(self, db: Session):
        self.db = db

    # ── Share-link creation ────────────────────────────────────────────

    def create_share_link(
        self,
        dataset_id: int,
        user_id: int,
        password: Optional[str] = None,
        enable_chat: bool = True,
    ) -> Dict[str, Any]:
        """Create a shareable link for a dataset."""
        dataset = self.db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.owner_id == user_id,
        ).first()
        if not dataset:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dataset not found or access denied")
        if not dataset.organization or not dataset.organization.allow_external_sharing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="External sharing is disabled for this organization")

        share_token = self._generate_token(dataset_id, user_id)
        dataset.public_share_enabled = True
        dataset.share_token = share_token
        dataset.share_password = get_password_hash(password) if password else None
        dataset.ai_chat_enabled = enable_chat and dataset.allow_ai_chat and settings.ENABLE_AI_CHAT

        if dataset.connector_id:
            self._create_proxy_connector_sync(dataset, share_token)

        self.db.commit()
        self.db.refresh(dataset)

        if dataset.ai_chat_enabled:
            self._init_ai_context(dataset)

        return {
            "share_token": share_token,
            "share_url": f"/shared/{share_token}",
            "chat_enabled": dataset.ai_chat_enabled,
            "password_protected": bool(password),
            "dataset_name": dataset.name,
        }

    # ── Shared-dataset access ──────────────────────────────────────────

    async def get_shared_dataset(
        self,
        share_token: str,
        password: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return dataset info via share token."""
        dataset = self.db.query(Dataset).filter(
            Dataset.share_token == share_token,
            Dataset.public_share_enabled == True,
            Dataset.is_deleted == False,
            Dataset.is_active == True,
        ).first()
        if not dataset:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Shared dataset not found or no longer available")

        self.require_password(dataset, password)

        # Validate connector-based datasets
        if dataset.connector_id:
            connector = self.db.query(DatabaseConnector).filter(
                DatabaseConnector.id == dataset.connector_id,
                DatabaseConnector.is_deleted == False,
                DatabaseConnector.is_active == True,
            ).first()
            if not connector:
                dataset.public_share_enabled = False
                self.db.commit()
                raise HTTPException(status.HTTP_410_GONE, detail="Dataset source is no longer available")

        # File existence check
        await self._verify_files_exist(dataset)

        self._log_access(dataset, share_token, ip_address, user_agent)
        dataset.share_view_count += 1
        dataset.last_accessed = datetime.utcnow()
        self.db.commit()

        preview_data = await self._generate_preview(dataset)

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
            "is_uploaded_file": self._is_uploaded_file(dataset),
            "is_connector_dataset": bool(dataset.connector_id),
            "has_proxy_connection": bool(dataset.connector_id),
            "proxy_connection_info": self._proxy_info(dataset, share_token) if dataset.connector_id else None,
        }

    def verify_password(self, dataset: Dataset, password: Optional[str]) -> bool:
        """Check share-link password. Returns True if no password set."""
        if not dataset.share_password:
            return True
        if not password:
            return False
        try:
            return verify_password(password, dataset.share_password)
        except Exception:
            return password == dataset.share_password

    def require_password(self, dataset: Dataset, password: Optional[str]) -> None:
        """Raise 401 if password is wrong."""
        if not self.verify_password(dataset, password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    # ── Sharing-level management ───────────────────────────────────────

    def update_sharing_level(self, user: User, dataset: Dataset, new_level: DataSharingLevel) -> bool:
        """Change a dataset's sharing level (owner or org admin only)."""
        if not (dataset.owner_id == user.id or (
                user.organization_id == dataset.organization_id and user.role in ("owner", "admin"))):
            return False
        dataset.sharing_level = new_level
        self.db.commit()
        logger.info("Dataset %s sharing level → %s by user %s", dataset.id, new_level, user.id)
        return True

    def get_sharing_stats(self, org_id: int, user: User) -> dict:
        """Aggregate sharing statistics (org admin/owner only)."""
        if (not user.organization_id or user.organization_id != org_id
                or user.role not in ("owner", "admin")):
            return {}
        datasets = self.db.query(Dataset).filter(Dataset.organization_id == org_id).all()
        stats = {
            "total_datasets": len(datasets),
            "by_sharing_level": {"private": 0, "organization": 0, "public": 0},
            "by_type": {},
            "total_access_logs": 0,
            "unique_users_accessed": 0,
        }
        for ds in datasets:
            level = ds.sharing_level.value if hasattr(ds.sharing_level, 'value') else str(ds.sharing_level).lower()
            if level in stats["by_sharing_level"]:
                stats["by_sharing_level"][level] += 1
            dtype = ds.type.value if ds.type else "unknown"
            stats["by_type"][dtype] = stats["by_type"].get(dtype, 0) + 1

        logs = self.db.query(DatasetShareAccess).join(Dataset).filter(
            Dataset.organization_id == org_id,
        ).all()
        stats["total_access_logs"] = len(logs)
        stats["unique_users_accessed"] = len({l.user_id for l in logs if l.user_id})
        return stats

    def get_org_shared_datasets(self, org_id: int, user: User) -> list:
        """Datasets shared at ORGANIZATION level in an org."""
        if not user.organization_id or user.organization_id != org_id:
            return []
        return self.db.query(Dataset).filter(
            Dataset.organization_id == org_id,
            Dataset.sharing_level == DataSharingLevel.ORGANIZATION,
        ).all()

    def get_dataset_analytics(self, dataset_id: int, user_id: int) -> Dict[str, Any]:
        """Analytics for a shared dataset (owner only)."""
        dataset = self.db.query(Dataset).filter(
            Dataset.id == dataset_id, Dataset.owner_id == user_id,
        ).first()
        if not dataset:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        total_accesses = self.db.query(DatasetShareAccess).filter(
            DatasetShareAccess.dataset_id == dataset_id,
        ).count()
        chat_sessions = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.dataset_id == dataset_id,
        ).count()
        total_messages = self.db.query(ChatMessage).join(DatasetChatSession).filter(
            DatasetChatSession.dataset_id == dataset_id,
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
            "last_accessed": dataset.last_accessed,
        }

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _generate_token(dataset_id: int, user_id: int) -> str:
        data = f"{dataset_id}-{user_id}-{datetime.utcnow().isoformat()}-{secrets.token_hex(16)}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _log_access(self, dataset: Dataset, share_token: str, ip: Optional[str], ua: Optional[str]) -> None:
        log = DatasetShareAccess(
            dataset_id=dataset.id, share_token=share_token, ip_address=ip, user_agent=ua,
        )
        self.db.add(log)
        self.db.commit()

    def _init_ai_context(self, dataset: Dataset) -> None:
        """Set up AI context for chat on a shared dataset."""
        if dataset.chat_context:
            return
        file_url = None
        if dataset.file_path or dataset.source_url:
            try:
                path = dataset.file_path or dataset.source_url
                file_url = storage_service.get_dataset_file_url(path, expires_in=86400)
                if file_url and not file_url.startswith('http'):
                    base = getattr(settings, 'BASE_URL', 'http://localhost:8000')
                    file_url = f"{base}{file_url}"
            except Exception as e:
                logger.warning("File URL generation failed for dataset %s: %s", dataset.id, e)

        dataset.chat_context = {
            "dataset_name": dataset.name,
            "description": dataset.description,
            "type": dataset.type,
            "columns": dataset.schema_info.get("columns", []) if dataset.schema_info else [],
            "row_count": dataset.row_count,
            "summary": dataset.ai_summary,
            "file_url": file_url,
            "file_path": dataset.file_path,
            "accessible_via_url": bool(file_url),
            "mindsdb_datasource": None,
            "mindsdb_available": False,
        }
        dataset.chat_model_name = settings.DEFAULT_GEMINI_MODEL
        self.db.commit()

    def _create_proxy_connector_sync(self, dataset: Dataset, share_token: str):
        """Create proxy connector (synchronous) for connector-based datasets."""
        try:
            from app.models.proxy_connector import ProxyConnector
            from urllib.parse import quote
            import uuid
            import json

            existing = self.db.query(ProxyConnector).filter(
                ProxyConnector.name == dataset.name,
                ProxyConnector.organization_id == dataset.organization_id,
                ProxyConnector.is_active == True,
            ).first()
            if existing:
                return existing

            if dataset.connector_id:
                original = self.db.query(DatabaseConnector).filter(
                    DatabaseConnector.id == dataset.connector_id,
                ).first()
                config = original.connection_config if original and original.connection_config else {}
                conn_config = {
                    "base_url": config.get("base_url", "https://jsonplaceholder.typicode.com"),
                    "dataset_id": dataset.id,
                    "share_token": share_token,
                    "type": "dataset_api",
                }
            else:
                conn_config = {
                    "base_url": "https://jsonplaceholder.typicode.com",
                    "dataset_id": dataset.id,
                    "share_token": share_token,
                    "type": "dataset_api",
                }

            connector = ProxyConnector(
                proxy_id=str(uuid.uuid4()),
                name=dataset.name,
                connector_type="api",
                description=f"API access for shared dataset: {dataset.description or dataset.name}",
                proxy_url=f"http://localhost:8000/api/proxy/api/{quote(dataset.name)}",
                real_connection_config=json.dumps(conn_config),
                real_credentials=json.dumps({"token": share_token, "auth_type": "share_token"}),
                organization_id=dataset.organization_id,
                created_by=dataset.owner_id,
                is_public=True,
                allowed_operations=["GET", "POST"],
                is_active=True,
            )
            self.db.add(connector)
            self.db.commit()
            return connector
        except Exception as e:
            logger.error("Proxy connector creation failed: %s", e)
            return None

    async def _verify_files_exist(self, dataset: Dataset) -> None:
        """Disable sharing if files are gone."""
        from app.models.dataset import DatasetFile

        if dataset.is_multi_file_dataset:
            existing = self.db.query(DatasetFile).filter(
                DatasetFile.dataset_id == dataset.id,
                DatasetFile.is_deleted == False,
            ).all()
            found = False
            for f in existing:
                if f.file_path:
                    try:
                        if await storage_service.dataset_file_exists(f.relative_path or f.file_path):
                            found = True
                            break
                    except Exception:
                        continue
            if not found:
                self._disable_sharing(dataset)
                raise HTTPException(status.HTTP_410_GONE, detail="Dataset files are no longer available")
        elif dataset.file_path:
            try:
                exists = await storage_service.dataset_file_exists(dataset.file_path)
            except Exception:
                exists = False
            if not exists:
                self._disable_sharing(dataset)
                raise HTTPException(status.HTTP_410_GONE, detail="Dataset file is no longer available")

    def _disable_sharing(self, dataset: Dataset) -> None:
        dataset.public_share_enabled = False
        self.db.commit()

    async def _generate_preview(self, dataset: Dataset) -> Optional[Dict[str, Any]]:
        """Generate a preview for a shared dataset."""
        try:
            if dataset.is_multi_file_dataset:
                from app.models.dataset import DatasetFile
                files = self.db.query(DatasetFile).filter(
                    DatasetFile.dataset_id == dataset.id,
                    DatasetFile.is_deleted == False,
                ).order_by(DatasetFile.is_primary.desc(), DatasetFile.file_order.asc()).all()
                if not files:
                    return None
                primary = files[0]
                preview = {
                    "type": "multi_file",
                    "total_files": len(files),
                    "files_list": [{
                        "filename": f.filename, "file_type": f.file_type,
                        "file_size": f.file_size, "is_primary": f.is_primary,
                    } for f in files[:5]],
                    "primary_file": {"filename": primary.filename, "file_type": primary.file_type},
                }
                # Try CSV preview of primary file
                if (primary.file_type and primary.file_type.lower() == 'csv'
                        and primary.file_path and hasattr(storage_service.backend, 'storage_dir')):
                    try:
                        full = os.path.join(storage_service.backend.storage_dir, primary.file_path)
                        if os.path.exists(full):
                            self._attach_csv_preview(preview, pd.read_csv(full, nrows=10))
                    except Exception:
                        pass
                return preview

            if dataset.file_path and hasattr(storage_service.backend, 'storage_dir'):
                full = os.path.join(storage_service.backend.storage_dir, dataset.file_path)
                if os.path.exists(full) and dataset.type.value.lower() == 'csv':
                    preview = {"type": "csv", "preview_source": "single_file"}
                    self._attach_csv_preview(preview, pd.read_csv(full, nrows=10))
                    return preview
        except Exception as e:
            logger.warning("Preview generation failed: %s", e)
        return None

    @staticmethod
    def _attach_csv_preview(preview: dict, df: pd.DataFrame) -> None:
        preview["headers"] = df.columns.tolist()
        rows = []
        for row in df.values:
            converted = []
            for val in row:
                if pd.isna(val):
                    converted.append(None)
                elif isinstance(val, (np.integer, int)):
                    converted.append(int(val))
                elif isinstance(val, (np.floating, float)):
                    converted.append(float(val))
                elif isinstance(val, np.bool_):
                    converted.append(bool(val))
                else:
                    converted.append(str(val))
            rows.append(converted)
        preview["rows"] = rows
        preview["total_rows"] = len(rows)

    async def validate_dataset_files(self, dataset: Dataset) -> Dict[str, Any]:
        """Validate whether a dataset's files are accessible.

        Returns a dict with:
        - ``file_valid``: bool — whether files exist
        - ``file_check_method``: str — how the check was performed
        - ``error``: optional error message
        """
        from app.models.dataset import DatasetFile

        result: Dict[str, Any] = {"file_valid": True, "file_check_method": "not_applicable"}

        if dataset.connector_id:
            # Connector-based datasets: check connector validity
            connector = self.db.query(DatabaseConnector).filter(
                DatabaseConnector.id == dataset.connector_id,
                DatabaseConnector.is_deleted == False,
                DatabaseConnector.is_active == True,
            ).first()
            result["file_valid"] = connector is not None
            result["file_check_method"] = "connector_check"
            if not connector:
                result["error"] = "Connector is deleted or inactive"
            return result

        # Uploaded file datasets: check dataset_files table first (new upload system)
        dataset_files = self.db.query(DatasetFile).filter(
            DatasetFile.dataset_id == dataset.id,
            DatasetFile.is_deleted == False,
        ).all()

        if dataset_files:
            files_exist = False
            for dataset_file in dataset_files:
                if dataset_file.file_path:
                    try:
                        file_path = dataset_file.relative_path or dataset_file.file_path
                        if await storage_service.dataset_file_exists(file_path):
                            files_exist = True
                            break
                    except Exception:
                        continue
            result["file_valid"] = files_exist
            result["file_check_method"] = "dataset_files_table"
            if not files_exist:
                result["error"] = "No files found in storage"
            return result

        if dataset.file_path:
            try:
                result["file_valid"] = await storage_service.dataset_file_exists(dataset.file_path)
                result["file_check_method"] = "legacy_file_path"
            except Exception as e:
                result["file_valid"] = False
                result["error"] = str(e)
            return result

        if dataset.source_url and not dataset.source_url.startswith(('http://', 'https://')):
            try:
                result["file_valid"] = await storage_service.dataset_file_exists(dataset.source_url)
                result["file_check_method"] = "source_url"
            except Exception as e:
                result["file_valid"] = False
                result["error"] = str(e)
            return result

        # No file references found
        result["file_valid"] = False
        result["file_check_method"] = "no_references"
        result["error"] = "Dataset has no file references"
        return result

    @staticmethod
    def _is_uploaded_file(dataset: Dataset) -> bool:
        if dataset.source_url and not dataset.source_url.startswith('http'):
            return True
        if dataset.is_multi_file_dataset or dataset.file_path:
            return True
        if not dataset.connector_id and dataset.type.value.lower() in (
                'pdf', 'csv', 'json', 'excel', 'txt', 'docx', 'doc', 'rtf', 'odt', 'image'):
            return True
        return False

    @staticmethod
    def _proxy_info(dataset: Dataset, share_token: str) -> Optional[Dict[str, Any]]:
        base = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        return {
            "connection_type": dataset.type.value,
            "proxy_url": f"{base}/api/proxy",
            "access_token": share_token,
            "database_name": dataset.name,
            "supports_sql": dataset.type.value in ('csv', 'database', 'api'),
        }