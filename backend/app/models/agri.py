"""
Agricultural reference data models.

Region and Crop are admin-managed reference lists used to tag Datasets.
Entries are soft-deactivatable: a deactivated entry disappears from active
listings but remains resolvable for Datasets already tagged with it, so
historical tags never break.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime

from app.core.database import Base


class Region(Base):
    """An administrative area from the managed reference list (province-level in v1)."""
    __tablename__ = "agri_regions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    code = Column(String(50), unique=True, index=True, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Crop(Base):
    """A crop type from the managed reference list that a dataset's records concern."""
    __tablename__ = "agri_crops"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
