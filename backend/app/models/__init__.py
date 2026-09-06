# Database models - Import all models to ensure they are registered with SQLAlchemy

from app.core.database import Base
from .user import User
from .organization import Organization, OrganizationType, DataSharingLevel, UserRole
from .config import Configuration
from .dataset import (
    Dataset, DatasetAccessLog, DatasetModel, DatasetChatSession, 
    ChatMessage, DatasetShareAccess, DatasetType, DatasetStatus, 
    AIProcessingStatus, DatabaseConnector, DatasetDownload, 
    LLMConfiguration, ShareAccessSession
)
from .file_handler import FileUpload, MindsDBHandler, FileProcessingLog, UploadStatus, ProcessingStatus
from .analytics import (
    ActivityLog, UsageMetric, DatashareStats, UserSessionLog, 
    ModelPerformanceLog, ActivityType, UsageMetricType, DatasetAccess,
    SystemMetrics, AccessRequest, AuditLog, RequestType, AccessLevel,
    RequestStatus, UrgencyLevel, RequestCategory, Notification
)
from .proxy_connector import (
    ProxyConnector, SharedProxyLink, ProxyAccessLog, ProxyCredentialVault
)
from .admin_config import (
    ConfigurationOverride, MindsDBConfiguration, ConfigurationHistory
)
from .agri import Region, Crop
from .data_connector import DataConnector

__all__ = [
    # SQLAlchemy base
    "Base",

    # User models
    "User",
    
    # Organization models
    "Organization", "OrganizationType", "DataSharingLevel", "UserRole",
    
    # Configuration models
    "Configuration",
    
    # Dataset models
    "Dataset", "DatasetAccessLog", "DatasetModel", "DatasetChatSession",
    "ChatMessage", "DatasetShareAccess", "DatasetType", "DatasetStatus",
    "AIProcessingStatus", "DatabaseConnector", "DatasetDownload",
    "LLMConfiguration", "ShareAccessSession",
    
    # File handler models
    "FileUpload", "MindsDBHandler", "FileProcessingLog", "UploadStatus", "ProcessingStatus",
    
    # Analytics models
    "ActivityLog", "UsageMetric", "DatashareStats", "UserSessionLog",
    "ModelPerformanceLog", "ActivityType", "UsageMetricType", "DatasetAccess",
    "SystemMetrics", "AccessRequest", "AuditLog", "RequestType", "AccessLevel",
    "RequestStatus", "UrgencyLevel", "RequestCategory", "Notification",
    
    # Proxy connector models
    "ProxyConnector", "SharedProxyLink", "ProxyAccessLog", "ProxyCredentialVault",
    
    # Admin config models
    "ConfigurationOverride", "MindsDBConfiguration", "ConfigurationHistory",

    # Agricultural reference models
    "Region", "Crop",

    # Compatibility alias
    "DataConnector",
]