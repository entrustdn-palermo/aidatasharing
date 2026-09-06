"""
DataConnector — compatibility alias for DatabaseConnector.

The PermissionService and encryption-migration code reference DataConnector
(from app.models.data_connector), while the canonical model lives in
dataset.py as DatabaseConnector. This module provides the alias so that
imports resolve without breaking existing references.
"""

from app.models.dataset import DatabaseConnector as DataConnector

__all__ = ["DataConnector"]
