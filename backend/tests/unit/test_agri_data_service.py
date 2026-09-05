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


# ── Regional Aggregate ────────────────────────────────────────────────

# A lightweight Dataset-like object for testing aggregate queries.
# Uses a plain class rather than the real SQLAlchemy model so that the
# unit tests never touch the DB schema at all — the external seam is
# the mocked db_session, same as every other test in this file.


class FakeDataset:
    """Stand-in for a SQLAlchemy Dataset row in aggregate tests."""

    def __init__(self, *, id=1, organization_id=10, region_id=1, crop_id=1,
                 season="2026A", yield_column="produksi",
                 column_statistics=None, is_active=True, is_deleted=False,
                 sharing_level="private"):
        self.id = id
        self.organization_id = organization_id
        self.region_id = region_id
        self.crop_id = crop_id
        self.season = season
        self.yield_column = yield_column
        self.column_statistics = column_statistics or {}
        self.is_active = is_active
        self.is_deleted = is_deleted
        self.sharing_level = sharing_level


def make_ds(**kw):
    """Convenience factory for FakeDataset with a minimal column_statistics."""
    kw.setdefault("column_statistics", {"produksi": {"mean": 5.0}})
    return FakeDataset(**kw)


class TestContributorMinimum:
    def test_default_is_five(self, svc, db_session):
        db_session.first.return_value = None
        assert svc.get_contributor_minimum() == 5

    def test_reads_stored_value(self, svc, db_session):
        from app.models.config import Configuration

        db_session.first.return_value = Configuration(
            key=svc.CONTRIBUTOR_MINIMUM_KEY, value="7"
        )
        assert svc.get_contributor_minimum() == 7

    def test_set_and_read_back(self, svc, db_session):
        db_session.first.return_value = None  # no existing row

        svc.set_contributor_minimum(10)

        assert db_session.add.called
        added = db_session.add.call_args[0][0]
        assert added.key == svc.CONTRIBUTOR_MINIMUM_KEY
        assert added.value == "10"
        db_session.commit.assert_called()

    def test_set_rejects_less_than_two(self, svc):
        with pytest.raises(ValueError, match=">= 2"):
            svc.set_contributor_minimum(1)
        with pytest.raises(ValueError, match=">= 2"):
            svc.set_contributor_minimum(0)
        with pytest.raises(ValueError, match=">= 2"):
            svc.set_contributor_minimum(-5)

    def test_update_existing_value(self, svc, db_session):
        from app.models.config import Configuration

        existing = Configuration(key=svc.CONTRIBUTOR_MINIMUM_KEY, value="5")
        db_session.first.return_value = existing

        svc.set_contributor_minimum(8)

        assert existing.value == "8"
        db_session.commit.assert_called()


class TestRegionalAggregate:
    def test_cross_org_pooling(self, svc, db_session):
        """Datasets from different orgs all contribute to the pool."""
        ds1 = make_ds(id=1, organization_id=10, yield_column="hasil",
                       column_statistics={"hasil": {"mean": 4.5}})
        ds2 = make_ds(id=2, organization_id=20, yield_column="hasil",
                       column_statistics={"hasil": {"mean": 5.2}})
        ds3 = make_ds(id=3, organization_id=30, yield_column="hasil",
                       column_statistics={"hasil": {"mean": 6.0}})
        db_session.all.return_value = [ds1, ds2, ds3]

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A"
        )

        # 3 datasets from 3 different orgs pool together, but the
        # Contributor Minimum (5) is not met → honest not-enough-data.
        assert result["state"] == "not-enough-data"
        assert result["contributor_count"] == 3

    def test_aggregate_math(self, svc, db_session):
        """Pooled mean is the arithmetic mean of per-dataset yield means."""
        datasets = [
            make_ds(id=i, organization_id=10 + i,
                    column_statistics={"produksi": {"mean": v}})
            for i, v in enumerate([4.0, 5.0, 6.0, 7.0, 8.0], start=1)
        ]
        db_session.all.return_value = datasets

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A"
        )

        assert result["state"] == "ready"
        # (4+5+6+7+8) / 5 = 6.0
        assert abs(result["pooled_mean_yield"] - 6.0) < 0.0001
        assert result["contributor_count"] == 5

    def test_minimum_gate_below_threshold(self, svc, db_session):
        """Below the minimum, the API returns not-enough-data."""
        # Only 3 contributing datasets (minimum is 5)
        datasets = [
            make_ds(id=i, organization_id=10 + i)
            for i in range(1, 4)
        ]
        db_session.all.return_value = datasets

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A"
        )

        assert result["state"] == "not-enough-data"
        assert result["contributor_count"] == 3
        assert result["minimum"] == 5
        assert "pooled_mean_yield" not in result

    def test_own_dataset_counts_toward_minimum(self, svc, db_session):
        """The querying member's dataset always counts toward the minimum.

        It counts by being part of the pool: the pool query has no
        organization filter, so the member's own dataset is included
        exactly like every other Contributing Dataset.
        """
        # 4 other orgs + the member's own org = 5
        own_org_id = 99
        others = [
            make_ds(id=i, organization_id=10 + i)
            for i in range(1, 5)
        ]
        own = make_ds(id=99, organization_id=own_org_id)
        db_session.all.return_value = others + [own]

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A",
        )

        assert result["state"] == "ready"
        assert result["contributor_count"] == 5

    def test_minimum_gate_met_exactly(self, svc, db_session):
        """Exactly 5 contributing datasets produces a ready aggregate."""
        datasets = [
            make_ds(id=i, organization_id=10 + i)
            for i in range(1, 6)
        ]
        db_session.all.return_value = datasets

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A"
        )

        assert result["state"] == "ready"
        assert result["contributor_count"] == 5

    def test_admin_configurable_minimum(self, svc, db_session):
        """When admin sets minimum to 3, 3 datasets is enough."""
        from app.models.config import Configuration

        db_session.first.return_value = Configuration(
            key=svc.CONTRIBUTOR_MINIMUM_KEY, value="3"
        )
        datasets = [
            make_ds(id=i, organization_id=10 + i)
            for i in range(1, 4)
        ]
        db_session.all.return_value = datasets

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A"
        )

        assert result["state"] == "ready"
        assert result["contributor_count"] == 3

    def test_region_crop_season_filtering(self, svc, db_session):
        """Only datasets matching region_id + crop_id + season qualify."""
        # The mock simulates SQL WHERE: only matching datasets are returned.
        # Non-matching datasets (wrong region/crop/season) would be filtered
        # out by the query and never reach the Python-level loop.
        matching = [
            make_ds(id=i, organization_id=10 + i)
            for i in range(1, 6)
        ]
        db_session.all.return_value = matching

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A"
        )

        assert result["state"] == "ready"
        assert result["contributor_count"] == 5

    def test_no_yield_data_returns_not_enough(self, svc, db_session):
        """5 datasets but none have yield means in stats → not-enough-data."""
        datasets = [
            make_ds(id=i, organization_id=10 + i,
                    column_statistics={"produksi": {}})  # no "mean" key
            for i in range(1, 6)
        ]
        db_session.all.return_value = datasets

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A"
        )

        assert result["state"] == "not-enough-data"
        assert result["contributor_count"] == 5
        assert "pooled_mean_yield" not in result

    def test_excludes_inactive_and_deleted(self, svc, db_session):
        """Inactive and soft-deleted datasets do not count."""
        # The mock simulates SQL WHERE: the query already filters out
        # is_active=False and is_deleted=True, so only qualifying rows
        # reach the Python-level loop.
        datasets = [
            make_ds(id=3, organization_id=30),
            make_ds(id=4, organization_id=40),
            make_ds(id=5, organization_id=50),
            make_ds(id=6, organization_id=60),
            make_ds(id=7, organization_id=70),
        ]
        db_session.all.return_value = datasets

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A"
        )

        assert result["state"] == "ready"
        assert result["contributor_count"] == 5  # only 5 (not 7) → 2 excluded

    def test_never_exposes_individual_rows(self, svc, db_session):
        """Response never contains raw yield values or contributor identities."""
        datasets = [
            make_ds(id=i, organization_id=10 + i,
                    column_statistics={"produksi": {"mean": 5.0 + i}})
            for i in range(1, 6)
        ]
        db_session.all.return_value = datasets

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A"
        )

        assert result["state"] == "ready"
        assert "pooled_mean_yield" in result
        # Must not leak individual values
        for key in ("yield_values", "datasets", "organizations", "contributor_ids"):
            assert key not in result, f"Response must not contain '{key}'"

    def test_sharing_level_irrelevant_to_pool_membership(self, svc, db_session):
        """Private datasets join the pool just like shared ones (ADR-0001).

        Sharing Level governs the dataset itself, not the pool — a fully
        tagged private dataset is a Contributing Dataset like any other.
        """
        datasets = [
            make_ds(id=i, organization_id=10 + i,
                    sharing_level="private" if i % 2 else "organization")
            for i in range(1, 6)
        ]
        db_session.all.return_value = datasets

        result = svc.compute_regional_aggregate(
            region_id=1, crop_id=1, season="2026A"
        )

        assert result["state"] == "ready"
        assert result["contributor_count"] == 5

class TestYieldMeanFromStats:
    def test_extracts_flat_mean(self):
        stats = {"produksi": {"mean": 5.25}}
        ds = FakeDataset(yield_column="produksi", column_statistics=stats)
        assert AgriDataService._yield_mean_from_stats(ds) == 5.25

    def test_extracts_nested_mean(self):
        stats = {"columns": {"produksi": {"mean": 6.0}}}
        ds = FakeDataset(yield_column="produksi", column_statistics=stats)
        assert AgriDataService._yield_mean_from_stats(ds) == 6.0

    def test_returns_none_when_missing(self):
        ds = FakeDataset(yield_column="hasil", column_statistics={})
        assert AgriDataService._yield_mean_from_stats(ds) is None

    def test_returns_none_when_stats_none(self):
        ds = FakeDataset(yield_column="produksi", column_statistics=None)
        assert AgriDataService._yield_mean_from_stats(ds) is None

    def test_returns_none_for_nan_mean(self):
        """A NaN mean (legacy data) must not poison the pooled aggregate."""
        import math

        ds = FakeDataset(
            yield_column="produksi",
            column_statistics={"produksi": {"mean": float("nan")}},
        )
        result = AgriDataService._yield_mean_from_stats(ds)
        assert result is None or not math.isnan(result)
        assert result is None

    def test_returns_none_for_non_numeric_mean(self):
        ds = FakeDataset(
            yield_column="produksi",
            column_statistics={"produksi": {"mean": "not-a-number"}},
        )
        assert AgriDataService._yield_mean_from_stats(ds) is None

    def test_nested_non_dict_column_is_skipped(self):
        ds = FakeDataset(
            yield_column="produksi",
            column_statistics={"columns": {"produksi": "corrupt"}},
        )
        assert AgriDataService._yield_mean_from_stats(ds) is None
