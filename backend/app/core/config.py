import secrets
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from .app_config import get_app_config


class Settings(BaseSettings):
    SECRET_KEY: str = secrets.token_urlsafe(32)
    
    # Database - Single unified database location (loaded from .env)
    DATABASE_URL: str = Field(default=None, env="DATABASE_URL", description="Database connection URL")
    
    # Database connection pool settings (loaded from .env)
    DB_POOL_SIZE: int = Field(default=10, env="DB_POOL_SIZE", description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=20, env="DB_MAX_OVERFLOW", description="Database connection pool max overflow")
    DB_POOL_PRE_PING: bool = Field(default=True, env="DB_POOL_PRE_PING", description="Enable database connection pre-ping")
    DB_POOL_RECYCLE: int = Field(default=3600, env="DB_POOL_RECYCLE", description="Database connection pool recycle time in seconds")
    
    # Database timeout settings (loaded from .env)
    DB_CONNECTION_TIMEOUT: int = Field(default=30, env="DB_CONNECTION_TIMEOUT", description="Database connection timeout in seconds")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Validate that DATABASE_URL is provided
        if not self.DATABASE_URL:
            raise ValueError(
                "DATABASE_URL is required. Please set it in your .env file or environment variables. "
                "Example: DATABASE_URL=postgresql://user:password@host:port/database"
            )
        # Get centralized configuration
        self._app_config = get_app_config()
    
    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins from centralized configuration."""
        return self._app_config.services.get_cors_origins()
    
    # JWT
    @property
    def ACCESS_TOKEN_EXPIRE_MINUTES(self) -> int:
        """Get JWT expiry from centralized config"""
        return self._app_config.security.JWT_ACCESS_TOKEN_EXPIRE_MINUTES

    @property
    def ALGORITHM(self) -> str:
        """Get JWT algorithm from centralized config"""
        return self._app_config.security.JWT_ALGORITHM

    # Encryption Configuration
    ENCRYPTION_KEY: Optional[str] = Field(
        default=None,
        env="ENCRYPTION_KEY",
        description="Encryption key for sensitive data (credentials, API keys). Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    )
    
    # Google API Configuration - Now from environment
    @property
    def GOOGLE_API_KEY(self) -> Optional[str]:
        """Get Google API key from centralized config"""
        return self._app_config.integrations.GOOGLE_API_KEY
    
    # MindsDB Configuration
    @property
    def MINDSDB_URL(self) -> str:
        """Get MindsDB URL from centralized config"""
        return self._app_config.services.get_mindsdb_url()
    
    # AI Model Configuration - MindsDB Agent-Based Architecture
    MINDSDB_AGENT_MODEL: Optional[str] = Field(
        default=None,
        env="MINDSDB_AGENT_MODEL",
        description="Optional display label for the MindsDB agent model; agent creation uses MindsDB's configured default LLM"
    )

    ENABLE_AI_CHAT: bool = True
    MAX_CHAT_SESSIONS_PER_DATASET: int = 10
    DATASET_STORAGE_PATH: str = "../storage/datasets"
    MAX_FILE_SIZE_MB: int = 100
    # MindsDB Agent-supported file types: CSV, XLSX, XLS, JSON, TXT, PDF, Parquet
    ALLOWED_FILE_TYPES: str = Field(default_factory=lambda: "csv,xlsx,xls,json,txt,pdf,parquet")

    def get_allowed_file_types(self) -> List[str]:
        """Parse allowed file types from comma-separated string."""
        return [ext.strip() for ext in self.ALLOWED_FILE_TYPES.split(",") if ext.strip()]
    
    # Admin user
    FIRST_SUPERUSER: Optional[str] = None
    FIRST_SUPERUSER_PASSWORD: Optional[str] = None
    
    class Config:
        env_file = ".env"  # Use local .env file in backend directory
        env_file_encoding = "utf-8"
        extra = "allow"


settings = Settings()