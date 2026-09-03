from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.auth import get_current_superuser
from app.models.user import User
from app.models.config import Configuration
from app.models.dataset import Dataset
from app.models.analytics import DatasetAccess, SystemMetrics, AccessRequest, AuditLog
from app.models.admin_config import ConfigurationOverride as ConfigurationOverrideModel, MindsDBConfiguration as MindsDBConfigurationModel, ConfigurationHistory as ConfigurationHistoryModel
from app.schemas.config import Configuration as ConfigSchema, ConfigurationCreate, ConfigurationUpdate
from app.schemas.admin_config import (
    ConfigurationOverrideCreate,
    ConfigurationOverrideUpdate,
    MindsDBConfigurationCreate,
    MindsDBConfigurationUpdate,
    SystemConfiguration,
    EnvironmentVariablesResponse,
    ConfigurationApplicationResult,
    BulkConfigurationUpdate,
    ConfigurationOverride as ConfigurationOverrideSchema,
    MindsDBConfiguration as MindsDBConfigurationSchema
)
from app.services.admin_config import AdminConfigurationService
from app.services.storage import storage_service
from app.models.organization import Organization
from app.core.auth import get_password_hash
import logging
import json
import tempfile
import os

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/config", response_model=List[ConfigSchema])
async def get_configurations(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get all configuration settings."""
    configs = db.query(Configuration).all()
    return configs


@router.post("/config", response_model=ConfigSchema)
async def create_configuration(
    config: ConfigurationCreate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Create a new configuration setting."""
    # Check if configuration already exists
    existing_config = db.query(Configuration).filter(Configuration.key == config.key).first()
    if existing_config:
        raise HTTPException(status_code=400, detail="Configuration key already exists")
    
    db_config = Configuration(**config.dict())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config


@router.put("/config/{config_key}", response_model=ConfigSchema)
async def update_configuration(
    config_key: str,
    config_update: ConfigurationUpdate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Update a configuration setting."""
    config = db.query(Configuration).filter(Configuration.key == config_key).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    update_data = config_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)
    
    db.commit()
    db.refresh(config)
    return config


@router.delete("/config/{config_key}")
async def delete_configuration(
    config_key: str,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Delete a configuration setting."""
    config = db.query(Configuration).filter(Configuration.key == config_key).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    db.delete(config)
    db.commit()
    return {"message": "Configuration deleted successfully"}


@router.get("/config/{config_key}", response_model=ConfigSchema)
async def get_configuration(
    config_key: str,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get a specific configuration setting."""
    config = db.query(Configuration).filter(Configuration.key == config_key).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return config


@router.post("/google-api-key")
async def set_google_api_key(
    api_key_data: Dict[str, str],
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Set or update Google API key."""
    api_key = api_key_data.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    
    # Check if configuration exists
    config = db.query(Configuration).filter(Configuration.key == "google_api_key").first()
    
    if config:
        config.value = api_key
    else:
        config = Configuration(
            key="google_api_key",
            value=api_key,
            description="Google API key for Gemini Flash integration"
        )
        db.add(config)
    
    db.commit()
    return {"message": "Google API key updated successfully"}


@router.get("/google-api-key")
async def get_google_api_key(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get Google API key status."""
    config = db.query(Configuration).filter(Configuration.key == "google_api_key").first()
    
    return {
        "has_api_key": config is not None and config.value is not None,
        "key_length": len(config.value) if config and config.value else 0
    }


@router.get("/stats")
async def get_admin_stats(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get admin dashboard statistics."""
    try:
        # Get date ranges
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        
        # Total users - with error handling
        try:
            total_users = db.query(User).count()
        except Exception as e:
            logger.warning(f"Could not get total users: {e}")
            total_users = 0
        
        # Active users (users who accessed data in last 7 days) - with error handling
        try:
            active_users = db.query(func.count(func.distinct(DatasetAccess.user_id))).filter(
                DatasetAccess.timestamp >= last_7d
            ).scalar() or 0
        except Exception as e:
            logger.warning(f"Could not get active users: {e}")
            active_users = 0
        
        # Total datasets (only active, non-deleted) - with error handling
        try:
            active_datasets_count = db.query(Dataset).filter(
                Dataset.is_deleted == False,
                Dataset.is_active == True
            ).count()
        except Exception as e:
            logger.warning(f"Could not get dataset count: {e}")
            active_datasets_count = 0
        
        # Pending requests - with error handling
        try:
            pending_requests = db.query(func.count(AccessRequest.id)).filter(AccessRequest.status == 'pending').scalar() or 0
        except Exception as e:
            logger.warning(f"Could not get pending requests: {e}")
            pending_requests = 0
        
        # Get latest system metrics - with error handling
        try:
            latest_metrics = db.query(SystemMetrics).order_by(
                SystemMetrics.timestamp.desc()
            ).first()
        except Exception as e:
            logger.warning(f"Could not get system metrics: {e}")
            latest_metrics = None
        
        # System health data
        system_health = {
            "uptime": "99.9%",  # Mock - would calculate from system start time
            "cpuUsage": latest_metrics.cpu_usage_percent if latest_metrics else 45,
            "memoryUsage": latest_metrics.memory_usage_percent if latest_metrics else 67,
            "diskUsage": latest_metrics.disk_usage_percent if latest_metrics else 78,
            "networkStatus": "healthy" if latest_metrics and latest_metrics.network_latency_ms < 200 else "warning"
        }
        
        # Recent activity (last 10 audit logs) - with error handling
        recent_activity = []
        try:
            recent_logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(10).all()
            
            for log in recent_logs:
                recent_activity.append({
                    "id": str(log.id),
                    "type": log.action,
                    "description": log.details,
                    "timestamp": log.timestamp.isoformat() + "Z",
                    "severity": "info"
                })
        except Exception as e:
            logger.warning(f"Could not get recent activity: {e}")
            # Provide some mock recent activity
            recent_activity = [
                {
                    "id": "1",
                    "type": "dataset_upload",
                    "description": "Dataset uploaded successfully",
                    "timestamp": now.isoformat() + "Z",
                    "severity": "info"
                }
            ]
        
        return {
            "totalUsers": total_users,
            "activeUsers": active_users,
            "totalDatasets": active_datasets_count,
            "pendingRequests": pending_requests,
            "systemHealth": system_health,
            "recentActivity": recent_activity
        }
        
    except Exception as e:
        logger.error(f"Error getting admin stats: {str(e)}")
        # Return default stats instead of raising an error
        return {
            "totalUsers": 0,
            "activeUsers": 0,
            "totalDatasets": 0,
            "pendingRequests": 0,
            "systemHealth": {
                "uptime": "99.9%",
                "cpuUsage": 45,
                "memoryUsage": 67,
                "diskUsage": 78,
                "networkStatus": "healthy"
            },
            "recentActivity": [
                {
                    "id": "1",
                    "type": "system_status",
                    "description": "System is running normally",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "severity": "info"
                }
            ]
        }


@router.get("/datasets")
async def get_admin_datasets(
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
    include_inactive: bool = False,
    organization_id: Optional[int] = None,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get all datasets for admin management with explicit control over deleted/inactive datasets."""
    logger.info(f"get_admin_datasets called by admin user {current_user.id} ({current_user.email})")
    logger.info(f"Admin parameters: skip={skip}, limit={limit}, include_deleted={include_deleted}, include_inactive={include_inactive}, organization_id={organization_id}")
    
    try:
        query = db.query(Dataset)
        
        # Filter by organization if specified
        if organization_id:
            query = query.filter(Dataset.organization_id == organization_id)
            logger.info(f"Filtered by organization_id: {organization_id}")
        
        # Filter deleted datasets unless explicitly requested
        if not include_deleted:
            query = query.filter(Dataset.is_deleted == False)
            logger.info("Filtered out deleted datasets")
        
        # Filter inactive datasets unless explicitly requested  
        if not include_inactive:
            query = query.filter(Dataset.is_active == True)
            logger.info("Filtered out inactive datasets")
        
        # Get total count before pagination
        total_count = query.count()
        logger.info(f"Total datasets matching criteria: {total_count}")
        
        # Apply pagination
        datasets = query.offset(skip).limit(limit).all()
        logger.info(f"Retrieved {len(datasets)} datasets after pagination")
        
        # Convert to response format
        dataset_responses = []
        for dataset in datasets:
            dataset_responses.append({
                "id": dataset.id,
                "name": dataset.name,
                "description": dataset.description,
                "type": dataset.type,
                "sharing_level": dataset.sharing_level,
                "organization_id": dataset.organization_id,
                "owner_id": dataset.owner_id,
                "is_active": dataset.is_active,
                "is_deleted": dataset.is_deleted,
                "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
                "updated_at": dataset.updated_at.isoformat() if dataset.updated_at else None,
                "deleted_at": dataset.deleted_at.isoformat() if dataset.deleted_at else None,
                "deleted_by": dataset.deleted_by,
                "size_bytes": dataset.size_bytes,
                "allow_download": dataset.allow_download,
                "allow_api_access": dataset.allow_api_access
            })
        
        logger.info(f"Admin datasets endpoint returning {len(dataset_responses)} datasets")
        
        return {
            "datasets": dataset_responses,
            "total": total_count,
            "skip": skip,
            "limit": limit,
            "filters": {
                "include_deleted": include_deleted,
                "include_inactive": include_inactive,
                "organization_id": organization_id
            }
        }
        
    except Exception as e:
        logger.error(f"Error in get_admin_datasets: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving admin datasets: {str(e)}")


@router.delete("/datasets/{dataset_id}")
async def admin_delete_dataset(
    dataset_id: int,
    force_delete: bool = False,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Admin endpoint to delete datasets with optional force delete."""
    try:
        # Find dataset (including deleted ones for admin)
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        
        if not dataset:
            raise HTTPException(
                status_code=404,
                detail="Dataset not found"
            )
        
        if dataset.is_deleted and not force_delete:
            raise HTTPException(
                status_code=400,
                detail="Dataset is already deleted. Use force_delete=true to permanently delete."
            )
        
        # Clean up associated MindsDB agent first
        try:
            from app.services.mindsdb import MindsDBService
            mindsdb_service = MindsDBService()
            if dataset.agent_name:
                agent_name = dataset.agent_name
                if mindsdb_service.delete_dataset_agent(dataset, db):
                    logger.info(f"Agent {agent_name} deleted")
        except Exception as e:
            logger.warning(f"Agent cleanup failed: {e}")
        
        if force_delete:
            # Hard delete (permanent removal) - need to clean up related records first
            logger.info(f"Performing hard delete of dataset {dataset_id}")
            
            # Delete related records that have NOT NULL foreign keys
            from app.models.dataset import DatasetAccessLog, DatasetDownload, DatasetModel, DatasetChatSession, ChatMessage, DatasetShareAccess
            
            # Delete chat messages first (they reference chat sessions)
            chat_sessions = db.query(DatasetChatSession).filter(DatasetChatSession.dataset_id == dataset_id).all()
            for session in chat_sessions:
                db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
            
            # Delete chat sessions
            db.query(DatasetChatSession).filter(DatasetChatSession.dataset_id == dataset_id).delete()
            
            # Delete access logs
            db.query(DatasetAccessLog).filter(DatasetAccessLog.dataset_id == dataset_id).delete()
            
            # Delete downloads
            db.query(DatasetDownload).filter(DatasetDownload.dataset_id == dataset_id).delete()
            
            # Delete models
            db.query(DatasetModel).filter(DatasetModel.dataset_id == dataset_id).delete()
            
            # Delete share accesses
            db.query(DatasetShareAccess).filter(DatasetShareAccess.dataset_id == dataset_id).delete()
            
            # Now delete the dataset itself
            db.delete(dataset)
            db.commit()
            
            logger.info(f"Successfully hard deleted dataset {dataset_id} and all related records")
            return {
                "message": "Dataset permanently deleted",
                "dataset_id": dataset_id,
                "deletion_type": "hard",
                "deleted_by": current_user.id
            }
        else:
            # Soft delete
            if not dataset.is_deleted:
                dataset.soft_delete(current_user.id)
                db.commit()
            return {
                "message": "Dataset deleted successfully",
                "dataset_id": dataset_id,
                "deletion_type": "soft",
                "deleted_at": dataset.deleted_at.isoformat() if dataset.deleted_at else None,
                "deleted_by": dataset.deleted_by
            }
            
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting dataset: {str(e)}")


@router.patch("/datasets/{dataset_id}/restore")
async def admin_restore_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Admin endpoint to restore a soft-deleted dataset."""
    try:
        # Find deleted dataset
        dataset = db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.is_deleted == True
        ).first()
        
        if not dataset:
            raise HTTPException(
                status_code=404,
                detail="Deleted dataset not found"
            )
        
        # Restore dataset
        dataset.is_deleted = False
        dataset.deleted_at = None
        dataset.deleted_by = None
        dataset.is_active = True
        dataset.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "message": "Dataset restored successfully",
            "dataset_id": dataset_id,
            "restored_by": current_user.id,
            "restored_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error restoring dataset: {str(e)}")


@router.get("/datasets/stats")
async def get_admin_dataset_stats(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get comprehensive dataset statistics for admin dashboard."""
    try:
        # Total datasets (including deleted)
        total_datasets = db.query(Dataset).count()
        
        # Active datasets
        active_datasets = db.query(Dataset).filter(
            Dataset.is_deleted == False,
            Dataset.is_active == True
        ).count()
        
        # Deleted datasets
        deleted_datasets = db.query(Dataset).filter(Dataset.is_deleted == True).count()
        
        # Inactive datasets (not deleted but inactive)
        inactive_datasets = db.query(Dataset).filter(
            Dataset.is_deleted == False,
            Dataset.is_active == False
        ).count()
        
        # Datasets by sharing level
        sharing_stats = {}
        for level in ["PRIVATE", "ORGANIZATION", "PUBLIC"]:
            count = db.query(Dataset).filter(
                Dataset.is_deleted == False,
                Dataset.sharing_level == level
            ).count()
            sharing_stats[level.lower()] = count
        
        # Recent deletions (last 7 days)
        from datetime import datetime, timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_deletions = db.query(Dataset).filter(
            Dataset.is_deleted == True,
            Dataset.deleted_at >= week_ago
        ).count()
        
        return {
            "total_datasets": total_datasets,
            "active_datasets": active_datasets,
            "deleted_datasets": deleted_datasets,
            "inactive_datasets": inactive_datasets,
            "recent_deletions": recent_deletions,
            "sharing_level_stats": sharing_stats,
            "health_status": {
                "deletion_rate": recent_deletions / max(total_datasets, 1) * 100,
                "active_rate": active_datasets / max(total_datasets, 1) * 100
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting dataset stats: {str(e)}")


# Enhanced Configuration Management Endpoints

@router.get("/system-config", response_model=SystemConfiguration)
async def get_system_configuration(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get complete system configuration including environment overrides and MindsDB config"""
    try:
        config_service = AdminConfigurationService(db)
        
        # Initialize default configurations if not exists
        config_service.initialize_default_configurations()
        
        # Get all configurations
        env_overrides = config_service.get_all_configurations()
        mindsdb_configs = config_service.get_mindsdb_configurations()
        
        # Find active MindsDB config
        active_mindsdb = next((c for c in mindsdb_configs if c.is_active), None)
        
        # Get system info
        system_info = {
            "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            "platform": os.name,
            "environment_variables_count": len(os.environ),
            "managed_configs_count": sum(len(configs) for configs in env_overrides.values()),
            "mindsdb_configs_count": len(mindsdb_configs),
            "current_working_directory": os.getcwd(),
            "config_file_exists": os.path.exists("./mindsdb_config.json")
        }
        
        # Check if restart is required
        restart_required = any(
            config.get("requires_restart", False) and config.get("is_overridden", False)
            for category_configs in env_overrides.values()
            for config in category_configs
        )
        
        return SystemConfiguration(
            environment_overrides=env_overrides,
            mindsdb_configurations=mindsdb_configs,
            active_mindsdb_config=active_mindsdb,
            system_info=system_info,
            restart_required=restart_required
        )
        
    except Exception as e:
        logger.error(f"Error getting system configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving system configuration: {str(e)}")


@router.get("/environment-variables", response_model=EnvironmentVariablesResponse)
async def get_environment_variables(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get all environment variables with management status"""
    try:
        config_service = AdminConfigurationService(db)
        env_vars = config_service.get_environment_variables()
        return EnvironmentVariablesResponse(**env_vars)
        
    except Exception as e:
        logger.error(f"Error getting environment variables: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving environment variables: {str(e)}")


@router.put("/config-override/{config_id}", response_model=ConfigurationApplicationResult)
async def update_configuration_override(
    config_id: int,
    config_update: ConfigurationOverrideUpdate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Update a configuration override"""
    try:
        config_service = AdminConfigurationService(db)
        result = config_service.update_configuration(
            config_id, config_update, current_user.id, current_user.email
        )
        return result
        
    except Exception as e:
        logger.error(f"Error updating configuration override: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating configuration: {str(e)}")


@router.post("/config-override")
async def create_configuration_override(
    config_create: ConfigurationOverrideCreate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Create a new configuration override"""
    try:
        # Check if configuration already exists
        existing = db.query(ConfigurationOverrideModel).filter(
            ConfigurationOverrideModel.key == config_create.key
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="Configuration key already exists")
        
        config = ConfigurationOverrideModel(**config_create.dict())
        db.add(config)
        db.commit()
        db.refresh(config)
        
        # Record history
        config_service = AdminConfigurationService(db)
        config_service._record_configuration_change(
            config.key,
            "override",
            None,
            config.value,
            current_user.id,
            current_user.email,
            "New configuration override created"
        )
        
        return config
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating configuration override: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating configuration: {str(e)}")


@router.delete("/config-override/{config_id}")
async def delete_configuration_override(
    config_id: int,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Delete a configuration override"""
    try:
        config = db.query(ConfigurationOverrideModel).filter(
            ConfigurationOverrideModel.id == config_id
        ).first()
        
        if not config:
            raise HTTPException(status_code=404, detail="Configuration not found")
        
        # Record history
        config_service = AdminConfigurationService(db)
        config_service._record_configuration_change(
            config.key,
            "override",
            config.value,
            None,
            current_user.id,
            current_user.email,
            "Configuration override deleted"
        )
        
        db.delete(config)
        db.commit()
        
        return {"message": "Configuration override deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting configuration override: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting configuration: {str(e)}")


@router.post("/mindsdb-config")
async def create_mindsdb_configuration(
    config_create: MindsDBConfigurationCreate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Create a new MindsDB configuration"""
    try:
        config_service = AdminConfigurationService(db)
        config = config_service.create_mindsdb_configuration(
            config_create, current_user.id, current_user.email
        )
        return config
        
    except Exception as e:
        logger.error(f"Error creating MindsDB configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating MindsDB configuration: {str(e)}")


@router.put("/mindsdb-config/{config_id}")
async def update_mindsdb_configuration(
    config_id: int,
    config_update: MindsDBConfigurationUpdate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Update a MindsDB configuration"""
    try:
        config_service = AdminConfigurationService(db)
        config = config_service.update_mindsdb_configuration(
            config_id, config_update, current_user.id, current_user.email
        )
        return config
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating MindsDB configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating MindsDB configuration: {str(e)}")


@router.delete("/mindsdb-config/{config_id}")
async def delete_mindsdb_configuration(
    config_id: int,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Delete a MindsDB configuration"""
    try:
        config = db.query(MindsDBConfigurationModel).filter(
            MindsDBConfigurationModel.id == config_id
        ).first()
        
        if not config:
            raise HTTPException(status_code=404, detail="MindsDB configuration not found")
        
        # Record history
        config_service = AdminConfigurationService(db)
        config_service._record_configuration_change(
            f"mindsdb.{config.config_name}",
            "mindsdb",
            json.dumps({"config_name": config.config_name, "mindsdb_url": config.mindsdb_url}),
            None,
            current_user.id,
            current_user.email,
            "MindsDB configuration deleted"
        )
        
        db.delete(config)
        db.commit()
        
        return {"message": "MindsDB configuration deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting MindsDB configuration: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting MindsDB configuration: {str(e)}")


@router.post("/mindsdb-config/{config_id}/test")
async def test_mindsdb_configuration(
    config_id: int,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Test a MindsDB configuration connection"""
    try:
        config_service = AdminConfigurationService(db)
        result = config_service.test_mindsdb_connection(config_id)
        return result
        
    except Exception as e:
        logger.error(f"Error testing MindsDB configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error testing MindsDB configuration: {str(e)}")


@router.post("/mindsdb-config/{config_id}/apply")
async def apply_mindsdb_configuration(
    config_id: int,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Apply MindsDB configuration to the actual config file"""
    try:
        config_service = AdminConfigurationService(db)
        success = config_service.apply_configuration_to_mindsdb_file(config_id)
        
        if success:
            return {"message": "MindsDB configuration applied successfully", "restart_required": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to apply MindsDB configuration")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying MindsDB configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error applying MindsDB configuration: {str(e)}")


@router.get("/mindsdb-config/{config_id}/export")
async def export_mindsdb_configuration(
    config_id: int,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Export MindsDB configuration as JSON file"""
    try:
        config_service = AdminConfigurationService(db)
        temp_file = config_service.export_mindsdb_config_file(config_id)
        
        return FileResponse(
            temp_file,
            media_type="application/json",
            filename=f"mindsdb_config_{config_id}.json",
            background=lambda: os.unlink(temp_file)  # Clean up after download
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error exporting MindsDB configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error exporting MindsDB configuration: {str(e)}")


@router.post("/mindsdb-config/import")
async def import_mindsdb_configuration(
    file: UploadFile = File(...),
    config_name: str = "imported_config",
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Import MindsDB configuration from JSON file"""
    try:
        # Read and parse uploaded file
        content = await file.read()
        config_data = json.loads(content)
        
        # Extract relevant configuration
        api_config = config_data.get("api", {}).get("http", {})
        host = api_config.get("host", "127.0.0.1")
        port = api_config.get("port", 47334)
        mindsdb_url = f"http://{host}:{port}"
        
        mindsdb_config = MindsDBConfigurationCreate(
            config_name=config_name,
            is_active=False,  # Don't activate imported configs by default
            mindsdb_url=mindsdb_url,
            permanent_storage_config=config_data.get("permanent_storage"),
            file_upload_config=config_data.get("url_file_upload"),
            custom_config={k: v for k, v in config_data.items() 
                          if k not in ["permanent_storage", "url_file_upload", "api", "paths"]}
        )
        
        config_service = AdminConfigurationService(db)
        config = config_service.create_mindsdb_configuration(
            mindsdb_config, current_user.id, current_user.email
        )
        
        return {
            "message": "MindsDB configuration imported successfully",
            "config_id": config.id,
            "config_name": config.config_name
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        logger.error(f"Error importing MindsDB configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error importing MindsDB configuration: {str(e)}")


@router.get("/config-history")
async def get_configuration_history(
    config_key: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get configuration change history"""
    try:
        config_service = AdminConfigurationService(db)
        history = config_service.get_configuration_history(config_key, limit)
        
        return {
            "history": [
                {
                    "id": h.id,
                    "config_key": h.config_key,
                    "config_type": h.config_type,
                    "old_value": h.old_value if not h.config_key.endswith(("password", "key", "secret")) else "***",
                    "new_value": h.new_value if not h.config_key.endswith(("password", "key", "secret")) else "***",
                    "change_reason": h.change_reason,
                    "changed_by_email": h.changed_by_email,
                    "changed_at": h.changed_at.isoformat(),
                    "applied_successfully": h.applied_successfully,
                    "application_error": h.application_error,
                    "applied_at": h.applied_at.isoformat() if h.applied_at else None
                }
                for h in history
            ],
            "total": len(history),
            "filtered_by": config_key
        }
        
    except Exception as e:
        logger.error(f"Error getting configuration history: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving configuration history: {str(e)}")


@router.post("/config/bulk-update", response_model=ConfigurationApplicationResult)
async def bulk_update_configurations(
    bulk_update: BulkConfigurationUpdate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Bulk update multiple configurations"""
    try:
        config_service = AdminConfigurationService(db)
        applied_configs = []
        failed_configs = []
        errors = []
        restart_required = False
        
        # Update overrides
        for i, override_update in enumerate(bulk_update.overrides):
            try:
                # Find config by index or key (this is simplified - you might want to pass IDs)
                configs = db.query(ConfigurationOverrideModel).all()
                if i < len(configs):
                    result = config_service.update_configuration(
                        configs[i].id, override_update, current_user.id, current_user.email
                    )
                    if result.success:
                        applied_configs.extend(result.applied_configs)
                        if result.restart_required:
                            restart_required = True
                    else:
                        failed_configs.append(f"override_{i}")
                        errors.extend(result.errors)
            except Exception as e:
                failed_configs.append(f"override_{i}")
                errors.append(str(e))
        
        # Update MindsDB config if provided
        if bulk_update.mindsdb_config:
            try:
                active_config = db.query(MindsDBConfigurationModel).filter(
                    MindsDBConfigurationModel.is_active == True
                ).first()
                
                if active_config:
                    config_service.update_mindsdb_configuration(
                        active_config.id, bulk_update.mindsdb_config, 
                        current_user.id, current_user.email
                    )
                    applied_configs.append("mindsdb_config")
                    restart_required = True
                else:
                    errors.append("No active MindsDB configuration found")
                    failed_configs.append("mindsdb_config")
            except Exception as e:
                failed_configs.append("mindsdb_config")
                errors.append(str(e))
        
        return ConfigurationApplicationResult(
            success=len(failed_configs) == 0,
            applied_configs=applied_configs,
            failed_configs=failed_configs,
            errors=errors,
            restart_required=restart_required
        )
        
    except Exception as e:
        logger.error(f"Error in bulk configuration update: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating configurations: {str(e)}")


@router.post("/restart-required", operation_id="check_restart_required_v1")
async def check_restart_required(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Check if application restart is required due to configuration changes"""
    try:
        # Check for configurations that require restart and have been modified
        restart_configs = db.query(ConfigurationOverride).filter(
            ConfigurationOverride.requires_restart == True,
            ConfigurationOverride.value != ConfigurationOverride.default_value
        ).all()
        
        return {
            "restart_required": len(restart_configs) > 0,
            "affected_configs": [
                {
                    "key": config.key,
                    "title": config.title,
                    "last_applied": config.last_applied_at.isoformat() if config.last_applied_at else None
                }
                for config in restart_configs
            ],
            "recommendation": "Restart the application to apply configuration changes" if restart_configs else "No restart required"
        }
        
    except Exception as e:
        logger.error(f"Error checking restart requirement: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking restart requirement: {str(e)}")
@router.get("/unified-config", response_model=Dict[str, Any], operation_id="get_unified_configuration_v1")
async def get_unified_configuration(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get unified system configuration including all necessary configs and environment variables"""
    try:
        config_service = AdminConfigService(db)
        
        # Initialize default configurations if not exists
        config_service.initialize_default_configurations()
        
        # Get all configurations grouped by category
        all_configs = config_service.get_all_configurations()
        
        # Get environment variables
        env_vars = config_service.get_environment_variables()
        
        # Get MindsDB configurations
        mindsdb_configs = config_service.get_mindsdb_configurations()
        active_mindsdb = next((c for c in mindsdb_configs if c.is_active), None)
        
        # Get Google API key status
        google_api_key = os.getenv("GOOGLE_API_KEY")
        
        # Organize configurations by category for unified display
        unified_config = {
            "categories": {},
            "environment_variables": env_vars,
            "mindsdb_configurations": [
                {
                    "id": config.id,
                    "config_name": config.config_name,
                    "is_active": config.is_active,
                    "mindsdb_url": config.mindsdb_url,
                    "storage_type": config.permanent_storage_config.get("location", "local") if config.permanent_storage_config else "local",
                    "is_healthy": config.is_healthy,
                    "last_health_check": config.last_health_check.isoformat() if config.last_health_check else None
                }
                for config in mindsdb_configs
            ],
            "active_mindsdb_config": {
                "id": active_mindsdb.id,
                "config_name": active_mindsdb.config_name,
                "storage_type": active_mindsdb.permanent_storage_config.get("location", "local") if active_mindsdb.permanent_storage_config else "local"
            } if active_mindsdb else None,
            "google_api_key_status": {
                "configured": bool(google_api_key),
                "masked_value": "••••••••" if google_api_key else None
            },
            "system_health": {
                "status": "healthy" if google_api_key else "warning",
                "checks": {
                    "google_api_key": bool(google_api_key),
                    "mindsdb_connection": active_mindsdb.is_healthy if active_mindsdb else False
                }
            }
        }
        
        # Organize configurations by category
        for category, configs in all_configs.items():
            unified_config["categories"][category] = {
                "name": category.replace("_", " ").title(),
                "description": f"Configuration settings for {category.replace('_', ' ').lower()}",
                "configs": configs
            }
        
        return unified_config
        
    except Exception as e:
        logger.error(f"Error getting unified configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving unified configuration: {str(e)}")


@router.put("/unified-config/environment/{key}")
async def update_environment_variable(
    key: str,
    update_data: Dict[str, str],
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Update an environment variable"""
    try:
        config_service = AdminConfigService(db)
        value = update_data.get("value")
        
        if not value:
            raise HTTPException(status_code=400, detail="Value is required")
        
        # Find the configuration override for this environment variable
        config = db.query(ConfigurationOverrideModel).filter(
            ConfigurationOverrideModel.env_var_name == key
        ).first()
        
        if config:
            # Update through the config service
            update_data_obj = ConfigurationOverrideUpdate(value=value)
            result = config_service.update_configuration(
                config.id, 
                update_data_obj, 
                current_user.id, 
                current_user.email
            )
            
            if result.success:
                return {"message": f"Environment variable '{key}' updated successfully"}
            else:
                raise HTTPException(status_code=400, detail=f"Failed to update: {', '.join(result.errors)}")
        else:
            # Direct environment variable update (not managed)
            # SECURITY: Only allow safe environment variables
            ALLOWED_ENV_VARS = {
                "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                "DEFAULT_GEMINI_MODEL", "LOG_LEVEL", "MAX_UPLOAD_SIZE_MB",
                "MAX_CHAT_SESSIONS_PER_DATASET", "DEFAULT_DOWNLOAD_EXPIRY_HOURS",
                "STORAGE_BACKEND", "S3_BUCKET", "S3_REGION", "S3_ENDPOINT_URL",
            }
            if key not in ALLOWED_ENV_VARS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Environment variable '{key}' is not in the allowed set for direct update"
                )
            os.environ[key] = value
            return {"message": f"Environment variable '{key}' updated successfully"}
            
    except Exception as e:
        logger.error(f"Error updating environment variable: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating environment variable: {str(e)}")


@router.post("/unified-config/mindsdb")
async def create_mindsdb_configuration(
    config: Dict[str, Any],
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Create a new MindsDB configuration with storage options"""
    try:
        config_service = AdminConfigService(db)
        
        # Build permanent storage config based on storage type
        storage_type = config.get("storage_type", "local")
        permanent_storage_config = {"location": storage_type}
        
        if storage_type == "s3":
            permanent_storage_config.update({
                "aws_access_key_id": config.get("aws_access_key_id"),
                "aws_secret_access_key": config.get("aws_secret_access_key"),
                "aws_default_region": config.get("aws_default_region", "us-east-1"),
                "bucket": config.get("s3_bucket_name")
            })
        
        mindsdb_config = MindsDBConfigurationCreate(
            config_name=config["config_name"],
            mindsdb_url=config.get("mindsdb_url", "http://127.0.0.1:47334"),
            mindsdb_database=config.get("mindsdb_database", "mindsdb"),
            mindsdb_username=config.get("mindsdb_username"),
            mindsdb_password=config.get("mindsdb_password"),
            permanent_storage_config=permanent_storage_config,
            is_active=config.get("is_active", True)
        )
        
        new_config = config_service.create_mindsdb_configuration(
            mindsdb_config,
            current_user.id,
            current_user.email
        )
        
        return {
            "id": new_config.id,
            "message": "MindsDB configuration created successfully",
            "config_name": new_config.config_name
        }
        
    except Exception as e:
        logger.error(f"Error creating MindsDB configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating MindsDB configuration: {str(e)}")


@router.put("/unified-config/mindsdb/{config_id}")
async def update_mindsdb_configuration(
    config_id: int,
    config: Dict[str, Any],
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Update a MindsDB configuration including storage options"""
    try:
        config_service = AdminConfigService(db)
        
        # Build permanent storage config based on storage type
        storage_type = config.get("storage_type", "local")
        permanent_storage_config = {"location": storage_type}
        
        if storage_type == "s3":
            permanent_storage_config.update({
                "aws_access_key_id": config.get("aws_access_key_id"),
                "aws_secret_access_key": config.get("aws_secret_access_key"),
                "aws_default_region": config.get("aws_default_region", "us-east-1"),
                "bucket": config.get("s3_bucket_name")
            })
        
        update_data = MindsDBConfigurationUpdate(
            config_name=config.get("config_name"),
            mindsdb_url=config.get("mindsdb_url"),
            mindsdb_database=config.get("mindsdb_database"),
            mindsdb_username=config.get("mindsdb_username"),
            mindsdb_password=config.get("mindsdb_password"),
            permanent_storage_config=permanent_storage_config,
            is_active=config.get("is_active")
        )
        
        updated_config = config_service.update_mindsdb_configuration(
            config_id,
            update_data,
            current_user.id,
            current_user.email
        )
        
        return {
            "id": updated_config.id,
            "message": "MindsDB configuration updated successfully",
            "config_name": updated_config.config_name
        }
        
    except Exception as e:
        logger.error(f"Error updating MindsDB configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating MindsDB configuration: {str(e)}")


@router.post("/restart-required", operation_id="check_restart_required_v2")
async def check_restart_required(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Check if system restart is required due to configuration changes"""
    try:
        # Check for configurations that require restart and have been modified
        restart_configs = db.query(ConfigurationOverrideModel).filter(
            and_(
                ConfigurationOverrideModel.requires_restart == True,
                ConfigurationOverrideModel.value != ConfigurationOverrideModel.default_value
            )
        ).all()
        
        return {
            "restart_required": len(restart_configs) > 0,
            "affected_configs": [
                {
                    "key": config.key,
                    "title": config.title,
                    "category": config.category
                }
                for config in restart_configs
            ],
            "message": "System restart required for configuration changes to take effect" if restart_configs else "No restart required"
        }
        
    except Exception as e:
        logger.error(f"Error checking restart status: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking restart status: {str(e)}")


# New Unified Configuration API Endpoints

@router.get("/unified-config", operation_id="get_unified_configuration_v2")
async def get_unified_configuration(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get unified configuration display with complete config from code and MindsDB S3/local storage options"""
    try:
        config_service = AdminConfigurationService(db)
        
        # Initialize default configurations if not exists
        config_service.initialize_default_configurations()
        
        # Get all configuration categories
        env_overrides = config_service.get_all_configurations()
        env_variables = config_service.get_environment_variables()
        mindsdb_configs = config_service.get_mindsdb_configurations()
        
        # Find active MindsDB config
        active_mindsdb = next((c for c in mindsdb_configs if c.is_active), None)
        
        # Get system health status
        system_health = await _get_system_health_status(db)
        
        # Get MindsDB storage configuration
        storage_config = _get_mindsdb_storage_config(active_mindsdb)
        
        # Organize configurations by category with enhanced metadata
        categorized_configs = {}
        for category, configs in env_overrides.items():
            categorized_configs[category] = {
                "configs": configs,
                "count": len(configs),
                "has_sensitive": any(config.get("is_sensitive", False) for config in configs),
                "has_required": any(config.get("is_required", False) for config in configs),
                "has_overrides": any(config.get("is_overridden", False) for config in configs)
            }
        
        # Get configuration statistics
        total_configs = sum(len(configs) for configs in env_overrides.values())
        overridden_configs = sum(
            sum(1 for config in configs if config.get("is_overridden", False))
            for configs in env_overrides.values()
        )
        
        return {
            "configurations": {
                "by_category": categorized_configs,
                "statistics": {
                    "total_configurations": total_configs,
                    "overridden_configurations": overridden_configs,
                    "environment_variables": env_variables.get("managed_count", 0),
                    "mindsdb_configurations": len(mindsdb_configs)
                }
            },
            "environment_variables": {
                "managed": env_variables.get("variables", []),
                "summary": {
                    "managed_count": env_variables.get("managed_count", 0),
                    "unmanaged_count": env_variables.get("unmanaged_count", 0),
                    "categories": env_variables.get("categories", {})
                }
            },
            "mindsdb": {
                "configurations": [
                    {
                        "id": config.id,
                        "config_name": config.config_name,
                        "mindsdb_url": config.mindsdb_url,
                        "is_active": config.is_active,
                        "is_healthy": config.is_healthy,
                        "storage_type": _extract_storage_type(config),
                        "last_health_check": config.last_health_check.isoformat() if config.last_health_check else None,
                        "created_at": config.created_at.isoformat() if config.created_at else None
                    }
                    for config in mindsdb_configs
                ],
                "active_config": {
                    "id": active_mindsdb.id,
                    "config_name": active_mindsdb.config_name,
                    "mindsdb_url": active_mindsdb.mindsdb_url,
                    "storage_config": storage_config,
                    "is_healthy": active_mindsdb.is_healthy,
                    "last_health_check": active_mindsdb.last_health_check.isoformat() if active_mindsdb.last_health_check else None
                } if active_mindsdb else None,
                "storage_options": {
                    "local": {
                        "type": "local",
                        "description": "Store data locally on the server filesystem",
                        "configuration": {
                            "location": "local",
                            "path": "./storage/mindsdb"
                        }
                    },
                    "s3": {
                        "type": "s3",
                        "description": "Store data in Amazon S3",
                        "configuration": {
                            "location": "s3",
                            "aws_access_key_id": "required",
                            "aws_secret_access_key": "required",
                            "bucket": "required",
                            "region": "optional"
                        },
                        "required_env_vars": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_BUCKET_NAME"]
                    }
                }
            },
            "system_health": system_health,
            "metadata": {
                "last_updated": datetime.utcnow().isoformat(),
                "restart_required": any(
                    config.get("requires_restart", False) and config.get("is_overridden", False)
                    for category_configs in env_overrides.values()
                    for config in category_configs
                ),
                "configuration_file_status": {
                    "mindsdb_config_exists": os.path.exists("./mindsdb_config.json"),
                    "config_file_path": "./mindsdb_config.json"
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting unified configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving unified configuration: {str(e)}")


@router.post("/unified-config/create")
async def create_unified_configuration(
    config_data: Dict[str, Any],
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Create new configuration entries across different categories"""
    try:
        config_service = AdminConfigurationService(db)
        created_configs = []
        errors = []
        
        # Create environment variable overrides
        if "environment_overrides" in config_data:
            for override_data in config_data["environment_overrides"]:
                try:
                    # Check if configuration already exists
                    existing = db.query(ConfigurationOverrideModel).filter(
                        ConfigurationOverrideModel.key == override_data.get("key")
                    ).first()
                    
                    if existing:
                        errors.append(f"Configuration key '{override_data.get('key')}' already exists")
                        continue
                    
                    config = ConfigurationOverrideModel(**override_data)
                    db.add(config)
                    db.commit()
                    db.refresh(config)
                    
                    created_configs.append({
                        "type": "environment_override",
                        "id": config.id,
                        "key": config.key
                    })
                    
                    # Record history
                    config_service._record_configuration_change(
                        config.key,
                        "override",
                        None,
                        config.value,
                        current_user.id,
                        current_user.email,
                        "New configuration override created via unified API"
                    )
                    
                except Exception as e:
                    errors.append(f"Error creating override '{override_data.get('key', 'unknown')}': {str(e)}")
        
        # Create MindsDB configuration
        if "mindsdb_config" in config_data:
            try:
                mindsdb_data = config_data["mindsdb_config"]
                mindsdb_config = MindsDBConfigurationCreate(**mindsdb_data)
                
                config = config_service.create_mindsdb_configuration(
                    mindsdb_config, current_user.id, current_user.email
                )
                
                created_configs.append({
                    "type": "mindsdb_config",
                    "id": config.id,
                    "config_name": config.config_name
                })
                
            except Exception as e:
                errors.append(f"Error creating MindsDB configuration: {str(e)}")
        
        return {
            "success": len(errors) == 0,
            "created_configurations": created_configs,
            "errors": errors,
            "message": f"Created {len(created_configs)} configurations" + (f" with {len(errors)} errors" if errors else "")
        }
        
    except Exception as e:
        logger.error(f"Error creating unified configuration: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating configuration: {str(e)}")


@router.put("/unified-config/update")
async def update_unified_configuration(
    updates: Dict[str, Any],
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Update configurations across different categories in a unified manner"""
    try:
        config_service = AdminConfigurationService(db)
        updated_configs = []
        errors = []
        restart_required = False
        
        # Update environment variable overrides
        if "environment_overrides" in updates:
            for update_data in updates["environment_overrides"]:
                try:
                    config_id = update_data.get("id")
                    if not config_id:
                        errors.append("Configuration ID is required for updates")
                        continue
                    
                    update_obj = ConfigurationOverrideUpdate(**{
                        k: v for k, v in update_data.items() if k != "id"
                    })
                    
                    result = config_service.update_configuration(
                        config_id, update_obj, current_user.id, current_user.email
                    )
                    
                    if result.success:
                        updated_configs.extend(result.applied_configs)
                        if result.restart_required:
                            restart_required = True
                    else:
                        errors.extend(result.errors)
                        
                except Exception as e:
                    errors.append(f"Error updating configuration {config_id}: {str(e)}")
        
        # Update MindsDB configuration
        if "mindsdb_config" in updates:
            try:
                mindsdb_update = updates["mindsdb_config"]
                config_id = mindsdb_update.get("id")
                
                if not config_id:
                    errors.append("MindsDB configuration ID is required for updates")
                else:
                    update_obj = MindsDBConfigurationUpdate(**{
                        k: v for k, v in mindsdb_update.items() if k != "id"
                    })
                    
                    config = config_service.update_mindsdb_configuration(
                        config_id, update_obj, current_user.id, current_user.email
                    )
                    
                    updated_configs.append(f"mindsdb.{config.config_name}")
                    restart_required = True
                    
            except Exception as e:
                errors.append(f"Error updating MindsDB configuration: {str(e)}")
        
        # Apply environment variables if requested
        if updates.get("apply_environment_changes", False):
            try:
                for config_key in updated_configs:
                    if not config_key.startswith("mindsdb."):
                        config = db.query(ConfigurationOverrideModel).filter(
                            ConfigurationOverrideModel.key == config_key
                        ).first()
                        
                        if config and config.env_var_name and config.value:
                            os.environ[config.env_var_name] = str(config.value)
                            config.last_applied_at = datetime.utcnow()
                
                db.commit()
                
            except Exception as e:
                errors.append(f"Error applying environment changes: {str(e)}")
        
        return {
            "success": len(errors) == 0,
            "updated_configurations": updated_configs,
            "errors": errors,
            "restart_required": restart_required,
            "message": f"Updated {len(updated_configs)} configurations" + (f" with {len(errors)} errors" if errors else "")
        }
        
    except Exception as e:
        logger.error(f"Error updating unified configuration: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating configuration: {str(e)}")


@router.get("/unified-config/health")
async def get_unified_health_status(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get comprehensive health status for all system components"""
    try:
        health_status = await _get_system_health_status(db)
        
        # Add configuration-specific health checks
        config_service = AdminConfigurationService(db)
        
        # Check MindsDB configurations health
        mindsdb_configs = config_service.get_mindsdb_configurations()
        mindsdb_health = []
        
        for config in mindsdb_configs:
            if config.is_active:
                test_result = config_service.test_mindsdb_connection(config.id)
                mindsdb_health.append({
                    "config_id": config.id,
                    "config_name": config.config_name,
                    "url": config.mindsdb_url,
                    "is_healthy": test_result.get("success", False),
                    "last_checked": test_result.get("last_checked"),
                    "error": test_result.get("error")
                })
        
        # Check required environment variables
        required_env_vars = []
        configs = db.query(ConfigurationOverrideModel).filter(
            ConfigurationOverrideModel.is_required == True
        ).all()
        
        for config in configs:
            if config.env_var_name:
                env_value = os.getenv(config.env_var_name)
                required_env_vars.append({
                    "name": config.env_var_name,
                    "is_set": env_value is not None,
                    "description": config.description,
                    "category": config.category
                })
        
        health_status.update({
            "mindsdb_connections": mindsdb_health,
            "required_environment_variables": required_env_vars,
            "configuration_status": {
                "total_configs": len(configs),
                "missing_required": sum(1 for var in required_env_vars if not var["is_set"]),
                "mindsdb_healthy": sum(1 for health in mindsdb_health if health["is_healthy"]),
                "mindsdb_total": len(mindsdb_health)
            }
        })
        
        return health_status
        
    except Exception as e:
        logger.error(f"Error getting unified health status: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving health status: {str(e)}")


# Helper functions for unified configuration

async def _get_system_health_status(db: Session) -> Dict[str, Any]:
    """Get comprehensive system health status"""
    try:
        # Check Google API key
        google_api_config = db.query(ConfigurationOverrideModel).filter(
            ConfigurationOverrideModel.env_var_name == "GOOGLE_API_KEY"
        ).first()
        
        google_api_status = {
            "configured": google_api_config is not None and google_api_config.value is not None,
            "env_var_set": os.getenv("GOOGLE_API_KEY") is not None,
            "last_updated": google_api_config.updated_at.isoformat() if google_api_config and google_api_config.updated_at else None
        }
        
        # Check MindsDB connection
        mindsdb_status = {"connected": False, "error": None}
        try:
            from app.services.mindsdb import MindsDBService
            mindsdb_service = MindsDBService()
            health_check = mindsdb_service.health_check()
            mindsdb_status = {
                "connected": health_check.get("status") == "healthy",
                "url": mindsdb_service.base_url,
                "response_time": health_check.get("response_time"),
                "error": health_check.get("error")
            }
        except Exception as e:
            mindsdb_status["error"] = str(e)
        
        # Check database connection
        database_status = {"connected": True, "error": None}
        try:
            db.execute("SELECT 1")
        except Exception as e:
            database_status = {"connected": False, "error": str(e)}
        
        return {
            "google_api": google_api_status,
            "mindsdb": mindsdb_status,
            "database": database_status,
            "overall_status": "healthy" if all([
                google_api_status["configured"],
                mindsdb_status["connected"],
                database_status["connected"]
            ]) else "warning"
        }
        
    except Exception as e:
        logger.error(f"Error getting system health status: {e}")
        return {
            "google_api": {"configured": False, "env_var_set": False, "error": str(e)},
            "mindsdb": {"connected": False, "error": str(e)},
            "database": {"connected": False, "error": str(e)},
            "overall_status": "error"
        }


def _get_mindsdb_storage_config(active_config) -> Dict[str, Any]:
    """Extract storage configuration from active MindsDB config"""
    if not active_config or not active_config.permanent_storage_config:
        return {"type": "local", "location": "./storage/mindsdb"}
    
    storage_config = active_config.permanent_storage_config
    storage_type = storage_config.get("location", "local")
    
    if storage_type == "s3":
        return {
            "type": "s3",
            "bucket": storage_config.get("bucket"),
            "region": storage_config.get("region"),
            "prefix": storage_config.get("prefix", ""),
            "aws_credentials_configured": all([
                os.getenv("AWS_ACCESS_KEY_ID"),
                os.getenv("AWS_SECRET_ACCESS_KEY")
            ])
        }
    else:
        return {
            "type": "local",
            "location": storage_config.get("path", "./storage/mindsdb")
        }


def _extract_storage_type(config) -> str:
    """Extract storage type from MindsDB configuration"""
    if not config.permanent_storage_config:
        return "local"
    
    return config.permanent_storage_config.get("location", "local")


@router.get("/storage-service/info")
async def get_storage_service_info(
    current_user: User = Depends(get_current_superuser)
):
    """Get storage service information and configuration."""
    try:
        # Get backend information
        backend_info = storage_service.get_backend_info()
        
        # Get environment configuration
        storage_config = {
            "STORAGE_TYPE": os.getenv('STORAGE_TYPE', 'local'),
            "AWS_ACCESS_KEY_ID": "***CONFIGURED***" if os.getenv('AWS_ACCESS_KEY_ID') else "Not configured",
            "AWS_SECRET_ACCESS_KEY": "***CONFIGURED***" if os.getenv('AWS_SECRET_ACCESS_KEY') else "Not configured",
            "AWS_DEFAULT_REGION": os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
            "S3_BUCKET_NAME": os.getenv('S3_BUCKET_NAME', 'Not configured'),
            "S3_COMPATIBLE_ENDPOINT": os.getenv('S3_COMPATIBLE_ENDPOINT', 'Not configured'),
            "S3_COMPATIBLE_ACCESS_KEY": "***CONFIGURED***" if os.getenv('S3_COMPATIBLE_ACCESS_KEY') else "Not configured",
            "S3_COMPATIBLE_SECRET_KEY": "***CONFIGURED***" if os.getenv('S3_COMPATIBLE_SECRET_KEY') else "Not configured",
            "S3_COMPATIBLE_BUCKET_NAME": os.getenv('S3_COMPATIBLE_BUCKET_NAME', 'Not configured'),
            "S3_COMPATIBLE_REGION": os.getenv('S3_COMPATIBLE_REGION', 'us-east-1')
        }
        
        # Check S3 library availability
        try:
            import boto3
            s3_available = True
        except ImportError:
            s3_available = False
        
        return {
            "backend_info": backend_info,
            "environment_config": storage_config,
            "s3_library_available": s3_available,
            "supported_storage_types": ["local", "s3", "s3_compatible"],
            "current_storage_type": backend_info.get("storage_type", "unknown"),
            "supports_presigned_urls": backend_info.get("supports_presigned_urls", False),
            "status": "operational"
        }
        
    except Exception as e:
        logger.error(f"Error getting storage service info: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving storage service information: {str(e)}")


@router.post("/storage-service/test-connection")
async def test_storage_connection(
    current_user: User = Depends(get_current_superuser)
):
    """Test the current storage backend connection."""
    try:
        # Create a test file
        test_content = b"Storage service connection test"
        test_filename = "storage_test.txt"
        
        # Store test file
        result = await storage_service.store_dataset_file(
            file_content=test_content,
            original_filename=test_filename,
            dataset_id=999999,  # Use a high number for test
            organization_id=999999
        )
        
        # Retrieve test file
        retrieved_content = await storage_service.retrieve_dataset_file(result['relative_path'])
        
        # Verify content matches
        if retrieved_content != test_content:
            raise Exception("Content mismatch during retrieval")
        
        # Clean up test file
        await storage_service.delete_dataset_file(result['relative_path'])
        
        return {
            "status": "success",
            "message": "Storage connection test passed",
            "backend_type": type(storage_service.backend).__name__,
            "test_file_size": len(test_content),
            "operations_tested": ["store", "retrieve", "delete"]
        }
        
    except Exception as e:
        logger.error(f"Storage connection test failed: {e}")
        return {
            "status": "error",
            "message": f"Storage connection test failed: {str(e)}",
            "backend_type": type(storage_service.backend).__name__ if storage_service.backend else "unknown"
        }


@router.get("/organizations")
async def get_all_organizations(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get all organizations for admin management."""
    try:
        organizations = db.query(Organization).all()
        
        org_list = []
        for org in organizations:
            # Count users in each organization
            user_count = db.query(User).filter(User.organization_id == org.id).count()
            
            org_list.append({
                "id": org.id,
                "name": org.name,
                "slug": org.slug,
                "description": org.description,
                "type": org.type,
                "is_active": org.is_active,
                "created_at": org.created_at.isoformat() if org.created_at else None,
                "user_count": user_count
            })
        
        return {
            "organizations": org_list,
            "total": len(org_list)
        }
        
    except Exception as e:
        logger.error(f"Error getting organizations: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving organizations: {str(e)}")


@router.post("/organizations")
async def create_organization(
    org_data: Dict[str, Any],
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Create a new organization."""
    try:
        # Validate required fields
        name = org_data.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Organization name is required")
        
        # Generate slug from name if not provided
        slug = org_data.get("slug", "").strip()
        if not slug:
            slug = name.lower().replace(" ", "-").replace("_", "-")
            # Remove special characters
            import re
            slug = re.sub(r'[^a-z0-9-]', '', slug)
        
        # Check if organization with same name or slug exists
        existing_org = db.query(Organization).filter(
            (Organization.name == name) | (Organization.slug == slug)
        ).first()
        
        if existing_org:
            raise HTTPException(status_code=400, detail="Organization with this name or slug already exists")
        
        # Create organization
        organization = Organization(
            name=name,
            slug=slug,
            description=org_data.get("description", ""),
            type=org_data.get("type", "SMALL_BUSINESS"),
            is_active=org_data.get("is_active", True)
        )
        
        db.add(organization)
        db.commit()
        db.refresh(organization)
        
        return {
            "message": "Organization created successfully",
            "organization": {
                "id": organization.id,
                "name": organization.name,
                "slug": organization.slug,
                "description": organization.description,
                "type": organization.type,
                "is_active": organization.is_active,
                "created_at": organization.created_at.isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating organization: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating organization: {str(e)}")


@router.put("/organizations/{org_id}")
async def update_organization(
    org_id: int,
    org_data: Dict[str, Any],
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Update an organization."""
    try:
        organization = db.query(Organization).filter(Organization.id == org_id).first()
        if not organization:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        # Update fields
        if "name" in org_data:
            organization.name = org_data["name"].strip()
        if "description" in org_data:
            organization.description = org_data["description"]
        if "type" in org_data:
            organization.type = org_data["type"]
        if "is_active" in org_data:
            organization.is_active = org_data["is_active"]
        
        db.commit()
        db.refresh(organization)
        
        return {
            "message": "Organization updated successfully",
            "organization": {
                "id": organization.id,
                "name": organization.name,
                "slug": organization.slug,
                "description": organization.description,
                "type": organization.type,
                "is_active": organization.is_active,
                "updated_at": organization.updated_at.isoformat() if organization.updated_at else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating organization: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating organization: {str(e)}")


@router.delete("/organizations/{org_id}")
async def delete_organization(
    org_id: int,
    force: bool = False,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Delete an organization."""
    try:
        organization = db.query(Organization).filter(Organization.id == org_id).first()
        if not organization:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        # Check if organization has users
        user_count = db.query(User).filter(User.organization_id == org_id).count()
        if user_count > 0 and not force:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot delete organization with {user_count} users. Use force=true to delete anyway."
            )
        
        # If force delete, update users to have no organization
        if force and user_count > 0:
            db.query(User).filter(User.organization_id == org_id).update({"organization_id": None})
        
        db.delete(organization)
        db.commit()
        
        return {
            "message": "Organization deleted successfully",
            "organization_id": org_id,
            "users_affected": user_count if force else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting organization: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting organization: {str(e)}")


@router.get("/users")
async def get_all_users(
    skip: int = 0,
    limit: int = 100,
    organization_id: Optional[int] = None,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get all users for admin management."""
    try:
        query = db.query(User)
        
        if organization_id:
            query = query.filter(User.organization_id == organization_id)
        
        total_count = query.count()
        users = query.offset(skip).limit(limit).all()
        
        user_list = []
        for user in users:
            org_name = None
            if user.organization_id:
                org = db.query(Organization).filter(Organization.id == user.organization_id).first()
                org_name = org.name if org else None
            
            user_list.append({
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "organization_id": user.organization_id,
                "organization_name": org_name,
                "created_at": user.created_at.isoformat() if user.created_at else None
            })
        
        return {
            "users": user_list,
            "total": total_count,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving users: {str(e)}")


@router.post("/users")
async def create_user(
    user_data: Dict[str, Any],
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Create a new user."""
    try:
        # Validate required fields
        email = user_data.get("email", "").strip().lower()
        password = user_data.get("password", "").strip()
        full_name = user_data.get("full_name", "").strip()
        
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        if not password:
            raise HTTPException(status_code=400, detail="Password is required")
        if not full_name:
            raise HTTPException(status_code=400, detail="Full name is required")
        
        # Validate email format
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="User with this email already exists")
        
        # Validate organization if provided
        organization_id = user_data.get("organization_id")
        if organization_id:
            org = db.query(Organization).filter(Organization.id == organization_id).first()
            if not org:
                raise HTTPException(status_code=400, detail="Organization not found")
        
        # Create user
        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            role=user_data.get("role", "member"),
            is_active=user_data.get("is_active", True),
            is_superuser=user_data.get("is_superuser", False),
            organization_id=organization_id
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Get organization name for response
        org_name = None
        if user.organization_id:
            org = db.query(Organization).filter(Organization.id == user.organization_id).first()
            org_name = org.name if org else None
        
        return {
            "message": "User created successfully",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "organization_id": user.organization_id,
                "organization_name": org_name,
                "created_at": user.created_at.isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: Dict[str, Any],
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Update a user."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Prevent admin from removing their own superuser status
        if user.id == current_user.id and "is_superuser" in user_data and not user_data["is_superuser"]:
            raise HTTPException(status_code=400, detail="Cannot remove your own superuser status")
        
        # Update fields
        if "full_name" in user_data:
            user.full_name = user_data["full_name"].strip()
        if "role" in user_data:
            user.role = user_data["role"]
        if "is_active" in user_data:
            user.is_active = user_data["is_active"]
        if "is_superuser" in user_data:
            user.is_superuser = user_data["is_superuser"]
        if "organization_id" in user_data:
            # Validate organization if provided
            if user_data["organization_id"]:
                org = db.query(Organization).filter(Organization.id == user_data["organization_id"]).first()
                if not org:
                    raise HTTPException(status_code=400, detail="Organization not found")
            user.organization_id = user_data["organization_id"]
        if "password" in user_data and user_data["password"].strip():
            user.hashed_password = get_password_hash(user_data["password"].strip())
        
        db.commit()
        db.refresh(user)
        
        # Get organization name for response
        org_name = None
        if user.organization_id:
            org = db.query(Organization).filter(Organization.id == user.organization_id).first()
            org_name = org.name if org else None
        
        return {
            "message": "User updated successfully",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "organization_id": user.organization_id,
                "organization_name": org_name,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating user: {str(e)}")


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    force: bool = False,
    transfer_to_admin: bool = True,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Delete a user with proper handling of owned datasets."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Prevent admin from deleting themselves
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot delete your own account")
        
        # Check if user owns any datasets
        owned_datasets = db.query(Dataset).filter(Dataset.owner_id == user_id).all()
        
        if owned_datasets:
            if not force:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Cannot delete user: owns {len(owned_datasets)} dataset(s). Use force=true to handle datasets automatically."
                )
            
            if transfer_to_admin:
                # Transfer ownership to the current admin user
                logger.info(f"Transferring {len(owned_datasets)} datasets from user {user_id} to admin {current_user.id}")
                for dataset in owned_datasets:
                    dataset.owner_id = current_user.id
                    # Update the organization to match the admin's organization if different
                    if dataset.organization_id != current_user.organization_id and current_user.organization_id:
                        dataset.organization_id = current_user.organization_id
            else:
                # Delete all owned datasets (cascade delete)
                logger.info(f"Deleting {len(owned_datasets)} datasets owned by user {user_id}")
                for dataset in owned_datasets:
                    db.delete(dataset)
        
        # Now delete the user
        db.delete(user)
        db.commit()
        
        action_taken = "User deleted successfully"
        if owned_datasets:
            if transfer_to_admin:
                action_taken += f" and {len(owned_datasets)} dataset(s) transferred to admin"
            else:
                action_taken += f" and {len(owned_datasets)} dataset(s) deleted"
        
        return {
            "message": action_taken,
            "user_id": user_id,
            "datasets_affected": len(owned_datasets),
            "action": "transferred" if transfer_to_admin and owned_datasets else "deleted" if owned_datasets else "none"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting user: {str(e)}")


# Database Cleanup Endpoints
@router.get("/cleanup/stats")
async def get_cleanup_stats(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Get database cleanup statistics - orphaned datasets and empty organizations."""
    try:
        # Find orphaned datasets (datasets with non-existent owner_id)
        orphaned_datasets = db.query(Dataset).filter(
            ~Dataset.owner_id.in_(db.query(User.id))
        ).all()
        
        # Find empty organizations (excluding admin organizations)
        empty_orgs_query = db.query(Organization).filter(
            ~Organization.id.in_(
                db.query(User.organization_id).filter(User.organization_id.isnot(None))
            )
        )
        
        # Filter out admin-related organizations
        empty_orgs = []
        for org in empty_orgs_query.all():
            if not any(keyword in org.name.lower() for keyword in ['admin', 'system', 'default', 'super']):
                empty_orgs.append(org)
        
        # Get related data counts for orphaned datasets
        orphaned_dataset_ids = [d.id for d in orphaned_datasets]
        related_data_counts = {}
        
        if orphaned_dataset_ids:
            from app.models.dataset import (
                DatasetAccessLog, DatasetDownload, DatasetModel, 
                DatasetChatSession, ChatMessage, DatasetShareAccess
            )
            
            related_data_counts = {
                'access_logs': db.query(DatasetAccessLog).filter(
                    DatasetAccessLog.dataset_id.in_(orphaned_dataset_ids)
                ).count(),
                'downloads': db.query(DatasetDownload).filter(
                    DatasetDownload.dataset_id.in_(orphaned_dataset_ids)
                ).count(),
                'models': db.query(DatasetModel).filter(
                    DatasetModel.dataset_id.in_(orphaned_dataset_ids)
                ).count(),
                'chat_sessions': db.query(DatasetChatSession).filter(
                    DatasetChatSession.dataset_id.in_(orphaned_dataset_ids)
                ).count(),
                'share_accesses': db.query(DatasetShareAccess).filter(
                    DatasetShareAccess.dataset_id.in_(orphaned_dataset_ids)
                ).count(),
            }
            
            # Count chat messages
            chat_sessions = db.query(DatasetChatSession).filter(
                DatasetChatSession.dataset_id.in_(orphaned_dataset_ids)
            ).all()
            
            if chat_sessions:
                session_ids = [cs.id for cs in chat_sessions]
                related_data_counts['chat_messages'] = db.query(ChatMessage).filter(
                    ChatMessage.session_id.in_(session_ids)
                ).count()
            else:
                related_data_counts['chat_messages'] = 0
        
        # Get organization related data counts
        empty_org_ids = [o.id for o in empty_orgs]
        org_related_data_counts = {}
        
        if empty_org_ids:
            from app.models.dataset import DatabaseConnector
            
            org_related_data_counts = {
                'connectors': db.query(DatabaseConnector).filter(
                    DatabaseConnector.organization_id.in_(empty_org_ids)
                ).count(),
                'org_datasets': db.query(Dataset).filter(
                    Dataset.organization_id.in_(empty_org_ids)
                ).count(),
            }
        
        return {
            "database_stats": {
                "total_users": db.query(User).count(),
                "total_organizations": db.query(Organization).count(),
                "total_datasets": db.query(Dataset).count(),
                "active_datasets": db.query(Dataset).filter(
                    Dataset.is_active == True, 
                    Dataset.is_deleted == False
                ).count(),
            },
            "orphaned_data": {
                "orphaned_datasets": {
                    "count": len(orphaned_datasets),
                    "datasets": [
                        {
                            "id": d.id,
                            "name": d.name,
                            "owner_id": d.owner_id,
                            "created_at": d.created_at.isoformat() if d.created_at else None
                        } for d in orphaned_datasets
                    ],
                    "related_data": related_data_counts
                },
                "empty_organizations": {
                    "count": len(empty_orgs),
                    "organizations": [
                        {
                            "id": o.id,
                            "name": o.name,
                            "type": o.type,
                            "created_at": o.created_at.isoformat() if o.created_at else None
                        } for o in empty_orgs
                    ],
                    "related_data": org_related_data_counts
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting cleanup stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting cleanup stats: {str(e)}")


@router.post("/cleanup/orphaned-datasets")
async def cleanup_orphaned_datasets(
    confirm: bool = False,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Clean up orphaned datasets (datasets with non-existent owners)."""
    try:
        if not confirm:
            raise HTTPException(
                status_code=400, 
                detail="Must set confirm=true to perform cleanup"
            )
        
        # Find orphaned datasets
        orphaned_datasets = db.query(Dataset).filter(
            ~Dataset.owner_id.in_(db.query(User.id))
        ).all()
        
        if not orphaned_datasets:
            return {
                "message": "No orphaned datasets found",
                "deleted_count": 0,
                "deleted_datasets": []
            }
        
        dataset_ids = [d.id for d in orphaned_datasets]

        try:
            from app.services.mindsdb import MindsDBService
            mindsdb_service = MindsDBService()
            for dataset in orphaned_datasets:
                if dataset.agent_name:
                    mindsdb_service.delete_agent(dataset.agent_name)
        except Exception as e:
            logger.warning(f"Agent cleanup failed for orphaned datasets: {e}")

        # Import related models
        from app.models.dataset import (
            DatasetAccessLog, DatasetDownload, DatasetModel, 
            DatasetChatSession, ChatMessage, DatasetShareAccess
        )
        
        # Delete related data in correct order (foreign key dependencies)
        deleted_counts = {}
        
        # Delete chat messages first
        chat_sessions = db.query(DatasetChatSession).filter(
            DatasetChatSession.dataset_id.in_(dataset_ids)
        ).all()
        
        if chat_sessions:
            session_ids = [cs.id for cs in chat_sessions]
            deleted_counts['chat_messages'] = db.query(ChatMessage).filter(
                ChatMessage.session_id.in_(session_ids)
            ).delete(synchronize_session=False)
        else:
            deleted_counts['chat_messages'] = 0
        
        # Delete chat sessions
        deleted_counts['chat_sessions'] = db.query(DatasetChatSession).filter(
            DatasetChatSession.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)
        
        # Delete other related data
        deleted_counts['access_logs'] = db.query(DatasetAccessLog).filter(
            DatasetAccessLog.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)
        
        deleted_counts['downloads'] = db.query(DatasetDownload).filter(
            DatasetDownload.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)
        
        deleted_counts['models'] = db.query(DatasetModel).filter(
            DatasetModel.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)
        
        deleted_counts['share_accesses'] = db.query(DatasetShareAccess).filter(
            DatasetShareAccess.dataset_id.in_(dataset_ids)
        ).delete(synchronize_session=False)
        
        # Finally delete the datasets themselves
        dataset_info = [
            {"id": d.id, "name": d.name, "owner_id": d.owner_id}
            for d in orphaned_datasets
        ]
        
        deleted_datasets_count = db.query(Dataset).filter(
            Dataset.id.in_(dataset_ids)
        ).delete(synchronize_session=False)
        
        db.commit()
        
        return {
            "message": f"Successfully deleted {deleted_datasets_count} orphaned datasets",
            "deleted_count": deleted_datasets_count,
            "deleted_datasets": dataset_info,
            "related_data_deleted": deleted_counts
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error cleaning up orphaned datasets: {e}")
        raise HTTPException(status_code=500, detail=f"Error cleaning up orphaned datasets: {str(e)}")


@router.post("/cleanup/empty-organizations") 
async def cleanup_empty_organizations(
    confirm: bool = False,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Clean up empty organizations (organizations with no users, excluding admin orgs)."""
    try:
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="Must set confirm=true to perform cleanup"
            )
        
        # Find empty organizations
        empty_orgs_query = db.query(Organization).filter(
            ~Organization.id.in_(
                db.query(User.organization_id).filter(User.organization_id.isnot(None))
            )
        )
        
        # Filter out admin-related organizations
        empty_orgs = []
        for org in empty_orgs_query.all():
            if not any(keyword in org.name.lower() for keyword in ['admin', 'system', 'default', 'super']):
                empty_orgs.append(org)
        
        if not empty_orgs:
            return {
                "message": "No empty organizations found",
                "deleted_count": 0,
                "deleted_organizations": []
            }
        
        org_ids = [o.id for o in empty_orgs]
        
        # Delete related data
        from app.models.dataset import DatabaseConnector
        
        deleted_counts = {}
        
        # Delete database connectors
        deleted_counts['connectors'] = db.query(DatabaseConnector).filter(
            DatabaseConnector.organization_id.in_(org_ids)
        ).delete(synchronize_session=False)
        
        # Get organization info before deletion
        org_info = [
            {"id": o.id, "name": o.name, "type": o.type}
            for o in empty_orgs
        ]
        
        # Delete the organizations themselves
        deleted_orgs_count = db.query(Organization).filter(
            Organization.id.in_(org_ids)
        ).delete(synchronize_session=False)
        
        db.commit()
        
        return {
            "message": f"Successfully deleted {deleted_orgs_count} empty organizations",
            "deleted_count": deleted_orgs_count,
            "deleted_organizations": org_info,
            "related_data_deleted": deleted_counts
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error cleaning up empty organizations: {e}")
        raise HTTPException(status_code=500, detail=f"Error cleaning up empty organizations: {str(e)}")


@router.post("/cleanup/all")
async def cleanup_all_orphaned_data(
    confirm: bool = False,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Clean up all orphaned data: datasets and empty organizations."""
    try:
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="Must set confirm=true to perform cleanup"
            )
        
        # Cleanup orphaned datasets first
        datasets_result = await cleanup_orphaned_datasets(confirm=True, current_user=current_user, db=db)
        
        # Then cleanup empty organizations
        orgs_result = await cleanup_empty_organizations(confirm=True, current_user=current_user, db=db)
        
        return {
            "message": "Full cleanup completed successfully",
            "orphaned_datasets": datasets_result,
            "empty_organizations": orgs_result,
            "total_deleted": {
                "datasets": datasets_result["deleted_count"],
                "organizations": orgs_result["deleted_count"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error performing full cleanup: {e}")
        raise HTTPException(status_code=500, detail=f"Error performing full cleanup: {str(e)}")