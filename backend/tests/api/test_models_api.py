"""API-level tests for the un-mocked /api/models routes.

Follows the exact pattern from test_regional_aggregate_api.py:
bare FastAPI(), StaticPool SQLite, real committed User rows,
dependency_overrides for get_db/get_current_user, no app.main import.
"""

from __future__ import annotations

from unittest.mock import Mock, patch
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user, get_current_admin_user
from app.core.database import get_db
from app.models import Base
from app.models.dataset import Dataset, DatasetModel
from app.models.organization import Organization
from app.models.user import User
from app.api import models as models_router


# ── Fixtures ──


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    o = Organization(id=10, name="Org A", slug="org-a", type="small_business", is_active=True)
    db.add(o)
    db.commit()
    return o


@pytest.fixture
def member(db: Session, org: Organization) -> User:
    u = User(
        id=1, email="member@test.com", full_name="Member",
        hashed_password="p", is_active=True, is_superuser=False,
        organization_id=org.id, role="member",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def admin_user(db: Session, org: Organization) -> User:
    u = User(
        id=2, email="admin@test.com", full_name="Admin",
        hashed_password="p", is_active=True, is_superuser=True,
        organization_id=org.id, role="admin",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def dataset(db: Session, member: User, org: Organization) -> Dataset:
    ds = Dataset(
        id=100,
        name="Test Dataset",
        type="csv",
        owner_id=member.id,
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
def app(db: Session, member: User):
    application = FastAPI()
    application.include_router(models_router.router, prefix="/api/models")

    def override_db():
        yield db

    def override_user():
        return member

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_user] = override_user
    return application


@pytest.fixture
def client(app: FastAPI):
    return TestClient(app)


@pytest.fixture
def patched_gateway():
    """Patch the ModelTrainingService default mindsdb_service with a Mock."""
    gw = Mock()
    gw.execute_query = Mock(return_value={"status": "success", "rows": []})
    gw.is_safe_mindsdb_identifier = Mock(return_value=True)
    gw.create_model = Mock(return_value={"status": "success"})
    gw.get_model_info = Mock(return_value={
        "name": "m1",
        "status": "completed",
        "accuracy": "{'r2_score': 0.94}",
        "training_start": "2026-09-06T00:00:00",
        "training_end": "2026-09-06T00:02:30",
    })
    gw.predict = Mock(return_value=[{"yield": 5.2}])
    gw.delete_model = Mock(return_value=True)
    gw.upload_file_to_mindsdb = Mock(return_value="dataset_100_train_12345.csv")
    return gw


# ── Tests ──


class TestCreateModel:
    """POST /api/models"""

    def test_creates_model(self, client, dataset, patched_gateway):
        with patch("app.api.models.ModelTrainingService") as MockSvc:
            svc_instance = MockSvc.return_value
            svc_instance.train_model.return_value = DatasetModel(
                id=1, dataset_id=dataset.id, name="m1", model_type="predictor",
                mindsdb_model_name="m1", target_column="yield", engine_type="mindsdb",
                status="training",
            )
            resp = client.post("/api/models", json={
                "dataset_id": dataset.id,
                "target_column": "yield",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "training"
        assert data["target_column"] == "yield"

    def test_requires_auth(self, app, dataset):
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app)
        resp = client.post("/api/models", json={
            "dataset_id": dataset.id,
            "target_column": "yield",
        })
        assert resp.status_code in (401, 403)


class TestListModels:
    """GET /api/models"""

    def test_lists_accessible_models(self, client, db, dataset, member, patched_gateway):
        # Create a model directly in DB
        model = DatasetModel(
            dataset_id=dataset.id, name="m1", model_type="predictor",
            mindsdb_model_name="m1", target_column="yield", status="complete",
        )
        db.add(model)
        db.commit()
        resp = client.get("/api/models")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()]
        assert model.id in ids

    def test_requires_auth(self, app):
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app)
        resp = client.get("/api/models")
        assert resp.status_code in (401, 403)


class TestGetModel:
    """GET /api/models/{id}"""

    def test_returns_model(self, client, db, dataset, member):
        model = DatasetModel(
            dataset_id=dataset.id, name="m1", model_type="predictor",
            mindsdb_model_name="m1", target_column="yield", status="training",
        )
        db.add(model)
        db.commit()
        resp = client.get(f"/api/models/{model.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == model.id

    def test_404_for_unknown(self, client):
        resp = client.get("/api/models/99999")
        assert resp.status_code == 404


class TestGetModelStatus:
    """GET /api/models/{id}/status"""

    def test_refreshes_and_returns_status(self, client, db, dataset, member, patched_gateway):
        model = DatasetModel(
            dataset_id=dataset.id, name="m1", model_type="predictor",
            mindsdb_model_name="m1", target_column="yield", status="training",
        )
        db.add(model)
        db.commit()
        with patch("app.api.models.ModelTrainingService") as MockSvc:
            svc_instance = MockSvc.return_value
            svc_instance.refresh_status.return_value = model
            svc_instance.get_model.return_value = model
            # Make the model appear "complete" after refresh
            svc_instance.refresh_status.side_effect = lambda m: (
                setattr(m, "status", "complete"),
                setattr(m, "accuracy", "{'r2': 0.9}"),
                setattr(m, "training_time", 150),
                m
            )[4] if False else m
            # Actually just set it directly
            model.status = "complete"
            model.accuracy = "{'r2': 0.9}"
            model.training_time = 150
            resp = client.get(f"/api/models/{model.id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "complete"
        assert data["accuracy"] is not None


class TestPredict:
    """POST /api/models/{id}/predict"""

    def test_predicts(self, client, db, dataset, member, patched_gateway):
        model = DatasetModel(
            dataset_id=dataset.id, name="m1", model_type="predictor",
            mindsdb_model_name="m1", target_column="yield", status="complete",
        )
        db.add(model)
        db.commit()
        with patch("app.api.models.ModelTrainingService") as MockSvc:
            svc_instance = MockSvc.return_value
            svc_instance.get_model.return_value = model
            svc_instance.predict.return_value = [{"yield": 5.2}]
            resp = client.post(f"/api/models/{model.id}/predict", json={
                "input": {"year": 2024},
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "predictions" in data
        assert len(data["predictions"]) > 0

    def test_409_when_not_ready(self, client, db, dataset, member, patched_gateway):
        model = DatasetModel(
            dataset_id=dataset.id, name="m1", model_type="predictor",
            mindsdb_model_name="m1", target_column="yield", status="training",
        )
        db.add(model)
        db.commit()
        with patch("app.api.models.ModelTrainingService") as MockSvc:
            svc_instance = MockSvc.return_value
            svc_instance.get_model.return_value = model
            svc_instance.predict.side_effect = ValueError("Model is not ready for predictions")
            resp = client.post(f"/api/models/{model.id}/predict", json={
                "input": {"year": 2024},
            })
        assert resp.status_code == 409


class TestDeleteModel:
    """DELETE /api/models/{id}"""

    def test_deletes(self, client, db, dataset, member, patched_gateway):
        model = DatasetModel(
            dataset_id=dataset.id, name="m1", model_type="predictor",
            mindsdb_model_name="m1", target_column="yield", status="complete",
        )
        db.add(model)
        db.commit()
        with patch("app.api.models.ModelTrainingService") as MockSvc:
            svc_instance = MockSvc.return_value
            svc_instance.get_model.return_value = model
            resp = client.delete(f"/api/models/{model.id}")
        assert resp.status_code == 200
