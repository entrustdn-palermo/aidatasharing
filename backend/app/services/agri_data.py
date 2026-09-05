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
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agri import Crop, Region

logger = logging.getLogger(__name__)


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

    # ── Internals ─────────────────────────────────────────────────────

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
