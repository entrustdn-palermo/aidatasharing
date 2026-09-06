"""
Unified API Router - Single Port Architecture
All API endpoints routed through a single port with path-based separation
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, File, UploadFile, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from app.core.database import get_db
from app.core.auth import get_current_user, get_optional_user
from app.models.user import User
# from app.services.unified_proxy_service import unified_proxy  # Archived
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

# Create main router
router = APIRouter()

# Sub-routers for different services
files_router = APIRouter(prefix="/files", tags=["files"])
connectors_router = APIRouter(prefix="/connectors", tags=["connectors"])
shared_router = APIRouter(prefix="/shared", tags=["shared"])
proxy_router = APIRouter(prefix="/proxy", tags=["proxy"])


# ============= Request/Response Models =============

class ConnectorCreate(BaseModel):
    name: str
    connector_type: str  # 'api', 'database', 's3'
    description: Optional[str] = None
    connection_config: Dict[str, Any]
    credentials: Dict[str, Any]
    is_public: bool = False
    allowed_operations: Optional[List[str]] = None


class SharedLinkCreate(BaseModel):
    connector_id: int
    name: str
    description: Optional[str] = None
    expires_in_hours: Optional[int] = 24
    max_uses: Optional[int] = None


class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    size: int
    content_type: str
    upload_path: str
    public_url: str


# ============= File Management Endpoints =============

@files_router.post("/upload", response_model=FileUploadResponse, operation_id="upload_file_unified")
async def upload_file(
    file: UploadFile = File(...),
    description: Optional[str] = None,
    is_public: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a file through unified routing"""
    
    storage_service = StorageService()
    
    try:
        # Save file
        file_info = await storage_service.save_uploaded_file(
            file=file,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            description=description,
            is_public=is_public
        )
        
        # Generate public URL using unified routing
        public_url = f"/api/files/{file_info['file_id']}"
        
        return FileUploadResponse(
            file_id=file_info["file_id"],
            filename=file_info["filename"],
            size=file_info["size"],
            content_type=file_info["content_type"],
            upload_path=file_info["path"],
            public_url=public_url
        )
        
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed"
        )


@files_router.get("/{file_id}")
async def get_file(
    file_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user)
):
    """Download or get file info"""
    
    storage_service = StorageService()
    
    try:
        file_info = await storage_service.get_file(
            file_id=file_id,
            user_id=current_user.id if current_user else None
        )
        
        return file_info
        
    except Exception as e:
        logger.error(f"File retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )


@files_router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a file"""
    
    storage_service = StorageService()
    
    try:
        await storage_service.delete_file(
            file_id=file_id,
            user_id=current_user.id
        )
        
        return {"message": "File deleted successfully"}
        
    except Exception as e:
        logger.error(f"File deletion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File deletion failed"
        )


# ============= Connector Management Endpoints =============

@connectors_router.post("/create")
async def create_connector(
    connector_data: ConnectorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new connector with unified routing"""
    
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    try:
        connector = await unified_proxy.create_connector(
            db=db,
            name=connector_data.name,
            connector_type=connector_data.connector_type,
            connection_config=connector_data.connection_config,
            credentials=connector_data.credentials,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            description=connector_data.description,
            is_public=connector_data.is_public,
            allowed_operations=connector_data.allowed_operations
        )
        
        return {
            "connector_id": connector.proxy_id,
            "name": connector.name,
            "type": connector.connector_type,
            "proxy_url": connector.proxy_url,
            "created_at": connector.created_at
        }
        
    except Exception as e:
        logger.error(f"Failed to create connector: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create connector"
        )


@connectors_router.get("/{connector_id}")
async def get_connector_info(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user)
):
    """Get connector information"""
    
    try:
        return unified_proxy.get_connector_info(db, connector_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get connector info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get connector info"
        )


@connectors_router.post("/{connector_id}/{path:path}")
async def execute_connector_request(
    connector_id: str,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
    body: Optional[Dict] = Body(default=None)
):
    """Execute request through connector"""
    
    try:
        # Get request details
        method = request.method
        headers = dict(request.headers)
        params = dict(request.query_params)
        
        # Execute through unified proxy
        result = await unified_proxy.execute_connector_request(
            db=db,
            connector_id=connector_id,
            request_path=path,
            method=method,
            headers=headers,
            params=params,
            data=body,
            user_id=current_user.id if current_user else None,
            client_ip=request.client.host if request.client else None
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connector request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Connector request failed"
        )


# Also support GET, PUT, DELETE methods
@connectors_router.get("/{connector_id}/{path:path}")
async def get_connector_data(
    connector_id: str,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user)
):
    """GET request through connector"""
    return await execute_connector_request(
        connector_id, path, request, db, current_user, None
    )


# ============= Shared Link Endpoints =============

@shared_router.post("/create")
async def create_shared_link(
    link_data: SharedLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a shared link for public access"""
    
    try:
        shared_link = await unified_proxy.create_shared_link(
            db=db,
            connector_id=link_data.connector_id,
            name=link_data.name,
            user_id=current_user.id,
            description=link_data.description,
            expires_in_hours=link_data.expires_in_hours,
            max_uses=link_data.max_uses,
            request_headers=dict(request.headers),
            request_host=request.client.host if request.client else None
        )
        
        return shared_link
        
    except Exception as e:
        logger.error(f"Failed to create shared link: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create shared link"
        )


@shared_router.get("/{share_id}")
async def access_shared_link(
    share_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Access a shared connector without authentication"""
    
    try:
        # Execute through unified proxy
        result = await unified_proxy.execute_connector_request(
            db=db,
            connector_id=share_id,  # Share ID is treated as connector ID
            request_path="",
            method="GET",
            headers=dict(request.headers),
            params=dict(request.query_params),
            data=None,
            user_id=None,  # No authentication required
            client_ip=request.client.host if request.client else None
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Shared link access failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shared link access failed"
        )


@shared_router.post("/{share_id}/{path:path}")
async def shared_link_request(
    share_id: str,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
    body: Optional[Dict] = Body(default=None)
):
    """Execute request through shared link"""
    
    try:
        result = await unified_proxy.execute_connector_request(
            db=db,
            connector_id=share_id,
            request_path=path,
            method=request.method,
            headers=dict(request.headers),
            params=dict(request.query_params),
            data=body,
            user_id=None,
            client_ip=request.client.host if request.client else None
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Shared link request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shared link request failed"
        )


# ============= Health Check =============

@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "service": "unified-api",
        "endpoints": {
            "files": "/api/files",
            "connectors": "/api/connectors",
            "shared": "/api/shared",
            "proxy": "/api/proxy"
        }
    }


# Include all sub-routers
router.include_router(files_router)
router.include_router(connectors_router)
router.include_router(shared_router)
router.include_router(proxy_router)