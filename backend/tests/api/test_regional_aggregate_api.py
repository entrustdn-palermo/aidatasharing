"""
API-level tests for Regional Aggregate (ticket #5, ADR-0001).

Covers:
- GET /api/agri/regional-aggregate — happy path and minimum gate
- GET /api/agri/contributor-minimum — read default and stored value
- PUT /api/agri/contributor-minimum — admin set and validation
- Auth enforcement for all endpoints
"""
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
from app.models.dataset import Dataset, DatasetType, DatasetStatus
from app.models.config import Configuration
from app.models.user import User
from app.api import agri


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
def app(db, member):
    application = FastAPI()
    application.include_router(agri.router, prefix="/api/agri")

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


# ── Contributing datasets factory ─────────────────────────────────────

def _make_dataset(db, organization_id, *,
                  region_id=1, crop_id=1, season="2026A",
                  yield_column="produksi",
                  column_statistics=None,
                  is_active=True, is_deleted=False):
    """Create a dataset that qualifies for the pool."""
    ds = Dataset(
        name=f"Farm {organization_id}",
        type=DatasetType.CSV,
        status=DatasetStatus.ACTIVE,
        owner_id=1,
        organization_id=organization_id,
        region_id=region_id,
        crop_id=crop_id,
        season=season,
        yield_column=yield_column,
        column_statistics=column_statistics or {"produksi": {"mean": 5.5}},
        is_active=is_active,
        is_deleted=is_deleted,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


# ── GET /regional-aggregate ──────────────────────────────────────────

class TestGetRegionalAggregate:
    def test_returns_pooled_mean_when_minimum_met(self, client, db):
        """5 datasets from 5 orgs → ready with pooled mean."""
        for i in range(5):
            _make_dataset(db, organization_id=10 + i)

        resp = client.get(
            "/api/agri/regional-aggregate?region_id=1&crop_id=1&season=2026A"
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "ready"
        assert body["contributor_count"] == 5
        assert body["pooled_mean_yield"] == 5.5  # all means are 5.5
        assert body["minimum"] == 5

    def test_not_enough_data_when_below_minimum(self, client, db):
        """Only 3 datasets → not-enough-data."""
        for i in range(3):
            _make_dataset(db, organization_id=10 + i)

        resp = client.get(
            "/api/agri/regional-aggregate?region_id=1&crop_id=1&season=2026A"
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "not-enough-data"
        assert body["contributor_count"] == 3
        assert body.get("pooled_mean_yield") is None

    def test_own_dataset_counts_toward_minimum(self, client, db, member):
        """Querying user's own dataset counts (they are org 10)."""
        _make_dataset(db, organization_id=10)  # member's org
        # 3 other orgs — total 4, still below minimum
        for i in range(3):
            _make_dataset(db, organization_id=20 + i)

        resp = client.get(
            "/api/agri/regional-aggregate?region_id=1&crop_id=1&season=2026A"
        )

        assert resp.status_code == 200
        assert resp.json()["state"] == "not-enough-data"
        assert resp.json()["contributor_count"] == 4

    def test_no_contributing_datasets_returns_not_enough(self, client, db):
        """Empty pool → not-enough-data."""
        resp = client.get(
            "/api/agri/regional-aggregate?region_id=1&crop_id=1&season=2026A"
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "not-enough-data"
        assert resp.json()["contributor_count"] == 0

    def test_never_exposes_individual_rows(self, client, db):
        """Response must not leak yield_values, datasets, or contributor_ids."""
        for i in range(5):
            _make_dataset(db, organization_id=10 + i)

        resp = client.get(
            "/api/agri/regional-aggregate?region_id=1&crop_id=1&season=2026A"
        )
        body = resp.json()
        for key in ("yield_values", "datasets", "organizations", "contributor_ids"):
            assert key not in body

    def test_requires_auth(self, app, db):
        """Unauthenticated request is rejected."""
        app.dependency_overrides.pop(get_current_user, None)
        unauth_client = TestClient(app)
        resp = unauth_client.get(
            "/api/agri/regional-aggregate?region_id=1&crop_id=1&season=2026A"
        )
        assert resp.status_code in (401, 403)


# ── GET /contributor-minimum ─────────────────────────────────────────

class TestGetContributorMinimum:
    def test_default_is_five(self, client):
        resp = client.get("/api/agri/contributor-minimum")
        assert resp.status_code == 200
        assert resp.json()["minimum"] == 5

    def test_reads_stored_value(self, client, db):
        db.add(Configuration(
            key="agri.contributor_minimum",
            value="7",
            description="Test",
        ))
        db.commit()

        resp = client.get("/api/agri/contributor-minimum")
        assert resp.json()["minimum"] == 7

    def test_requires_auth(self, app, db):
        app.dependency_overrides.pop(get_current_user, None)
        unauth_client = TestClient(app)
        resp = unauth_client.get("/api/agri/contributor-minimum")
        assert resp.status_code in (401, 403)


# ── PUT /contributor-minimum ─────────────────────────────────────────

class TestSetContributorMinimum:
    def test_admin_can_set(self, admin_client, db):
        resp = admin_client.put(
            "/api/agri/contributor-minimum",
            json={"minimum": 10},
        )
        assert resp.status_code == 200
        assert resp.json()["minimum"] == 10

        # Verify it persists
        row = db.query(Configuration).filter(
            Configuration.key == "agri.contributor_minimum"
        ).first()
        assert row is not None
        assert row.value == "10"

    def test_rejects_value_below_two(self, admin_client):
        resp = admin_client.put(
            "/api/agri/contributor-minimum",
            json={"minimum": 1},
        )
        assert resp.status_code == 400
        assert ">= 2" in resp.json()["detail"]

    def test_requires_admin(self, client):
        resp = client.put(
            "/api/agri/contributor-minimum",
            json={"minimum": 10},
        )
        assert resp.status_code in (400, 401, 403)

    def test_requires_auth(self, app, db):
        app.dependency_overrides.pop(get_current_user, None)
        unauth_client = TestClient(app)
        resp = unauth_client.put(
            "/api/agri/contributor-minimum",
            json={"minimum": 10},
        )
        assert resp.status_code in (401, 403)
