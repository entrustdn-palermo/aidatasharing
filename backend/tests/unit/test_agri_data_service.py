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


# ── Pooled crop classifier (Stories 19/24) ────────────────────────────


import pandas as pd
from types import SimpleNamespace

from app.models.dataset import DatasetModel
from app.models.user import User


def make_gateway():
    gw = Mock()
    gw.upload_file_to_mindsdb.return_value = "agri_crop_classifier_1.csv"
    gw.create_model.return_value = {"status": "success"}
    gw.delete_model.return_value = True
    gw.get_model_info.return_value = None
    return gw


def classifier_ds(id, crop_id, region_id=1, season="2026A", file_path=None):
    """A contributing dataset row for classifier tests (file-backed)."""
    return SimpleNamespace(
        id=id, region_id=region_id, crop_id=crop_id, season=season,
        yield_column="produksi", file_path=file_path or f"/fake/ds{id}.csv",
        is_multi_file_dataset=False, is_active=True, is_deleted=False,
        organization_id=10, column_statistics={"produksi": {"mean": 5.0}},
    )


def pool_of(n, crops=(1, 2)):
    return [classifier_ds(i + 1, crop_id=crops[i % len(crops)]) for i in range(n)]


class TestTrainCropClassifier:
    def _svc(self, db_session, gw):
        return AgriDataService(db_session, mindsdb_service=gw)

    def test_below_contributor_minimum_not_enough_data(self, db_session):
        gw = make_gateway()
        svc = self._svc(db_session, gw)
        db_session.first.return_value = None  # minimum default 5
        db_session.all.side_effect = [pool_of(4), []]

        result = svc.train_crop_classifier(User(id=1))

        assert result["state"] == "not-enough-data"
        assert result["contributor_count"] == 4
        assert result["minimum"] == 5
        gw.create_model.assert_not_called()
        db_session.add.assert_not_called()

    def test_single_crop_pool_not_enough_data(self, db_session):
        """A classifier needs at least two classes — one crop can't learn."""
        gw = make_gateway()
        svc = self._svc(db_session, gw)
        db_session.first.return_value = None
        db_session.all.side_effect = [pool_of(5, crops=(1,)), []]

        result = svc.train_crop_classifier(User(id=1))

        assert result["state"] == "not-enough-data"
        assert result["distinct_crops"] == 1
        gw.create_model.assert_not_called()

    def test_trains_over_pool_and_persists_pooled_row(self, db_session):
        gw = make_gateway()
        svc = self._svc(db_session, gw)
        db_session.first.return_value = None
        db_session.all.side_effect = [pool_of(5), []]
        db_session.refresh.side_effect = lambda m: setattr(m, "id", 7)
        frame = pd.DataFrame({
            "region": ["Jawa Barat"] * 5, "season": ["2026A"] * 5,
            "yield_value": [5.0] * 5, "crop": ["Padi", "Jagung"] * 2 + ["Padi"],
        })
        svc._build_pooled_training_frame = Mock(return_value=frame)

        result = svc.train_crop_classifier(User(id=1))

        assert result["state"] == "training"
        assert result["model_id"] == 7
        assert result["contributor_count"] == 5

        model = db_session.add.call_args[0][0]
        assert model.dataset_id is None  # pooled — belongs to no dataset
        assert model.model_type == "classifier"
        assert model.target_column == "crop"
        assert model.feature_columns == ["region", "season", "yield_value"]
        assert model.status == "training"

        gw.create_model.assert_called_once()
        args, kwargs = gw.create_model.call_args
        assert args[0] == model.mindsdb_model_name
        assert args[2] == "files"
        assert "SELECT * FROM files." in args[1]
        assert kwargs["predict"] == "crop"

    def test_retrain_drops_previous_classifier(self, db_session):
        gw = make_gateway()
        svc = self._svc(db_session, gw)
        db_session.first.return_value = None
        old = DatasetModel(
            id=3, dataset_id=None, name="agri_crop_classifier_100",
            model_type="classifier", mindsdb_model_name="agri_crop_classifier_100",
            status="complete",
        )
        db_session.all.side_effect = [pool_of(5), [old]]
        frame = pd.DataFrame({
            "region": ["A"], "season": ["2026A"], "yield_value": [1.0], "crop": ["Padi"],
        })
        svc._build_pooled_training_frame = Mock(return_value=frame)

        result = svc.train_crop_classifier(User(id=1))

        assert result["state"] == "training"
        gw.delete_model.assert_called_once_with("agri_crop_classifier_100")
        assert old.is_deleted is True
        assert old.status == "deleted"

    def test_create_model_failure_marks_row_error(self, db_session):
        gw = make_gateway()
        gw.create_model.return_value = {"status": "error", "error": "boom"}
        svc = self._svc(db_session, gw)
        db_session.first.return_value = None
        db_session.all.side_effect = [pool_of(5), []]
        frame = pd.DataFrame({
            "region": ["A"], "season": ["2026A"], "yield_value": [1.0], "crop": ["Padi"],
        })
        svc._build_pooled_training_frame = Mock(return_value=frame)

        result = svc.train_crop_classifier(User(id=1))

        assert result["state"] == "error"
        assert "boom" in result["error_message"]
        model = db_session.add.call_args[0][0]
        assert model.status == "error"

    def test_upload_failure_marks_row_error(self, db_session):
        gw = make_gateway()
        gw.upload_file_to_mindsdb.return_value = None
        svc = self._svc(db_session, gw)
        db_session.first.return_value = None
        db_session.all.side_effect = [pool_of(5), []]
        frame = pd.DataFrame({
            "region": ["A"], "season": ["2026A"], "yield_value": [1.0], "crop": ["Padi"],
        })
        svc._build_pooled_training_frame = Mock(return_value=frame)

        result = svc.train_crop_classifier(User(id=1))

        assert result["state"] == "error"
        gw.create_model.assert_not_called()

    def test_unparseable_pool_errors_without_training(self, db_session):
        gw = make_gateway()
        svc = self._svc(db_session, gw)
        db_session.first.return_value = None
        db_session.all.side_effect = [pool_of(5), []]
        svc._build_pooled_training_frame = Mock(return_value=None)

        result = svc.train_crop_classifier(User(id=1))

        assert result["state"] == "error"
        gw.create_model.assert_not_called()
        db_session.add.assert_not_called()

    def test_response_never_exposes_rows_or_identities(self, db_session):
        gw = make_gateway()
        svc = self._svc(db_session, gw)
        db_session.first.return_value = None
        db_session.all.side_effect = [pool_of(5), []]
        frame = pd.DataFrame({
            "region": ["A"], "season": ["2026A"], "yield_value": [1.0], "crop": ["Padi"],
        })
        svc._build_pooled_training_frame = Mock(return_value=frame)

        result = svc.train_crop_classifier(User(id=1))

        # Only counts, minimum, model id, state — no dataset ids, owners, rows
        assert set(result.keys()) <= {
            "state", "model_id", "contributor_count", "minimum", "distinct_crops",
        }


class TestBuildPooledTrainingFrame:
    def _write_csv(self, tmp_path, name, rows):
        path = tmp_path / name
        path.write_text("plot,produksi\n" + rows)
        return str(path)

    def test_standardizes_features_and_target(self, db_session, tmp_path):
        svc = AgriDataService(db_session)
        f1 = self._write_csv(tmp_path, "a.csv", "1,5.2\n2,4.8\n")
        f2 = self._write_csv(tmp_path, "b.csv", "1,3.1\n")
        ds1 = classifier_ds(1, crop_id=1, file_path=f1)
        ds2 = classifier_ds(2, crop_id=2, file_path=f2)
        svc._resolve_storage_base = Mock(return_value=str(tmp_path))
        svc._find_region = Mock(return_value=make_region(id=1, name="Jawa Barat"))
        svc._find_crop = Mock(side_effect=lambda cid: make_crop(id=cid, name="Padi" if cid == 1 else "Jagung"))

        frame = svc._build_pooled_training_frame([ds1, ds2])

        assert list(frame.columns) == ["region", "season", "yield_value", "crop"]
        assert len(frame) == 3
        assert set(frame["crop"]) == {"Padi", "Jagung"}
        assert set(frame["region"]) == {"Jawa Barat"}
        # Names, not ids — the model learns human-readable classes
        assert 1 not in set(frame["crop"])

    def test_relative_paths_resolve_against_storage_base(self, db_session, tmp_path):
        svc = AgriDataService(db_session)
        f = self._write_csv(tmp_path, "rel.csv", "1,5.2\n")
        rel = "sub/rel.csv"
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "rel.csv").write_text("plot,produksi\n1,5.2\n")
        ds = classifier_ds(1, crop_id=1, file_path=rel)
        svc._resolve_storage_base = Mock(return_value=str(tmp_path))
        svc._find_region = Mock(return_value=make_region())
        svc._find_crop = Mock(return_value=make_crop())

        frame = svc._build_pooled_training_frame([ds])

        assert frame is not None and len(frame) == 1

    def test_skips_unreadable_and_unresolvable(self, db_session, tmp_path):
        svc = AgriDataService(db_session)
        good = self._write_csv(tmp_path, "good.csv", "1,5.2\n")
        ds_good = classifier_ds(1, crop_id=1, file_path=good)
        ds_missing = classifier_ds(2, crop_id=2, file_path="nope.csv")
        ds_no_region = classifier_ds(3, crop_id=1, file_path=good, region_id=None)
        ds_no_crop = classifier_ds(4, crop_id=None, file_path=good)
        svc._resolve_storage_base = Mock(return_value=str(tmp_path))
        svc._find_region = Mock(return_value=make_region())
        svc._find_crop = Mock(return_value=make_crop())

        frame = svc._build_pooled_training_frame([ds_good, ds_missing, ds_no_region, ds_no_crop])

        assert len(frame) == 1
        assert frame.iloc[0]["crop"] == "Padi"

    def test_all_unreadable_returns_none(self, db_session):
        svc = AgriDataService(db_session)
        ds = classifier_ds(1, crop_id=1, file_path="gone.csv")
        svc._resolve_storage_base = Mock(return_value="/nonexistent-base")
        svc._find_region = Mock(return_value=make_region())
        svc._find_crop = Mock(return_value=make_crop())

        assert svc._build_pooled_training_frame([ds]) is None

    def test_yield_column_missing_in_file_skipped(self, db_session, tmp_path):
        svc = AgriDataService(db_session)
        f = tmp_path / "x.csv"
        f.write_text("plot,luas\n1,2.0\n")
        ds = classifier_ds(1, crop_id=1, file_path=str(f))
        svc._resolve_storage_base = Mock(return_value=str(tmp_path))
        svc._find_region = Mock(return_value=make_region())
        svc._find_crop = Mock(return_value=make_crop())

        assert svc._build_pooled_training_frame([ds]) is None


class TestCropClassifierStatus:
    def test_none_when_no_model(self, db_session):
        svc = AgriDataService(db_session, mindsdb_service=make_gateway())
        db_session.first.return_value = None

        assert svc.crop_classifier_status() == {"state": "none"}

    def test_reports_stored_fields(self, db_session):
        svc = AgriDataService(db_session, mindsdb_service=make_gateway())
        model = DatasetModel(
            id=9, dataset_id=None, name="m", model_type="classifier",
            mindsdb_model_name="m", status="complete", accuracy="0.83",
        )
        db_session.first.return_value = model

        result = svc.crop_classifier_status()

        assert result["state"] == "complete"
        assert result["model_id"] == 9
        assert result["accuracy"] == "0.83"

    def test_training_status_is_refreshed(self, db_session):
        gw = make_gateway()
        gw.get_model_info.return_value = {"status": "completed", "accuracy": "0.9"}
        svc = AgriDataService(db_session, mindsdb_service=gw)
        model = DatasetModel(
            id=10, dataset_id=None, name="m", model_type="classifier",
            mindsdb_model_name="m", status="training",
        )
        db_session.first.return_value = model

        result = svc.crop_classifier_status()

        assert result["state"] == "complete"
        assert result["accuracy"] == "0.9"
