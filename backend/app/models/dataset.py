from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.models.organization import DataSharingLevel
from app.core.database import Base


class DatasetType(str, enum.Enum):
    """Types of datasets"""
    CSV = "csv"
    JSON = "json"
    DATABASE = "database"
    API = "api"
    S3_BUCKET = "s3_bucket"
    EXCEL = "excel"
    PARQUET = "parquet"
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    TXT = "txt"
    RTF = "rtf"
    ODT = "odt"
    IMAGE = "image"


class DatasetStatus(str, enum.Enum):
    """Dataset status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PROCESSING = "processing"
    ERROR = "error"
    ARCHIVED = "archived"
    DELETED = "deleted"  # Added for soft delete


class AIProcessingStatus(str, enum.Enum):
    """AI processing status for datasets"""
    NOT_PROCESSED = "not_processed"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    type = Column(Enum(DatasetType), nullable=False)
    status = Column(Enum(DatasetStatus), default=DatasetStatus.ACTIVE)
    
    # Soft delete and activation flags
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Data source information
    source_url = Column(String, nullable=True)  # File path, API endpoint, etc.
    connection_params = Column(JSON, nullable=True)  # Connection parameters
    connector_id = Column(Integer, ForeignKey("database_connectors.id"), nullable=True)  # Link to connector
    
    # Multiple files support for uploaded datasets
    is_multi_file_dataset = Column(Boolean, default=False, nullable=False)  # True if dataset contains multiple files
    primary_file_path = Column(String, nullable=True)  # Main/primary file path for multi-file datasets
    
    # Organization and sharing - ORGANIZATION IS REQUIRED (no cross-org sharing)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)  # Required!
    sharing_level = Column(Enum(DataSharingLevel), default=DataSharingLevel.PRIVATE)
    
    # Metadata
    size_bytes = Column(Integer, nullable=True)
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    schema_info = Column(JSON, nullable=True)  # Schema/column information
    file_metadata = Column(JSON, nullable=True)  # Enhanced file metadata (structure, dtypes, etc.)
    content_preview = Column(Text, nullable=True)  # Sample of file content for AI context
    
    # MindsDB integration
    mindsdb_table_name = Column(String, nullable=True)  # Name in MindsDB
    mindsdb_database = Column(String, nullable=True)  # MindsDB database name
    
    # AI Processing Status
    ai_processing_status = Column(Enum(AIProcessingStatus), default=AIProcessingStatus.NOT_PROCESSED)
    ai_summary = Column(Text, nullable=True)  # AI-generated summary
    ai_insights = Column(JSON, nullable=True)  # AI-generated insights
    ai_recommendations = Column(JSON, nullable=True)  # AI recommendations
    
    # Data Sharing Features
    public_share_enabled = Column(Boolean, default=False)
    share_token = Column(String, nullable=True, unique=True)  # For public sharing
    share_password = Column(String, nullable=True)
    share_view_count = Column(Integer, default=0)
    
    # AI Chat Features
    ai_chat_enabled = Column(Boolean, default=True)
    chat_model_name = Column(String, nullable=True)  # Gemini model used for chat
    chat_context = Column(JSON, nullable=True)  # Context for AI chat

    # Agent-based AI Configuration (New architecture)
    agent_name = Column(String, nullable=True)  # MindsDB agent name for this dataset
    agent_created_at = Column(DateTime, nullable=True)  # When the agent was created
    agent_last_updated = Column(DateTime, nullable=True)  # Last agent update
    chat_model_provider = Column(String, nullable=True)  # LLM provider: 'google', 'openai', 'anthropic'
    chat_model_config = Column(JSON, nullable=True)  # Additional model parameters
    
    # Access control within organization
    allow_download = Column(Boolean, default=True)
    allow_api_access = Column(Boolean, default=True)
    allow_ai_chat = Column(Boolean, default=True)
    allow_model_training = Column(Boolean, default=True)
    
    # Data Quality Metrics (AI-powered)
    data_quality_score = Column(String, nullable=True)  # Overall quality score
    completeness_score = Column(String, nullable=True)
    consistency_score = Column(String, nullable=True)
    accuracy_score = Column(String, nullable=True)
    
    # Enhanced metadata for dataset management
    file_path = Column(String, nullable=True)  # Actual file storage path (separate from source_url)
    preview_data = Column(JSON, nullable=True)  # Cached preview data for quick access
    schema_metadata = Column(JSON, nullable=True)  # Detailed schema analysis results
    quality_metrics = Column(JSON, nullable=True)  # Enhanced data quality metrics
    column_statistics = Column(JSON, nullable=True)  # Per-column statistical analysis
    
    # Multiple files metadata
    files_metadata = Column(JSON, nullable=True)  # Metadata for all files in multi-file dataset
    total_files_count = Column(Integer, default=1)  # Total number of files in dataset
    
    # Download tracking
    download_count = Column(Integer, default=0)  # Total number of downloads
    last_downloaded_at = Column(DateTime, nullable=True)  # Last download timestamp

    # Agricultural tags (wizard upload): dataset-level in v1.
    # region_id/crop_id stay resolvable even after the reference entry is
    # deactivated — historical tags never break.
    region_id = Column(Integer, ForeignKey("agri_regions.id"), nullable=True, index=True)
    crop_id = Column(Integer, ForeignKey("agri_crops.id"), nullable=True, index=True)
    season = Column(String(50), nullable=True)  # Growing season the records cover
    yield_column = Column(String(255), nullable=True)  # User-confirmed numeric yield column
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_accessed = Column(DateTime, nullable=True)
    ai_processed_at = Column(DateTime, nullable=True)

    # Relationships
    owner = relationship("User", back_populates="owned_datasets", foreign_keys=[owner_id])
    deleted_by_user = relationship("User", foreign_keys=[deleted_by])
    organization = relationship("Organization")
    connector = relationship("DatabaseConnector", back_populates="datasets")
    access_logs = relationship("DatasetAccessLog", back_populates="dataset")
    downloads = relationship("DatasetDownload", back_populates="dataset")
    models = relationship("DatasetModel", back_populates="dataset")
    chat_sessions = relationship("DatasetChatSession", back_populates="dataset")
    share_accesses = relationship("DatasetShareAccess", back_populates="dataset")
    files = relationship("DatasetFile", back_populates="dataset", cascade="all, delete-orphan")

    def soft_delete(self, user_id: int, delete_file: bool = True):
        """Soft delete the dataset with optional file cleanup"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.deleted_by = user_id
        self.status = DatasetStatus.DELETED
        self.is_active = False
        
        # Note: File deletion is handled in the API layer since it requires
        # async operations and access to the storage service

    def activate(self):
        """Activate the dataset"""
        if not self.is_deleted:
            self.is_active = True
            self.status = DatasetStatus.ACTIVE

    def deactivate(self):
        """Deactivate the dataset"""
        if not self.is_deleted:
            self.is_active = False
            self.status = DatasetStatus.INACTIVE


class DatasetAccessLog(Base):
    __tablename__ = "dataset_access_logs"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Can be null for public access
    access_type = Column(String, nullable=False)  # 'view', 'download', 'api', 'query', 'chat'
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    share_token = Column(String, nullable=True)  # If accessed via share link
    session_id = Column(String, nullable=True)  # For tracking anonymous sessions
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    dataset = relationship("Dataset", back_populates="access_logs")
    user = relationship("User")


class DatasetDownload(Base):
    """Track dataset download operations with detailed metadata"""
    __tablename__ = "dataset_downloads"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Can be null for public access
    download_token = Column(String, nullable=False, unique=True, index=True)  # Secure download token
    
    # Download configuration
    file_format = Column(String, nullable=False)  # 'csv', 'json', 'excel', 'original'
    compression = Column(String, nullable=True)  # 'zip', 'gzip', None
    
    # File information
    original_filename = Column(String, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    
    # Download status and progress
    download_status = Column(String, default="pending")  # 'pending', 'in_progress', 'completed', 'failed', 'expired'
    progress_percentage = Column(Integer, default=0)  # 0-100
    error_message = Column(Text, nullable=True)
    
    # Timing information
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # Token expiration
    
    # Access tracking
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    share_token = Column(String, nullable=True)  # If accessed via share link
    
    # Performance metrics
    download_duration_seconds = Column(Integer, nullable=True)
    transfer_rate_mbps = Column(String, nullable=True)  # Megabits per second
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    dataset = relationship("Dataset", back_populates="downloads")
    user = relationship("User")


class DatasetModel(Base):
    __tablename__ = "dataset_models"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    name = Column(String, nullable=False)
    model_type = Column(String, nullable=False)  # 'predictor', 'classifier', 'chat', 'embedding'
    mindsdb_model_name = Column(String, nullable=False)
    
    # Soft delete and activation flags
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Model configuration
    target_column = Column(String, nullable=True)
    feature_columns = Column(JSON, nullable=True)
    model_params = Column(JSON, nullable=True)
    
    # AI Engine Information
    engine_type = Column(String, nullable=True)  # 'gemini', 'lightgbm', 'neural_network'
    ai_model_version = Column(String, nullable=True)  # e.g., 'gemini-2.0-flash'
    
    # Performance metrics
    accuracy = Column(String, nullable=True)
    training_time = Column(Integer, nullable=True)  # seconds
    prediction_count = Column(Integer, default=0)
    last_prediction_at = Column(DateTime, nullable=True)
    
    # Status
    status = Column(String, default="training")  # 'training', 'complete', 'error', 'archived', 'deleted'
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    dataset = relationship("Dataset", back_populates="models")
    deleted_by_user = relationship("User", foreign_keys=[deleted_by])

    def soft_delete(self, user_id: int):
        """Soft delete the model"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.deleted_by = user_id
        self.status = "deleted"
        self.is_active = False

    def activate(self):
        """Activate the model"""
        if not self.is_deleted:
            self.is_active = True
            if self.status == "archived":
                self.status = "complete"

    def deactivate(self):
        """Deactivate the model"""
        if not self.is_deleted:
            self.is_active = False
            self.status = "archived"


class DatasetChatSession(Base):
    __tablename__ = "dataset_chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Can be null for public access
    session_token = Column(String, nullable=False, unique=True)
    share_token = Column(String, nullable=True)  # If accessed via share link
    
    # Session metadata
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    
    # Chat configuration
    ai_model_name = Column(String, nullable=False)  # e.g., 'gemini-2.0-flash'
    system_prompt = Column(Text, nullable=True)
    context_data = Column(JSON, nullable=True)  # Dataset context for AI
    
    # Session stats
    message_count = Column(Integer, default=0)
    total_tokens_used = Column(Integer, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    ended_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    dataset = relationship("Dataset", back_populates="chat_sessions")
    user = relationship("User")
    messages = relationship("ChatMessage", back_populates="session")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("dataset_chat_sessions.id"), nullable=False)
    
    # Message content
    message_type = Column(String, nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    message_metadata = Column(JSON, nullable=True)  # Additional message metadata (renamed from metadata)
    
    # AI processing info
    tokens_used = Column(Integer, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    ai_model_version = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("DatasetChatSession", back_populates="messages")


class DatasetShareAccess(Base):
    __tablename__ = "dataset_share_accesses"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    share_token = Column(String, nullable=False)
    
    # Access details
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    referrer = Column(String, nullable=True)
    
    # Geographic info (optional)
    country = Column(String, nullable=True)
    city = Column(String, nullable=True)
    
    # Access metadata
    access_duration_seconds = Column(Integer, nullable=True)
    pages_viewed = Column(Integer, default=1)
    files_downloaded = Column(Integer, default=0)
    chat_messages_sent = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    dataset = relationship("Dataset", back_populates="share_accesses")


class DatabaseConnector(Base):
    """Database connector configuration for MySQL, PostgreSQL, S3 etc."""
    __tablename__ = "database_connectors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    connector_type = Column(String, nullable=False)  # 'mysql', 'postgresql', 's3', 'api'
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    
    # Connection configuration
    connection_config = Column(JSON, nullable=False)  # Connection parameters
    credentials = Column(JSON, nullable=True)  # Encrypted credentials
    
    # Soft delete and activation flags
    is_active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # MindsDB integration
    mindsdb_database_name = Column(String, nullable=True)
    
    # Metadata
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    last_tested_at = Column(DateTime, nullable=True)
    test_status = Column(String, default="untested")  # 'untested', 'success', 'failed'
    test_error = Column(Text, nullable=True)
    
    # Enhanced editing capabilities
    is_editable = Column(Boolean, default=True)
    supports_write = Column(Boolean, default=False)
    max_connections = Column(Integer, default=5)
    connection_timeout = Column(Integer, default=30)
    
    # Real-time capabilities
    supports_real_time = Column(Boolean, default=False)
    last_synced_at = Column(DateTime, nullable=True)
    sync_frequency = Column(Integer, default=3600)  # seconds
    auto_sync_enabled = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    created_by_user = relationship("User", foreign_keys=[created_by])
    deleted_by_user = relationship("User", foreign_keys=[deleted_by])
    datasets = relationship("Dataset", back_populates="connector")

    def soft_delete(self, user_id: int):
        """Soft delete the connector"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.deleted_by = user_id
        self.is_active = False


class LLMConfiguration(Base):
    """LLM configuration for LiteLLM and other providers"""
    __tablename__ = "llm_configurations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    provider = Column(String, nullable=False)  # 'gemini', 'openai', 'anthropic', 'litellm'
    llm_model_name = Column(String, nullable=False)  # 'gemini-2.0-flash', 'gpt-4', etc.
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    
    # Configuration
    api_key = Column(String, nullable=True)  # Encrypted API key
    api_base = Column(String, nullable=True)  # Custom API base URL
    model_params = Column(JSON, nullable=True)  # Model-specific configuration
    litellm_config = Column(JSON, nullable=True)  # LiteLLM specific config
    
    # Soft delete and activation flags
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)  # Default model for org
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Usage tracking
    total_tokens_used = Column(Integer, default=0)
    total_requests = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    
    # Metadata
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    created_by_user = relationship("User", foreign_keys=[created_by])
    deleted_by_user = relationship("User", foreign_keys=[deleted_by])

    def soft_delete(self, user_id: int):
        """Soft delete the LLM configuration"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.deleted_by = user_id
        self.is_active = False
        self.is_default = False


class ShareAccessSession(Base):
    """Track anonymous sessions for shared datasets"""
    __tablename__ = "share_access_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String, nullable=False, unique=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    share_token = Column(String, nullable=False)
    
    # Access details
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    referrer = Column(String, nullable=True)
    
    # Session state
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, default=datetime.utcnow)
    
    # Usage tracking
    pages_viewed = Column(Integer, default=0)
    files_downloaded = Column(Integer, default=0)
    chat_messages_sent = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    dataset = relationship("Dataset")


class DatasetFile(Base):
    """Individual files within a dataset (for multi-file datasets)"""
    __tablename__ = "dataset_files"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    
    # File information
    filename = Column(String, nullable=False)  # Original filename
    file_path = Column(String, nullable=False)  # Storage path
    relative_path = Column(String, nullable=True)  # Relative path for serving
    file_size = Column(Integer, nullable=True)  # File size in bytes
    file_type = Column(String, nullable=True)  # File extension/type
    mime_type = Column(String, nullable=True)  # MIME type
    
    # File metadata
    file_metadata = Column(JSON, nullable=True)  # File-specific metadata
    is_primary = Column(Boolean, default=False)  # Primary file in the dataset
    file_order = Column(Integer, default=0)  # Display order
    
    # Status flags
    is_processed = Column(Boolean, default=False)  # Processing status
    is_deleted = Column(Boolean, default=False)  # Soft delete flag
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    dataset = relationship("Dataset", back_populates="files")
    
    def soft_delete(self):
        """Mark file as deleted"""
        self.is_deleted = True
        self.updated_at = datetime.utcnow()

# Add to User model relationship
# Note: This would need to be added to the User model in user.py
# owned_datasets = relationship("Dataset", back_populates="owner") 