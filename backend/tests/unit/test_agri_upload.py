"""
Unit tests for agri-tagged upload (ticket #4).

Covers the AgriDataService upload-side methods (tag validation, yield-column
suggestion, Contributing Dataset qualification) and DatasetService.create_from_files
with optional agri tags. External seams are mocked per the existing pattern.
"""
import json
import pytest
from unittest.mock import Mock, AsyncMock, patch

from app.services.agri_data import AgriDataService
from app.services.dataset_service import DatasetService
from app.models.agri import Region, Crop
from app.models.dataset import Dataset, DatasetType, DatasetStatus
from app.models.user import User


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def db_session():
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
def agri_svc(db_session):
    return AgriDataService(db_session)


@pytest.fixture
def dataset_svc(db_session):
    return DatasetService(db_session)


@pytest.fixture
def owner():
    return User(
        id=1, email="owner@example.com", full_name="Owner",
        is_active=True, is_superuser=False, organization_id=10, role="member",
    )


@pytest.fixture
def mock_csv_file():
    f = Mock()
    f.filename = "farm_data.csv"
    f.content_type = "text/csv"
    csv_bytes = (
        b"plot,produksi,hasil,luas,hujan\n"
        b"1,5.2,3.1,2.0,120\n"
        b"2,4.8,3.4,1.5,130\n"
    )
    f.read = AsyncMock(return_value=csv_bytes)
    f.seek = AsyncMock()
    return f


def _active_region(id=5, name="Jawa Barat", code="JB"):
    return Region(id=id, name=name, code=code, is_active=True)


def _active_crop(id=2, name="Padi"):
    return Crop(id=id, name=name, is_active=True)


# ── Tag validation ────────────────────────────────────────────────────

class TestValidateUploadTags:
    def test_valid_tags_pass(self, agri_svc, db_session):
        db_session.first.side_effect = [_active_region(), _active_crop()]

        result = agri_svc.validate_upload_tags(
            {"region_id": 5, "crop_id": 2, "season": "2026A", "yield_column": "produksi"},
            numeric_columns=["produksi", "hasil", "luas", "hujan"],
        )

        assert result["region_id"] == 5
        assert result["crop_id"] == 2
        assert result["season"] == "2026A"
        assert result["yield_column"] == "produksi"

    def test_unknown_region_rejected(self, agri_svc, db_session):
        db_session.first.side_effect = [None]

        with pytest.raises(ValueError, match="Region"):
            agri_svc.validate_upload_tags(
                {"region_id": 999, "crop_id": 2, "season": "2026A", "yield_column": "produksi"},
                numeric_columns=["produksi"],
            )

    def test_deactivated_region_rejected(self, agri_svc, db_session):
        db_session.first.side_effect = [Region(id=5, name="Lama", is_active=False)]

        with pytest.raises(ValueError, match="no longer active"):
            agri_svc.validate_upload_tags(
                {"region_id": 5, "crop_id": 2, "season": "2026A", "yield_column": "produksi"},
                numeric_columns=["produksi"],
            )

    def test_deactivated_crop_rejected(self, agri_svc, db_session):
        db_session.first.side_effect = [_active_region(), Crop(id=2, name="Lama", is_active=False)]

        with pytest.raises(ValueError, match="no longer active"):
            agri_svc.validate_upload_tags(
                {"region_id": 5, "crop_id": 2, "season": "2026A", "yield_column": "produksi"},
                numeric_columns=["produksi"],
            )

    def test_missing_yield_column_rejected(self, agri_svc, db_session):
        db_session.first.side_effect = [_active_region(), _active_crop()]

        with pytest.raises(ValueError, match="Yield column"):
            agri_svc.validate_upload_tags(
                {"region_id": 5, "crop_id": 2, "season": "2026A", "yield_column": None},
                numeric_columns=["produksi"],
            )

    def test_non_numeric_yield_column_rejected(self, agri_svc, db_session):
        db_session.first.side_effect = [_active_region(), _active_crop()]

        with pytest.raises(ValueError, match="numeric"):
            agri_svc.validate_upload_tags(
                {"region_id": 5, "crop_id": 2, "season": "2026A", "yield_column": "plot"},
                numeric_columns=["produksi", "hasil"],
            )

    def test_yield_column_not_in_file_rejected(self, agri_svc, db_session):
        db_session.first.side_effect = [_active_region(), _active_crop()]

        with pytest.raises(ValueError, match="numeric"):
            agri_svc.validate_upload_tags(
                {"region_id": 5, "crop_id": 2, "season": "2026A", "yield_column": "nonexistent"},
                numeric_columns=["produksi"],
            )

    def test_missing_season_rejected(self, agri_svc, db_session):
        db_session.first.side_effect = [_active_region(), _active_crop()]

        with pytest.raises(ValueError, match="Season"):
            agri_svc.validate_upload_tags(
                {"region_id": 5, "crop_id": 2, "season": None, "yield_column": "produksi"},
                numeric_columns=["produksi"],
            )

    def test_overlong_season_rejected(self, agri_svc, db_session):
        db_session.first.side_effect = [_active_region(), _active_crop()]

        with pytest.raises(ValueError, match="50 characters"):
            agri_svc.validate_upload_tags(
                {"region_id": 5, "crop_id": 2, "season": "S" * 51, "yield_column": "produksi"},
                numeric_columns=["produksi"],
            )

    def test_missing_region_rejected_with_clear_message(self, agri_svc, db_session):
        with pytest.raises(ValueError, match="Region is required"):
            agri_svc.validate_upload_tags(
                {"crop_id": 2, "season": "2026A", "yield_column": "produksi"},
                numeric_columns=["produksi"],
            )

    def test_empty_tags_dict_rejected(self, agri_svc, db_session):
        """{} is an explicit (empty) tag set — validated, not ignored."""
        with pytest.raises(ValueError, match="Region"):
            agri_svc.validate_upload_tags({}, numeric_columns=["produksi"])


# ── Yield-column suggestion ───────────────────────────────────────────

class TestSuggestYieldColumn:
    def test_suggests_by_yield_name(self, agri_svc):
        assert agri_svc.suggest_yield_column(["plot", "yield", "rainfall"]) == "yield"

    def test_suggests_indonesian_names(self, agri_svc):
        assert agri_svc.suggest_yield_column(["plot", "produksi", "luas"]) == "produksi"
        assert agri_svc.suggest_yield_column(["hasil_panen", "curah_hujan"]) == "hasil_panen"

    def test_prefers_yield_over_secondary_matches(self, agri_svc):
        assert agri_svc.suggest_yield_column(["hasil", "yield_ton"]) == "yield_ton"

    def test_returns_none_when_no_match(self, agri_svc):
        assert agri_svc.suggest_yield_column(["plot", "rainfall", "area"]) is None

    def test_ignores_non_numeric_columns(self, agri_svc):
        # "yield" is present but not numeric -> not suggested
        assert agri_svc.suggest_yield_column(["yield"], numeric_only=True) is None

    def test_suggestion_is_only_a_guess(self, agri_svc):
        # Never raises, never mutates input; returns a column name or None
        cols = ["produksi", "lainnya"]
        result = agri_svc.suggest_yield_column(cols)
        assert result in cols or result is None


# ── Region pre-suggestion (Story 9) ───────────────────────────────────

class TestSuggestRegionForFile:
    def _csv(self, header, rows):
        """rows: one list of cells per data line."""
        lines = [",".join(header)] + [",".join(r) for r in rows]
        return ("\n".join(lines) + "\n").encode()

    def test_suggests_region_from_matching_column(self, agri_svc, db_session):
        db_session.all.return_value = [_active_region(id=5, name="Jawa Barat")]
        content = self._csv(
            ["plot", "wilayah", "produksi"],
            [["1", "Jawa Barat", "5.2"], ["2", "Jawa Barat", "4.8"]],
        )
        result = agri_svc.suggest_region_for_file(content, "farm.csv")
        assert result["region_column"] == "wilayah"
        assert result["suggestion"] == {"region_id": 5, "region_name": "Jawa Barat"}

    def test_matches_case_insensitively_and_by_code(self, agri_svc, db_session):
        db_session.all.return_value = [_active_region(id=5, name="Jawa Barat", code="JB")]
        content = self._csv(["Region"], [["jawa barat"], ["JB"]])
        result = agri_svc.suggest_region_for_file(content, "farm.csv")
        assert result["suggestion"]["region_id"] == 5

    def test_no_region_like_column_returns_none(self, agri_svc, db_session):
        content = self._csv(["plot", "produksi"], [["1", "5.2"]])
        result = agri_svc.suggest_region_for_file(content, "farm.csv")
        assert result == {"suggestion": None, "region_column": None}

    def test_unrecognizable_values_return_none(self, agri_svc, db_session):
        db_session.all.return_value = [_active_region(id=5, name="Jawa Barat")]
        content = self._csv(["wilayah"], [["Atlantis"]])
        result = agri_svc.suggest_region_for_file(content, "farm.csv")
        assert result["suggestion"] is None
        assert result["region_column"] == "wilayah"

    def test_mixed_regions_return_none(self, agri_svc, db_session):
        db_session.all.return_value = [
            _active_region(id=5, name="Jawa Barat"),
            _active_region(id=6, name="Jawa Tengah"),
        ]
        content = self._csv(["wilayah"], [["Jawa Barat"], ["Jawa Tengah"]])
        result = agri_svc.suggest_region_for_file(content, "farm.csv")
        assert result["suggestion"] is None
        assert result["region_column"] == "wilayah"

    def test_blank_cells_are_skipped(self, agri_svc, db_session):
        db_session.all.return_value = [_active_region(id=5, name="Jawa Barat")]
        content = self._csv(["wilayah"], [["Jawa Barat"], [""], ["jawa barat"]])
        result = agri_svc.suggest_region_for_file(content, "farm.csv")
        assert result["suggestion"]["region_id"] == 5

    def test_non_tabular_file_returns_none(self, agri_svc):
        result = agri_svc.suggest_region_for_file(b"not a csv", "notes.txt")
        assert result == {"suggestion": None, "region_column": None}

    def test_suggestion_never_applied_without_user(self, agri_svc, db_session):
        # The method only reports a guess; it must not touch the db.
        db_session.all.return_value = [_active_region(id=5, name="Jawa Barat")]
        content = self._csv(["wilayah"], [["Jawa Barat"]])
        agri_svc.suggest_region_for_file(content, "farm.csv")
        db_session.add.assert_not_called()
        db_session.commit.assert_not_called()


# ── Contributing Dataset qualification ────────────────────────────────

class TestQualification:
    def test_fully_tagged_dataset_qualifies(self, agri_svc):
        ds = Dataset(
            id=1, region_id=5, crop_id=2, season="2026A",
            yield_column="produksi", sharing_level=None,
        )
        assert agri_svc.is_contributing_dataset(ds) is True

    def test_missing_any_tag_disqualifies(self, agri_svc):
        for field in ["region_id", "crop_id", "season", "yield_column"]:
            kwargs = dict(id=1, region_id=5, crop_id=2, season="2026A", yield_column="produksi")
            kwargs[field] = None
            assert agri_svc.is_contributing_dataset(Dataset(**kwargs)) is False

    def test_untagged_dataset_does_not_qualify(self, agri_svc):
        assert agri_svc.is_contributing_dataset(Dataset(id=1)) is False


# ── create_from_files with agri tags ──────────────────────────────────

class TestCreateFromFilesWithTags:
    async def test_tags_stored_on_dataset(self, dataset_svc, db_session, owner, mock_csv_file):
        with (
            patch("app.services.dataset_service.mindsdb_service"),
            patch("app.services.dataset_service.storage_service") as mock_storage,
            patch("app.services.dataset_service.AgriDataService") as MockAgri,
        ):
            mock_storage.store_dataset_file = AsyncMock(
                return_value={"file_path": "/storage/f.csv", "relative_path": "f.csv"}
            )
            MockAgri.return_value.validate_upload_tags.return_value = {
                "region_id": 5, "crop_id": 2, "season": "2026A", "yield_column": "produksi",
            }

            result = await dataset_svc.create_from_files(
                files=[mock_csv_file], name="Agri CSV", sharing_level="private",
                user=owner, organization_id=owner.organization_id,
                agri_tags={"region_id": 5, "crop_id": 2, "season": "2026A", "yield_column": "produksi"},
            )

            assert result.region_id == 5
            assert result.crop_id == 2
            assert result.season == "2026A"
            assert result.yield_column == "produksi"

    async def test_invalid_tags_rejected_before_storage(self, dataset_svc, db_session, owner, mock_csv_file):
        with (
            patch("app.services.dataset_service.mindsdb_service"),
            patch("app.services.dataset_service.storage_service") as mock_storage,
            patch("app.services.dataset_service.AgriDataService") as MockAgri,
        ):
            mock_storage.store_dataset_file = AsyncMock()
            MockAgri.return_value.validate_upload_tags.side_effect = ValueError(
                "Region 999 not found"
            )

            with pytest.raises(ValueError, match="Region 999 not found"):
                await dataset_svc.create_from_files(
                    files=[mock_csv_file], name="Bad", sharing_level="private",
                    user=owner, organization_id=owner.organization_id,
                    agri_tags={"region_id": 999, "crop_id": 2, "season": "2026A", "yield_column": "produksi"},
                )

            # Nothing stored, no dataset record added
            mock_storage.store_dataset_file.assert_not_awaited()
            assert not db_session.add.called

    async def test_untagged_upload_unchanged(self, dataset_svc, db_session, owner, mock_csv_file):
        """No agri_tags -> no validation call, no agri columns set (no regression)."""
        with (
            patch("app.services.dataset_service.mindsdb_service"),
            patch("app.services.dataset_service.storage_service") as mock_storage,
            patch("app.services.dataset_service.AgriDataService") as MockAgri,
        ):
            mock_storage.store_dataset_file = AsyncMock(
                return_value={"file_path": "/storage/f.csv", "relative_path": "f.csv"}
            )

            result = await dataset_svc.create_from_files(
                files=[mock_csv_file], name="Plain CSV", sharing_level="private",
                user=owner, organization_id=owner.organization_id,
            )

            MockAgri.return_value.validate_upload_tags.assert_not_called()
            assert result.region_id is None
            assert result.crop_id is None
            assert result.season is None
            assert result.yield_column is None
            assert result.status == DatasetStatus.ACTIVE

    async def test_tags_survive_through_detail(self, dataset_svc, db_session, owner):
        """Agri tags appear in the dataset detail response, with names resolved."""
        ds = Dataset(
            id=42, name="Agri", type=DatasetType.CSV, status=DatasetStatus.ACTIVE,
            owner_id=owner.id, organization_id=owner.organization_id,
            region_id=5, crop_id=2, season="2026A", yield_column="produksi",
        )
        db_session.first.return_value = ds
        with (
            patch("app.services.dataset_service.DataSharingService") as MockDS,
            patch("app.services.dataset_service.AccessControlService"),
            patch("app.services.dataset_service.AgriDataService") as MockAgri,
        ):
            MockDS.return_value.can_access_dataset.return_value = True
            MockAgri.return_value.get_region.return_value = _active_region(id=5, name="Jawa Barat")
            MockAgri.return_value.get_crop.return_value = _active_crop(id=2, name="Padi")
            result = await dataset_svc.get_dataset_details(dataset_id=42, user=owner)

        assert result["region_id"] == 5
        assert result["crop_id"] == 2
        assert result["season"] == "2026A"
        assert result["yield_column"] == "produksi"
        # Story 30: names resolved for display (deactivated entries included)
        assert result["agri_tags"] == {
            "region_id": 5, "region_name": "Jawa Barat",
            "crop_id": 2, "crop_name": "Padi",
            "season": "2026A", "yield_column": "produksi",
        }

    async def test_untagged_dataset_has_no_agri_block(self, dataset_svc, db_session, owner):
        """A dataset without agri tags carries no agri_tags key."""
        ds = Dataset(
            id=43, name="Plain", type=DatasetType.CSV, status=DatasetStatus.ACTIVE,
            owner_id=owner.id, organization_id=owner.organization_id,
        )
        db_session.first.return_value = ds
        with (
            patch("app.services.dataset_service.DataSharingService") as MockDS,
            patch("app.services.dataset_service.AccessControlService"),
            patch("app.services.dataset_service.AgriDataService") as MockAgri,
        ):
            MockDS.return_value.can_access_dataset.return_value = True
            result = await dataset_svc.get_dataset_details(dataset_id=43, user=owner)

        assert "agri_tags" not in result
        MockAgri.assert_not_called()

    async def test_detail_resolves_deactivated_reference_entries(self, dataset_svc, db_session, owner):
        """A tag pointing at a deactivated Region/Crop still renders its name."""
        ds = Dataset(
            id=44, name="Legacy", type=DatasetType.CSV, status=DatasetStatus.ACTIVE,
            owner_id=owner.id, organization_id=owner.organization_id,
            region_id=7, crop_id=None, season=None, yield_column=None,
        )
        db_session.first.return_value = ds
        with (
            patch("app.services.dataset_service.DataSharingService") as MockDS,
            patch("app.services.dataset_service.AccessControlService"),
            patch("app.services.dataset_service.AgriDataService") as MockAgri,
        ):
            MockDS.return_value.can_access_dataset.return_value = True
            MockAgri.return_value.get_region.return_value = Region(
                id=7, name="Daerah Lama", is_active=False
            )
            result = await dataset_svc.get_dataset_details(dataset_id=44, user=owner)

        assert result["agri_tags"]["region_name"] == "Daerah Lama"
        assert result["agri_tags"]["crop_name"] is None
