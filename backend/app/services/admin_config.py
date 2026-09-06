"""
Enhanced Configuration Service for Admin Panel
Handles environment variable overrides and MindsDB configuration management
"""

import os
import json
import re
import tempfile
import shutil
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.models.admin_config import (
    ConfigurationOverride,
    MindsDBConfiguration,
    ConfigurationHistory,
    ConfigCategory,
    ConfigType
)
from app.schemas.admin_config import (
    ConfigurationOverrideCreate,
    ConfigurationOverrideUpdate,
    MindsDBConfigurationCreate,
    MindsDBConfigurationUpdate,
    ConfigurationHistoryCreate,
    EnvironmentVariable,
    ConfigurationValidationResult,
    ConfigurationApplicationResult
)
from app.core.config import settings
from app.services.agent_gateway import AgentGateway
from app.services.mindsdb import MindsDBService, mindsdb_service as _default_mindsdb

logger = logging.getLogger(__name__)


class AdminConfigurationService:
    """Service for managing system configuration through admin panel"""
    
    def __init__(self, db: Session, mindsdb_service: Optional[AgentGateway] = None):
        self.db = db
        self.mindsdb_service: AgentGateway = mindsdb_service or _default_mindsdb
        
        # Default environment variable mappings
        self.env_var_mappings = {
            # System
            "PROJECT_NAME": {
                "category": ConfigCategory.SYSTEM,
                "type": ConfigType.STRING,
                "title": "Project Name",
                "description": "Name of the application",
                "default": "AI Share Platform"
            },
            "VERSION": {
                "category": ConfigCategory.SYSTEM,
                "type": ConfigType.STRING,
                "title": "Application Version",
                "description": "Current version of the application",
                "default": "1.0.0"
            },
            
            # Database
            "DATABASE_URL": {
                "category": ConfigCategory.DATABASE,
                "type": ConfigType.URL,
                "title": "Database URL",
                "description": "Database connection string",
                "default": "postgresql://user:password@localhost:5432/database",
                "placeholder": "postgresql://user:password@host:port/database",
                "env_var": "DATABASE_URL",
                "required": True,
                "restart_required": True
            },
            
            # MindsDB
            "MINDSDB_URL": {
                "category": ConfigCategory.MINDSDB,
                "type": ConfigType.URL,
                "title": "MindsDB URL",
                "description": "MindsDB server URL",
                "default": "http://127.0.0.1:47334",
                "required": True
            },
            "MINDSDB_DATABASE": {
                "category": ConfigCategory.MINDSDB,
                "type": ConfigType.STRING,
                "title": "MindsDB Database",
                "description": "Default MindsDB database name",
                "default": "mindsdb"
            },
            "MINDSDB_USERNAME": {
                "category": ConfigCategory.MINDSDB,
                "type": ConfigType.STRING,
                "title": "MindsDB Username",
                "description": "MindsDB authentication username"
            },
            "MINDSDB_PASSWORD": {
                "category": ConfigCategory.MINDSDB,
                "type": ConfigType.PASSWORD,
                "title": "MindsDB Password",
                "description": "MindsDB authentication password",
                "sensitive": True
            },
            
            # AI Models
            "GOOGLE_API_KEY": {
                "category": ConfigCategory.AI_MODELS,
                "type": ConfigType.PASSWORD,
                "title": "Google API Key",
                "description": "Google API key for Gemini models",
                "sensitive": True,
                "required": True
            },
            "DEFAULT_GEMINI_MODEL": {
                "category": ConfigCategory.AI_MODELS,
                "type": ConfigType.STRING,
                "title": "Default Gemini Model",
                "description": "Default Gemini model to use",
                "default": "gemini-2.0-flash",
                "allowed_values": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
            },
            "GEMINI_ENGINE_NAME": {
                "category": ConfigCategory.AI_MODELS,
                "type": ConfigType.STRING,
                "title": "Gemini Engine Name",
                "description": "Name for the Gemini engine in MindsDB",
                "default": "google_gemini_engine"
            },
            
            # Security
            "SECRET_KEY": {
                "category": ConfigCategory.SECURITY,
                "type": ConfigType.PASSWORD,
                "title": "Secret Key",
                "description": "Application secret key for JWT tokens",
                "sensitive": True,
                "required": True,
                "restart_required": True
            },
            "ACCESS_TOKEN_EXPIRE_MINUTES": {
                "category": ConfigCategory.SECURITY,
                "type": ConfigType.INTEGER,
                "title": "Token Expiry (Minutes)",
                "description": "JWT token expiration time in minutes",
                "default": "30",
                "min_value": 5,
                "max_value": 1440
            },
            
            # CORS
            "BACKEND_CORS_ORIGINS": {
                "category": ConfigCategory.CORS,
                "type": ConfigType.LIST,
                "title": "CORS Origins",
                "description": "Allowed CORS origins (comma-separated)",
                "default": "http://localhost:3000,http://127.0.0.1:3000"
            },
            
            # File Upload
            "MAX_FILE_SIZE_MB": {
                "category": ConfigCategory.FILE_UPLOAD,
                "type": ConfigType.INTEGER,
                "title": "Max File Size (MB)",
                "description": "Maximum file upload size in megabytes",
                "default": "100",
                "min_value": 1,
                "max_value": 1000
            },
            "ALLOWED_FILE_TYPES": {
                "category": ConfigCategory.FILE_UPLOAD,
                "type": ConfigType.LIST,
                "title": "Allowed File Types",
                "description": "Allowed file extensions (comma-separated)",
                "default": "csv,json,xlsx,xls,txt,pdf,docx,doc,rtf,odt"
            },
            "UPLOAD_PATH": {
                "category": ConfigCategory.FILE_UPLOAD,
                "type": ConfigType.STRING,
                "title": "Upload Path",
                "description": "Local upload directory path",
                "default": "../storage/uploads"
            },
            
            # Storage Configuration
            "STORAGE_TYPE": {
                "category": ConfigCategory.STORAGE,
                "type": ConfigType.STRING,
                "title": "Storage Type",
                "description": "Storage backend type (local, s3, s3_compatible)",
                "default": "local",
                "required": True,
                "restart_required": True,
                "options": ["local", "s3", "s3_compatible"]
            },
            "STORAGE_DIR": {
                "category": ConfigCategory.STORAGE,
                "type": ConfigType.STRING,
                "title": "Local Storage Directory",
                "description": "Local storage directory path (used when storage_type is local)",
                "default": "../storage"
            },
            
            # S3-Compatible Storage Configuration
            "S3_ENDPOINT_URL": {
                "category": ConfigCategory.STORAGE,
                "type": ConfigType.URL,
                "title": "S3 Endpoint URL",
                "description": "S3-compatible endpoint URL (e.g., https://s3.amazonaws.com or custom endpoint)",
                "placeholder": "https://g7h4.fra3.idrivee2-51.com"
            },
            "S3_ACCESS_KEY_ID": {
                "category": ConfigCategory.STORAGE,
                "type": ConfigType.STRING,
                "title": "S3 Access Key ID",
                "description": "S3-compatible access key ID"
            },
            "S3_SECRET_ACCESS_KEY": {
                "category": ConfigCategory.STORAGE,
                "type": ConfigType.PASSWORD,
                "title": "S3 Secret Access Key",
                "description": "S3-compatible secret access key",
                "sensitive": True
            },
            "S3_BUCKET_NAME": {
                "category": ConfigCategory.STORAGE,
                "type": ConfigType.STRING,
                "title": "S3 Bucket Name",
                "description": "S3-compatible bucket name for file storage"
            },
            "S3_REGION": {
                "category": ConfigCategory.STORAGE,
                "type": ConfigType.STRING,
                "title": "S3 Region",
                "description": "S3-compatible region (some providers may not require this)",
                "default": "us-east-1"
            },
            "S3_USE_SSL": {
                "category": ConfigCategory.STORAGE,
                "type": ConfigType.BOOLEAN,
                "title": "Use SSL for S3",
                "description": "Use SSL/TLS for S3 connections",
                "default": "true"
            },
            "S3_ADDRESSING_STYLE": {
                "category": ConfigCategory.STORAGE,
                "type": ConfigType.STRING,
                "title": "S3 Addressing Style",
                "description": "S3 addressing style (path or virtual)",
                "default": "path",
                "options": ["path", "virtual"]
            },
            
            # Legacy AWS Configuration (kept for backward compatibility)
            "AWS_ACCESS_KEY_ID": {
                "category": ConfigCategory.AWS,
                "type": ConfigType.STRING,
                "title": "AWS Access Key ID (Legacy)",
                "description": "AWS access key for S3 integration (legacy, use S3_ACCESS_KEY_ID instead)"
            },
            "AWS_SECRET_ACCESS_KEY": {
                "category": ConfigCategory.AWS,
                "type": ConfigType.PASSWORD,
                "title": "AWS Secret Access Key (Legacy)",
                "description": "AWS secret key for S3 integration (legacy, use S3_SECRET_ACCESS_KEY instead)",
                "sensitive": True
            },
            "AWS_DEFAULT_REGION": {
                "category": ConfigCategory.AWS,
                "type": ConfigType.STRING,
                "title": "AWS Region (Legacy)",
                "description": "Default AWS region (legacy, use S3_REGION instead)",
                "default": "us-east-1"
            },
            
            # Data Sharing
            "ENABLE_DATA_SHARING": {
                "category": ConfigCategory.DATA_SHARING,
                "type": ConfigType.BOOLEAN,
                "title": "Enable Data Sharing",
                "description": "Enable data sharing functionality",
                "default": "true"
            },
            "ENABLE_AI_CHAT": {
                "category": ConfigCategory.DATA_SHARING,
                "type": ConfigType.BOOLEAN,
                "title": "Enable AI Chat",
                "description": "Enable AI chat functionality",
                "default": "true"
            },
            "SHARE_LINK_EXPIRY_HOURS": {
                "category": ConfigCategory.DATA_SHARING,
                "type": ConfigType.INTEGER,
                "title": "Share Link Expiry (Hours)",
                "description": "Default expiry time for share links",
                "default": "24",
                "min_value": 1,
                "max_value": 8760
            }
        }
    
    def initialize_default_configurations(self) -> None:
        """Initialize default configuration overrides from environment variable mappings"""
        try:
            for env_var, config in self.env_var_mappings.items():
                existing = self.db.query(ConfigurationOverride).filter(
                    ConfigurationOverride.env_var_name == env_var
                ).first()
                
                if not existing:
                    override = ConfigurationOverride(
                        key=env_var.lower().replace('_', '.'),
                        env_var_name=env_var,
                        category=config["category"],
                        config_type=config["type"],
                        title=config["title"],
                        description=config.get("description"),
                        default_value=config.get("default"),
                        value=os.getenv(env_var, config.get("default")),
                        is_sensitive=config.get("sensitive", False),
                        is_required=config.get("required", False),
                        requires_restart=config.get("restart_required", False),
                        min_value=config.get("min_value"),
                        max_value=config.get("max_value"),
                        allowed_values=config.get("allowed_values")
                    )
                    self.db.add(override)
            
            self.db.commit()
            logger.info("Default configurations initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize default configurations: {e}")
            self.db.rollback()
    
    def get_all_configurations(self) -> Dict[str, Any]:
        """Get all configuration overrides grouped by category"""
        try:
            overrides = self.db.query(ConfigurationOverride).filter(
                ConfigurationOverride.is_active == True
            ).all()
            
            # Group by category
            configurations = {}
            for override in overrides:
                category = override.category
                if category not in configurations:
                    configurations[category] = []
                
                config_data = {
                    "id": override.id,
                    "key": override.key,
                    "env_var_name": override.env_var_name,
                    "title": override.title,
                    "description": override.description,
                    "config_type": override.config_type,
                    "value": override.value if not override.is_sensitive else "***" if override.value else None,
                    "default_value": override.default_value,
                    "is_sensitive": override.is_sensitive,
                    "is_required": override.is_required,
                    "requires_restart": override.requires_restart,
                    "validation_regex": override.validation_regex,
                    "min_value": override.min_value,
                    "max_value": override.max_value,
                    "allowed_values": override.allowed_values,
                    "current_env_value": os.getenv(override.env_var_name) if override.env_var_name else None,
                    "is_overridden": override.value != override.default_value,
                    "last_applied_at": override.last_applied_at
                }
                configurations[category].append(config_data)
            
            return configurations
            
        except Exception as e:
            logger.error(f"Failed to get configurations: {e}")
            return {}
    
    def update_configuration(
        self,
        config_id: int,
        update_data: ConfigurationOverrideUpdate,
        user_id: int,
        user_email: str
    ) -> ConfigurationApplicationResult:
        """Update a configuration override"""
        try:
            config = self.db.query(ConfigurationOverride).filter(
                ConfigurationOverride.id == config_id
            ).first()
            
            if not config:
                return ConfigurationApplicationResult(
                    success=False,
                    errors=["Configuration not found"]
                )
            
            # Validate the new value
            validation_result = self._validate_configuration_value(config, update_data.value)
            if not validation_result.is_valid:
                return ConfigurationApplicationResult(
                    success=False,
                    errors=validation_result.errors
                )
            
            # Record history
            old_value = config.value
            self._record_configuration_change(
                config.key,
                "override",
                old_value,
                update_data.value,
                user_id,
                user_email,
                "Admin panel update"
            )
            
            # Update configuration
            update_dict = update_data.dict(exclude_unset=True)
            for field, value in update_dict.items():
                setattr(config, field, value)
            
            config.updated_at = datetime.utcnow()
            self.db.commit()
            
            # Apply to environment if requested
            if config.env_var_name and update_data.value is not None:
                os.environ[config.env_var_name] = str(update_data.value)
                config.last_applied_at = datetime.utcnow()
                self.db.commit()
            
            return ConfigurationApplicationResult(
                success=True,
                applied_configs=[config.key],
                restart_required=config.requires_restart
            )
            
        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            self.db.rollback()
            return ConfigurationApplicationResult(
                success=False,
                errors=[str(e)]
            )
    
    def get_environment_variables(self) -> Dict[str, Any]:
        """Get all environment variables with management status"""
        try:
            managed_vars = {
                override.env_var_name: override 
                for override in self.db.query(ConfigurationOverride).all()
                if override.env_var_name
            }
            
            # Get all environment variables
            all_env_vars = dict(os.environ)
            
            variables = []
            categories = {}
            
            for name, value in all_env_vars.items():
                is_managed = name in managed_vars
                category = None
                description = None
                
                if is_managed:
                    override = managed_vars[name]
                    category = override.category
                    description = override.description
                    
                    if category not in categories:
                        categories[category] = 0
                    categories[category] += 1
                
                variables.append(EnvironmentVariable(
                    name=name,
                    value=value if not (is_managed and managed_vars[name].is_sensitive) else "***",
                    is_set=True,
                    is_managed=is_managed,
                    category=category,
                    description=description
                ))
            
            # Add managed variables that aren't set in environment
            for name, override in managed_vars.items():
                if name not in all_env_vars:
                    variables.append(EnvironmentVariable(
                        name=name,
                        value=None,
                        is_set=False,
                        is_managed=True,
                        category=override.category,
                        description=override.description
                    ))
            
            return {
                "variables": sorted(variables, key=lambda x: x.name),
                "managed_count": len(managed_vars),
                "unmanaged_count": len(all_env_vars) - len(managed_vars),
                "categories": categories
            }
            
        except Exception as e:
            logger.error(f"Failed to get environment variables: {e}")
            return {
                "variables": [],
                "managed_count": 0,
                "unmanaged_count": 0,
                "categories": {}
            }
    
    def get_mindsdb_configurations(self) -> List[MindsDBConfiguration]:
        """Get all MindsDB configurations"""
        try:
            return self.db.query(MindsDBConfiguration).all()
        except Exception as e:
            logger.error(f"Failed to get MindsDB configurations: {e}")
            return []
    
    def create_mindsdb_configuration(
        self,
        config_data: MindsDBConfigurationCreate,
        user_id: int,
        user_email: str
    ) -> MindsDBConfiguration:
        """Create a new MindsDB configuration"""
        try:
            # If this is set as active, deactivate others
            if config_data.is_active:
                self.db.query(MindsDBConfiguration).update({"is_active": False})
            
            config = MindsDBConfiguration(**config_data.dict())
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
            
            # Record history
            self._record_configuration_change(
                f"mindsdb.{config.config_name}",
                "mindsdb",
                None,
                json.dumps(config_data.dict()),
                user_id,
                user_email,
                "New MindsDB configuration created"
            )
            
            return config
            
        except Exception as e:
            logger.error(f"Failed to create MindsDB configuration: {e}")
            self.db.rollback()
            raise
    
    def update_mindsdb_configuration(
        self,
        config_id: int,
        update_data: MindsDBConfigurationUpdate,
        user_id: int,
        user_email: str
    ) -> MindsDBConfiguration:
        """Update a MindsDB configuration"""
        try:
            config = self.db.query(MindsDBConfiguration).filter(
                MindsDBConfiguration.id == config_id
            ).first()
            
            if not config:
                raise ValueError("MindsDB configuration not found")
            
            # Record old value for history
            old_value = {
                "config_name": config.config_name,
                "mindsdb_url": config.mindsdb_url,
                "is_active": config.is_active
            }
            
            # If setting as active, deactivate others
            if update_data.is_active:
                self.db.query(MindsDBConfiguration).filter(
                    MindsDBConfiguration.id != config_id
                ).update({"is_active": False})
            
            # Update configuration
            update_dict = update_data.dict(exclude_unset=True)
            for field, value in update_dict.items():
                setattr(config, field, value)
            
            config.updated_at = datetime.utcnow()
            self.db.commit()
            
            # Record history
            self._record_configuration_change(
                f"mindsdb.{config.config_name}",
                "mindsdb",
                json.dumps(old_value),
                json.dumps(update_dict),
                user_id,
                user_email,
                "MindsDB configuration updated"
            )
            
            return config
            
        except Exception as e:
            logger.error(f"Failed to update MindsDB configuration: {e}")
            self.db.rollback()
            raise
    
    def test_mindsdb_connection(self, config_id: int) -> Dict[str, Any]:
        """Test MindsDB connection with specific configuration"""
        try:
            config = self.db.query(MindsDBConfiguration).filter(
                MindsDBConfiguration.id == config_id
            ).first()
            
            if not config:
                return {"success": False, "error": "Configuration not found"}
            
            # Create temporary MindsDB service with this configuration
            temp_service: AgentGateway = MindsDBService()
            temp_service.base_url = config.mindsdb_url
            
            # Test connection
            health_result = temp_service.health_check()
            
            # Update health status
            config.last_health_check = datetime.utcnow()
            config.is_healthy = health_result.get("status") == "healthy"
            config.health_status = health_result
            self.db.commit()
            
            return {
                "success": config.is_healthy,
                "health_status": health_result,
                "last_checked": config.last_health_check.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to test MindsDB connection: {e}")
            return {"success": False, "error": str(e)}
    
    def export_mindsdb_config_file(self, config_id: int) -> str:
        """Export MindsDB configuration as JSON file"""
        try:
            config = self.db.query(MindsDBConfiguration).filter(
                MindsDBConfiguration.id == config_id
            ).first()
            
            if not config:
                raise ValueError("Configuration not found")
            
            # Build MindsDB config structure
            mindsdb_config = {
                "permanent_storage": config.permanent_storage_config or {
                    "location": "local"
                },
                "paths": {
                    "root": "./storage/mindsdb",
                    "content": "./storage/mindsdb/content",
                    "storage": "./storage/mindsdb/storage",
                    "static": "./storage/mindsdb/static",
                    "tmp": "./storage/mindsdb/tmp",
                    "cache": "./storage/mindsdb/cache",
                    "locks": "./storage/mindsdb/locks"
                },
                "api": {
                    "http": {
                        "host": "127.0.0.1",
                        "port": 47334
                    }
                },
                "log": {
                    "level": {
                        "console": "INFO"
                    }
                },
                "cache": {
                    "type": "local"
                },
                "url_file_upload": config.file_upload_config or {
                    "enabled": True,
                    "allowed_origins": [],
                    "disallowed_origins": []
                },
                "storage_dir": "./storage/mindsdb"
            }
            
            # Add AI engines configuration
            if config.ai_engines_config:
                mindsdb_config.update(config.ai_engines_config)
            
            # Add custom configuration
            if config.custom_config:
                mindsdb_config.update(config.custom_config)
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(mindsdb_config, f, indent=2)
                return f.name
                
        except Exception as e:
            logger.error(f"Failed to export MindsDB config: {e}")
            raise
    
    def apply_configuration_to_mindsdb_file(self, config_id: int) -> bool:
        """Apply configuration to the actual MindsDB config file"""
        try:
            # Export to temporary file
            temp_file = self.export_mindsdb_config_file(config_id)
            
            # Copy to actual MindsDB config location
            mindsdb_config_path = "./mindsdb_config.json"
            shutil.copy2(temp_file, mindsdb_config_path)
            
            # Clean up temporary file
            os.unlink(temp_file)
            
            logger.info(f"Applied MindsDB configuration {config_id} to {mindsdb_config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply MindsDB configuration: {e}")
            return False
    
    def _validate_configuration_value(
        self,
        config: ConfigurationOverride,
        value: Optional[str]
    ) -> ConfigurationValidationResult:
        """Validate a configuration value"""
        errors = []
        warnings = []
        
        if config.is_required and (value is None or value.strip() == ""):
            errors.append(f"{config.title} is required")
        
        if value is not None:
            # Type validation
            if config.config_type == ConfigType.INTEGER:
                try:
                    int_value = int(value)
                    if config.min_value is not None and int_value < config.min_value:
                        errors.append(f"{config.title} must be at least {config.min_value}")
                    if config.max_value is not None and int_value > config.max_value:
                        errors.append(f"{config.title} must be at most {config.max_value}")
                except ValueError:
                    errors.append(f"{config.title} must be a valid integer")
            
            elif config.config_type == ConfigType.BOOLEAN:
                if value.lower() not in ["true", "false", "1", "0", "yes", "no"]:
                    errors.append(f"{config.title} must be a valid boolean value")
            
            elif config.config_type == ConfigType.URL:
                url_pattern = re.compile(
                    r'^https?://'  # http:// or https://
                    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
                    r'localhost|'  # localhost...
                    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
                    r'(?::\d+)?'  # optional port
                    r'(?:/?|[/?]\S+)$', re.IGNORECASE)
                if not url_pattern.match(value):
                    errors.append(f"{config.title} must be a valid URL")
            
            elif config.config_type == ConfigType.EMAIL:
                email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
                if not email_pattern.match(value):
                    errors.append(f"{config.title} must be a valid email address")
            
            # Regex validation
            if config.validation_regex:
                try:
                    if not re.match(config.validation_regex, value):
                        errors.append(f"{config.title} does not match required format")
                except re.error:
                    warnings.append(f"Invalid validation regex for {config.title}")
            
            # Allowed values validation
            if config.allowed_values and value not in config.allowed_values:
                errors.append(f"{config.title} must be one of: {', '.join(config.allowed_values)}")
        
        return ConfigurationValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _record_configuration_change(
        self,
        config_key: str,
        config_type: str,
        old_value: Optional[str],
        new_value: Optional[str],
        user_id: int,
        user_email: str,
        reason: str
    ) -> None:
        """Record configuration change in history"""
        try:
            history = ConfigurationHistory(
                config_key=config_key,
                config_type=config_type,
                old_value=old_value,
                new_value=new_value,
                change_reason=reason,
                changed_by_user_id=user_id,
                changed_by_email=user_email
            )
            self.db.add(history)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to record configuration change: {e}")
    
    def get_configuration_history(
        self,
        config_key: Optional[str] = None,
        limit: int = 100
    ) -> List[ConfigurationHistory]:
        """Get configuration change history"""
        try:
            query = self.db.query(ConfigurationHistory)
            
            if config_key:
                query = query.filter(ConfigurationHistory.config_key == config_key)
            
            return query.order_by(ConfigurationHistory.changed_at.desc()).limit(limit).all()
            
        except Exception as e:
            logger.error(f"Failed to get configuration history: {e}")
            return []