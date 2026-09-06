"""
API-level tests for agri-tagged upload (ticket #4).

Covers auth and validation errors on the HTTP surface:
- upload with valid/invalid agri tags (400 with clear messages)
- malformed agri_tags JSON rejected before any processing
- unauthenticated upload rejected
- agri tags appear in the dataset detail response
- yield-column suggestion endpoint (auth + suggestion shape)

The real service runs against an in-memory SQLite db; only the storage
seam (filesystem) is mocked.
"""
import io
import json
import pytest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user, get_current_admin_user
from app.core.database import get_db
from app.models import Base
from app.models.agri import Region, Crop
from app.models.dataset import DatasetModel
from app.models.user import User
from app.api import agri, datasets


CSV_BYTES = (
    b"plot,farmer,produksi,hasil,luas,hujan\n"
    b"1,Budi,5.2,3.1,2.0,120\n"
    b"2,Sari,4.8,3.4,1.5,130\n"
)


# ── Fixtures ──────────────────────────────────────────────────────────

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
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def member(db):
    user = User(
        email="member@example.com", hashed_password="x", full_name="Member",
        is_active=True, is_superuser=False, organization_id=10, role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin(db):
    user = User(
        email="admin@example.com", hashed_password="x", full_name="Admin",
        is_active=True, is_superuser=True, organization_id=10, role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def references(db):
    region = Region(name="Jawa Barat", code="JB", is_active=True)
    crop = Crop(name="Padi", is_active=True)
    old_region = Region(name="Lama Sekali", code="LM", is_active=False)
    db.add_all([region, crop, old_region])
    db.commit()
    db.refresh(region)
    db.refresh(crop)
    db.refresh(old_region)
    return {"region": region, "crop": crop, "old_region": old_region}


@pytest.fixture
def app(db, member):
    application = FastAPI()
    application.include_router(agri.router, prefix="/api/agri")
    application.include_router(datasets.router, prefix="/api/datasets")

    def override_db():
        yield db

    def override_user():
        return member

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_user] = override_user
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def admin_client(app, db, admin):
    app.dependency_overrides[get_current_admin_user] = lambda: admin
    app.dependency_overrides[get_current_user] = lambda: admin
    return TestClient(app)


def _upload(client, agri_tags=None, filename="farm.csv"):
    data = {"name": "Farm data"}
    if agri_tags is not None:
        data["agri_tags"] = (
            agri_tags if isinstance(agri_tags, str) else json.dumps(agri_tags)
        )
    return client.post(
        "/api/datasets/upload",
        files={"file": (filename, io.BytesIO(CSV_BYTES), "text/csv")},
        data=data,
    )


# ── Upload with agri tags ─────────────────────────────────────────────

class TestUploadWithAgriTags:
    def test_valid_tags_accepted_and_stored(self, client, references):
        tags = {
            "region_id": references["region"].id,
            "crop_id": references["crop"].id,
            "season": "2026A",
            "yield_column": "produksi",
        }
        with patch("app.services.dataset_service.storage_service") as mock_storage:
            mock_storage.store_dataset_file = AsyncMock(
                return_value={"file_path": "/s/f.csv", "relative_path": "f.csv"}
            )
            resp = _upload(client, tags)

        assert resp.status_code == 200, resp.text
        ds = resp.json()["dataset"]
        assert ds["region_id"] == references["region"].id
        assert ds["crop_id"] == references["crop"].id
        assert ds["season"] == "2026A"
        assert ds["yield_column"] == "produksi"

    def test_unknown_region_rejected_400(self, client, references):
        tags = {
            "region_id": 9999,
            "crop_id": references["crop"].id,
            "season": "2026A",
            "yield_column": "produksi",
        }
        resp = _upload(client, tags)

        assert resp.status_code == 400
        assert "Region" in resp.json()["detail"]

    def test_deactivated_region_rejected_400(self, client, references):
        tags = {
            "region_id": references["old_region"].id,
            "crop_id": references["crop"].id,
            "season": "2026A",
            "yield_column": "produksi",
        }
        resp = _upload(client, tags)

        assert resp.status_code == 400
        assert "no longer active" in resp.json()["detail"]

    def test_missing_yield_column_rejected_400(self, client, references):
        tags = {
            "region_id": references["region"].id,
            "crop_id": references["crop"].id,
            "season": "2026A",
        }
        resp = _upload(client, tags)

        assert resp.status_code == 400
        assert "Yield column" in resp.json()["detail"]

    def test_non_numeric_yield_column_rejected_400(self, client, references):
        tags = {
            "region_id": references["region"].id,
            "crop_id": references["crop"].id,
            "season": "2026A",
            "yield_column": "farmer",
        }
        resp = _upload(client, tags)

        assert resp.status_code == 400
        assert "numeric" in resp.json()["detail"]

    def test_malformed_agri_tags_json_rejected_400(self, client):
        resp = _upload(client, "{not json")
        assert resp.status_code == 400
        assert "agri_tags" in resp.json()["detail"]

    def test_upload_without_tags_unchanged(self, client):
        with patch("app.services.dataset_service.storage_service") as mock_storage:
            mock_storage.store_dataset_file = AsyncMock(
                return_value={"file_path": "/s/f.csv", "relative_path": "f.csv"}
            )
            resp = _upload(client)

        assert resp.status_code == 200, resp.text
        ds = resp.json()["dataset"]
        assert ds["region_id"] is None
        assert ds["crop_id"] is None
        assert ds["season"] is None
        assert ds["yield_column"] is None

    def test_unauthenticated_upload_rejected(self, app, db, references):
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app)
        resp = _upload(client, {"region_id": 1})
        assert resp.status_code in (401, 403)


# ── Detail response carries tags ──────────────────────────────────────

class TestDetailResponse:
    def test_tags_appear_in_dataset_detail(self, client, references):
        tags = {
            "region_id": references["region"].id,
            "crop_id": references["crop"].id,
            "season": "2026A",
            "yield_column": "produksi",
        }
        # AccessControlService is untracked working-tree code from another
        # feature (its log_access has a pre-existing bug); patch it out so
        # this test exercises ticket #4 surface only.
        with (
            patch("app.services.dataset_service.storage_service") as mock_storage,
            patch("app.services.dataset_service.AccessControlService"),
        ):
            mock_storage.store_dataset_file = AsyncMock(
                return_value={"file_path": "/s/f.csv", "relative_path": "f.csv"}
            )
            upload = _upload(client, tags)
        assert upload.status_code == 200
        dataset_id = upload.json()["dataset"]["id"]

        with patch("app.services.dataset_service.AccessControlService"):
            detail = client.get(f"/api/datasets/{dataset_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["region_id"] == tags["region_id"]
        assert body["crop_id"] == tags["crop_id"]
        assert body["season"] == "2026A"
        assert body["yield_column"] == "produksi"


# ── Suggest-yield-column endpoint ─────────────────────────────────────

class TestSuggestEndpoint:
    def _make_dataset(self, db, member, schema_metadata):
        from app.models.dataset import Dataset, DatasetType, DatasetStatus

        ds = Dataset(
            name="S", type=DatasetType.CSV, status=DatasetStatus.ACTIVE,
            owner_id=member.id, organization_id=member.organization_id,
            schema_metadata=schema_metadata,
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)
        return ds

    def test_suggests_numeric_yield_column(self, client, db, member):
        ds = self._make_dataset(db, member, {
            "columns": ["plot", "yield_ton", "rainfall"],
            "data_types": {"plot": "int64", "yield_ton": "float64", "rainfall": "float64"},
        })
        resp = client.get(f"/api/agri/suggest-yield-column?dataset_id={ds.id}")
        assert resp.status_code == 200
        assert resp.json()["suggestion"] == "yield_ton"

    def test_suggests_indonesian_name(self, client, db, member):
        ds = self._make_dataset(db, member, {
            "columns": ["plot", "produksi", "luas"],
            "data_types": {"plot": "int64", "produksi": "float64", "luas": "float64"},
        })
        resp = client.get(f"/api/agri/suggest-yield-column?dataset_id={ds.id}")
        assert resp.json()["suggestion"] == "produksi"

    def test_no_suggestion_returns_none(self, client, db, member):
        ds = self._make_dataset(db, member, {
            "columns": ["plot", "rainfall"],
            "data_types": {"plot": "int64", "rainfall": "float64"},
        })
        resp = client.get(f"/api/agri/suggest-yield-column?dataset_id={ds.id}")
        assert resp.status_code == 200
        assert resp.json()["suggestion"] is None

    def test_non_numeric_match_not_suggested(self, client, db, member):
        ds = self._make_dataset(db, member, {
            "columns": ["yield_note", "rainfall"],
            "data_types": {"yield_note": "object", "rainfall": "float64"},
        })
        resp = client.get(f"/api/agri/suggest-yield-column?dataset_id={ds.id}")
        assert resp.json()["suggestion"] is None

    def test_missing_dataset_404(self, client):
        resp = client.get("/api/agri/suggest-yield-column?dataset_id=9999")
        assert resp.status_code == 404

    def test_requires_auth(self, app, db):
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app)
        resp = client.get("/api/agri/suggest-yield-column?dataset_id=1")
        assert resp.status_code in (401, 403)

    def test_access_denied_for_foreign_private_dataset(self, app, db, member):
        from app.models.dataset import Dataset, DatasetType, DatasetStatus

        other = User(
            email="other@example.com", hashed_password="x", full_name="Other",
            is_active=True, is_superuser=False, organization_id=77, role="member",
        )
        db.add(other)
        db.commit()
        ds = Dataset(
            name="Private", type=DatasetType.CSV, status=DatasetStatus.ACTIVE,
            owner_id=other.id, organization_id=77,
            sharing_level="private",
            schema_metadata={"columns": ["yield"], "data_types": {"yield": "float64"}},
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)

        resp = client_of(app).get(f"/api/agri/suggest-yield-column?dataset_id={ds.id}")
        assert resp.status_code == 403

    # ── Pre-upload suggestion (wizard flow) ───────────────────────────

    def test_suggest_from_file_before_upload(self, client):
        resp = client.post(
            "/api/agri/suggest-yield-column/file",
            files={"file": ("farm.csv", io.BytesIO(CSV_BYTES), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dataset_id"] is None
        assert body["suggestion"] == "hasil"
        assert "farmer" not in body["numeric_columns"]

    def test_suggest_from_file_requires_auth(self, app):
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app)
        resp = client.post(
            "/api/agri/suggest-yield-column/file",
            files={"file": ("farm.csv", io.BytesIO(CSV_BYTES), "text/csv")},
        )
        assert resp.status_code in (401, 403)


# ── Region pre-suggestion endpoint (Story 9) ──────────────────────────

REGION_CSV = (
    b"plot,wilayah,produksi\n"
    b"1,Jawa Barat,5.2\n"
    b"2,jawa barat,4.8\n"
)


class TestSuggestRegionEndpoint:
    def test_suggests_region_from_file(self, client, references):
        resp = client.post(
            "/api/agri/suggest-region/file",
            files={"file": ("farm.csv", io.BytesIO(REGION_CSV), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["region_column"] == "wilayah"
        assert body["suggestion"] == {
            "region_id": references["region"].id,
            "region_name": "Jawa Barat",
        }

    def test_no_region_column_returns_null_suggestion(self, client, references):
        resp = client.post(
            "/api/agri/suggest-region/file",
            files={"file": ("farm.csv", io.BytesIO(CSV_BYTES), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["suggestion"] is None
        assert body["region_column"] is None

    def test_deactivated_region_not_suggested(self, client, references):
        """Only the active reference list is matched — a file tagged with a
        deactivated region gets no suggestion (the user picks explicitly)."""
        csv_bytes = b"wilayah,produksi\nLama Sekali,5.2\n"
        resp = client.post(
            "/api/agri/suggest-region/file",
            files={"file": ("farm.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["suggestion"] is None

    def test_requires_auth(self, app):
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app)
        resp = client.post(
            "/api/agri/suggest-region/file",
            files={"file": ("farm.csv", io.BytesIO(REGION_CSV), "text/csv")},
        )
        assert resp.status_code in (401, 403)


def client_of(app):
    return TestClient(app)


# ── Pooled crop classifier (Stories 19/24) ────────────────────────────

class TestCropClassifierEndpoints:
    def test_train_requires_admin(self, client):
        """A member may read classifier status but not trigger training.

        (This codebase's admin gate answers 400 for a non-admin member.)
        """
        resp = client.post("/api/agri/crop-classifier/train")
        assert resp.status_code in (400, 401, 403)

    def test_train_not_enough_data_shape(self, admin_client):
        """Empty pool → not-enough-data with counts, never rows/identities."""
        resp = admin_client.post("/api/agri/crop-classifier/train")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["state"] == "not-enough-data"
        assert body["contributor_count"] == 0
        assert body["minimum"] == 5
        assert set(body.keys()) <= {
            "state", "model_id", "contributor_count", "minimum",
            "distinct_crops", "error_message",
        }

    def test_status_none_before_training(self, client):
        resp = client.get("/api/agri/crop-classifier")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"state": "none", "model_id": None,
                               "accuracy": None, "error_message": None}

    def test_status_requires_auth(self, app):
        app.dependency_overrides.pop(get_current_user, None)
        resp = TestClient(app).get("/api/agri/crop-classifier")
        assert resp.status_code in (401, 403)

    def test_train_trains_when_pool_qualifies(self, admin_client, db, references):
        """Qualified pool → endpoint delegates to the service and reports
        training. MindsDB stays out via the gateway seam."""
        from unittest.mock import Mock
        import pandas as pd
        from app.models.dataset import Dataset, DatasetType
        from app.services.agri_data import AgriDataService

        crop2 = Crop(name="Jagung", is_active=True)
        db.add(crop2)
        db.commit()

        for i in range(5):
            db.add(Dataset(
                name=f"pool-{i}", type=DatasetType.CSV,
                file_path=f"/s/p{i}.csv", size_bytes=100,
                owner_id=1, organization_id=10 + i,
                is_active=True, is_deleted=False,
                region_id=references["region"].id,
                crop_id=references["crop"].id if i % 2 else crop2.id,
                season="2026A", yield_column="produksi",
                column_statistics={"produksi": {"mean": 5.0}},
            ))
        db.commit()

        gateway = Mock()
        gateway.upload_file_to_mindsdb.return_value = "agri_crop_classifier_1.csv"
        gateway.create_model.return_value = {"status": "success"}
        gateway.delete_model.return_value = True

        pooled_frame = pd.DataFrame({
            "region": ["Jawa Barat"] * 3,
            "season": ["2026A"] * 3,
            "yield_value": [5.0, 4.8, 5.2],
            "crop": ["Padi", "Padi", "Jagung"],
        })
        with patch.object(AgriDataService, "mindsdb",
                          new_callable=lambda: property(lambda self: gateway)), \
             patch.object(AgriDataService, "_build_pooled_training_frame",
                          return_value=pooled_frame):
            resp = admin_client.post("/api/agri/crop-classifier/train")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["state"] == "training", body
        assert body["model_id"] is not None
        assert body["contributor_count"] == 5
        assert body["distinct_crops"] == 2

        # The classifier row is persisted as a pooled model (no dataset).
        model = db.query(DatasetModel).filter(
            DatasetModel.id == body["model_id"]).first()
        assert model is not None
        assert model.dataset_id is None
        assert model.model_type == "classifier"
        assert model.status == "training"

        # Status endpoint reads the same row — refresh_status is the seam
        # that would otherwise reach live MindsDB.
        with patch("app.services.model_training.ModelTrainingService.refresh_status",
                   side_effect=lambda m: m):
            status_resp = admin_client.get("/api/agri/crop-classifier")
        assert status_resp.status_code == 200
        assert status_resp.json()["state"] == "training"
        assert status_resp.json()["model_id"] == body["model_id"]
