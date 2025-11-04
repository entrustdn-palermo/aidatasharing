"""
Secure Proxy API endpoints for managing proxy connectors and shared links
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime
import logging

from app.core.database import get_db
from app.core.auth import get_current_user, get_optional_user
from app.models.user import User
from app.models.proxy_connector import ProxyConnector, SharedProxyLink, ProxyAccessLog
from app.services.proxy_service import ProxyService
# from app.services.integrated_proxy_service import integrated_proxy  # Archived
from app.utils.proxy_url_converter import get_corrected_proxy_url, convert_proxy_urls_in_response

logger = logging.getLogger(__name__)

router = APIRouter()
proxy_service = ProxyService()


# Pydantic models for API
class ProxyConnectorCreate(BaseModel):
    name: str
    connector_type: str  # 'api', 'database', 'shared_link'
    description: Optional[str] = None
    real_connection_config: Dict[str, Any]
    real_credentials: Dict[str, Any]
    is_public: bool = False
    allowed_operations: Optional[List[str]] = None


class ProxyConnectorResponse(BaseModel):
    id: int
    proxy_id: str
    name: str
    description: Optional[str]
    connector_type: str
    proxy_url: str
    is_public: bool
    allowed_operations: List[str]
    total_requests: int
    created_at: datetime
    last_accessed_at: Optional[datetime]


class SharedLinkCreate(BaseModel):
    proxy_connector_id: int
    name: str
    description: Optional[str] = None
    is_public: bool = False
    requires_authentication: bool = True
    allowed_users: Optional[List[str]] = None
    max_uses: Optional[int] = None


class SharedLinkResponse(BaseModel):
    id: int
    share_id: str
    name: str
    description: Optional[str]
    public_url: str
    is_public: bool
    requires_authentication: bool
    # Expiration functionality removed
    max_uses: Optional[int]
    current_uses: int
    created_at: datetime


class ProxyOperationRequest(BaseModel):
    operation_type: str
    operation_data: Dict[str, Any]


class ProxyOperationResponse(BaseModel):
    status: str
    data: Any
    execution_time_ms: Optional[int] = None


# Proxy Connector Management Endpoints

@router.post("/proxy-connectors", response_model=ProxyConnectorResponse)
async def create_proxy_connector(
    connector_data: ProxyConnectorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new proxy connector that hides real connection details"""
    
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    try:
        proxy_connector = await proxy_service.create_proxy_connector(
            db=db,
            name=connector_data.name,
            connector_type=connector_data.connector_type,
            real_connection_config=connector_data.real_connection_config,
            real_credentials=connector_data.real_credentials,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            description=connector_data.description,
            is_public=connector_data.is_public,
            allowed_operations=connector_data.allowed_operations
        )
        
        return ProxyConnectorResponse(
            id=proxy_connector.id,
            proxy_id=proxy_connector.proxy_id,
            name=proxy_connector.name,
            description=proxy_connector.description,
            connector_type=proxy_connector.connector_type,
            proxy_url=get_corrected_proxy_url(proxy_connector),
            is_public=proxy_connector.is_public,
            allowed_operations=proxy_connector.allowed_operations or [],
            total_requests=proxy_connector.total_requests,
            created_at=proxy_connector.created_at,
            last_accessed_at=proxy_connector.last_accessed_at
        )
        
    except Exception as e:
        logger.error(f"Failed to create proxy connector: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create proxy connector"
        )


@router.get("/proxy-connectors", response_model=List[ProxyConnectorResponse])
async def get_proxy_connectors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all proxy connectors for the user's organization"""
    
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    connectors = db.query(ProxyConnector).filter(
        ProxyConnector.organization_id == current_user.organization_id,
        ProxyConnector.is_active == True
    ).all()
    
    return [
        ProxyConnectorResponse(
            id=connector.id,
            proxy_id=connector.proxy_id,
            name=connector.name,
            description=connector.description,
            connector_type=connector.connector_type,
            proxy_url=get_corrected_proxy_url(connector),
            is_public=connector.is_public,
            allowed_operations=connector.allowed_operations or [],
            total_requests=connector.total_requests,
            created_at=connector.created_at,
            last_accessed_at=connector.last_accessed_at
        )
        for connector in connectors
    ]


@router.get("/proxy-connectors/{proxy_connector_id}", response_model=ProxyConnectorResponse)
async def get_proxy_connector(
    proxy_connector_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific proxy connector"""
    
    connector = db.query(ProxyConnector).filter(
        ProxyConnector.id == proxy_connector_id,
        ProxyConnector.organization_id == current_user.organization_id,
        ProxyConnector.is_active == True
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy connector not found"
        )
    
    return ProxyConnectorResponse(
        id=connector.id,
        proxy_id=connector.proxy_id,
        name=connector.name,
        description=connector.description,
        connector_type=connector.connector_type,
        proxy_url=get_corrected_proxy_url(connector),
        is_public=connector.is_public,
        allowed_operations=connector.allowed_operations or [],
        total_requests=connector.total_requests,
        created_at=connector.created_at,
        last_accessed_at=connector.last_accessed_at
    )


@router.delete("/proxy-connectors/{proxy_connector_id}")
async def delete_proxy_connector(
    proxy_connector_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a proxy connector"""
    
    connector = db.query(ProxyConnector).filter(
        ProxyConnector.id == proxy_connector_id,
        ProxyConnector.organization_id == current_user.organization_id,
        ProxyConnector.is_active == True
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy connector not found"
        )
    
    connector.is_active = False
    db.commit()
    
    return {"message": "Proxy connector deleted successfully"}


# Shared Link Management Endpoints

@router.post("/shared-links", response_model=SharedLinkResponse)
async def create_shared_link(
    link_data: SharedLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a shared link for secure access to a proxy connector"""
    
    try:
        shared_link = await proxy_service.create_shared_link(
            db=db,
            proxy_connector_id=link_data.proxy_connector_id,
            name=link_data.name,
            user_id=current_user.id,
            description=link_data.description,
            is_public=link_data.is_public,
            requires_authentication=link_data.requires_authentication,
            allowed_users=link_data.allowed_users,
            max_uses=link_data.max_uses
        )
        
        return SharedLinkResponse(
            id=shared_link.id,
            share_id=shared_link.share_id,
            name=shared_link.name,
            description=shared_link.description,
            public_url=shared_link.public_url,
            is_public=shared_link.is_public,
            requires_authentication=shared_link.requires_authentication,
            # Expiration functionality removed
            max_uses=shared_link.max_uses,
            current_uses=shared_link.current_uses,
            created_at=shared_link.created_at
        )
        
    except Exception as e:
        logger.error(f"Failed to create shared link: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create shared link"
        )


@router.get("/shared-links", response_model=List[SharedLinkResponse])
async def get_shared_links(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all shared links created by the user"""
    
    links = db.query(SharedProxyLink).filter(
        SharedProxyLink.created_by == current_user.id,
        SharedProxyLink.is_active == True
    ).all()
    
    return [
        SharedLinkResponse(
            id=link.id,
            share_id=link.share_id,
            name=link.name,
            description=link.description,
            public_url=link.public_url,
            is_public=link.is_public,
            requires_authentication=link.requires_authentication,
            # Expiration functionality removed
            max_uses=link.max_uses,
            current_uses=link.current_uses,
            created_at=link.created_at
        )
        for link in links
    ]


# Proxy Operation Endpoints

@router.post("/proxy/{proxy_id}/execute", response_model=ProxyOperationResponse)
async def execute_proxy_operation(
    proxy_id: str,
    operation: ProxyOperationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user)
):
    """Execute an operation through a proxy connector"""
    
    try:
        result = await proxy_service.execute_proxy_operation(
            db=db,
            proxy_id=proxy_id,
            operation_type=operation.operation_type,
            operation_data=operation.operation_data,
            user_id=current_user.id if current_user else None,
            user_ip=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        
        return ProxyOperationResponse(
            status="success" if "error" not in result else "error",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Proxy operation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Proxy operation failed"
        )


@router.get("/share/{share_id}")
async def access_shared_link(
    share_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user)
):
    """Access a shared link through the proxy"""
    
    try:
        # Validate shared link access
        shared_link = await proxy_service.validate_shared_link_access(
            db=db,
            share_id=share_id,
            user_id=current_user.id if current_user else None,
            user_email=current_user.email if current_user else None
        )
        
        # Increment usage count
        shared_link.current_uses += 1
        db.commit()
        
        # Execute default operation for the shared link
        result = await proxy_service.execute_proxy_operation(
            db=db,
            proxy_id=shared_link.proxy_connector.proxy_id,
            operation_type="access",
            operation_data={"source": "shared_link"},
            user_id=current_user.id if current_user else None,
            user_ip=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        
        return {
            "shared_link": {
                "name": shared_link.name,
                "description": shared_link.description
            },
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Shared link access failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shared link access failed"
        )


# Analytics and Monitoring Endpoints

@router.get("/proxy-connectors/{proxy_connector_id}/analytics")
async def get_proxy_analytics(
    proxy_connector_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get analytics for a proxy connector"""
    
    connector = db.query(ProxyConnector).filter(
        ProxyConnector.id == proxy_connector_id,
        ProxyConnector.organization_id == current_user.organization_id,
        ProxyConnector.is_active == True
    ).first()
    
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy connector not found"
        )
    
    # Get access logs for analytics
    logs = db.query(ProxyAccessLog).filter(
        ProxyAccessLog.proxy_connector_id == proxy_connector_id
    ).order_by(ProxyAccessLog.accessed_at.desc()).limit(100).all()
    
    return {
        "connector": {
            "name": connector.name,
            "total_requests": connector.total_requests,
            "last_accessed_at": connector.last_accessed_at
        },
        "recent_access": [
            {
                "accessed_at": log.accessed_at,
                "operation_type": log.operation_type,
                "status_code": log.status_code,
                "execution_time_ms": log.execution_time_ms,
                "user_ip": log.user_ip
            }
            for log in logs
        ]
    }