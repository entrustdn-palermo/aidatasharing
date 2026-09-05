"""
Dataset Service — deep module for dataset lifecycle orchestration.

Absorbs complexity that was previously inline in api/datasets.py route handlers.
Routes become thin adapters; tests mock the external seams (mindsdb, storage, db).
"""
import json
import logging
import hashlib
import os
import tempfile
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException, status

from app.core.config import settings
from app.models.user import User
from app.models.dataset import (
    Dataset, DatasetType, DatasetStatus, DatasetFile,
    AIProcessingStatus, DatabaseConnector,
    DatasetAccessLog, DatasetDownload, DatasetModel,
    DatasetChatSession, ChatMessage, DatasetShareAccess,
)
from app.models.organization import DataSharingLevel
from app.models.file_handler import FileUpload
from app.services.agent_gateway import AgentGateway
from app.services.mindsdb import mindsdb_service
from app.services.storage import storage_service
from app.services.data_sharing import DataSharingService
from app.services.access_control import AccessControlService
from app.services.agri_data import AgriDataService, columns_of_file
from app.services.metadata import MetadataService
from app.services.preview import PreviewService
from app.utils.file_utils import sanitize_filename

logger = logging.getLogger(__name__)


def _count_json_nesting(obj, level=0):
    if isinstance(obj, dict):
        if not obj:
            return level
        return max(_count_json_nesting(v, level + 1) for v in obj.values())
    elif isinstance(obj, list):
        if not obj:
            return level
        return max(_count_json_nesting(item, level + 1) for item in obj)
    return level


def _count_json_elements(obj):
    if isinstance(obj, dict):
        return sum(_count_json_elements(v) for v in obj.values()) + len(obj)
    elif isinstance(obj, list):
        return sum(_count_json_elements(item) for item in obj) + len(obj)
    return 1


def _analyze_json_types(obj, max_depth=3, current_depth=0):
    if current_depth >= max_depth:
        return type(obj).__name__
    if isinstance(obj, dict):
        return {k: _analyze_json_types(v, max_depth, current_depth + 1)
                for k, v in list(obj.items())[:5]}
    elif isinstance(obj, list):
        if obj:
            return [_analyze_json_types(obj[0], max_depth, current_depth + 1)]
        return []
    return type(obj).__name__


class DatasetService:
    """Orchestrates dataset lifecycle: create, upload, activate, delete, metadata, preview.

    Construct per-request with a DB session, same as DataSharingService.
    """

    def __init__(self, db: Session):
        self.db = db

    # ── Lifecycle ────────────────────────────────────────────────

    async def create_from_files(
        self,
        files: List[UploadFile],
        name: str = None,
        description: str = None,
        sharing_level: str = "private",
        user: User = None,
        organization_id: int = None,
        agri_tags: Optional[Dict[str, Any]] = None,
    ) -> Dataset:
        """Validate, store, create DB record, process metadata, and set up MindsDB agent.

        agri_tags (optional): {region_id, crop_id, season, yield_column}. Validated
        upfront — invalid tags abort before any storage or DB side effects.
        """
        if not organization_id:
            raise ValueError("Must be part of an organization to upload datasets")

        # Normalise files list
        upload_files = [f for f in files if f]
        if not upload_files:
            raise ValueError("No files provided")

        is_multi_file = len(upload_files) > 1

        # Normalise sharing level
        try:
            normalized = sharing_level.lower() if isinstance(sharing_level, str) else "private"
            sharing_level_enum = DataSharingLevel(normalized)
        except ValueError:
            sharing_level_enum = DataSharingLevel.PRIVATE

        # ── Validate all files ──
        total_size = 0
        allowed_extensions = settings.get_allowed_file_types()
        for upload_file in upload_files:
            if not upload_file.filename:
                raise ValueError("All files must have valid names")
            ext = upload_file.filename.split(".")[-1].lower()
            if ext not in allowed_extensions:
                raise ValueError(
                    f"Unsupported file type '{ext}' in '{upload_file.filename}'. "
                    f"Supported formats: {', '.join(allowed_extensions).upper()}"
                )
            content = await upload_file.read()
            await upload_file.seek(0)
            total_size += len(content)

        # ── Determine dataset name & type ──
        primary_file = upload_files[0]
        dataset_name = name or (
            primary_file.filename.rsplit(".", 1)[0]
            if len(upload_files) == 1
            else f"Multi-file dataset ({len(upload_files)} files)"
        )
        primary_ext = primary_file.filename.split(".")[-1].lower()
        dataset_type = self._infer_dataset_type(primary_ext)

        # ── Validate agri tags upfront (before any storage or DB side effects) ──
        # `is not None` so an explicit {} is validated (and rejected for
        # missing fields) rather than silently treated as "no tags".
        validated_tags = None
        if agri_tags is not None:
            primary_content = await primary_file.read()
            await primary_file.seek(0)
            _, numeric_columns = columns_of_file(primary_content, primary_ext)
            validated_tags = AgriDataService(self.db).validate_upload_tags(
                agri_tags, numeric_columns=numeric_columns
            )

        # ── Create temporary dataset record ──
        temp_dataset = Dataset(
            name=dataset_name,
            description=description,
            type=dataset_type,
            status=DatasetStatus.PROCESSING,
            owner_id=user.id,
            organization_id=organization_id,
            sharing_level=sharing_level_enum,
            size_bytes=total_size,
            allow_download=True,
            allow_api_access=True,
            is_multi_file_dataset=is_multi_file,
            total_files_count=len(upload_files),
            **(validated_tags or {}),
        )
        self.db.add(temp_dataset)
        self.db.commit()
        self.db.refresh(temp_dataset)

        # ── Store files ──
        stored_files = []
        try:
            stored_files = await self._store_uploaded_files(
                upload_files, temp_dataset, user, organization_id
            )
        except Exception as e:
            self.db.rollback()
            self.db.delete(temp_dataset)
            self.db.commit()
            raise RuntimeError(f"Failed to store files: {e}") from e

        # ── Process primary file metadata ──
        primary_info = stored_files[0]
        metadata = self._process_primary_file(
            primary_info, primary_ext, primary_file, temp_dataset
        )

        # ── Update dataset with processed metadata ──
        for key, value in metadata.items():
            setattr(temp_dataset, key, value)
        temp_dataset.status = DatasetStatus.ACTIVE
        self.db.add(temp_dataset)
        self.db.commit()
        self.db.refresh(temp_dataset)

        # ── Auto-create share link for public datasets ──
        if sharing_level_enum == DataSharingLevel.PUBLIC:
            try:
                sharing_service = DataSharingService(self.db)
                sharing_service.create_share_link(
                    dataset_id=temp_dataset.id,
                    user_id=user.id,
                    password=None,
                    enable_chat=True,
                )
                self.db.refresh(temp_dataset)
            except Exception:
                logger.warning(f"Could not auto-create share link for dataset {temp_dataset.id}")

        return temp_dataset

    async def create_dataset(
        self,
        dataset_data: Dict[str, Any],
        user: User,
    ) -> Dataset:
        """Create a new dataset programmatically (not file upload)."""
        from app.models.dataset import Dataset, DatasetType, DatasetStatus
        from app.models.organization import DataSharingLevel

        name = dataset_data.get("name")
        if not name:
            raise ValueError("Dataset name is required")
        if not user.organization_id:
            raise ValueError("Must be part of an organization to create datasets")

        data_format = dataset_data.get("data_format", "CSV")
        dataset_type = DatasetType.CSV if data_format.upper() == "CSV" else DatasetType.JSON

        sharing_level_str = dataset_data.get("sharing_level", "private")
        try:
            normalized_level = sharing_level_str.lower() if isinstance(sharing_level_str, str) else "private"
            sharing_level = DataSharingLevel(normalized_level)
        except ValueError:
            sharing_level = DataSharingLevel.PRIVATE

        schema_info = {}
        if "columns" in dataset_data:
            schema_info["columns"] = dataset_data["columns"]
        if "row_count" in dataset_data:
            schema_info["row_count"] = dataset_data["row_count"]

        columns = dataset_data.get("columns", [])
        row_count = dataset_data.get("row_count", 0)

        schema_metadata = {
            "columns": columns,
            "data_types": {},
            "programmatically_created": True,
            "created_at": datetime.utcnow().isoformat()
        }
        quality_metrics = {
            "overall_score": 0.9,
            "completeness": 1.0,
            "consistency": 1.0,
            "accuracy": 0.9,
            "issues": [],
            "last_analyzed": datetime.utcnow().isoformat()
        }
        column_statistics = {}
        for col in columns:
            column_statistics[col] = {
                "data_type": "unknown",
                "non_null_count": row_count,
                "null_count": 0,
                "unique_count": "unknown"
            }
        preview_data = {
            "headers": columns,
            "sample_rows": [],
            "total_rows": row_count,
            "is_sample": False,
            "preview_generated_at": datetime.utcnow().isoformat()
        }

        db_dataset = Dataset(
            name=name,
            description=dataset_data.get("description"),
            type=dataset_type,
            status=DatasetStatus.ACTIVE,
            owner_id=user.id,
            organization_id=user.organization_id,
            sharing_level=sharing_level,
            source_url=dataset_data.get("source_url"),
            connector_id=dataset_data.get("connector_id"),
            schema_info=schema_info if schema_info else None,
            allow_download=True,
            allow_api_access=True,
            row_count=row_count,
            column_count=len(columns),
            schema_metadata=schema_metadata,
            quality_metrics=quality_metrics,
            column_statistics=column_statistics,
            preview_data=preview_data,
            download_count=0,
            last_downloaded_at=None
        )

        self.db.add(db_dataset)
        self.db.commit()
        self.db.refresh(db_dataset)
        return db_dataset

    async def activate(self, dataset_id: int, user: User) -> Dataset:
        """Activate a dataset (requires access)."""
        dataset = self._get_dataset(dataset_id)
        self._check_access(dataset, user)
        dataset.activate()
        self.db.commit()
        return dataset

    async def deactivate(self, dataset_id: int, user: User) -> Dataset:
        """Deactivate a dataset (owner or superuser only)."""
        dataset = self._get_dataset(dataset_id)
        self._check_owner(dataset, user)
        dataset.deactivate()
        self.db.commit()
        return dataset

    async def delete(self, dataset_id: int, force: bool, user: User) -> Dict[str, Any]:
        """Soft or hard delete a dataset with full cascade cleanup."""
        dataset = self._get_dataset(dataset_id)
        self._check_owner(dataset, user)

        # Clean up MindsDB agent
        try:
            if dataset.agent_name:
                mindsdb_service.delete_dataset_agent(dataset, self.db)
        except Exception as e:
            logger.warning(f"Agent cleanup failed: {e}")

        # Clean up MindsDB files, connectors, and storage
        await self._cleanup_mindsdb_resources(dataset_id)

        # Clean up DatasetFile records (multi-file)
        file_results = await self._cleanup_dataset_files(dataset)

        if force and user.is_superuser:
            return self._hard_delete(dataset, file_results)
        else:
            return self._soft_delete(dataset, file_results)

    # ── Metadata & preview ──────────────────────────────────────

    async def refresh_metadata(self, dataset_id: int, user: User) -> Dict[str, Any]:
        """Re-analyse dataset schema, quality, and column stats."""
        dataset = self._get_dataset(dataset_id)
        self._check_owner(dataset, user)

        metadata_service = MetadataService(self.db)
        schema_meta = await metadata_service.analyze_dataset_schema(dataset)
        quality = await metadata_service.get_data_quality_metrics(dataset)
        columns = await metadata_service.generate_column_statistics(dataset)

        dataset.schema_metadata = schema_meta
        dataset.quality_metrics = quality
        dataset.column_statistics = columns
        dataset.updated_at = datetime.utcnow()
        self.db.commit()

        return {
            "schema_metadata": schema_meta,
            "quality_metrics": quality,
            "column_statistics": columns,
            "dataset_id": dataset_id,
            "generated_at": schema_meta.get("analysis_timestamp") if isinstance(schema_meta, dict) else None,
        }

    async def get_preview(self, dataset_id: int, user: User, rows: int = 20, include_stats: bool = True) -> Dict[str, Any]:
        """Get dataset content preview via PreviewService."""
        dataset = self._get_dataset(dataset_id)
        self._check_access(dataset, user)

        preview_service = PreviewService(self.db)
        preview_data = await preview_service.generate_preview_data(
            dataset=dataset, rows=rows, include_stats=include_stats
        )
        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "preview": preview_data,
        }

    async def generate_download_token(self, dataset_id: int, user: User) -> Dict[str, Any]:
        """Generate a secure download token."""
        from app.services.download import DownloadService
        dataset = self._get_dataset(dataset_id)
        self._check_access(dataset, user)
        download_service = DownloadService(self.db)
        return await download_service.initiate_download(
            dataset_id=dataset_id, user=user
        )

    async def update_dataset_metadata(
        self,
        dataset_id: int,
        metadata_update: Dict[str, Any],
        user: User,
    ) -> Dataset:
        """Update dataset metadata fields."""
        from app.models.dataset import Dataset
        from app.models.organization import DataSharingLevel

        dataset = self._get_dataset(dataset_id)

        access = AccessControlService(self.db)
        if not access.can_access_dataset(user, dataset):
            raise ValueError("Access denied to this dataset")

        if dataset.owner_id != user.id and not user.is_superuser:
            if user.organization_id != dataset.organization_id or user.role not in ["owner", "admin"]:
                raise ValueError("Only dataset owner or organization admin can update metadata")

        allowed_fields = [
            'name', 'description', 'schema_info', 'file_metadata', 'content_preview',
            'ai_summary', 'ai_insights', 'ai_recommendations', 'sharing_level',
            'ai_chat_enabled', 'allow_download'
        ]

        for field, value in metadata_update.items():
            if field in allowed_fields:
                if field == 'sharing_level':
                    try:
                        if isinstance(value, str):
                            normalized_value = value.lower()
                            value = DataSharingLevel(normalized_value)
                        elif not isinstance(value, DataSharingLevel):
                            continue
                    except ValueError:
                        continue
                setattr(dataset, field, value)

        dataset.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(dataset)

        access.log_access(user=user, dataset=dataset, access_type="metadata_update")

        return dataset

    async def get_dataset_metadata(
        self,
        dataset_id: int,
        user: User,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """Get detailed metadata for a dataset."""
        from app.services.data_sharing import DataSharingService
        from app.services.metadata import MetadataService

        dataset = self._get_dataset(dataset_id)

        access = AccessControlService(self.db)
        if not access.can_access_dataset(user, dataset):
            raise ValueError("Access denied to this dataset")

        metadata_service = MetadataService(self.db)

        schema_metadata = await metadata_service.analyze_dataset_schema(dataset)
        quality_metrics = await metadata_service.get_data_quality_metrics(dataset)
        column_statistics = await metadata_service.generate_column_statistics(dataset)

        metadata_response = {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "schema_metadata": schema_metadata,
            "quality_metrics": quality_metrics,
            "column_statistics": column_statistics,
            "basic_info": {
                "type": dataset.type.value if dataset.type else "unknown",
                "size_bytes": dataset.size_bytes,
                "row_count": dataset.row_count,
                "column_count": dataset.column_count,
                "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
                "updated_at": dataset.updated_at.isoformat() if dataset.updated_at else None
            },
            "generated_at": schema_metadata.get("analysis_timestamp")
        }

        access.log_access(user=user, dataset=dataset, access_type="metadata")

        return metadata_response

    # ── Dataset details & schema ─────────────────────────────────────

    async def get_dataset_details(self, dataset_id: int, user: User) -> Dict[str, Any]:
        """Get dataset with merged file records."""
        dataset = self._get_dataset(dataset_id)
        self._check_access(dataset, user)

        # Log access
        access = AccessControlService(self.db)
        access.log_access(user=user, dataset=dataset, access_type="view")

        from sqlalchemy.inspection import inspect
        dataset_dict = {c.key: getattr(dataset, c.key) for c in inspect(dataset).mapper.column_attrs}

        # Merge files from DatasetFile and FileUpload
        dataset_files = self.db.query(DatasetFile).filter(
            DatasetFile.dataset_id == dataset_id,
            DatasetFile.is_deleted == False,
        ).all()
        if not dataset_files:
            from app.models.file_handler import FileUpload
            dataset_files = self.db.query(FileUpload).filter(
                FileUpload.dataset_id == dataset_id,
            ).all()

        dataset_dict["files"] = []
        for f in dataset_files:
            dataset_dict["files"].append({
                "id": f.id,
                "filename": getattr(f, 'filename', None) or getattr(f, 'original_filename', 'unknown'),
                "file_path": f.file_path,
                "file_size": getattr(f, 'file_size', 0),
                "file_type": getattr(f, 'file_type', None),
                "mime_type": getattr(f, 'mime_type', None),
                "created_at": getattr(f, 'created_at', None).isoformat() if hasattr(f, 'created_at') and getattr(f, 'created_at') else None,
            })
        dataset_dict["is_multi_file"] = len(dataset_files) > 1
        dataset_dict["total_files_count"] = len(dataset_files)

        for key in ['created_at', 'updated_at', 'last_accessed', 'deleted_at',
                     'last_downloaded_at', 'ai_processed_at', 'share_expires_at',
                     'agent_created_at', 'agent_last_updated']:
            if key in dataset_dict and dataset_dict[key]:
                dataset_dict[key] = dataset_dict[key].isoformat()
        return dataset_dict

    async def get_dataset_schema(self, dataset_id: int, user: User) -> Dict[str, Any]:
        """Return schema info for a dataset."""
        dataset = self._get_dataset(dataset_id)
        self._check_access(dataset, user)

        access = AccessControlService(self.db)
        access.log_access(user=user, dataset=dataset, access_type="schema")

        schema_info = dataset.schema_metadata or dataset.schema_info or {}
        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "schema": schema_info,
            "basic_info": {
                "type": dataset.type.value if dataset.type else "unknown",
                "row_count": dataset.row_count,
                "column_count": dataset.column_count,
            },
        }

    async def get_detailed_metadata(self, dataset_id: int, user: User) -> Dict[str, Any]:
        """Return comprehensive metadata with connector info."""
        dataset = self._get_dataset(dataset_id)
        self._check_access(dataset, user)

        access = AccessControlService(self.db)
        access.log_access(user=user, dataset=dataset, access_type="metadata_view")

        metadata = {
            "basic_info": {
                "id": dataset.id, "name": dataset.name, "description": dataset.description,
                "type": dataset.type, "status": dataset.status,
                "created_at": dataset.created_at, "updated_at": dataset.updated_at,
            },
            "ownership": {
                "owner_id": dataset.owner_id,
                "owner_name": dataset.owner.full_name if dataset.owner else None,
                "organization_id": dataset.organization_id,
                "organization_name": dataset.organization.name if dataset.organization else None,
            },
            "data_structure": {
                "size_bytes": dataset.size_bytes, "row_count": dataset.row_count,
                "column_count": dataset.column_count, "schema_info": dataset.schema_info,
                "file_metadata": dataset.file_metadata,
            },
            "ai_processing": {
                "ai_processing_status": dataset.ai_processing_status,
                "ai_summary": dataset.ai_summary, "ai_insights": dataset.ai_insights,
                "ai_recommendations": dataset.ai_recommendations,
                "ai_chat_enabled": dataset.ai_chat_enabled,
                "chat_model_name": dataset.chat_model_name, "chat_context": dataset.chat_context,
            },
            "sharing_settings": {
                "sharing_level": dataset.sharing_level,
                "public_share_enabled": dataset.public_share_enabled,
                "share_token": dataset.share_token if dataset.public_share_enabled else None,
                "share_view_count": dataset.share_view_count,
                "allow_download": dataset.allow_download,
            },
            "data_source": {
                "source_url": dataset.source_url, "connection_params": dataset.connection_params,
                "connector_id": dataset.connector_id,
                "mindsdb_table_name": dataset.mindsdb_table_name,
                "mindsdb_database": dataset.mindsdb_database,
            },
            "content_preview": dataset.content_preview[:500] if dataset.content_preview else None,
            "statistics": {
                "access_count": getattr(dataset, 'access_count', 0),
                "download_count": getattr(dataset, 'download_count', 0),
                "last_accessed": getattr(dataset, 'last_accessed_at', None),
                "last_downloaded": getattr(dataset, 'last_downloaded_at', None),
            },
        }
        if dataset.connector_id:
            connector = self.db.query(DatabaseConnector).filter(
                DatabaseConnector.id == dataset.connector_id,
            ).first()
            if connector:
                metadata["connector_info"] = {
                    "name": connector.name, "description": connector.description,
                    "type": connector.type, "host": connector.host,
                    "port": connector.port, "status": connector.status,
                }
        return metadata

    async def get_stats(self, dataset_id: int, user: User,
                        include_downloads: bool = True,
                        include_access_logs: bool = False) -> Dict[str, Any]:
        """Comprehensive dataset statistics."""
        dataset = self._get_dataset(dataset_id)
        self._check_access(dataset, user)

        access = AccessControlService(self.db)
        access.log_access(user=user, dataset=dataset, access_type="stats")

        stats = {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "basic_stats": {
                "total_size_bytes": dataset.size_bytes, "row_count": dataset.row_count,
                "column_count": dataset.column_count,
                "file_type": dataset.type.value if dataset.type else "unknown",
                "sharing_level": dataset.sharing_level.value if dataset.sharing_level else "private",
                "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
                "updated_at": dataset.updated_at.isoformat() if dataset.updated_at else None,
                "last_accessed": dataset.last_accessed.isoformat() if dataset.last_accessed else None,
            },
            "usage_stats": {
                "download_count": dataset.download_count or 0,
                "last_downloaded_at": dataset.last_downloaded_at.isoformat() if dataset.last_downloaded_at else None,
                "is_downloadable": dataset.allow_download,
                "api_access_enabled": dataset.allow_api_access,
                "ai_chat_enabled": dataset.allow_ai_chat,
            },
        }

        if include_downloads and (dataset.owner_id == user.id or user.is_superuser):
            downloads = self.db.query(DatasetDownload).filter(
                DatasetDownload.dataset_id == dataset_id,
            ).all()
            successful = [d for d in downloads if d.download_status == "completed"]
            failed = [d for d in downloads if d.download_status == "failed"]
            format_counts = {}
            for d in downloads:
                fmt = d.file_format
                format_counts[fmt] = format_counts.get(fmt, 0) + 1
            stats["download_analytics"] = {
                "total_download_attempts": len(downloads),
                "successful_downloads": len(successful),
                "failed_downloads": len(failed),
                "success_rate": len(successful) / len(downloads) if downloads else 0,
                "average_download_time": (
                    sum(d.download_duration_seconds or 0 for d in successful) / len(successful)
                    if successful else 0
                ),
                "popular_formats": format_counts,
            }

        if include_access_logs and (dataset.owner_id == user.id or user.is_superuser):
            recent = self.db.query(DatasetAccessLog).filter(
                DatasetAccessLog.dataset_id == dataset_id,
            ).order_by(DatasetAccessLog.created_at.desc()).limit(10).all()
            stats["recent_access"] = [
                {"access_type": log.access_type, "user_id": log.user_id,
                 "ip_address": log.ip_address,
                 "created_at": log.created_at.isoformat() if log.created_at else None}
                for log in recent
            ]

        if dataset.quality_metrics:
            stats["quality_summary"] = {
                "overall_score": dataset.quality_metrics.get("overall_score"),
                "completeness": dataset.quality_metrics.get("completeness"),
                "consistency": dataset.quality_metrics.get("consistency"),
                "accuracy": dataset.quality_metrics.get("accuracy"),
                "last_analyzed": dataset.quality_metrics.get("last_analyzed"),
            }
        return stats

    async def update_dataset(
        self,
        dataset_id: int,
        dataset_update,
        user: User,
    ) -> Dataset:
        """Update a dataset (owner only)."""
        from app.models.organization import DataSharingLevel

        dataset = self._get_dataset(dataset_id)

        if dataset.owner_id != user.id and not user.is_superuser:
            if user.organization_id != dataset.organization_id or user.role not in ["owner", "admin"]:
                raise ValueError("Only dataset owner or organization admin can update")

        for field, value in dataset_update.dict(exclude_unset=True).items():
            if field == 'sharing_level':
                try:
                    if isinstance(value, str):
                        normalized_value = value.lower()
                        value = DataSharingLevel(normalized_value)
                    elif not isinstance(value, DataSharingLevel):
                        continue
                except ValueError:
                    continue
            setattr(dataset, field, value)

        dataset.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    # ── Content editing & reupload ──────────────────────────────────

    async def edit_content(self, dataset_id: int, edit_request: Dict[str, Any], user: User) -> Dict[str, Any]:
        """Edit dataset content and structure (CSV, JSON, TXT only)."""
        dataset = self._get_dataset(dataset_id)
        if dataset.owner_id != user.id and not user.is_superuser:
            if user.role not in ("owner", "admin"):
                raise ValueError("Only dataset owner or organization admin can edit content")

        editable = {DatasetType.CSV, DatasetType.JSON, DatasetType.TXT}
        if dataset.type not in editable:
            raise ValueError(f"Dataset type {dataset.type} does not support content editing")

        edit_type = edit_request.get("edit_type")
        if edit_type == "update_content":
            new_content = edit_request.get("content")
            if not new_content:
                raise ValueError("Content is required for content update")
            dataset.content_preview = new_content[:1000] + ("..." if len(new_content) > 1000 else "")
            dataset.size_bytes = len(new_content.encode("utf-8"))
            if dataset.type == DatasetType.CSV:
                lines = new_content.strip().split("\n")
                dataset.row_count = len(lines) - 1 if lines else 0
                dataset.column_count = len(lines[0].split(",")) if lines else 0
            elif dataset.type == DatasetType.JSON:
                try:
                    json_data = json.loads(new_content)
                    if isinstance(json_data, list):
                        dataset.row_count = len(json_data)
                    dataset.schema_info = {"type": "json", "structure": type(json_data).__name__}
                except json.JSONDecodeError:
                    raise ValueError("Invalid JSON content")
            elif dataset.type == DatasetType.TXT:
                lines = new_content.split("\n")
                dataset.schema_info = {
                    "type": "text", "line_count": len(lines),
                    "word_count": len(new_content.split()), "character_count": len(new_content),
                }
        elif edit_type == "update_schema":
            if edit_request.get("schema_info"):
                dataset.schema_info = edit_request["schema_info"]
        elif edit_type == "update_metadata":
            if edit_request.get("file_metadata"):
                dataset.file_metadata = edit_request["file_metadata"]
        else:
            raise ValueError("Invalid edit_type. Supported: update_content, update_schema, update_metadata")

        dataset.updated_at = datetime.utcnow()
        dataset.ai_processing_status = AIProcessingStatus.NOT_PROCESSED
        self.db.commit()
        self.db.refresh(dataset)

        access = AccessControlService(self.db)
        access.log_access(user=user, dataset=dataset, access_type="content_edit", details={"edit_type": edit_type})

        return {
            "success": True,
            "message": f"Dataset {edit_type} completed successfully",
            "updated_at": dataset.updated_at,
            "ai_processing_status": dataset.ai_processing_status,
        }

    async def reupload_file(self, dataset_id: int, file, user: User,
                            preserve_metadata: bool = True,
                            update_sharing_settings: bool = False) -> Dict[str, Any]:
        """Replace a dataset's file while preserving configuration."""
        dataset = self._get_dataset(dataset_id)
        if dataset.owner_id != user.id and not user.is_superuser:
            if user.role not in ("owner", "admin"):
                raise ValueError("Only dataset owner or organization admin can reupload files")

        if not file.filename:
            raise ValueError("No file provided")

        file_ext = file.filename.split(".")[-1].lower()
        allowed = settings.get_allowed_file_types()
        if file_ext not in allowed:
            raise ValueError(f"Unsupported file type. Supported: {', '.join(allowed).upper()}")

        content = await file.read()
        file_size = len(content)

        original_meta = {}
        if preserve_metadata:
            original_meta = {
                "name": dataset.name, "description": dataset.description,
                "sharing_level": dataset.sharing_level,
                "ai_summary": dataset.ai_summary, "ai_insights": dataset.ai_insights,
                "ai_recommendations": dataset.ai_recommendations,
                "custom_metadata": getattr(dataset, 'custom_metadata', {}),
                "tags": getattr(dataset, 'tags', []),
            }

        storage_result = await storage_service.store_dataset_file(
            file_content=content, original_filename=file.filename,
            dataset_id=dataset_id, organization_id=user.organization_id,
        )

        new_type = self._infer_dataset_type(file_ext)
        file_meta, content_preview, row_count, column_count = {}, None, None, None

        temp_path = None
        try:
            import tempfile as tf_mod
            with tf_mod.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tf:
                tf.write(content)
                temp_path = tf.name

            if file_ext in ("pdf", "json"):
                try:
                    result = mindsdb_service.process_file_content(temp_path, file_ext)
                    if result.get("success"):
                        file_meta = result.get("metadata", {})
                        preview = result["content"]
                        content_preview = preview[:500] + ("..." if len(preview) > 500 else "")
                        if file_ext == "json":
                            row_count = file_meta.get("element_count")
                            column_count = 1
                except Exception as e:
                    logger.warning("Reupload processing failed: %s", e)
            elif file_ext == "csv":
                try:
                    import pandas as pd
                    df = pd.read_csv(temp_path)
                    file_meta = {
                        "row_count": len(df), "column_count": len(df.columns),
                        "columns": df.columns.tolist(),
                        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
                    }
                    content_preview = df.head(3).to_string()
                    row_count = len(df)
                    column_count = len(df.columns)
                except Exception as e:
                    logger.warning("CSV analysis failed: %s", e)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

        # Build enhanced metadata
        schema_meta, quality, col_stats, preview_data = {}, {}, {}, {}
        if file_meta:
            schema_meta = {
                "file_type": file_ext, "original_filename": file.filename, "encoding": "utf-8",
                "structure": file_meta.get("structure", {}),
                "columns": file_meta.get("columns", []),
                "data_types": file_meta.get("dtypes", {}),
                "sample_data": file_meta.get("sample_data", []),
                "reupload_timestamp": datetime.utcnow().isoformat(),
            }
            quality = {
                "overall_score": 0.85,
                "completeness": 1.0 if row_count and row_count > 0 else 0.0,
                "consistency": 0.9, "accuracy": 0.8, "issues": [],
                "last_analyzed": datetime.utcnow().isoformat(),
                "reupload_analysis": True,
            }
            if "dtypes" in file_meta:
                col_stats = {
                    col: {"data_type": dtype, "non_null_count": row_count or 0,
                          "null_count": 0, "unique_count": "unknown"}
                    for col, dtype in file_meta["dtypes"].items()
                }
            preview_data = {
                "headers": file_meta.get("columns", []),
                "sample_rows": file_meta.get("sample_data", [])[:10],
                "total_rows": row_count or 0, "is_sample": True,
                "preview_generated_at": datetime.utcnow().isoformat(),
                "from_reupload": True,
            }

        dataset.type = new_type
        dataset.size_bytes = file_size
        dataset.source_url = storage_result["relative_path"]
        dataset.file_path = storage_result["file_path"]
        dataset.row_count = row_count
        dataset.column_count = column_count
        dataset.file_metadata = file_meta
        dataset.content_preview = content_preview
        dataset.schema_metadata = schema_meta
        dataset.quality_metrics = quality
        dataset.column_statistics = col_stats
        dataset.preview_data = preview_data
        dataset.updated_at = datetime.utcnow()

        if preserve_metadata and not update_sharing_settings:
            for k in ("name", "description", "sharing_level", "ai_summary", "ai_insights", "ai_recommendations"):
                if original_meta.get(k) is not None:
                    setattr(dataset, k, original_meta[k])

        dataset.ai_processing_status = AIProcessingStatus.NOT_PROCESSED
        self.db.commit()
        self.db.refresh(dataset)

        # Recreate agent
        agent_result = None
        try:
            if dataset.agent_name:
                mindsdb_service.delete_agent(dataset.agent_name)
            if dataset.is_multi_file_dataset:
                agent_result = mindsdb_service.setup_multi_file_agent(dataset, self.db)
            else:
                agent_result = mindsdb_service.setup_single_file_agent(dataset, self.db)
        except Exception as e:
            logger.error("Agent recreation failed: %s", e)
            agent_result = {"success": False, "error": str(e)}

        access = AccessControlService(self.db)
        access.log_access(user=user, dataset=dataset, access_type="file_reupload")

        resp = {
            "message": "Dataset file reuploaded successfully",
            "dataset_id": dataset_id, "dataset_name": dataset.name,
            "file_changes": {
                "new_file_type": new_type.value, "new_filename": file.filename,
                "new_size_bytes": file_size, "new_row_count": row_count,
                "new_column_count": column_count,
            },
            "metadata_preserved": preserve_metadata,
            "ml_models": agent_result,
            "updated_at": dataset.updated_at.isoformat(),
        }
        if agent_result and agent_result.get("success"):
            resp["ai_features"] = {"chat_enabled": True, "model_ready": True, "chat_endpoint": f"/api/datasets/{dataset_id}/chat"}
        else:
            resp["ai_features"] = {"chat_enabled": False, "model_ready": False, "error": agent_result.get("error") if agent_result else "Unknown"}
        return resp

    async def transfer_ownership(self, dataset_id: int, new_owner_id: int, user: User) -> Dict[str, Any]:
        """Transfer dataset ownership to another user in the same org."""
        from app.models.user import User as UserModel

        dataset = self._get_dataset(dataset_id)
        if dataset.owner_id != user.id and not user.is_superuser:
            if not (user.organization_id == dataset.organization_id and user.role in ("owner", "admin")):
                raise ValueError("Only dataset owner or organization admin can transfer ownership")

        new_owner = self.db.query(UserModel).filter(UserModel.id == new_owner_id).first()
        if not new_owner:
            raise ValueError("New owner user not found")
        if new_owner.organization_id != dataset.organization_id:
            raise ValueError("New owner must be in the same organization")
        if new_owner_id == dataset.owner_id:
            raise ValueError("Dataset is already owned by this user")

        old_owner_id = dataset.owner_id
        dataset.owner_id = new_owner_id
        dataset.updated_at = datetime.utcnow()

        log = DatasetAccessLog(
            dataset_id=dataset_id, user_id=user.id, access_type="ownership_transfer",
            details={"old_owner_id": old_owner_id, "new_owner_id": new_owner_id, "transferred_by": user.id},
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(dataset)

        return {
            "message": "Dataset ownership transferred successfully",
            "dataset_id": dataset_id, "dataset_name": dataset.name,
            "old_owner_id": old_owner_id, "new_owner_id": new_owner_id,
            "transferred_by": user.id,
            "transferred_at": dataset.updated_at.isoformat(),
        }

    async def chat_with_dataset(
        self,
        dataset_id: int,
        message: dict,
        user: User,
    ) -> Dict[str, Any]:
        """Chat with the AI model for a dataset."""
        from app.services.data_sharing import DataSharingService
        from app.services.mindsdb import mindsdb_service

        dataset = self._get_dataset(dataset_id)
        self._check_access(dataset, user)

        if not dataset.ai_chat_enabled or not dataset.allow_ai_chat:
            raise ValueError("Chat is disabled for this dataset")

        user_message = message.get("message", "")
        if not user_message:
            raise ValueError("Message is required")

        response = await mindsdb_service.chat_with_dataset_agent(
            dataset_id=dataset_id,
            message=user_message,
            db=self.db,
            session_id=message.get("session_id"),
            stream=True
        )

        access = AccessControlService(self.db)
        access.log_access(user=user, dataset=dataset, access_type="ai_chat")

        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "question": user_message,
            "model_type": "agent_chat",
            "agent_system": True,
            **response
        }

    async def get_dataset_models(
        self,
        dataset_id: int,
        user: User,
    ) -> Dict[str, Any]:
        """Get information about ML models associated with this dataset."""
        from app.services.mindsdb import mindsdb_service

        dataset = self._get_dataset(dataset_id)
        self._check_access(dataset, user)

        models_info = []
        chat_model_name = f"dataset_{dataset_id}_chat_model"

        try:
            models_query = f"SHOW MODELS WHERE name LIKE 'dataset_{dataset_id}_%';"
            result = mindsdb_service.execute_query(models_query)

            if result.get('data'):
                for model_data in result['data']:
                    model_info = {
                        "name": model_data[0] if len(model_data) > 0 else "unknown",
                        "engine": model_data[1] if len(model_data) > 1 else "unknown",
                        "status": model_data[5] if len(model_data) > 5 else "unknown",
                        "predict": model_data[7] if len(model_data) > 7 else "unknown",
                    }
                    models_info.append(model_info)
        except Exception as e:
            logger.warning(f"Could not fetch model status for dataset {dataset_id}: {e}")

        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "models": models_info,
            "available_models": {"chat_model": chat_model_name},
            "endpoints": {"chat": f"/api/datasets/{dataset_id}/chat"}
        }

    async def recreate_dataset_models(
        self,
        dataset_id: int,
        user: User,
    ) -> Dict[str, Any]:
        """Recreate ML models for this dataset."""
        from app.services.mindsdb import mindsdb_service

        dataset = self._get_dataset(dataset_id)
        self._check_owner(dataset, user)

        if dataset.agent_name:
            mindsdb_service.delete_agent(dataset.agent_name)

        if dataset.is_multi_file_dataset:
            agent_result = mindsdb_service.setup_multi_file_agent(dataset, self.db)
        else:
            agent_result = mindsdb_service.setup_single_file_agent(dataset, self.db)

        if not agent_result.get("success"):
            raise ValueError(f"Failed to create agent: {agent_result.get('error')}")

        return {
            "message": "Dataset agent recreated successfully",
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "agent_name": agent_result.get("agent_name"),
            "agent_status": agent_result.get("status")
        }

    async def visualize_dataset(
        self,
        dataset_id: int,
        user: User,
        visualization_type: Optional[str] = None,
        max_visualizations: int = 4,
    ) -> Dict[str, Any]:
        """Generate visualizations for a dataset using LIDA."""
        from app.services.data_sharing import DataSharingService
        from app.services.mindsdb import mindsdb_service
        from app.services.data_visualization import get_visualization_service
        from app.core.app_config import get_app_config

        dataset = self._get_dataset(dataset_id)

        access = AccessControlService(self.db)
        if not access.can_access_dataset(user, dataset):
            raise ValueError("You don't have permission to visualize this dataset")

        dataset_df = await mindsdb_service.load_dataset_for_visualization(dataset, self.db)

        if dataset_df is None or dataset_df.empty:
            raise ValueError("Unable to load dataset data for visualization")

        app_config = get_app_config()
        api_key = app_config.integrations.GOOGLE_API_KEY
        viz_service = get_visualization_service(api_key)

        data_analysis = viz_service.analyze_dataset(dataset_df, dataset.name)

        if visualization_type:
            query = f"Generate {visualization_type} visualizations for this dataset"
        else:
            query = "Generate useful visualizations for this dataset"

        visualizations = viz_service.generate_visualizations_with_lida(
            dataset_df, query=query, max_visualizations=max_visualizations
        )

        access.log_access(user=user, dataset=dataset, access_type="visualization")

        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "data_analysis": data_analysis,
            "visualizations": visualizations,
            "visualization_count": len(visualizations),
            "timestamp": datetime.utcnow().isoformat()
        }

    # ── Internal helpers ─────────────────────────────────────────

    def _get_dataset(self, dataset_id: int) -> Dataset:
        dataset = self.db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.is_deleted == False,
        ).first()
        if not dataset:
            raise ValueError("Dataset not found or already deleted")
        return dataset

    def _check_access(self, dataset: Dataset, user: User):
        data_service = DataSharingService(self.db)
        if not data_service.can_access_dataset(user, dataset) and not user.is_superuser:
            raise ValueError("Access denied to this dataset")

    def _check_owner(self, dataset: Dataset, user: User):
        if dataset.owner_id != user.id and not user.is_superuser:
            raise ValueError("Can only modify your own datasets")

    @staticmethod
    def _infer_dataset_type(extension: str) -> DatasetType:
        mapping = {
            "csv": DatasetType.CSV,
            "json": DatasetType.JSON,
            "xlsx": DatasetType.EXCEL,
            "xls": DatasetType.EXCEL,
            "pdf": DatasetType.PDF,
            "parquet": DatasetType.PARQUET,
            "txt": DatasetType.TXT,
        }
        image_exts = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "svg"}
        if extension.lower() in image_exts:
            return DatasetType.IMAGE
        return mapping.get(extension.lower(), DatasetType.TXT)

    async def _store_uploaded_files(
        self,
        upload_files: List[UploadFile],
        temp_dataset: Dataset,
        user: User,
        organization_id: int,
    ) -> List[Dict[str, Any]]:
        """Store files, create DatasetFile + FileUpload records."""
        stored = []
        for i, upload_file in enumerate(upload_files):
            content = await upload_file.read()
            file_size = len(content)

            storage_result = await storage_service.store_dataset_file(
                file_content=content,
                original_filename=upload_file.filename,
                dataset_id=temp_dataset.id,
                organization_id=organization_id,
            )

            file_ext = upload_file.filename.split(".")[-1].lower()
            dataset_file = DatasetFile(
                dataset_id=temp_dataset.id,
                filename=upload_file.filename,
                file_path=storage_result["file_path"],
                relative_path=storage_result["relative_path"],
                file_size=file_size,
                file_type=file_ext,
                mime_type=upload_file.content_type,
                is_primary=(i == 0),
                file_order=i,
                is_processed=False,
            )
            self.db.add(dataset_file)

            # FileUpload record for MindsDB compatibility
            file_hash = hashlib.md5(upload_file.filename.encode()).hexdigest()
            file_upload = FileUpload(
                dataset_id=temp_dataset.id,
                user_id=user.id,
                organization_id=organization_id,
                original_filename=upload_file.filename,
                file_path=storage_result["file_path"],
                file_size=file_size,
                file_hash=file_hash,
                mime_type=upload_file.content_type,
                file_type=file_ext,
                upload_status="completed",
                mindsdb_file_id=None,
                created_at=datetime.utcnow(),
            )
            self.db.add(file_upload)

            stored.append({
                "file_record": dataset_file,
                "storage_result": storage_result,
                "content": content,
                "upload_file": upload_file,
                "file_size": file_size,
            })

        self.db.commit()
        return stored

    def _process_primary_file(
        self,
        primary_info: Dict[str, Any],
        primary_ext: str,
        primary_upload_file: UploadFile,
        temp_dataset: Dataset,
    ) -> Dict[str, Any]:
        """Analyse primary file content and return metadata dict to set on dataset."""
        content = primary_info["content"]
        file_size = primary_info["file_size"]
        storage_result = primary_info["storage_result"]

        metadata = {
            "size_bytes": file_size,
            "source_url": storage_result["relative_path"],
            "file_path": storage_result["file_path"],
        }

        file_meta = {}
        content_preview = None
        row_count = None
        column_count = None
        schema_metadata = {}
        quality_metrics = {}
        column_statistics = {}
        preview_data = {}

        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{primary_ext}") as tf:
                tf.write(content)
                temp_file_path = tf.name

            if primary_ext in ("pdf", "json"):
                try:
                    result = mindsdb_service.process_file_content(temp_file_path, primary_ext)
                    if result.get("success"):
                        file_meta = result.get("metadata", {})
                        preview = result["content"]
                        content_preview = preview[:500] + "..." if len(preview) > 500 else preview

                        if primary_ext == "json":
                            row_count = file_meta.get("element_count")
                            column_count = 1
                            # Enhanced JSON metadata
                            import json as json_module
                            with open(temp_file_path, "r", encoding="utf-8") as f:
                                json_data = json_module.load(f)
                            schema_metadata = {
                                "file_type": "json",
                                "original_filename": primary_upload_file.filename,
                                "encoding": "utf-8",
                                "structure": {
                                    "type": type(json_data).__name__,
                                    "is_array": isinstance(json_data, list),
                                    "nested_levels": _count_json_nesting(json_data),
                                    "total_elements": _count_json_elements(json_data),
                                },
                                "data_types": _analyze_json_types(json_data),
                                "sample_data": str(json_data)[:200] + ("..." if len(str(json_data)) > 200 else ""),
                            }
                            quality_metrics = {
                                "overall_score": 95,
                                "completeness": 100,
                                "consistency": 95,
                                "accuracy": 90,
                                "issues": [],
                                "last_analyzed": datetime.utcnow().isoformat(),
                            }
                            preview_data = {
                                "type": "json",
                                "structure_preview": str(json_data)[:500] + ("..." if len(str(json_data)) > 500 else ""),
                                "total_elements": _count_json_elements(json_data),
                                "is_sample": len(str(json_data)) > 500,
                                "preview_generated_at": datetime.utcnow().isoformat(),
                            }
                except Exception as e:
                    logger.warning(f"Could not process {primary_ext} file: {e}")

            elif primary_ext == "csv":
                try:
                    import pandas as pd
                    df = pd.read_csv(temp_file_path)
                    file_meta = {
                        "row_count": len(df),
                        "column_count": len(df.columns),
                        "columns": df.columns.tolist(),
                        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
                    }
                    content_preview = df.head(3).to_string()
                    row_count = len(df)
                    column_count = len(df.columns)
                except Exception as e:
                    logger.warning(f"Could not analyse CSV: {e}")
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

        # Build enhanced metadata for unprocessed types
        if not schema_metadata and file_meta:
            schema_metadata = {
                "file_type": primary_ext,
                "original_filename": primary_upload_file.filename,
                "encoding": "utf-8",
                "structure": file_meta.get("structure", {}),
                "columns": file_meta.get("columns", []),
                "data_types": file_meta.get("dtypes", {}),
                "sample_data": file_meta.get("sample_data", []),
            }
            quality_metrics = {
                "overall_score": 0.85,
                "completeness": 1.0 if (row_count and row_count > 0) else 0.0,
                "consistency": 0.9,
                "accuracy": 0.8,
                "issues": [],
                "last_analyzed": datetime.utcnow().isoformat(),
            }
            if "column_stats" in file_meta:
                column_statistics = file_meta["column_stats"]
            elif "dtypes" in file_meta:
                column_statistics = {
                    col: {"data_type": dtype, "non_null_count": row_count or 0, "null_count": 0, "unique_count": "unknown"}
                    for col, dtype in file_meta["dtypes"].items()
                }
            preview_data = {
                "headers": file_meta.get("columns", []),
                "sample_rows": file_meta.get("sample_data", [])[:10],
                "total_rows": row_count or 0,
                "is_sample": True,
                "preview_generated_at": datetime.utcnow().isoformat(),
            }

        metadata.update({
            "row_count": row_count,
            "column_count": column_count,
            "file_metadata": file_meta,
            "content_preview": content_preview,
            "schema_metadata": schema_metadata,
            "quality_metrics": quality_metrics,
            "column_statistics": column_statistics,
            "preview_data": preview_data,
            "download_count": 0,
            "last_downloaded_at": None,
        })
        return metadata

    async def _cleanup_mindsdb_resources(self, dataset_id: int):
        """Delete MindsDB files, connectors, and storage for a dataset."""
        try:
            file_uploads = self.db.query(FileUpload).filter(
                FileUpload.dataset_id == dataset_id
            ).all()
            for fu in file_uploads:
                mindsdb_name = f"dataset_{fu.dataset_id}_file_{fu.id}"
                mindsdb_service.delete_file_from_mindsdb(mindsdb_name)
                connector_name = f"file_db_{fu.id}"
                mindsdb_service.delete_database_connector(connector_name)
                if fu.file_path:
                    try:
                        await storage_service.delete_dataset_file(fu.file_path)
                    except Exception:
                        logger.warning(f"Storage deletion failed for {fu.file_path}")
        except Exception as e:
            logger.warning(f"MindsDB cleanup failed: {e}")

    async def _cleanup_dataset_files(self, dataset: Dataset) -> List[Dict[str, Any]]:
        """Delete all DatasetFile records and their storage files."""
        results = []
        dataset_files = self.db.query(DatasetFile).filter(
            DatasetFile.dataset_id == dataset.id,
            DatasetFile.is_deleted == False,
        ).all()

        for df in dataset_files:
            try:
                deleted = False
                if df.file_path:
                    try:
                        success = await storage_service.delete_dataset_file(df.file_path)
                        deleted = success
                    except Exception:
                        pass
                if not deleted and df.file_path and os.path.exists(df.file_path):
                    os.remove(df.file_path)
                    deleted = True
                df.is_deleted = True
                df.deleted_at = datetime.utcnow()
                results.append({"file": df.filename, "success": deleted})
            except Exception as e:
                results.append({"file": df.filename, "success": False, "error": str(e)})

        # Legacy single-file cleanup
        if not dataset_files and (dataset.file_path or dataset.source_url):
            try:
                if dataset.file_path and os.path.exists(dataset.file_path):
                    os.remove(dataset.file_path)
                    results.append({"file": os.path.basename(dataset.file_path), "success": True})
                elif dataset.source_url and not dataset.source_url.startswith("http"):
                    success = await storage_service.delete_dataset_file(dataset.source_url)
                    results.append({"file": dataset.source_url, "success": success})
            except Exception as e:
                results.append({"file": "legacy_file", "success": False, "error": str(e)})

        return results

    def _soft_delete(self, dataset: Dataset, file_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        if dataset.public_share_enabled:
            dataset.public_share_enabled = False
            dataset.share_token = None
            dataset.share_password = None
            dataset.ai_chat_enabled = False
        dataset.soft_delete(dataset.owner_id)
        # Disable proxy connectors
        try:
            from app.models.proxy_connector import ProxyConnector
            connectors = self.db.query(ProxyConnector).filter(
                ProxyConnector.name == dataset.name,
                ProxyConnector.organization_id == dataset.organization_id,
                ProxyConnector.is_active == True,
            ).all()
            for c in connectors:
                c.is_active = False
        except Exception:
            pass
        self.db.commit()
        return {
            "message": "Dataset deleted successfully",
            "dataset_id": dataset.id,
            "deletion_type": "soft",
            "deleted_at": dataset.deleted_at,
            "file_deletion": {
                "total_files": len(file_results),
                "successful": sum(1 for r in file_results if r.get("success")),
                "failed": sum(1 for r in file_results if not r.get("success")),
                "details": file_results,
            },
        }

    def _hard_delete(self, dataset: Dataset, file_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        dataset_id = dataset.id
        # Delete related records
        chat_sessions = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.dataset_id == dataset_id
        ).all()
        for s in chat_sessions:
            self.db.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete()
        self.db.query(DatasetChatSession).filter(DatasetChatSession.dataset_id == dataset_id).delete()
        self.db.query(DatasetAccessLog).filter(DatasetAccessLog.dataset_id == dataset_id).delete()
        self.db.query(DatasetDownload).filter(DatasetDownload.dataset_id == dataset_id).delete()
        self.db.query(DatasetModel).filter(DatasetModel.dataset_id == dataset_id).delete()
        self.db.query(DatasetShareAccess).filter(DatasetShareAccess.dataset_id == dataset_id).delete()
        self.db.query(DatasetFile).filter(DatasetFile.dataset_id == dataset_id).delete()
        self.db.delete(dataset)
        self.db.commit()
        return {
            "message": "Dataset permanently deleted",
            "dataset_id": dataset_id,
            "deletion_type": "hard",
            "file_deletion": {
                "total_files": len(file_results),
                "successful": sum(1 for r in file_results if r.get("success")),
                "failed": sum(1 for r in file_results if not r.get("success")),
                "details": file_results,
            },
        }
