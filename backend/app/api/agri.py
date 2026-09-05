"""
Agri reference data API — thin controllers over AgriDataService.

Members browse active Regions/Crops for dropdowns; admins create entries and
deactivate them. Deactivated entries leave active listings but remain
resolvable by id for Datasets already tagged with them.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user, get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.agri_data import AgriDataService

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────

class RegionResponse(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    is_active: bool


class CropResponse(BaseModel):
    id: int
    name: str
    is_active: bool


class RegionCreate(BaseModel):
    name: str
    code: Optional[str] = None


class CropCreate(BaseModel):
    name: str


# ── Helpers ───────────────────────────────────────────────────────────

def _to_region_response(region) -> RegionResponse:
    return RegionResponse(
        id=region.id, name=region.name, code=region.code, is_active=region.is_active
    )


def _to_crop_response(crop) -> CropResponse:
    return CropResponse(id=crop.id, name=crop.name, is_active=crop.is_active)


def _map_service_error(err: ValueError) -> HTTPException:
    # Match on message suffixes, not substrings: user-supplied names are
    # embedded in the message and could otherwise flip the status code.
    message = str(err)
    if message.endswith("not found"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if message.endswith("already exists"):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


# ── Browsing (any authenticated member) ───────────────────────────────

@router.get("/regions", response_model=List[RegionResponse])
async def list_regions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active Regions (dropdown-ready)."""
    return [_to_region_response(r) for r in AgriDataService(db).list_regions()]


@router.get("/crops", response_model=List[CropResponse])
async def list_crops(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active Crops (dropdown-ready)."""
    return [_to_crop_response(c) for c in AgriDataService(db).list_crops()]


# ── Admin CRUD ────────────────────────────────────────────────────────

@router.post("/regions", response_model=RegionResponse, status_code=status.HTTP_201_CREATED)
async def create_region(
    payload: RegionCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Create a new Region entry (admin)."""
    try:
        region = AgriDataService(db).create_region(name=payload.name, code=payload.code)
    except ValueError as err:
        raise _map_service_error(err)
    return _to_region_response(region)


@router.post("/crops", response_model=CropResponse, status_code=status.HTTP_201_CREATED)
async def create_crop(
    payload: CropCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Create a new Crop entry (admin)."""
    try:
        crop = AgriDataService(db).create_crop(name=payload.name)
    except ValueError as err:
        raise _map_service_error(err)
    return _to_crop_response(crop)


@router.post("/regions/{region_id}/deactivate", response_model=RegionResponse)
async def deactivate_region(
    region_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Deactivate a Region (admin). It leaves active listings but stays resolvable."""
    try:
        region = AgriDataService(db).deactivate_region(region_id)
    except ValueError as err:
        raise _map_service_error(err)
    return _to_region_response(region)


@router.post("/crops/{crop_id}/deactivate", response_model=CropResponse)
async def deactivate_crop(
    crop_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Deactivate a Crop (admin). It leaves active listings but stays resolvable."""
    try:
        crop = AgriDataService(db).deactivate_crop(crop_id)
    except ValueError as err:
        raise _map_service_error(err)
    return _to_crop_response(crop)


# ── Yield-column suggestion ───────────────────────────────────────────

class YieldSuggestionResponse(BaseModel):
    dataset_id: Optional[int] = None
    suggestion: Optional[str] = None
    numeric_columns: List[str]


@router.get("/suggest-yield-column", response_model=YieldSuggestionResponse)
async def suggest_yield_column(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Best-guess yield column for an uploaded dataset (suggestion only).

    Never applied without the user's choice.
    """
    try:
        return AgriDataService(db).suggest_yield_column_for_dataset(
            dataset_id, current_user
        )
    except ValueError as err:
        raise _map_service_error(err)
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(err)
        )


@router.post("/suggest-yield-column/file", response_model=YieldSuggestionResponse)
async def suggest_yield_column_for_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Best-guess yield column for a not-yet-uploaded file.

    Lets a tagging wizard ask "which column is the yield?" before the
    upload commits; the tags themselves are only ever set at upload time.
    """
    content = await file.read()
    return AgriDataService(db).suggest_yield_column_for_file(
        content, file.filename or ""
    )
