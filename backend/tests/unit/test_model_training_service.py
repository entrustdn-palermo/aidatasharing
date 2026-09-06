"""Unit tests for ModelTrainingService.

Tests the DB-backed model lifecycle using a real SQLite session and
a mocked AgentGateway (bare Mock() with the model training protocol
methods stubbed).  Follows the house pattern from test_connector_service.py.
"""

from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import Mock, PropertyMock, patch
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.models.dataset import Dataset, DatasetModel
from app.models.organization import Organization
from app.models.user import User
from app.services.model_training import ModelTrainingService


# ── Fixtures ──


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models import Base
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def org(db: Session) -> Organization:
    org = Organization(id=10, name="Org A", slug="org-a", type="small_business", is_active=True)
    db.add(org)
    db.commit()
    return org


@pytest.fixture
def owner(db: Session, org: Organization) -> User:
    u = User(
        id=1, email="owner@test.com", full_name="Owner",
        hashed_password="p", is_active=True, is_superuser=False,
        organization_id=org.id, role="member",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def other_user(db: Session) -> User:
    u = User(
        id=2, email="other@test.com", full_name="Other",
        hashed_password="p", is_active=True, is_superuser=False,
        organization_id=99, role="member",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def dataset(db: Session, owner: User, org: Organization) -> Dataset:
    ds = Dataset(
        id=100,
        name="Test Dataset",
        description="A test dataset",
        type="csv",
        owner_id=owner.id,
        organization_id=org.id,
        file_path="/data/test.csv",
        sharing_level="private",
        column_statistics={"yield": {"mean": 5.5}, "price": {"mean": 10.0}},
        is_active=True,
    )
    db.add(ds)
    db.commit()
    return ds


@pytest.fixture
def mindsdb_gateway() -> Mock:
    """Mock AgentGateway with model training methods stubbed.

    Matches the house pattern (test_connector_service.py:53-67):
    a bare Mock() with only the protocol methods the test paths touch.
    """
    gw = Mock()
    gw.execute_query = Mock(return_value={"status": "success", "rows": [], "columns": [], "row_count": 0})
    gw.is_safe_mindsdb_identifier = Mock(return_value=True)
    gw.create_model = Mock(return_value={"status": "success", "rows": [], "columns": []})
    gw.get_model_info = Mock(return_value={
        "name": "dataset_100_predict_yield_12345",
        "status": "completed",
        "accuracy": "{'r2_score': 0.94}",
        "training_start": "2026-09-06T00:00:00",
        "training_end": "2026-09-06T00:02:30",
    })
    gw.predict = Mock(return_value=[{"yield": 5.2, "confidence": 0.95}])
    gw.delete_model = Mock(return_value=True)
    gw.upload_file_to_mindsdb = Mock(return_value="dataset_100_train_12345.csv")
    return gw


@pytest.fixture
def svc(db: Session, mindsdb_gateway: Mock) -> ModelTrainingService:
    return ModelTrainingService(db, mindsdb_service=mindsdb_gateway)


# ── train_model ──


class TestTrainModel:
    """ModelTrainingService.train_model()"""

    def test_happy_path_creates_row(self, svc, dataset, owner, mindsdb_gateway):
        """Successful training creates DatasetModel with status='training'."""
        result = svc.train_model(
            dataset_id=dataset.id,
            user=owner,
            target_column="yield",
        )
        assert result.dataset_id == dataset.id
        assert result.target_column == "yield"
        assert result.model_type == "predictor"
        assert result.status == "training"
        assert result.engine_type == "mindsdb"
        assert result.error_message is None
        # Verify create_model was called with correct SQL shape
        call_name = mindsdb_gateway.create_model.call_args[0][0]
        assert "dataset_100_predict_yield_" in call_name
        call_args = mindsdb_gateway.create_model.call_args[0]
        assert len(call_args) >= 3  # model_name, query, engine

    def test_persists_to_database(self, svc, db, dataset, owner):
        """Row is committed to the DB."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        db.refresh(row)
        fetched = db.query(DatasetModel).filter(DatasetModel.id == row.id).first()
        assert fetched is not None
        assert fetched.status == "training"
        assert fetched.mindsdb_model_name is not None

    def test_create_model_error_sets_status_error(self, svc, dataset, owner, mindsdb_gateway):
        """When MindsDB create_model returns error, row persists as 'error'."""
        mindsdb_gateway.create_model.return_value = {
            "status": "error",
            "error": "MindsDB training failed: invalid target",
        }
        result = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        assert result.status == "error"
        assert "invalid target" in (result.error_message or "")

    def test_access_denied_for_private_dataset(self, svc, dataset, other_user):
        """User from different org on PRIVATE dataset gets ValueError."""
        with pytest.raises(ValueError, match="Access denied"):
            svc.train_model(dataset_id=dataset.id, user=other_user, target_column="yield")

    def test_dataset_not_found(self, svc, owner):
        """Deleted or nonexistent dataset raises 'not found'."""
        with pytest.raises(ValueError, match="not found"):
            svc.train_model(dataset_id=99999, user=owner, target_column="yield")

    def test_invalid_target_column(self, svc, dataset, owner, mindsdb_gateway):
        """Target column not in column_statistics raises ValueError."""
        mindsdb_gateway.is_safe_mindsdb_identifier.return_value = True
        with pytest.raises(ValueError, match="not found in dataset"):
            svc.train_model(dataset_id=dataset.id, user=owner, target_column="nonexistent")

    def test_unsafe_target_column(self, svc, dataset, owner, mindsdb_gateway):
        """Target that fails is_safe_mindsdb_identifier raises ValueError."""
        mindsdb_gateway.is_safe_mindsdb_identifier.return_value = False
        with pytest.raises(ValueError, match="Invalid target"):
            svc.train_model(dataset_id=dataset.id, user=owner, target_column="bad; drop")

    def test_unsupported_source(self, svc, db, dataset, owner, mindsdb_gateway):
        """Dataset with no mindsdb_database/table and unsupported type raises."""
        dataset.is_multi_file_dataset = True
        dataset.file_path = None
        dataset.mindsdb_database = None
        dataset.mindsdb_table_name = None
        db.commit()
        with pytest.raises(ValueError, match="not supported"):
            svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")


# ── refresh_status ──


class TestRefreshStatus:
    """ModelTrainingService.refresh_status()"""

    def test_maps_completed_to_complete(self, svc, dataset, owner, mindsdb_gateway):
        """MindsDB 'completed' status maps to 'complete' in DatasetModel."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        assert row.status == "training"
        refreshed = svc.refresh_status(row)
        assert refreshed.status == "complete"

    def test_stores_accuracy(self, svc, dataset, owner, mindsdb_gateway):
        """Accuracy string is stored from MindsDB info."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        refreshed = svc.refresh_status(row)
        assert refreshed.accuracy is not None
        assert isinstance(refreshed.accuracy, str)
        assert "r2_score" in refreshed.accuracy

    def test_stores_training_time(self, svc, dataset, owner, mindsdb_gateway):
        """training_time is computed from training_start/end."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        refreshed = svc.refresh_status(row)
        assert refreshed.training_time is not None
        assert refreshed.training_time == 150  # 2m30s

    def test_error_status_mapped(self, svc, dataset, owner, mindsdb_gateway):
        """MindsDB 'error' status maps to 'error' in DatasetModel."""
        mindsdb_gateway.get_model_info.return_value = {
            "name": "m1",
            "status": "error",
            "error": "training crashed",
        }
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        refreshed = svc.refresh_status(row)
        assert refreshed.status == "error"
        assert "training crashed" in (refreshed.error_message or "")

    def test_missing_model_during_training(self, svc, dataset, owner, mindsdb_gateway):
        """When model not found and status is training, set to error."""
        mindsdb_gateway.get_model_info.return_value = None
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        refreshed = svc.refresh_status(row)
        assert refreshed.status == "error"
        assert "not found" in (refreshed.error_message or "")

    def test_no_change_when_info_none_and_not_training(self, svc, dataset, owner, mindsdb_gateway):
        """If model gone and row already complete, don't overwrite."""
        # First train and complete normally
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        svc.refresh_status(row)  # becomes complete
        # Then simulate MindsDB losing the model
        mindsdb_gateway.get_model_info.return_value = None
        refreshed = svc.refresh_status(row)
        assert refreshed.status == "complete"  # stays complete


# ── predict ──


class TestPredict:
    """ModelTrainingService.predict()"""

    def test_returns_predictions(self, svc, dataset, owner, mindsdb_gateway):
        """Complete model returns prediction rows."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        svc.refresh_status(row)  # make complete
        db = next(s for s in [svc.db])
        db.refresh(row)
        result = svc.predict(row, {"year": 2024, "crop": "corn"})
        assert result == [{"yield": 5.2, "confidence": 0.95}]

    def test_increments_prediction_count(self, svc, dataset, owner, mindsdb_gateway):
        """prediction_count increments after predict."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        svc.refresh_status(row)
        db = next(s for s in [svc.db])
        db.refresh(row)
        svc.predict(row, {"year": 2024})
        assert row.prediction_count == 1

    def test_raises_when_not_complete(self, svc, dataset, owner, mindsdb_gateway):
        """Predict on training model raises ValueError."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        with pytest.raises(ValueError, match="not ready"):
            svc.predict(row, {"year": 2024})


# ── delete_model ──


class TestDeleteModel:
    """ModelTrainingService.delete_model()"""

    def test_soft_deletes_and_drops(self, svc, dataset, owner, mindsdb_gateway):
        """Calls gateway delete_model and soft-deletes the row."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        svc.delete_model(row, owner)
        assert row.is_deleted is True
        assert row.status == "deleted"
        assert row.deleted_by == owner.id
        mindsdb_gateway.delete_model.assert_called_once_with(row.mindsdb_model_name)

    def test_handles_gateway_failure(self, svc, dataset, owner, mindsdb_gateway):
        """If gateway delete_model returns False, still soft-deletes locally."""
        mindsdb_gateway.delete_model.return_value = False
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        svc.delete_model(row, owner)
        assert row.is_deleted is True


# ── get_model / list_models_for_user ──


class TestGetModel:
    """ModelTrainingService.get_model()"""

    def test_returns_model_for_accessible_dataset(self, svc, dataset, owner):
        """Owner can retrieve their model."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        fetched = svc.get_model(row.id, owner)
        assert fetched.id == row.id


class TestListModelsForUser:
    """ModelTrainingService.list_models_for_user()"""

    def test_lists_only_accessible_models(self, svc, dataset, owner, other_user, db):
        """Other-org user on PRIVATE dataset doesn't see the model."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        owner_models = svc.list_models_for_user(owner)
        assert row.id in [m.id for m in owner_models]
        other_models = svc.list_models_for_user(other_user)
        assert row.id not in [m.id for m in other_models]

    def test_excludes_deleted_models(self, svc, dataset, owner):
        """Soft-deleted models are excluded from listing."""
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        svc.delete_model(row, owner)
        models = svc.list_models_for_user(owner)
        assert row.id not in [m.id for m in models]

    def test_superuser_sees_all(self, svc, dataset, owner, db, org):
        """Superuser bypasses access check."""
        superuser = User(
            id=99, email="admin@test.com", full_name="Admin",
            hashed_password="p", is_active=True, is_superuser=True,
            organization_id=org.id, role="admin",
        )
        db.add(superuser)
        db.commit()
        row = svc.train_model(dataset_id=dataset.id, user=owner, target_column="yield")
        models = svc.list_models_for_user(superuser)
        assert row.id in [m.id for m in models]
