from pydantic import BaseModel, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.models.dataset import DatasetType, DatasetStatus
from app.models.organization import DataSharingLevel


class DatasetBase(BaseModel):
    name: str
    description: Optional[str] = None
    type: DatasetType
    sharing_level: DataSharingLevel = DataSharingLevel.PRIVATE
    source_url: Optional[str] = None
    connection_params: Optional[Dict[str, Any]] = None
    connector_id: Optional[int] = None
    schema_info: Optional[Dict[str, Any]] = None
    allow_download: bool = True
    allow_api_access: bool = True


class DatasetCreate(DatasetBase):
    @validator('sharing_level')
    def validate_sharing_level(cls, v):
        # Validate sharing level
        if v not in [DataSharingLevel.PRIVATE, DataSharingLevel.ORGANIZATION, DataSharingLevel.PUBLIC]:
            raise ValueError('Invalid sharing level')
        return v


class DatasetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sharing_level: Optional[DataSharingLevel] = None
    connector_id: Optional[int] = None
    allow_download: Optional[bool] = None
    allow_api_access: Optional[bool] = None
    schema_info: Optional[Dict[str, Any]] = None


class DatasetOwner(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class DatasetResponse(DatasetBase):
    id: int
    status: DatasetStatus
    owner_id: int
    organization_id: int
    connector_id: Optional[int] = None
    size_bytes: Optional[int] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    mindsdb_table_name: Optional[str] = None
    mindsdb_database: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_accessed: Optional[datetime] = None
    
    # Enhanced metadata fields
    file_metadata: Optional[Dict[str, Any]] = None
    content_preview: Optional[str] = None
    file_path: Optional[str] = None
    preview_data: Optional[Dict[str, Any]] = None
    schema_metadata: Optional[Dict[str, Any]] = None
    quality_metrics: Optional[Dict[str, Any]] = None
    column_statistics: Optional[Dict[str, Any]] = None
    
    # AI processing fields
    ai_processing_status: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_insights: Optional[Dict[str, Any]] = None
    ai_recommendations: Optional[Dict[str, Any]] = None
    ai_processed_at: Optional[datetime] = None
    
    # Data sharing fields
    public_share_enabled: Optional[bool] = None
    share_token: Optional[str] = None
    share_expires_at: Optional[datetime] = None
    share_view_count: Optional[int] = None
    
    # AI chat fields
    ai_chat_enabled: Optional[bool] = None
    chat_model_name: Optional[str] = None
    chat_context: Optional[Dict[str, Any]] = None
    
    # Access control fields
    allow_ai_chat: Optional[bool] = None
    allow_model_training: Optional[bool] = None
    
    # Download tracking
    download_count: Optional[int] = None
    last_downloaded_at: Optional[datetime] = None
    
    # Soft delete fields
    is_active: Optional[bool] = None
    is_deleted: Optional[bool] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[int] = None
    
    owner: Optional[DatasetOwner] = None
    
    class Config:
        from_attributes = True


class DatasetAccessLog(BaseModel):
    id: int
    dataset_id: int
    user_id: int
    access_type: str
    ip_address: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True