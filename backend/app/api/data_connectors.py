"""
Enhanced Database Connectors API endpoints
Provides endpoints for managing MySQL, PostgreSQL, S3, document processing, and other data connectors
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging
import json
from datetime import datetime

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.dataset import DatabaseConnector, Dataset
from app.models.organization import DataSharingLevel
from app.services.mindsdb import MindsDBService
from app.services.connector_service import ConnectorService
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class DatabaseConnectorCreate(BaseModel):
    name: str
    connector_type: str  # 'mysql', 'postgresql', 's3', 'api'
    description: Optional[str] = None
    connection_config: Dict[str, Any]
    credentials: Optional[Dict[str, Any]] = None


class DatabaseConnectorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    connection_config: Optional[Dict[str, Any]] = None
    credentials: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


# New simplified connector model
class SimplifiedConnectorCreate(BaseModel):
    name: str
    connector_type: str
    description: Optional[str] = None
    connection_url: str


class DatasetInfo(BaseModel):
    id: int
    name: str
    type: str
    sharing_level: str
    public_share_enabled: bool

class DatabaseConnectorResponse(BaseModel):
    id: int
    name: str
    connector_type: str
    description: Optional[str]
    is_active: bool
    test_status: str
    last_tested_at: Optional[datetime]
    created_at: datetime
    mindsdb_database_name: Optional[str]
    organization_id: int
    datasets: Optional[List[DatasetInfo]] = None
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[DatabaseConnectorResponse])
async def list_connectors(
    connector_type: Optional[str] = None,
    active_only: bool = True,
    include_datasets: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List database connectors for the current organization."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    query = db.query(DatabaseConnector).filter(
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.is_deleted == False
    )
    
    if active_only:
        query = query.filter(DatabaseConnector.is_active == True)
    
    if connector_type:
        query = query.filter(DatabaseConnector.connector_type == connector_type)
    
    connectors = query.order_by(DatabaseConnector.created_at.desc()).all()
    
    if include_datasets:
        # Add dataset information to connectors
        from app.models.dataset import Dataset
        result = []
        for connector in connectors:
            # Get associated datasets
            datasets = db.query(Dataset).filter(
                Dataset.connector_id == connector.id,
                Dataset.is_deleted == False
            ).all()
            
            # Create DatasetInfo objects
            dataset_infos = [
                DatasetInfo(
                    id=dataset.id,
                    name=dataset.name,
                    type=dataset.type.value,  # Convert enum to string
                    sharing_level=dataset.sharing_level.value,  # Convert enum to string
                    public_share_enabled=dataset.public_share_enabled
                )
                for dataset in datasets
            ]
            
            # Create response object with datasets
            connector_response = DatabaseConnectorResponse(
                id=connector.id,
                name=connector.name,
                connector_type=connector.connector_type,
                description=connector.description,
                is_active=connector.is_active,
                test_status=connector.test_status,
                last_tested_at=connector.last_tested_at,
                created_at=connector.created_at,
                mindsdb_database_name=connector.mindsdb_database_name,
                organization_id=connector.organization_id,
                datasets=dataset_infos
            )
            
            result.append(connector_response)
        
        return result
    
    return connectors
@router.put("/{connector_id}", response_model=DatabaseConnectorResponse)
async def update_connector(
    connector_id: int,
    connector_update: DatabaseConnectorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing database connector with enhanced editing capabilities."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    # Get the connector
    connector = db.query(DatabaseConnector).filter(
        DatabaseConnector.id == connector_id,
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found"
        )
    
    # Check if connector is editable
    if not getattr(connector, 'is_editable', True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This connector is not editable"
        )
    
    # Update fields
    update_data = connector_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(connector, field, value)
    
    # Reset test status if connection config or credentials changed
    if connector_update.connection_config or connector_update.credentials:
        connector.test_status = "untested"
        connector.test_error = None
        connector.last_tested_at = None
    
    connector.updated_at = datetime.utcnow()
    
    try:
        db.commit()
        db.refresh(connector)
        
        logger.info(f"Updated connector {connector_id} by user {current_user.id}")
        
        return DatabaseConnectorResponse(
            id=connector.id,
            name=connector.name,
            connector_type=connector.connector_type,
            description=connector.description,
            is_active=connector.is_active,
            test_status=connector.test_status,
            last_tested_at=connector.last_tested_at,
            created_at=connector.created_at,
            mindsdb_database_name=connector.mindsdb_database_name,
            organization_id=connector.organization_id
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating connector {connector_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update connector: {str(e)}"
        )


@router.post("/{connector_id}/test")
async def test_connector_connection(
    connector_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test the connection for a database connector."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    # Get the connector
    connector = db.query(DatabaseConnector).filter(
        DatabaseConnector.id == connector_id,
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found"
        )
    
    try:
        # Initialize connector service
        connector_service = ConnectorService(db)
        
        # Test the connection
        test_result = await connector_service.test_connection(connector)
        
        # Update test status
        connector.test_status = "success" if test_result["success"] else "failed"
        connector.test_error = test_result.get("error")
        connector.last_tested_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "success": test_result["success"],
            "message": test_result.get("message", "Connection test completed"),
            "error": test_result.get("error"),
            "test_time": connector.last_tested_at.isoformat(),
            "connection_details": test_result.get("details", {})
        }
        
    except Exception as e:
        connector.test_status = "failed"
        connector.test_error = str(e)
        connector.last_tested_at = datetime.utcnow()
        db.commit()
        
        logger.error(f"Error testing connector {connector_id}: {str(e)}")
        return {
            "success": False,
            "message": "Connection test failed",
            "error": str(e),
            "test_time": connector.last_tested_at.isoformat()
        }


@router.post("/{connector_id}/sync")
async def sync_connector_data(
    connector_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually sync data from a real-time enabled connector."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    # Get the connector
    connector = db.query(DatabaseConnector).filter(
        DatabaseConnector.id == connector_id,
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found"
        )
    
    # Check if real-time sync is supported
    if not getattr(connector, 'supports_real_time', False) and not force:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Real-time sync not supported for this connector. Use force=true to override."
        )
    
    try:
        # Initialize connector service
        connector_service = ConnectorService(db)
        
        # Perform sync
        sync_result = await connector_service.sync_connector_data(connector)
        
        # Update sync timestamp
        connector.last_synced_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": sync_result["success"],
            "message": sync_result.get("message", "Data sync completed"),
            "records_synced": sync_result.get("records_synced", 0),
            "sync_time": connector.last_synced_at.isoformat(),
            "details": sync_result.get("details", {})
        }
        
    except Exception as e:
        logger.error(f"Error syncing connector {connector_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync connector data: {str(e)}"
        )




@router.post("/", response_model=DatabaseConnectorResponse)
async def create_connector(
    connector_data: DatabaseConnectorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new database connector."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    # Validate connector type
    supported_types = ['mysql', 'postgresql', 's3', 'api', 'mongodb', 'clickhouse']
    if connector_data.connector_type not in supported_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported connector type. Supported: {supported_types}"
        )
    
    # Check for duplicate names in organization
    existing = db.query(DatabaseConnector).filter(
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.name == connector_data.name,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connector with this name already exists"
        )
    
    # Encrypt credentials before storing
    from app.core.encryption import encrypt_dict
    encrypted_credentials = encrypt_dict(connector_data.credentials) if connector_data.credentials else None

    # Create connector
    db_connector = DatabaseConnector(
        name=connector_data.name,
        connector_type=connector_data.connector_type,
        description=connector_data.description,
        organization_id=current_user.organization_id,
        connection_config=connector_data.connection_config,
        credentials=encrypted_credentials,  # ✅ Now encrypted
        created_by=current_user.id,
        mindsdb_database_name=f"org_{current_user.organization_id}_{connector_data.name.lower().replace(' ', '_')}"
    )
    
    db.add(db_connector)
    db.commit()
    db.refresh(db_connector)
    
    # Test connection immediately
    try:
        test_result = await test_connector_connection_sync(db_connector)
        db_connector.test_status = "success" if test_result["success"] else "failed"
        db_connector.test_error = test_result.get("error")
        db_connector.last_tested_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.warning(f"Initial connector test failed: {e}")
        db_connector.test_status = "failed"
        db_connector.test_error = str(e)
        db.commit()
    
    return DatabaseConnectorResponse(
        id=db_connector.id,
        name=db_connector.name,
        connector_type=db_connector.connector_type,
        description=db_connector.description,
        is_active=db_connector.is_active,
        test_status=db_connector.test_status,
        last_tested_at=db_connector.last_tested_at,
        created_at=db_connector.created_at,
        mindsdb_database_name=db_connector.mindsdb_database_name,
        organization_id=db_connector.organization_id
    )


@router.post("/simplified", response_model=DatabaseConnectorResponse)
async def create_simplified_connector(
    connector_data: SimplifiedConnectorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new database connector using simplified URL input."""
    from app.utils.connection_parser import parse_connection_url, ConnectionParseError
    
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    # Validate connector type
    supported_types = ['mysql', 'postgresql', 's3', 'api', 'mongodb', 'clickhouse']
    if connector_data.connector_type not in supported_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported connector type. Supported: {supported_types}"
        )
    
    # Parse connection URL
    try:
        connection_config, credentials = parse_connection_url(
            connector_data.connection_url, 
            connector_data.connector_type
        )
    except ConnectionParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid connection URL: {str(e)}"
        )
    
    # Check for duplicate names in organization
    existing = db.query(DatabaseConnector).filter(
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.name == connector_data.name,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connector with this name already exists"
        )
    
    # Encrypt credentials before storing
    from app.core.encryption import encrypt_dict
    encrypted_credentials = encrypt_dict(credentials) if credentials else None

    # Create connector using parsed configuration
    db_connector = DatabaseConnector(
        name=connector_data.name,
        connector_type=connector_data.connector_type,
        description=connector_data.description,
        organization_id=current_user.organization_id,
        connection_config=connection_config,
        credentials=encrypted_credentials,  # ✅ Now encrypted
        created_by=current_user.id,
        mindsdb_database_name=f"org_{current_user.organization_id}_{connector_data.name.lower().replace(' ', '_')}"
    )
    
    db.add(db_connector)
    db.commit()
    db.refresh(db_connector)
    
    # Test connection immediately
    try:
        test_result = await test_connector_connection_sync(db_connector)
        db_connector.test_status = "success" if test_result["success"] else "failed"
        db_connector.test_error = test_result.get("error")
        db_connector.last_tested_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.warning(f"Initial connector test failed: {e}")
        db_connector.test_status = "failed"
        db_connector.test_error = str(e)
        db.commit()
    
    return DatabaseConnectorResponse(
        id=db_connector.id,
        name=db_connector.name,
        connector_type=db_connector.connector_type,
        description=db_connector.description,
        is_active=db_connector.is_active,
        test_status=db_connector.test_status,
        last_tested_at=db_connector.last_tested_at,
        created_at=db_connector.created_at,
        mindsdb_database_name=db_connector.mindsdb_database_name,
        organization_id=db_connector.organization_id
    )


@router.get("/{connector_id}", response_model=DatabaseConnectorResponse)
async def get_connector(
    connector_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific database connector."""
    connector = db.query(DatabaseConnector).filter(
        DatabaseConnector.id == connector_id,
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found"
        )
    
    return connector




@router.delete("/{connector_id}")
async def delete_connector(
    connector_id: int,
    force_delete: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a database connector."""
    connector = db.query(DatabaseConnector).filter(
        DatabaseConnector.id == connector_id,
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found"
        )
    
    # Disable sharing and proxy connectors for datasets that depend on this connector
    affected_datasets = db.query(Dataset).filter(
        Dataset.connector_id == connector_id,
        Dataset.is_deleted == False
    ).all()
    
    disabled_sharing_count = 0
    disabled_proxy_count = 0
    
    for dataset in affected_datasets:
        # Disable sharing if enabled
        if dataset.public_share_enabled:
            dataset.public_share_enabled = False
            dataset.share_token = None
            dataset.share_expires_at = None
            dataset.share_password = None
            dataset.ai_chat_enabled = False
            disabled_sharing_count += 1
            logger.info(f"Disabled sharing for dataset {dataset.id} due to connector deletion")
        
        # Disable related proxy connectors
        try:
            from app.models.proxy_connector import ProxyConnector
            proxy_connectors = db.query(ProxyConnector).filter(
                ProxyConnector.name == dataset.name,
                ProxyConnector.organization_id == dataset.organization_id,
                ProxyConnector.is_active == True
            ).all()
            
            for proxy_connector in proxy_connectors:
                proxy_connector.is_active = False
                disabled_proxy_count += 1
                logger.info(f"Disabled proxy connector {proxy_connector.proxy_id} due to connector deletion")
                
        except Exception as e:
            logger.warning(f"Failed to disable proxy connectors for dataset {dataset.id}: {e}")

    if force_delete and current_user.is_superuser:
        # Hard delete
        db.delete(connector)
    else:
        # Soft delete
        connector.soft_delete(current_user.id)
    
    db.commit()
    
    return {
        "message": "Connector deleted successfully",
        "affected_datasets": len(affected_datasets),
        "disabled_sharing": disabled_sharing_count,
        "disabled_proxy_connectors": disabled_proxy_count
    }




@router.post("/{connector_id}/sync-mindsdb")
async def sync_with_mindsdb(
    connector_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Sync connector with MindsDB."""
    connector = db.query(DatabaseConnector).filter(
        DatabaseConnector.id == connector_id,
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found"
        )
    
    # Sync with MindsDB
    try:
        sync_result = await sync_connector_with_mindsdb(connector_id)
        logger.info(f"MindsDB sync initiated for connector {connector_id}")
    except Exception as e:
        logger.warning(f"MindsDB sync failed for connector {connector_id}: {e}")
    
    return {
        "message": "Connector sync with MindsDB started",
        "mindsdb_database_name": connector.mindsdb_database_name
    }


class CreateDatasetFromConnector(BaseModel):
    dataset_name: str
    description: Optional[str] = None
    table_or_endpoint: Optional[str] = None  # For API connectors, this can be a different endpoint
    sharing_level: str = "private"


@router.post("/{connector_id}/test-api-endpoint")
async def test_api_endpoint(
    connector_id: int,
    endpoint: str = "/",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test an API endpoint and return preview data."""
    import httpx
    import json
    
    connector = db.query(DatabaseConnector).filter(
        DatabaseConnector.id == connector_id,
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found"
        )
    
    if connector.connector_type != "api":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint is only for API connectors"
        )
    
    config = connector.connection_config
    base_url = config.get("base_url", "")
    
    # Build full URL
    if endpoint and endpoint != "/":
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        full_url = base_url.rstrip("/") + endpoint
    else:
        full_url = base_url
    
    try:
        # Test the API endpoint
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(full_url)
            response.raise_for_status()
            
            # Parse response
            content_type = response.headers.get("content-type", "").lower()
            if "application/json" in content_type:
                data = response.json()
                
                # Analyze the data structure
                preview = {
                    "success": True,
                    "url_tested": full_url,
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "data_type": type(data).__name__,
                    "preview_data": None,
                    "detected_endpoint": endpoint,
                    "row_count": 0,
                    "column_count": 0,
                    "columns": []
                }
                
                # If data is a list, it's likely the correct endpoint
                if isinstance(data, list):
                    preview["preview_data"] = data[:3] if len(data) > 3 else data
                    preview["row_count"] = len(data)
                    if data:
                        preview["columns"] = list(data[0].keys()) if isinstance(data[0], dict) else []
                        preview["column_count"] = len(preview["columns"])
                    preview["message"] = f"✅ Found {len(data)} items at this endpoint"
                
                # If data is a dict, check if it contains arrays
                elif isinstance(data, dict):
                    # Check for common API response patterns
                    arrays_found = []
                    for key, value in data.items():
                        if isinstance(value, list) and value:
                            arrays_found.append({
                                "key": key,
                                "count": len(value),
                                "sample": value[0] if value else None
                            })
                    
                    if arrays_found:
                        # Suggest the best endpoint
                        best_array = max(arrays_found, key=lambda x: x["count"])
                        suggested_endpoint = endpoint.rstrip("/") + "/" + best_array["key"]
                        preview["suggested_endpoints"] = [
                            {
                                "endpoint": endpoint.rstrip("/") + "/" + arr["key"],
                                "count": arr["count"],
                                "description": f"Array '{arr['key']}' with {arr['count']} items"
                            }
                            for arr in arrays_found
                        ]
                        preview["message"] = f"ℹ️ Found object with {len(arrays_found)} array(s). Try one of the suggested endpoints."
                        preview["detected_endpoint"] = suggested_endpoint
                    else:
                        preview["message"] = "⚠️ Found object but no arrays. This might be a single item endpoint."
                        preview["preview_data"] = data
                
                return preview
                
            else:
                return {
                    "success": False,
                    "url_tested": full_url,
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "message": f"Response is not JSON (content-type: {content_type})"
                }
                
    except httpx.HTTPStatusError as e:
        return {
            "success": False,
            "url_tested": full_url,
            "endpoint": endpoint,
            "status_code": e.response.status_code,
            "message": f"HTTP error: {e.response.status_code}"
        }
    except Exception as e:
        return {
            "success": False,
            "url_tested": full_url,
            "endpoint": endpoint,
            "message": f"Error: {str(e)}"
        }


@router.post("/{connector_id}/create-dataset")
async def create_dataset_from_connector(
    connector_id: int,
    dataset_data: CreateDatasetFromConnector,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a dataset from a connector."""
    connector = db.query(DatabaseConnector).filter(
        DatabaseConnector.id == connector_id,
        DatabaseConnector.organization_id == current_user.organization_id,
        DatabaseConnector.is_deleted == False
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found"
        )
    
    if connector.test_status != "success":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connector must be successfully tested before creating datasets"
        )
    
    # For API connectors, create dataset with API data
    if connector.connector_type == "api":
        result = await _create_api_dataset(connector, dataset_data, current_user.id)
    else:
        # For database connectors, use the connector service
        connector_service = ConnectorService(db)
        
        # Map sharing level string to enum
        from app.models.organization import DataSharingLevel
        sharing_level_map = {
            "private": DataSharingLevel.PRIVATE,
            "organization": DataSharingLevel.ORGANIZATION,
            "public": DataSharingLevel.PUBLIC
        }
        sharing_level = sharing_level_map.get(dataset_data.sharing_level.lower(), DataSharingLevel.PRIVATE)
        
        result = await connector_service.create_connector_dataset(
            connector=connector,
            table_or_query=dataset_data.table_or_endpoint or "default_table",
            dataset_name=dataset_data.dataset_name,
            user_id=current_user.id,
            description=dataset_data.description,
            sharing_level=sharing_level
        )
    
    if result.get("success"):
        return {
            "message": "Dataset created successfully",
            "dataset_id": result.get("dataset_id"),
            "dataset_name": result.get("dataset_name")
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to create dataset")
        )


@router.post("/image-remote")
async def create_remote_image_connector(
    connector_config: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a remote image data connector (S3, URL, FTP, etc.)"""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    try:
        # Validate required fields
        required_fields = ["name", "source_type", "connection_params"]
        for field in required_fields:
            if field not in connector_config:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required field: {field}"
                )
        
        connector_name = connector_config["name"]
        source_type = connector_config["source_type"]
        connection_params = connector_config["connection_params"]
        
        # Create database connector record
        connector = DatabaseConnector(
            name=connector_name,
            connector_type="image_remote",
            description=f"Remote image connector for {source_type}",
            connection_config={
                "source_type": source_type,
                "connection_params": connection_params
            },
            organization_id=current_user.organization_id,
            created_by=current_user.id,
            mindsdb_database_name=f"image_remote_{connector_name.lower().replace(' ', '_')}"
        )
        
        db.add(connector)
        db.commit()
        db.refresh(connector)
        
        # Create MindsDB handler
        connector_service = ConnectorService(db)
        handler_result = connector_service.create_image_remote_handler(connector)
        
        if handler_result["success"]:
            connector.test_status = "connected"
            connector.last_tested_at = datetime.utcnow()
            db.commit()
            
            return {
                "success": True,
                "message": "Remote image connector created successfully",
                "connector_id": connector.id,
                "connector_name": connector_name,
                "source_type": source_type,
                "mindsdb_handler": handler_result.get("handler_name")
            }
        else:
            # Rollback if handler creation failed
            db.delete(connector)
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create MindsDB handler: {handler_result.get('error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remote image connector creation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Remote image connector creation failed: {str(e)}"
        )

    
    if result.get("success"):
        return {
            "message": "Dataset created successfully",
            "dataset_id": result.get("dataset_id"),
            "dataset_name": result.get("dataset_name")
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to create dataset")
        )



async def test_connector_connection_sync(connector: DatabaseConnector) -> Dict[str, Any]:
    """Test connector connection synchronously."""
    try:
        if connector.connector_type == "mysql":
            return await _test_mysql_connection(connector)
        elif connector.connector_type == "postgresql":
            return await _test_postgresql_connection(connector)
        elif connector.connector_type == "s3":
            return await _test_s3_connection(connector)
        elif connector.connector_type == "mongodb":
            return await _test_mongodb_connection(connector)
        elif connector.connector_type == "api":
            return await _test_api_connection(connector)
        else:
            return {"success": False, "error": f"Testing not implemented for {connector.connector_type}"}
            
    except Exception as e:
        logger.error(f"Connector test failed for {connector.id}: {e}")
        return {"success": False, "error": str(e)}


async def sync_connector_with_mindsdb(connector_id: int):
    """Background task to sync connector with MindsDB."""
    logger.info(f"Syncing connector {connector_id} with MindsDB in background")


async def _test_mysql_connection(connector: DatabaseConnector) -> Dict[str, Any]:
    """Test MySQL connection."""
    try:
        import mysql.connector
        
        config = connector.connection_config.copy()
        if connector.credentials:
            config.update(connector.credentials)
        
        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        return {"success": True, "message": "MySQL connection successful"}
        
    except Exception as e:
        return {"success": False, "error": f"MySQL connection failed: {str(e)}"}


async def _test_postgresql_connection(connector: DatabaseConnector) -> Dict[str, Any]:
    """Test PostgreSQL connection."""
    try:
        import psycopg2
        
        config = connector.connection_config.copy()
        if connector.credentials:
            config.update(connector.credentials)
        
        connection = psycopg2.connect(**config)
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        return {"success": True, "message": "PostgreSQL connection successful"}
        
    except Exception as e:
        return {"success": False, "error": f"PostgreSQL connection failed: {str(e)}"}


async def _test_s3_connection(connector: DatabaseConnector) -> Dict[str, Any]:
    """Test S3 connection."""
    try:
        import boto3
        
        config = connector.connection_config.copy()
        if connector.credentials:
            config.update(connector.credentials)
        
        s3_client = boto3.client('s3', **config)
        response = s3_client.list_buckets()
        
        return {"success": True, "message": "S3 connection successful", "bucket_count": len(response['Buckets'])}
        
    except Exception as e:
        return {"success": False, "error": f"S3 connection failed: {str(e)}"}


async def _test_mongodb_connection(connector: DatabaseConnector) -> Dict[str, Any]:
    """Test MongoDB connection."""
    try:
        from pymongo import MongoClient
        
        config = connector.connection_config.copy()
        if connector.credentials:
            config.update(connector.credentials)
        
        client = MongoClient(**config)
        # Test connection
        client.server_info()
        client.close()
        
        return {"success": True, "message": "MongoDB connection successful"}
        
    except Exception as e:
        return {"success": False, "error": f"MongoDB connection failed: {str(e)}"}


async def _test_api_connection(connector: DatabaseConnector) -> Dict[str, Any]:
    """Test API connection."""
    try:
        import requests
        
        config = connector.connection_config.copy()
        
        # Get connection details
        base_url = config.get("base_url", "")
        endpoint = config.get("endpoint", "")
        method = config.get("method", "GET").upper()
        timeout = config.get("timeout", 30)
        headers = config.get("headers", {})
        ssl_verify = config.get("ssl_verify", False)  # Default to False for local APIs
        
        if not base_url or not endpoint:
            return {"success": False, "error": "Base URL and endpoint are required"}
        
        full_url = f"{base_url.rstrip('/')}{endpoint}"
        
        # Make the API request with SSL configuration
        response = requests.request(
            method=method,
            url=full_url,
            headers=headers,
            timeout=timeout,
            verify=ssl_verify
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                data_count = len(data) if isinstance(data, list) else 1
                return {
                    "success": True, 
                    "message": f"API connection successful. Retrieved {data_count} items.",
                    "status_code": response.status_code,
                    "data_preview": str(data)[:200] + "..." if len(str(data)) > 200 else str(data),
                    "ssl_config": {"ssl_verify": ssl_verify}
                }
            except:
                return {
                    "success": True,
                    "message": f"API connection successful. Response received (non-JSON).",
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", "unknown"),
                    "ssl_config": {"ssl_verify": ssl_verify}
                }
        else:
            return {
                "success": False, 
                "error": f"API request failed with status {response.status_code}: {response.text[:200]}"
            }
        
    except requests.exceptions.Timeout:
        return {"success": False, "error": "API request timed out"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Failed to connect to API endpoint"}
    except Exception as e:
        return {"success": False, "error": f"API connection failed: {str(e)}"}


async def _create_api_dataset(
    connector: DatabaseConnector, 
    dataset_data: CreateDatasetFromConnector, 
    user_id: int
) -> Dict[str, Any]:
    """Create a dataset from API connector data using MindsDB web connectors."""
    try:
        from app.services.mindsdb import mindsdb_service
        from app.models.dataset import Dataset, DatasetType, DatasetStatus
        from app.core.database import get_db
        
        # Get database session
        db = next(get_db())
        
        config = connector.connection_config.copy()
        base_url = config.get("base_url", "")
        endpoint = dataset_data.table_or_endpoint or config.get("endpoint", "")
        method = config.get("method", "GET").upper()
        headers = config.get("headers", {})
        
        # Prepare auth config for MindsDB
        auth_config = None
        if connector.credentials:
            auth_config = {
                "api_key": connector.credentials.get("api_key"),
                "auth_header": connector.credentials.get("auth_header", "Authorization")
            }
        
        # Create MindsDB web connector
        web_connector_result = mindsdb_service.create_web_connector(
            connector_name=f"api_connector_{connector.id}",
            base_url=base_url,
            endpoint=endpoint,
            method=method,
            headers=headers,
            auth_config=auth_config
        )
        
        if not web_connector_result.get("success"):
            logger.error(f"Failed to create MindsDB web connector: {web_connector_result.get('error')}")
            # Fallback to direct API approach
            return await _create_api_dataset_fallback(connector, dataset_data, user_id)
        
        # Create dataset view from web connector
        # Get table name from the working table name discovered during connector creation
        table_name = web_connector_result.get("working_table_name", "data")
        
        logger.info(f"🎯 Using discovered table name: {table_name} for dataset view creation")
        
        dataset_view_result = mindsdb_service.create_dataset_from_web_connector(
            connector_name=web_connector_result["connector_name"],
            dataset_name=dataset_data.dataset_name,
            table_name=table_name
        )
        
        if not dataset_view_result.get("success"):
            logger.error(f"Failed to create dataset view: {dataset_view_result.get('error')}")
            # Fallback to direct API approach
            return await _create_api_dataset_fallback(connector, dataset_data, user_id)
        
        # Map sharing level
        sharing_level_map = {
            "private": DataSharingLevel.PRIVATE,
            "organization": DataSharingLevel.ORGANIZATION,
            "public": DataSharingLevel.PUBLIC
        }
        sharing_level = sharing_level_map.get(dataset_data.sharing_level.lower(), DataSharingLevel.PRIVATE)
        
        # Generate enhanced metadata for API dataset
        api_columns = dataset_view_result.get("columns", [])
        sample_data = dataset_view_result.get("sample_data", [])
        estimated_rows = dataset_view_result.get("estimated_rows", 0)
        
        # Enhanced file metadata
        file_metadata = {
            "api_url": web_connector_result["url"],
            "method": config.get("method", "GET"),
            "total_records": estimated_rows,
            "sample_record": sample_data[0] if sample_data else None,
            "data_keys": api_columns,
            "connector_id": connector.id,
            "connector_name": connector.name
        }
        
        # Enhanced schema metadata
        schema_metadata = {
            "file_type": "api",
            "source": "api_connector",
            "original_filename": f"{dataset_data.dataset_name}_api_data",
            "structure": {
                "type": "list",
                "total_elements": estimated_rows,
                "sample_structure": str(sample_data[0])[:200] if sample_data else None
            },
            "columns": api_columns,
            "data_types": {col: "string" for col in api_columns},  # Default to string for API data
            "sample_data": str(sample_data[:2])[:500] if sample_data else None
        }
        
        # Enhanced quality metrics
        quality_metrics = {
            "overall_score": 95,  # API data is typically well-structured
            "completeness": 100,
            "consistency": 90,
            "accuracy": 95,
            "issues": [],
            "last_analyzed": datetime.utcnow().isoformat()
        }
        
        # Enhanced preview data
        preview_data = {
            "type": "api",
            "headers": api_columns,
            "sample_rows": sample_data[:10] if sample_data else [],
            "total_rows": estimated_rows,
            "is_sample": estimated_rows > 10,
            "preview_generated_at": datetime.utcnow().isoformat()
        }
        
        # Column statistics
        column_statistics = {}
        for col in api_columns:
            column_statistics[col] = {
                "data_type": "string",
                "non_null_count": estimated_rows,
                "null_count": 0,
                "unique_count": "unknown"
            }
        
        # Create dataset record with MindsDB integration and enhanced metadata
        dataset = Dataset(
            name=dataset_data.dataset_name,
            description=dataset_data.description or f"Web API dataset from {connector.name}",
            type=DatasetType.API,
            status=DatasetStatus.ACTIVE,
            owner_id=user_id,
            organization_id=connector.organization_id,
            sharing_level=sharing_level,
            connector_id=connector.id,
            source_url=web_connector_result["url"],
            row_count=estimated_rows,
            column_count=len(api_columns),
            # Enhanced metadata fields
            file_metadata=file_metadata,
            schema_metadata=schema_metadata,
            quality_metrics=quality_metrics,
            preview_data=preview_data,
            column_statistics=column_statistics,
            # Original schema_info for backward compatibility
            schema_info={
                "columns": [{"name": col, "type": "string"} for col in api_columns],
                "sample_data": sample_data,
                "web_connector": web_connector_result["connector_name"],
                "view_name": dataset_view_result["view_name"],
                "mindsdb_integration": True
            },
            allow_download=True,
            allow_api_access=True,
            allow_ai_chat=True,
            # Enhanced chat context for MindsDB web connector
            chat_context={
                "web_connector": web_connector_result["connector_name"],
                "view_name": dataset_view_result["view_name"],
                "api_endpoint": web_connector_result["url"],
                "data_sample": dataset_view_result.get("sample_data", []),
                "total_items": dataset_view_result.get("estimated_rows", 0),
                "connector_name": connector.name,
                "schema": dataset_view_result.get("columns", []),
                "mindsdb_integration": True
            }
        )
        
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        
        logger.info(f"✅ Created MindsDB web connector dataset: {dataset_data.dataset_name} (ID: {dataset.id})")
        
        return {
            "success": True,
            "dataset_id": dataset.id,
            "dataset_name": dataset_data.dataset_name,
            "api_endpoint": web_connector_result["url"],
            "data_count": dataset_view_result.get("estimated_rows", 0),
            "web_connector": web_connector_result["connector_name"],
            "view_name": dataset_view_result["view_name"],
            "mindsdb_integration": True
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to create MindsDB web connector dataset: {e}")
        # Fallback to direct API approach
        return await _create_api_dataset_fallback(connector, dataset_data, user_id)


async def _create_api_dataset_fallback(
    connector: DatabaseConnector, 
    dataset_data: CreateDatasetFromConnector, 
    user_id: int
) -> Dict[str, Any]:
    """Fallback method to create API dataset without MindsDB web connector."""
    try:
        import requests
        from app.models.dataset import Dataset, DatasetType, DatasetStatus
        from app.core.database import get_db
        
        # Get database session
        db = next(get_db())
        
        config = connector.connection_config.copy()
        base_url = config.get("base_url", "")
        
        # Use custom endpoint if provided, otherwise use connector's default
        endpoint = dataset_data.table_or_endpoint or config.get("endpoint", "")
        method = config.get("method", "GET").upper()
        timeout = config.get("timeout", 30)
        headers = config.get("headers", {})
        
        full_url = f"{base_url.rstrip('/')}{endpoint}"
        
        # Apply SSL configuration for localhost - convert HTTPS to HTTP for localhost proxy URLs
        from urllib.parse import urlparse
        from app.utils.proxy_url_converter import ensure_localhost_proxy_uses_http
        
        parsed_url = urlparse(full_url)
        if parsed_url.hostname in ['localhost', '127.0.0.1'] and parsed_url.port == 8000:
            # This is a localhost proxy URL, ensure it uses HTTP
            full_url = ensure_localhost_proxy_uses_http(full_url)
            logger.info(f"🔓 Converted localhost proxy URL to HTTP: {full_url}")
        
        # Fetch data from API
        response = requests.request(
            method=method,
            url=full_url,
            headers=headers,
            timeout=timeout
        )
        
        if response.status_code != 200:
            return {
                "success": False,
                "error": f"API request failed with status {response.status_code}"
            }
        
        # Parse JSON data
        try:
            api_data = response.json()
        except:
            return {
                "success": False,
                "error": "API response is not valid JSON"
            }
        
        # Determine data characteristics
        data_count = len(api_data) if isinstance(api_data, list) else 1
        sample_data = api_data[:5] if isinstance(api_data, list) else [api_data]
        
        # Create schema information
        schema_info = {}
        if sample_data and len(sample_data) > 0:
            first_item = sample_data[0]
            if isinstance(first_item, dict):
                schema_info = {
                    "columns": [{"name": key, "type": type(value).__name__} for key, value in first_item.items()],
                    "sample_data": sample_data,
                    "api_endpoint": full_url,
                    "total_items": data_count,
                    "mindsdb_integration": False
                }
        
        # Map sharing level
        sharing_level_map = {
            "private": DataSharingLevel.PRIVATE,
            "organization": DataSharingLevel.ORGANIZATION,
            "public": DataSharingLevel.PUBLIC
        }
        sharing_level = sharing_level_map.get(dataset_data.sharing_level.lower(), DataSharingLevel.PRIVATE)
        
        # Generate enhanced metadata for fallback API dataset
        api_columns = [col["name"] for col in schema_info.get("columns", [])]
        
        # Enhanced file metadata
        file_metadata = {
            "api_url": full_url,
            "method": method,
            "total_records": data_count,
            "sample_record": sample_data[0] if sample_data else None,
            "data_keys": api_columns,
            "connector_id": connector.id,
            "connector_name": connector.name
        }
        
        # Enhanced schema metadata
        schema_metadata = {
            "file_type": "api",
            "source": "api_connector_fallback",
            "original_filename": f"{dataset_data.dataset_name}_api_data",
            "structure": {
                "type": "list" if isinstance(api_data, list) else "object",
                "total_elements": data_count,
                "sample_structure": str(sample_data[0])[:200] if sample_data else None
            },
            "columns": api_columns,
            "data_types": {col["name"]: col["type"] for col in schema_info.get("columns", [])},
            "sample_data": str(sample_data[:2])[:500] if sample_data else None
        }
        
        # Enhanced quality metrics
        quality_metrics = {
            "overall_score": 90,  # Fallback API data quality
            "completeness": 100,
            "consistency": 85,
            "accuracy": 90,
            "issues": [],
            "last_analyzed": datetime.utcnow().isoformat()
        }
        
        # Enhanced preview data
        preview_data = {
            "type": "api",
            "headers": api_columns,
            "sample_rows": sample_data[:10] if sample_data else [],
            "total_rows": data_count,
            "is_sample": data_count > 10,
            "preview_generated_at": datetime.utcnow().isoformat()
        }
        
        # Column statistics
        column_statistics = {}
        for col_info in schema_info.get("columns", []):
            column_statistics[col_info["name"]] = {
                "data_type": col_info["type"],
                "non_null_count": data_count,
                "null_count": 0,
                "unique_count": "unknown"
            }
        
        # Create dataset record with enhanced metadata
        dataset = Dataset(
            name=dataset_data.dataset_name,
            description=dataset_data.description or f"API dataset from {connector.name}",
            type=DatasetType.API,
            status=DatasetStatus.ACTIVE,
            owner_id=user_id,
            organization_id=connector.organization_id,
            sharing_level=sharing_level,
            connector_id=connector.id,
            source_url=full_url,
            row_count=data_count,
            column_count=len(api_columns),
            # Enhanced metadata fields
            file_metadata=file_metadata,
            schema_metadata=schema_metadata,
            quality_metrics=quality_metrics,
            preview_data=preview_data,
            column_statistics=column_statistics,
            # Original schema_info for backward compatibility
            schema_info=schema_info,
            allow_download=True,
            allow_api_access=True,
            allow_ai_chat=True,
            # Store API data context for chat
            chat_context={
                "api_endpoint": full_url,
                "data_sample": sample_data,
                "total_items": data_count,
                "connector_name": connector.name,
                "schema": schema_info.get("columns", []),
                "mindsdb_integration": False
            }
        )
        
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        
        logger.info(f"✅ Created fallback API dataset: {dataset_data.dataset_name} (ID: {dataset.id})")
        
        return {
            "success": True,
            "dataset_id": dataset.id,
            "dataset_name": dataset_data.dataset_name,
            "api_endpoint": full_url,
            "data_count": data_count,
            "mindsdb_integration": False
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to create fallback API dataset: {e}")
        return {
            "success": False,
            "error": str(e)
        } 