"""
AgriDataService — the agricultural service seam (reference-data half).

Owns the admin-managed Region and Crop reference lists:
- listing active entries for member dropdowns
- admin create / deactivate (soft deactivation: deactivated entries leave
  active listings but stay resolvable for Datasets already tagged with them)
- idempotent seeding of the initial province-level Region list (Indonesia)
  and a starter Crop list

The db session is the only external seam; it is injected, matching the
DatasetService pattern.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agri import Crop, Region

logger = logging.getLogger(__name__)


_NUMERIC_DTYPE_KINDS = ("i", "u", "f", "c")
_NUMERIC_DTYPE_PREFIXES = ("int", "uint", "float", "complex")

# Extensions whose files carry columns a yield column could live in
TABULAR_EXTENSIONS = ("csv", "xlsx", "xls", "parquet")


def is_numeric_dtype(dtype: Any) -> bool:
    """Numeric check for both live pandas dtypes and stored dtype strings.

    One definition shared by upload validation and the yield-column
    suggestion, so the two paths can never diverge on what "numeric" means.
    """
    if isinstance(dtype, str):
        lowered = dtype.lower()
        if lowered.startswith("interval"):
            return False
        return lowered.startswith(_NUMERIC_DTYPE_PREFIXES)
    return getattr(dtype, "kind", None) in _NUMERIC_DTYPE_KINDS


def columns_of_file(content: bytes, extension: str) -> Tuple[List[str], List[str]]:
    """(all columns, numeric columns) of an uploaded tabular file.

    Only tabular formats carry a yield column; anything else — or anything
    unparseable — returns ([], []), which makes every yield-column choice
    fail validation: the safe direction for a consent-bearing tag.
    """
    if extension not in TABULAR_EXTENSIONS:
        return [], []
    try:
        import io

        import pandas as pd

        if extension == "csv":
            df = pd.read_csv(io.BytesIO(content))
        elif extension == "parquet":
            df = pd.read_parquet(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
        columns = [str(col) for col in df.columns]
        numeric = [col for col in columns if is_numeric_dtype(df[col].dtype)]
        return columns, numeric
    except Exception as e:
        logger.warning(f"Could not read columns from uploaded file: {e}")
        return [], []


def numeric_columns_of_dataset(dataset: Any) -> List[str]:
    """Numeric column names from a stored dataset's schema metadata."""
    schema = getattr(dataset, "schema_metadata", None) or {}
    data_types = schema.get("data_types") or {}
    return [col for col, dtype in data_types.items() if is_numeric_dtype(dtype)]


# Indonesia's 38 provinces (province-level Region list, v1)
INDONESIA_PROVINCES: List[Dict[str, str]] = [
    {"name": "Aceh", "code": "ACH"},
    {"name": "Sumatera Utara", "code": "SU"},
    {"name": "Sumatera Barat", "code": "SB"},
    {"name": "Riau", "code": "RI"},
    {"name": "Jambi", "code": "JA"},
    {"name": "Sumatera Selatan", "code": "SS"},
    {"name": "Bengkulu", "code": "BE"},
    {"name": "Lampung", "code": "LA"},
    {"name": "Kepulauan Bangka Belitung", "code": "BB"},
    {"name": "Kepulauan Riau", "code": "KR"},
    {"name": "DKI Jakarta", "code": "JK"},
    {"name": "Jawa Barat", "code": "JB"},
    {"name": "Jawa Tengah", "code": "JT"},
    {"name": "DI Yogyakarta", "code": "YO"},
    {"name": "Jawa Timur", "code": "JI"},
    {"name": "Banten", "code": "BT"},
    {"name": "Bali", "code": "BA"},
    {"name": "Nusa Tenggara Barat", "code": "NB"},
    {"name": "Nusa Tenggara Timur", "code": "NT"},
    {"name": "Kalimantan Barat", "code": "KB"},
    {"name": "Kalimantan Tengah", "code": "KT"},
    {"name": "Kalimantan Selatan", "code": "KS"},
    {"name": "Kalimantan Timur", "code": "KI"},
    {"name": "Kalimantan Utara", "code": "KU"},
    {"name": "Sulawesi Utara", "code": "SA"},
    {"name": "Sulawesi Tengah", "code": "ST"},
    {"name": "Sulawesi Selatan", "code": "SN"},
    {"name": "Sulawesi Tenggara", "code": "SG"},
    {"name": "Gorontalo", "code": "GO"},
    {"name": "Sulawesi Barat", "code": "SR"},
    {"name": "Maluku", "code": "MA"},
    {"name": "Maluku Utara", "code": "MU"},
    {"name": "Papua", "code": "PA"},
    {"name": "Papua Barat", "code": "PB"},
    {"name": "Papua Selatan", "code": "PS"},
    {"name": "Papua Tengah", "code": "PT"},
    {"name": "Papua Pegunungan", "code": "PP"},
    {"name": "Papua Barat Daya", "code": "PD"},
]

# Starter crop list for agricultural tagging
STARTER_CROPS: List[Dict[str, str]] = [
    {"name": "Padi"},
    {"name": "Jagung"},
    {"name": "Kedelai"},
    {"name": "Karet"},
    {"name": "Sawit"},
    {"name": "Kopi"},
    {"name": "Teh"},
    {"name": "Kakao"},
    {"name": "Tebu"},
    {"name": "Bawang Merah"},
    {"name": "Cabai"},
    {"name": "Kentang"},
]


class AgriDataService:
    """Reference data for agricultural tagging: Regions and Crops."""

    SEED_REGIONS = INDONESIA_PROVINCES
    SEED_CROPS = STARTER_CROPS

    def __init__(self, db: Session):
        self.db = db

    # ── Browsing (member-facing) ──────────────────────────────────────

    def list_regions(self, active_only: bool = True) -> List[Region]:
        """List Regions, active-only by default (dropdown-ready)."""
        query = self.db.query(Region)
        if active_only:
            query = query.filter(Region.is_active.is_(True))
        return query.order_by(Region.name).all()

    def list_crops(self, active_only: bool = True) -> List[Crop]:
        """List Crops, active-only by default (dropdown-ready)."""
        query = self.db.query(Crop)
        if active_only:
            query = query.filter(Crop.is_active.is_(True))
        return query.order_by(Crop.name).all()

    # ── Resolution (historical tags never break) ──────────────────────

    def get_region(self, region_id: int) -> Region:
        """Resolve a Region by id regardless of active state."""
        region = self.db.query(Region).filter(Region.id == region_id).first()
        if region is None:
            raise ValueError(f"Region {region_id} not found")
        return region

    def get_crop(self, crop_id: int) -> Crop:
        """Resolve a Crop by id regardless of active state."""
        crop = self.db.query(Crop).filter(Crop.id == crop_id).first()
        if crop is None:
            raise ValueError(f"Crop {crop_id} not found")
        return crop

    # ── Admin CRUD ────────────────────────────────────────────────────

    def create_region(self, name: str, code: Optional[str] = None) -> Region:
        """Create a new active Region entry."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Region name is required")
        self._ensure_region_name_available(name)
        code = (code or "").strip() or None
        if code is not None:
            self._ensure_region_code_available(code)

        region = Region(name=name, code=code, is_active=True)
        self.db.add(region)
        self.db.commit()
        self.db.refresh(region)
        return region

    def create_crop(self, name: str) -> Crop:
        """Create a new active Crop entry."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Crop name is required")
        self._ensure_crop_name_available(name)

        crop = Crop(name=name, is_active=True)
        self.db.add(crop)
        self.db.commit()
        self.db.refresh(crop)
        return crop

    def deactivate_region(self, region_id: int) -> Region:
        """Soft-deactivate a Region: leaves active listings, stays resolvable."""
        region = self.get_region(region_id)
        region.is_active = False
        self.db.commit()
        return region

    def deactivate_crop(self, crop_id: int) -> Crop:
        """Soft-deactivate a Crop: leaves active listings, stays resolvable."""
        crop = self.get_crop(crop_id)
        crop.is_active = False
        self.db.commit()
        return crop

    # ── Seeding ───────────────────────────────────────────────────────

    def seed_reference_data(self) -> Dict[str, int]:
        """Idempotently seed the province-level Region list and starter Crop list.

        Existing entries (matched case-insensitively by name) are skipped, so
        admin edits and deactivations survive re-seeding.
        """
        regions_created = 0
        for entry in self.SEED_REGIONS:
            if self._region_exists(entry["name"]):
                continue
            self.db.add(
                Region(name=entry["name"], code=entry.get("code"), is_active=True)
            )
            regions_created += 1

        crops_created = 0
        for entry in self.SEED_CROPS:
            if self._crop_exists(entry["name"]):
                continue
            self.db.add(Crop(name=entry["name"], is_active=True))
            crops_created += 1

        self.db.commit()
        logger.info(
            "Agri reference data seeded: %s regions, %s crops created",
            regions_created,
            crops_created,
        )
        return {"regions_created": regions_created, "crops_created": crops_created}

    # ── Upload tagging ────────────────────────────────────────────────

    YIELD_NAME_KEYWORDS = ("yield", "hasil", "produksi")

    def validate_upload_tags(
        self,
        tags: Dict[str, Any],
        numeric_columns: List[str],
    ) -> Dict[str, Any]:
        """Validate agri tags for an upload; return the normalised tag set.

        References must exist and be active; season must be present; the yield
        column must be one of the file's numeric columns. Raises ValueError
        with a clear message on any violation.
        """
        region_id = tags.get("region_id")
        crop_id = tags.get("crop_id")
        season = (tags.get("season") or "").strip()
        yield_column = tags.get("yield_column")

        # Non-raising lookups: get_region/get_crop raise "not found", but
        # validation wants one consistent "not found or no longer active".
        if region_id is None:
            raise ValueError("Region is required for an agri-tagged upload")
        region = self._find_region(region_id)
        if region is None:
            raise ValueError(f"Region {region_id} not found or no longer active")
        if not region.is_active:
            raise ValueError(f"Region {region_id} is no longer active")

        if crop_id is None:
            raise ValueError("Crop is required for an agri-tagged upload")
        crop = self._find_crop(crop_id)
        if crop is None:
            raise ValueError(f"Crop {crop_id} not found or no longer active")
        if not crop.is_active:
            raise ValueError(f"Crop {crop_id} is no longer active")

        if not season:
            raise ValueError("Season is required for an agri-tagged upload")
        if len(season) > 50:
            raise ValueError("Season must be 50 characters or fewer")

        if not yield_column:
            raise ValueError("Yield column is required for an agri-tagged upload")
        if yield_column not in numeric_columns:
            raise ValueError(
                f"Yield column '{yield_column}' is not a numeric column of the file"
            )

        return {
            "region_id": region.id,
            "crop_id": crop.id,
            "season": season,
            "yield_column": yield_column,
        }

    def suggest_yield_column(
        self,
        columns: List[str],
        numeric_only: bool = False,
        numeric_columns: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Best-guess yield column by name matching.

        A suggestion only — never applied without the user's choice. Matches
        names containing "yield", "hasil", or "produksi" (case-insensitive);
        "yield" wins over secondary matches. With numeric_only=True the guess
        is restricted to the provided numeric_columns (empty when unknown).
        Returns None when nothing matches.
        """
        candidates = columns
        if numeric_only:
            pool = numeric_columns or []
            candidates = [c for c in columns if c in pool]

        lowered = {c: c.lower() for c in candidates}
        for keyword in self.YIELD_NAME_KEYWORDS:
            for col in candidates:
                if keyword in lowered[col]:
                    return col
        return None

    def suggest_yield_column_for_dataset(
        self, dataset_id: int, current_user: Any
    ) -> Dict[str, Any]:
        """Suggestion payload for an already-uploaded dataset.

        Raises ValueError ("... not found") for a missing dataset and
        PermissionError when the user may not see it; the controller maps
        those to 404/403.
        """
        from app.models.dataset import Dataset
        from app.services.data_sharing import DataSharingService

        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if dataset is None:
            raise ValueError("Dataset not found")
        if not current_user.is_superuser and not DataSharingService(
            self.db
        ).can_access_dataset(current_user, dataset):
            raise PermissionError("Access denied to this dataset")

        schema = dataset.schema_metadata or {}
        columns = schema.get("columns") or list((schema.get("data_types") or {}).keys())
        numeric_columns = numeric_columns_of_dataset(dataset)
        return {
            "dataset_id": dataset.id,
            "suggestion": self.suggest_yield_column(
                columns, numeric_only=True, numeric_columns=numeric_columns
            ),
            "numeric_columns": numeric_columns,
        }

    def suggest_yield_column_for_file(
        self, content: bytes, filename: str
    ) -> Dict[str, Any]:
        """Suggestion payload for a not-yet-uploaded file.

        Lets a tagging wizard ask "which column is the yield?" before the
        upload commits — the tags themselves are only ever set by the user's
        choice at upload time.
        """
        ext = filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
        columns, numeric_columns = columns_of_file(content, ext)
        return {
            "dataset_id": None,
            "suggestion": self.suggest_yield_column(
                columns, numeric_only=True, numeric_columns=numeric_columns
            ),
            "numeric_columns": numeric_columns,
        }

    def is_contributing_dataset(self, dataset: "Dataset") -> bool:
        """Whether a Dataset qualifies for the cross-org pool (ADR-0001).

        Tagging with Region, Crop, Season, and Yield Column is the single
        consent act: a fully tagged dataset feeds both Regional Aggregates
        and Model training. Partially tagged datasets never qualify.
        """
        return all(
            getattr(dataset, field, None)
            for field in ("region_id", "crop_id", "season", "yield_column")
        )

    # ── Internals ─────────────────────────────────────────────────────

    def _find_region(self, region_id: Optional[int]) -> Optional[Region]:
        """Resolve a Region by id without raising (None when absent)."""
        if region_id is None:
            return None
        return self.db.query(Region).filter(Region.id == region_id).first()

    def _find_crop(self, crop_id: Optional[int]) -> Optional[Crop]:
        """Resolve a Crop by id without raising (None when absent)."""
        if crop_id is None:
            return None
        return self.db.query(Crop).filter(Crop.id == crop_id).first()

    def _region_exists(self, name: str) -> bool:
        return (
            self.db.query(Region)
            .filter(func.lower(Region.name) == name.lower())
            .first()
            is not None
        )

    def _crop_exists(self, name: str) -> bool:
        return (
            self.db.query(Crop)
            .filter(func.lower(Crop.name) == name.lower())
            .first()
            is not None
        )

    def _region_code_exists(self, code: str) -> bool:
        return (
            self.db.query(Region)
            .filter(func.upper(Region.code) == code.upper())
            .first()
            is not None
        )

    def _ensure_region_name_available(self, name: str):
        if self._region_exists(name):
            raise ValueError(f"Region '{name}' already exists")

    def _ensure_region_code_available(self, code: str):
        if self._region_code_exists(code):
            raise ValueError(f"Region code '{code}' already exists")

    def _ensure_crop_name_available(self, name: str):
        if self._crop_exists(name):
            raise ValueError(f"Crop '{name}' already exists")
