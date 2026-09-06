"""
ModelTrainingService — DB-backed model lifecycle for MindsDB training.

Orchestrates model creation, status polling, prediction, and deletion
using the AgentGateway protocol (typically MindsDBService).  Access is
enforced via the canonical ``AccessControlService.can_access_dataset``
check at every public method entry point.

This is the core service behind the un-mocked ``/api/models`` routes.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.dataset import Dataset, DatasetModel
from app.models.user import User
from app.services.access_control import AccessControlService
from app.services.agent_gateway import AgentGateway
from app.services.mindsdb import mindsdb_service as _default_mindsdb

logger = logging.getLogger(__name__)

TABULAR_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".parquet"}


class ModelTrainingService:
    """Manage the DatasetModel lifecycle backed by a MindsDB training run."""

    def __init__(
        self,
        db: Session,
        mindsdb_service: Optional[AgentGateway] = None,
    ):
        self.db = db
        self.mindsdb_service: AgentGateway = mindsdb_service or _default_mindsdb
        self._access = AccessControlService(db)

    # ── Public API ─────────────────────────────────────────────────────

    def train_model(
        self,
        dataset_id: int,
        user: User,
        target_column: str,
        name: Optional[str] = None,
    ) -> DatasetModel:
        """Start training a model on *target_column* for the given dataset.

        Returns a ``DatasetModel`` row with ``status='training'`` (or
        ``'error'`` if the CREATE MODEL SQL itself fails synchronously).
        The caller should poll ``refresh_status()`` to detect completion.

        Raises
            ValueError: access denied, dataset not found, invalid target,
                        unsupported source, or unsafe identifier.
        """
        dataset = self._get_dataset(dataset_id)
        self._check_access(dataset, user)

        # Validate target column
        if not self.mindsdb_service.is_safe_mindsdb_identifier(target_column):
            raise ValueError(f"Invalid target column name: {target_column}")
        if dataset.column_statistics and target_column not in dataset.column_statistics:
            raise ValueError(f"Target column '{target_column}' not found in dataset columns")

        # Resolve the training source (database + SELECT query)
        source_db, inner_select = self._resolve_training_source(dataset)

        # Build a unique MindsDB model name
        safe_col = re.sub(r"[^a-zA-Z0-9_]", "_", target_column)
        ts = int(time.time())
        mindsdb_model_name = f"dataset_{dataset.id}_predict_{safe_col}_{ts}"

        # Persist a training row immediately
        model = DatasetModel(
            dataset_id=dataset.id,
            name=name or mindsdb_model_name,
            model_type="predictor",
            mindsdb_model_name=mindsdb_model_name,
            target_column=target_column,
            feature_columns=list(dataset.column_statistics.keys()) if dataset.column_statistics else None,
            engine_type="mindsdb",
            status="training",
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)

        # Issue CREATE MODEL to MindsDB (async — returns immediately)
        result = self.mindsdb_service.create_model(
            mindsdb_model_name,
            inner_select,
            source_db,
            predict=target_column,
        )
        if result.get("status") != "success":
            model.status = "error"
            model.error_message = str(result.get("error", "Unknown error"))[:2000]
            self.db.commit()
            self.db.refresh(model)

        return model

    def refresh_status(self, model: DatasetModel) -> DatasetModel:
        """Poll MindsDB for the current model status and persist any changes.

        Updates ``status``, ``accuracy``, ``training_time``, and
        ``error_message`` on the DatasetModel row.  Commits only when
        a field actually changed.
        """
        info = self.mindsdb_service.get_model_info(model.mindsdb_model_name)
        changed = False

        if info is None:
            if model.status == "training":
                model.status = "error"
                model.error_message = "Model not found in MindsDB"
                changed = True
            # If already in a terminal state, leave it alone
        else:
            # Defensive lowercase-key lookup (MindsDB version drift)
            info_lower = {k.lower(): v for k, v in info.items()}

            raw_status = str(info_lower.get("status", "unknown")).lower()
            status_map = {
                "training": "training",
                "completed": "complete",
                "complete": "complete",
                "error": "error",
            }
            mapped = status_map.get(raw_status)
            if mapped and mapped != model.status:
                model.status = mapped
                changed = True

            # Accuracy — MindsDB returns a JSON metrics string; store raw
            accuracy_raw = info_lower.get("accuracy")
            if accuracy_raw is not None and str(accuracy_raw) != (model.accuracy or ""):
                model.accuracy = str(accuracy_raw)
                changed = True

            # Error message
            err = info_lower.get("error")
            if err and str(err) != (model.error_message or ""):
                model.error_message = str(err)[:2000]
                changed = True

            # Training time — parse start/end timestamps defensively
            start = self._parse_ts(info_lower.get("training_start"))
            end = self._parse_ts(info_lower.get("training_end"))
            if start and end:
                seconds = int((end - start).total_seconds())
                if seconds != model.training_time:
                    model.training_time = seconds
                    changed = True

        if changed:
            self.db.commit()
            self.db.refresh(model)

        return model

    def predict(
        self, model: DatasetModel, input_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Run a prediction against a completed model.

        Raises ``ValueError`` if the model is not in ``'complete'`` status.
        """
        if model.status != "complete":
            raise ValueError(
                f"Model is not ready for predictions (status={model.status})"
            )
        rows = self.mindsdb_service.predict(model.mindsdb_model_name, input_data)
        if rows:
            model.prediction_count = (model.prediction_count or 0) + 1
            model.last_prediction_at = datetime.utcnow()
            self.db.commit()
        return rows

    def delete_model(self, model: DatasetModel, user: User) -> None:
        """Drop the model from MindsDB and soft-delete the DatasetModel row."""
        try:
            self.mindsdb_service.delete_model(model.mindsdb_model_name)
        except Exception as e:
            logger.warning(
                f"MindsDB delete_model failed for {model.mindsdb_model_name}: {e}"
            )
        model.soft_delete(user.id)
        self.db.commit()

    def get_model(self, model_id: int, user: User) -> DatasetModel:
        """Fetch a single model by id, enforcing access on its dataset.

        Pooled models (``dataset_id IS NULL`` — e.g. the crop classifier)
        are readable by any authenticated member; their training data is
        governed by the pool policy, not per-dataset access.
        """
        model = self.db.query(DatasetModel).filter(
            DatasetModel.id == model_id,
            DatasetModel.is_deleted == False,
        ).first()
        if model is None:
            raise ValueError("Model not found")
        if model.dataset_id is not None:
            self._check_access(model.dataset, user)
        return model

    def list_models_for_user(self, user: User) -> List[DatasetModel]:
        """List all non-deleted models whose datasets the user can access.

        Superusers bypass per-dataset access checks. Pooled models
        (``dataset_id IS NULL``) are listed for everyone — outer join so
        they survive the join to datasets.
        """
        rows = (
            self.db.query(DatasetModel)
            .outerjoin(Dataset)
            .filter(DatasetModel.is_deleted == False)
            .all()
        )
        if user.is_superuser:
            return rows
        return [
            r for r in rows
            if r.dataset_id is None
            or (r.dataset and self._access.can_access_dataset(user, r.dataset))
        ]

    # ── Internal helpers ───────────────────────────────────────────────

    def _get_dataset(self, dataset_id: int) -> Dataset:
        """Fetch a non-deleted dataset or raise ``ValueError``."""
        dataset = self.db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.is_deleted == False,
        ).first()
        if dataset is None:
            raise ValueError("Dataset not found or already deleted")
        return dataset

    def _check_access(self, dataset: Dataset, user: User) -> None:
        """Raise ``ValueError`` if *user* cannot access *dataset*."""
        if user.is_superuser:
            return
        if not self._access.can_access_dataset(user, dataset):
            raise ValueError("Access denied to this dataset")

    def _resolve_training_source(self, dataset: Dataset) -> Tuple[str, str]:
        """Determine the MindsDB database and inner SELECT for training.

        Returns ``(database, inner_select)`` suitable for passing to
        ``CREATE MODEL ... FROM <database> (<inner_select>)``.

        Priority:
        1. Connector-backed dataset (mindsdb_database + mindsdb_table_name)
        2. Single file-backed dataset (tabular format — upload to MindsDB)
        3. Multi-file or unsupported → raises ``ValueError``
        """
        # Connector-backed
        if dataset.mindsdb_database and dataset.mindsdb_table_name:
            db_name = dataset.mindsdb_database
            if db_name.lower() in ("files", "mindsdb"):
                # Treat files-database entries the same as file-backed
                pass
            else:
                inner = f"SELECT * FROM {db_name}.{dataset.mindsdb_table_name}"
                return (db_name, inner)

        # File-backed
        if dataset.file_path and not dataset.is_multi_file_dataset:
            ext = os.path.splitext(dataset.file_path.lower())[1]
            if ext not in TABULAR_EXTENSIONS:
                raise ValueError(
                    f"Unsupported file type '{ext}' for model training"
                )

            # Resolve full path (mirrors mindsdb.py:959-968)
            storage_base = self._resolve_storage_base()
            full_path = os.path.join(storage_base, dataset.file_path)

            # Upload to MindsDB with a timestamped name to avoid collisions
            ts = int(time.time())
            upload_name = f"dataset_{dataset.id}_train_{ts}{ext}"
            uploaded = self.mindsdb_service.upload_file_to_mindsdb(full_path, upload_name)
            if not uploaded:
                raise ValueError("Failed to upload dataset file to MindsDB for training")

            inner = f"SELECT * FROM files.{uploaded}"
            return ("files", inner)

        raise ValueError("Dataset source not supported for model training")

    def _resolve_storage_base(self) -> str:
        """Determine the local storage base path for dataset files."""
        try:
            from app.services.storage import StorageService
            storage_service = StorageService()
            if (
                hasattr(storage_service, "backend")
                and hasattr(storage_service.backend, "storage_dir")
            ):
                return storage_service.backend.storage_dir
        except Exception:
            pass
        from app.core.config import settings
        return os.path.abspath(settings.DATASET_STORAGE_PATH)

    @staticmethod
    def _parse_ts(value: Any) -> Optional[datetime]:
        """Parse a timestamp string (ISO-8601) defensively.

        Returns ``None`` if the value is missing or unparseable.
        """
        if value is None or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
