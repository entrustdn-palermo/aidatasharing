"""
Unified Proxy Service - Single Port Architecture
Handles all proxy operations through path-based routing on a single port
"""

import json
import secrets
import hashlib
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Request
import httpx
import asyncio
import logging
import os

from app.models.proxy_connector import ProxyConnector, SharedProxyLink, ProxyAccessLog
from app.models.user import User
from app.core.database import get_db

logger = logging.getLogger(__name__)


class UnifiedProxyService:
    """
    Unified Proxy Service that handles all operations through a single port
    Uses path-based routing to distinguish between different types of operations
    """
    
    def __init__(self):
        self.encryption_key = self._get_or_create_encryption_key()
        self.fernet = Fernet(self.encryption_key)
        
        # Dynamic base URL detection - will be set per request if not configured
        self.base_url = os.getenv("API_BASE_URL", None)  # None means auto-detect
        self.is_production = os.getenv("ENVIRONMENT", "development") == "production"
        
        # SSL configuration
        self.ssl_config = self._get_ssl_configuration()
        
        # Rate limiting configuration
        self.rate_limits = {
            "requests_per_minute": 60,
            "requests_per_hour": 1000,
            "max_response_size": 10 * 1024 * 1024  # 10MB
        }
        
        # Path prefixes for different services
        self.path_prefixes = {
            "files": "/api/files",
            "connectors": "/api/connectors",
            "proxy": "/api/proxy",
            "shared": "/api/shared",
            "datasets": "/api/datasets"
        }
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for credential storage"""
        # Use relative path for local development, absolute for production
        if os.getenv("ENVIRONMENT") == "production":
            key_file = os.getenv("ENCRYPTION_KEY_FILE", "/tmp/encryption.key")
        else:
            key_file = os.getenv("ENCRYPTION_KEY_FILE", "../storage/encryption.key")

        # Ensure directory exists (only if not /tmp)
        key_dir = os.path.dirname(key_file)
        if key_dir and key_dir != '/tmp':
            os.makedirs(key_dir, exist_ok=True)

        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            try:
                with open(key_file, "wb") as f:
                    f.write(key)
            except (OSError, PermissionError):
                # If can't write, just use in-memory key
                logger.warning(f"Could not write encryption key to {key_file}, using in-memory key")
            return key
    
    def _get_ssl_configuration(self) -> Dict[str, Any]:
        """Configure SSL settings based on environment"""
        return {
            "require_ssl": os.getenv("REQUIRE_SSL", "auto").lower(),  # auto, true, false
            "ssl_redirect": os.getenv("SSL_REDIRECT", "auto").lower(),  # auto, true, false
            "force_https_urls": os.getenv("FORCE_HTTPS_URLS", "auto").lower(),  # auto, true, false
        }
    
    def _detect_base_url(self, request_headers: Dict[str, str], request_host: Optional[str] = None) -> str:
        """Dynamically detect base URL from request context"""
        
        # If explicitly configured, use that
        if self.base_url:
            return self.base_url
        
        # Auto-detect from request headers
        host = request_headers.get("host") or request_host or "localhost:8000"
        
        # Determine protocol
        protocol = self._determine_protocol(request_headers, host)
        
        return f"{protocol}://{host}"
    
    def _determine_protocol(self, headers: Dict[str, str], host: str) -> str:
        """Determine HTTP or HTTPS based on environment and request"""
        
        # Check for explicit SSL configuration
        if self.ssl_config["require_ssl"] == "true":
            return "https"
        elif self.ssl_config["require_ssl"] == "false":
            return "http"
        
        # Auto-detection logic
        # Check X-Forwarded-Proto header (from reverse proxy/load balancer)
        forwarded_proto = headers.get("x-forwarded-proto", "").lower()
        if forwarded_proto in ["https", "http"]:
            return forwarded_proto
        
        # Check if request came through HTTPS
        if headers.get("x-forwarded-ssl") == "on":
            return "https"
        
        # Check for development/localhost
        if "localhost" in host or "127.0.0.1" in host or host.startswith("192.168."):
            return "http"  # Default to HTTP for local development
        
        # Production environments - prefer HTTPS
        if self.is_production:
            return "https"
        
        # Default fallback
        return "http"
    
    def _is_ssl_required(self, host: str) -> bool:
        """Check if SSL is required for the given host"""
        
        # Explicit configuration
        if self.ssl_config["require_ssl"] == "true":
            return True
        elif self.ssl_config["require_ssl"] == "false":
            return False
        
        # Auto-detection
        # Never require SSL for localhost/development
        if any(dev_host in host.lower() for dev_host in ["localhost", "127.0.0.1", "192.168."]):
            return False
        
        # Require SSL in production
        if self.is_production:
            return True
        
        return False
    
    def encrypt_credentials(self, credentials: Dict[str, Any]) -> str:
        """Encrypt credentials for secure storage"""
        json_data = json.dumps(credentials)
        encrypted_data = self.fernet.encrypt(json_data.encode())
        return encrypted_data.decode()
    
    def decrypt_credentials(self, encrypted_credentials: str) -> Dict[str, Any]:
        """Decrypt credentials for use"""
        try:
            decrypted_data = self.fernet.decrypt(encrypted_credentials.encode())
            return json.loads(decrypted_data.decode())
        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decrypt credentials"
            )
    
    async def create_connector(
        self,
        db: Session,
        name: str,
        connector_type: str,
        connection_config: Dict[str, Any],
        credentials: Dict[str, Any],
        organization_id: int,
        user_id: int,
        description: Optional[str] = None,
        is_public: bool = False,
        allowed_operations: Optional[List[str]] = None
    ) -> ProxyConnector:
        """Create a new connector with unified routing"""
        
        # Generate unique connector ID
        connector_id = str(secrets.token_urlsafe(16))
        
        # Create unified proxy URL using path-based routing
        proxy_url = f"{self.path_prefixes['connectors']}/{connector_id}"
        
        # Add metadata for routing
        enhanced_config = {
            **connection_config,
            "_connector_type": connector_type,
            "_created_at": datetime.utcnow().isoformat(),
            "_routing_path": proxy_url
        }
        
        # Encrypt sensitive data
        encrypted_config = self.encrypt_credentials(enhanced_config)
        encrypted_credentials = self.encrypt_credentials(credentials)
        
        # Create connector record
        connector = ProxyConnector(
            proxy_id=connector_id,
            name=name,
            description=description,
            connector_type=connector_type,
            proxy_url=proxy_url,
            real_connection_config=encrypted_config,
            real_credentials=encrypted_credentials,
            is_public=is_public,
            allowed_operations=allowed_operations or ["GET", "POST"],
            organization_id=organization_id,
            created_by=user_id
        )
        
        db.add(connector)
        db.commit()
        db.refresh(connector)
        
        logger.info(f"Created unified connector {connector.id} with path {proxy_url}")
        return connector
    
    async def create_shared_link(
        self,
        db: Session,
        connector_id: int,
        name: str,
        user_id: int,
        description: Optional[str] = None,
        expires_in_hours: Optional[int] = 24,
        max_uses: Optional[int] = None,
        allowed_endpoints: Optional[List[str]] = None,
        request_headers: Optional[Dict[str, str]] = None,
        request_host: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a shared link for public access"""
        
        # Get connector
        connector = db.query(ProxyConnector).filter(
            ProxyConnector.id == connector_id,
            ProxyConnector.is_active == True
        ).first()
        
        if not connector:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connector not found"
            )
        
        # Generate share ID
        share_id = str(secrets.token_urlsafe(24))
        
        # Create unified public URL
        public_url = f"{self.path_prefixes['shared']}/{share_id}"
        
        # Calculate expiration
        expires_at = None
        if expires_in_hours:
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
        
        # Create shared link
        shared_link = SharedProxyLink(
            share_id=share_id,
            proxy_connector_id=connector_id,
            name=name,
            description=description,
            public_url=public_url,
            is_public=True,
            requires_authentication=False,
            allowed_users=[],
            expires_at=expires_at,
            max_uses=max_uses,
            created_by=user_id
        )
        
        db.add(shared_link)
        db.commit()
        db.refresh(shared_link)
        
        # Generate access information with dynamic URL detection
        detected_base_url = self._detect_base_url(
            request_headers or {}, 
            request_host
        )
        full_url = f"{detected_base_url}{public_url}"
        
        return {
            "share_id": share_id,
            "public_url": public_url,
            "full_url": full_url,
            "expires_at": expires_at,
            "max_uses": max_uses,
            "connector_info": {
                "name": connector.name,
                "type": connector.connector_type,
                "allowed_operations": connector.allowed_operations
            },
            "usage_examples": self._generate_usage_examples(full_url, connector.connector_type)
        }
    
    def _generate_usage_examples(self, base_url: str, connector_type: str) -> Dict[str, str]:
        """Generate usage examples for different connector types"""
        
        if connector_type == "api":
            return {
                "get_data": f'curl "{base_url}/data"',
                "post_data": f'curl -X POST "{base_url}/data" -H "Content-Type: application/json" -d \'{{"key": "value"}}\'',
                "custom_endpoint": f'curl "{base_url}/custom/endpoint"'
            }
        elif connector_type == "database":
            return {
                "query": f'curl -X POST "{base_url}/query" -H "Content-Type: application/json" -d \'{{"query": "SELECT * FROM users LIMIT 10"}}\''
            }
        elif connector_type == "s3":
            return {
                "list_files": f'curl "{base_url}/files"',
                "download_file": f'curl "{base_url}/files/filename.csv"'
            }
        else:
            return {
                "access": f'curl "{base_url}"'
            }
    
    async def execute_connector_request(
        self,
        db: Session,
        connector_id: str,
        request_path: str,
        method: str,
        headers: Dict[str, str],
        params: Dict[str, Any],
        data: Optional[Any] = None,
        user_id: Optional[int] = None,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute request through connector using unified routing"""
        
        # Get connector by ID
        connector = db.query(ProxyConnector).filter(
            ProxyConnector.proxy_id == connector_id,
            ProxyConnector.is_active == True
        ).first()
        
        if not connector:
            # Try to find by share ID
            shared_link = db.query(SharedProxyLink).filter(
                SharedProxyLink.share_id == connector_id,
                SharedProxyLink.is_active == True
            ).first()
            
            if shared_link:
                connector = shared_link.proxy_connector
                # Validate shared link access
                await self._validate_shared_access(shared_link)
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Connector not found"
                )
        
        # Check allowed operations
        if method.upper() not in connector.allowed_operations:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail=f"Method {method} not allowed"
            )
        
        # Decrypt credentials
        config = self.decrypt_credentials(connector.real_connection_config)
        credentials = self.decrypt_credentials(connector.real_credentials)
        
        # Execute based on connector type
        start_time = datetime.utcnow()
        try:
            if connector.connector_type == "api":
                result = await self._execute_api_request(
                    config, credentials, method, request_path, headers, params, data
                )
            elif connector.connector_type == "database":
                result = await self._execute_database_query(
                    config, credentials, data
                )
            elif connector.connector_type == "s3":
                result = await self._execute_s3_operation(
                    config, credentials, request_path, method
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported connector type: {connector.connector_type}"
                )
            
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Log access
            await self._log_access(
                db, connector.id, user_id, client_ip,
                method, request_path, 200, execution_time
            )
            
            # Update statistics
            connector.total_requests += 1
            connector.last_accessed_at = datetime.utcnow()
            db.commit()
            
            return result
            
        except Exception as e:
            logger.error(f"Connector request failed: {e}")
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Log failed access
            await self._log_access(
                db, connector.id, user_id, client_ip,
                method, request_path, 500, execution_time
            )
            
            raise
    
    async def _validate_shared_access(self, shared_link: SharedProxyLink):
        """Validate access to a shared link"""
        
        # Check expiration
        if shared_link.expires_at and shared_link.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Shared link has expired"
            )
        
        # Check usage limits
        if shared_link.max_uses and shared_link.current_uses >= shared_link.max_uses:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usage limit exceeded"
            )
        
        # Increment usage
        shared_link.current_uses += 1
    
    async def _execute_api_request(
        self,
        config: Dict[str, Any],
        credentials: Dict[str, Any],
        method: str,
        path: str,
        headers: Dict[str, str],
        params: Dict[str, Any],
        data: Optional[Any]
    ) -> Dict[str, Any]:
        """Execute API request"""
        
        base_url = config.get("base_url")
        if not base_url:
            raise ValueError("API configuration missing base_url")
        
        # Build full URL
        full_url = f"{base_url.rstrip('/')}/{path.lstrip('/')}" if path else base_url
        
        # Prepare headers with authentication
        request_headers = headers.copy()
        
        # Add API key authentication
        if credentials.get("api_key"):
            auth_header = credentials.get("auth_header", "Authorization")
            auth_prefix = credentials.get("auth_prefix", "Bearer")
            request_headers[auth_header] = f"{auth_prefix} {credentials['api_key']}"
        
        # Add basic authentication
        elif credentials.get("username") and credentials.get("password"):
            import base64
            auth_string = f"{credentials['username']}:{credentials['password']}"
            encoded = base64.b64encode(auth_string.encode()).decode()
            request_headers["Authorization"] = f"Basic {encoded}"
        
        # Execute request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method.upper(),
                url=full_url,
                headers=request_headers,
                params=params,
                json=data if method.upper() in ["POST", "PUT", "PATCH"] else None
            )
            
            # Parse response
            content_type = response.headers.get("content-type", "").lower()
            
            if "application/json" in content_type:
                response_data = response.json()
            elif "text/" in content_type:
                response_data = response.text
            else:
                response_data = f"<binary: {len(response.content)} bytes>"
            
            return {
                "status_code": response.status_code,
                "data": response_data,
                "headers": dict(response.headers),
                "success": response.is_success
            }
    
    async def _execute_database_query(
        self,
        config: Dict[str, Any],
        credentials: Dict[str, Any],
        query_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute database query"""
        
        query = query_data.get("query") if isinstance(query_data, dict) else str(query_data)
        
        if not query:
            raise ValueError("No query provided")
        
        # For now, return a placeholder
        # In production, integrate with actual database connection
        return {
            "status": "success",
            "query": query,
            "message": "Database query execution would happen here",
            "rows_affected": 0
        }
    
    async def _execute_s3_operation(
        self,
        config: Dict[str, Any],
        credentials: Dict[str, Any],
        path: str,
        method: str
    ) -> Dict[str, Any]:
        """Execute S3 operation"""
        
        # For now, return a placeholder
        # In production, integrate with boto3 for S3 operations
        return {
            "status": "success",
            "operation": method,
            "path": path,
            "message": "S3 operation would happen here"
        }
    
    async def _log_access(
        self,
        db: Session,
        connector_id: int,
        user_id: Optional[int],
        client_ip: Optional[str],
        method: str,
        path: str,
        status_code: int,
        execution_time_ms: int
    ):
        """Log access for auditing"""
        
        access_log = ProxyAccessLog(
            proxy_connector_id=connector_id,
            user_id=user_id,
            user_ip=client_ip,
            user_agent="",
            operation_type=f"{method.lower()}_{path}",
            operation_details={
                "method": method,
                "path": path,
                "unified_routing": True
            },
            status_code=status_code,
            execution_time_ms=execution_time_ms
        )
        
        db.add(access_log)
        db.commit()
    
    def get_connector_info(self, db: Session, connector_id: str) -> Dict[str, Any]:
        """Get connector information without exposing credentials"""
        
        connector = db.query(ProxyConnector).filter(
            ProxyConnector.proxy_id == connector_id,
            ProxyConnector.is_active == True
        ).first()
        
        if not connector:
            shared_link = db.query(SharedProxyLink).filter(
                SharedProxyLink.share_id == connector_id,
                SharedProxyLink.is_active == True
            ).first()
            
            if shared_link:
                connector = shared_link.proxy_connector
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Connector not found"
                )
        
        return {
            "id": connector.proxy_id,
            "name": connector.name,
            "description": connector.description,
            "type": connector.connector_type,
            "allowed_operations": connector.allowed_operations,
            "total_requests": connector.total_requests,
            "last_accessed": connector.last_accessed_at,
            "created_at": connector.created_at,
            "is_public": connector.is_public,
            "proxy_url": f"{self.base_url}{connector.proxy_url}"
        }


# Singleton instance
unified_proxy = UnifiedProxyService()