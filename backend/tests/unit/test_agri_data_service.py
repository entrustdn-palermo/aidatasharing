"""
Unit tests for AgriDataService — reference-data half of the agricultural seam.

Tests mock the external seam (db session) exactly as the DatasetService unit
tests do: chainable query/filter/order_by/first/all, plus add/commit/refresh.

Covers: listing active entries, admin create, deactivate, deactivated-still-
resolves behavior, and idempotent seeding.
"""
import pytest
from unittest.mock import Mock

from app.services.agri_data import AgriDataService
from app.models.agri import Region, Crop


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def db_session():
    """Mock DB session with proper chainable query."""
    mock = Mock()
    mock.query.return_value = mock
    mock.filter.return_value = mock
    mock.order_by.return_value = mock
    mock.first.return_value = None
    mock.all.return_value = []
    mock.add = Mock()
    mock.commit = Mock()
    mock.rollback = Mock()
    mock.refresh = Mock()
    return mock


@pytest.fixture
def svc(db_session):
    return AgriDataService(db_session)


def make_region(id=1, name="Jawa Barat", code="JKR", is_active=True):
    return Region(id=id, name=name, code=code, is_active=is_active)


def make_crop(id=1, name="Padi", is_active=True):
    return Crop(id=id, name=name, is_active=is_active)


# ── Listing ───────────────────────────────────────────────────────────

class TestListing:
    def test_list_regions_returns_active(self, svc, db_session):
        regions = [make_region(id=1, name="Aceh"), make_region(id=2, name="Bali")]
        db_session.all.return_value = regions

        result = svc.list_regions()

        assert result == regions
        db_session.query.assert_called_once_with(Region)

    def test_list_regions_active_only_by_default(self, svc, db_session):
        svc.list_regions()
        # filter was applied (active-only predicate) before ordering
        db_session.filter.assert_called()

    def test_list_regions_includes_inactive_when_asked(self, svc, db_session):
        regions = [make_region(id=1, name="Aceh"), make_region(id=2, name="Old Region", is_active=False)]
        db_session.all.return_value = regions

        result = svc.list_regions(active_only=False)

        assert result == regions
        db_session.filter.assert_not_called()

    def test_list_crops_returns_active(self, svc, db_session):
        crops = [make_crop(id=1, name="Padi"), make_crop(id=2, name="Jagung")]
        db_session.all.return_value = crops

        result = svc.list_crops()

        assert result == crops
        db_session.query.assert_called_once_with(Crop)

    def test_list_crops_includes_inactive_when_asked(self, svc, db_session):
        crops = [make_crop(id=1, name="Padi"), make_crop(id=2, name="Lama", is_active=False)]
        db_session.all.return_value = crops

        result = svc.list_crops(active_only=False)

        assert result == crops
        db_session.filter.assert_not_called()


# ── Admin create ──────────────────────────────────────────────────────

class TestCreate:
    def test_create_region_persists_active_entry(self, svc, db_session):
        db_session.first.return_value = None  # no duplicate

        svc.create_region(name="Sumatera Barat", code="SUMBAR")

        assert db_session.add.called
        assert db_session.commit.called
        added = db_session.add.call_args[0][0]
        assert isinstance(added, Region)
        assert added.name == "Sumatera Barat"
        assert added.code == "SUMBAR"
        assert added.is_active is True

    def test_create_region_rejects_duplicate_code(self, svc, db_session):
        existing = make_region(name="Jawa Barat", code="JB")
        # name check passes (None), code check finds the existing row
        db_session.first.side_effect = [None, existing]

        with pytest.raises(ValueError, match="already exists"):
            svc.create_region(name="Daerah Istimewa", code="jb")

        assert not db_session.add.called

    def test_create_region_rejects_duplicate_name(self, svc, db_session):
        db_session.first.return_value = make_region(name="Jawa Barat")

        with pytest.raises(ValueError, match="already exists"):
            svc.create_region(name="Jawa Barat")

        assert not db_session.add.called

    def test_create_region_rejects_duplicate_case_insensitively(self, svc, db_session):
        db_session.first.return_value = make_region(name="Jawa Barat")

        with pytest.raises(ValueError, match="already exists"):
            svc.create_region(name="jawa barat")

    def test_create_crop_persists_active_entry(self, svc, db_session):
        db_session.first.return_value = None

        crop = svc.create_crop(name="Kedelai")

        assert db_session.add.called
        assert db_session.commit.called
        added = db_session.add.call_args[0][0]
        assert isinstance(added, Crop)
        assert added.name == "Kedelai"
        assert added.is_active is True

    def test_create_crop_rejects_duplicate_name(self, svc, db_session):
        db_session.first.return_value = make_crop(name="Padi")

        with pytest.raises(ValueError, match="already exists"):
            svc.create_crop(name="Padi")

        assert not db_session.add.called

    def test_create_rejects_empty_name(self, svc):
        with pytest.raises(ValueError, match="required"):
            svc.create_region(name="   ")
        with pytest.raises(ValueError, match="required"):
            svc.create_crop(name="")


# ── Deactivation ──────────────────────────────────────────────────────

class TestDeactivate:
    def test_deactivate_region_sets_inactive(self, svc, db_session):
        region = make_region(id=7, name="Kalimantan Tengah")
        db_session.first.return_value = region

        result = svc.deactivate_region(region_id=7)

        assert result is region
        assert region.is_active is False
        db_session.commit.assert_called_once()

    def test_deactivate_crop_sets_inactive(self, svc, db_session):
        crop = make_crop(id=3, name="Tebu")
        db_session.first.return_value = crop

        result = svc.deactivate_crop(crop_id=3)

        assert result is crop
        assert crop.is_active is False
        db_session.commit.assert_called_once()

    def test_deactivate_missing_region_raises(self, svc, db_session):
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            svc.deactivate_region(region_id=999)

    def test_deactivate_missing_crop_raises(self, svc, db_session):
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            svc.deactivate_crop(crop_id=999)

    def test_deactivate_is_idempotent(self, svc, db_session):
        region = make_region(id=7, name="Kalimantan Tengah", is_active=False)
        db_session.first.return_value = region

        result = svc.deactivate_region(region_id=7)

        assert result.is_active is False
        db_session.commit.assert_called_once()


# ── Deactivated entries remain resolvable ─────────────────────────────

class TestResolve:
    def test_get_region_resolves_inactive_entry(self, svc, db_session):
        region = make_region(id=7, name="Kalimantan Tengah", is_active=False)
        db_session.first.return_value = region

        result = svc.get_region(region_id=7)

        assert result is region
        assert result.name == "Kalimantan Tengah"

    def test_get_crop_resolves_inactive_entry(self, svc, db_session):
        crop = make_crop(id=3, name="Tebu", is_active=False)
        db_session.first.return_value = crop

        result = svc.get_crop(crop_id=3)

        assert result is crop
        assert result.name == "Tebu"

    def test_get_region_missing_raises(self, svc, db_session):
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            svc.get_region(region_id=999)

    def test_get_crop_missing_raises(self, svc, db_session):
        db_session.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            svc.get_crop(crop_id=999)


# ── Seeding ───────────────────────────────────────────────────────────

class TestSeed:
    def test_seed_creates_missing_regions_and_crops(self, svc, db_session):
        # Nothing exists yet: every duplicate-check query returns None.
        db_session.first.return_value = None

        counts = svc.seed_reference_data()

        assert counts["regions_created"] == len(svc.SEED_REGIONS)
        assert counts["crops_created"] == len(svc.SEED_CROPS)
        assert db_session.commit.called

        added = [c[0][0] for c in db_session.add.call_args_list]
        region_names = {a.name for a in added if isinstance(a, Region)}
        crop_names = {a.name for a in added if isinstance(a, Crop)}
        assert "Jawa Barat" in region_names
        assert "DKI Jakarta" in region_names
        assert "Padi" in crop_names
        # All 38 Indonesia provinces seeded
        assert len(region_names) == 38

    def test_seed_is_idempotent_when_entries_exist(self, svc, db_session):
        # Every duplicate-check query finds an existing row.
        db_session.first.side_effect = lambda: make_region()

        counts = svc.seed_reference_data()

        assert counts["regions_created"] == 0
        assert counts["crops_created"] == 0
        assert not db_session.add.called

    def test_seed_regions_are_indonesia_provinces(self, svc):
        names = [r["name"] for r in svc.SEED_REGIONS]
        assert len(names) == 38
        assert len(set(names)) == 38
        for expected in ["Aceh", "Sumatera Utara", "Jawa Tengah", "Jawa Timur", "Papua"]:
            assert expected in names

    def test_seed_crops_are_a_starter_list(self, svc):
        names = [c["name"] for c in svc.SEED_CROPS]
        assert len(names) >= 5
        assert "Padi" in names
        assert "Jagung" in names
