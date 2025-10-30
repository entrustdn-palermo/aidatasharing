"""
Integrated Proxy Service for AI Share Platform
Runs proxy services within the main backend process using background tasks
"""

import asyncio
import logging
import json
import urllib.parse
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import HTTPException, Request, Response, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import or_
import mysql.connector
import psycopg2
import pymongo
from clickhouse_driver import Client as ClickHouseClient

from app.core.database import get_db
from app.models.proxy_connector import ProxyConnector, SharedProxyLink
from app.services.proxy_service import ProxyService
from app.core.app_config import get_app_config

logger = logging.getLogger(__name__)

class IntegratedProxyService:
    """Integrated proxy service that runs within the main backend"""
    
    def __init__(self):
        self.proxy_service = ProxyService()
        self.app_config = get_app_config()
        # Use unified proxy approach - no separate ports needed
        self.proxy_enabled = self.app_config.proxy.PROXY_ENABLED
        
        # Store running proxy tasks
        self.proxy_tasks = {}
        self.proxy_running = False
        
    async def start_proxy_service(self, background_tasks: BackgroundTasks):
        """Start proxy service as background task"""
        if not self.proxy_enabled:
            logger.info("Proxy service is disabled")
            return
            
        if self.proxy_running:
            logger.info("Proxy service is already running")
            return
            
        logger.info("🚀 Starting Integrated Proxy Service...")
        
        # Start proxy service in background
        background_tasks.add_task(self._run_proxy_service)
        self.proxy_running = True
        
        logger.info("✅ Integrated Proxy Service started")
        
    async def _run_proxy_service(self):
        """Run proxy service in the background"""
        try:
            while self.proxy_running:
                # Keep proxy service alive
                await asyncio.sleep(10)
                
        except Exception as e:
            logger.error(f"Proxy service error: {e}")
        finally:
            self.proxy_running = False
            
    async def stop_proxy_service(self):
        """Stop proxy service"""
        logger.info("Stopping Integrated Proxy Service...")
        self.proxy_running = False
        
        # Cancel all proxy tasks
        for task in self.proxy_tasks.values():
            if not task.done():
                task.cancel()
                
        self.proxy_tasks.clear()
        logger.info("✅ Integrated Proxy Service stopped")
        
    async def handle_proxy_request(
        self,
        proxy_type: str,
        database_name: str,
        request: Request,
        db: Session,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Handle proxy request for specific database type"""
        
        if not self.proxy_enabled:
            raise HTTPException(status_code=503, detail="Proxy service is disabled")
            
        # Get token from query params or headers
        if not token:
            token = request.query_params.get("token")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        
        if not token:
            raise HTTPException(status_code=401, detail="Token required")
        
        # Use database name directly (FastAPI already decodes path parameters)
        decoded_db_name = database_name
        
        try:
            from urllib.parse import quote
            
            # Find proxy connector by database name and type
            # Try both original name and URL-encoded variants to handle different naming conventions
            proxy_connector = db.query(ProxyConnector).filter(
                or_(
                    ProxyConnector.name == decoded_db_name,
                    ProxyConnector.name == quote(decoded_db_name, safe=''),
                    ProxyConnector.name == urllib.parse.unquote(decoded_db_name)
                ),
                ProxyConnector.connector_type.in_(["database", "api"]),
                ProxyConnector.is_active == True
            ).first()
            
            if proxy_connector:
                logger.info(f"Found proxy connector: {proxy_connector.name} (ID: {proxy_connector.id}, Type: {proxy_connector.connector_type})")
            else:
                logger.error(f"No proxy connector found for '{decoded_db_name}'")
            
            if not proxy_connector:
                # Try case-insensitive search
                proxy_connector = db.query(ProxyConnector).filter(
                    ProxyConnector.name.ilike(f"%{decoded_db_name}%"),
                    ProxyConnector.connector_type.in_(["database", "api"]),
                    ProxyConnector.is_active == True
                ).first()
            
            if not proxy_connector:
                # Try to find by share token
                shared_link = db.query(SharedProxyLink).filter(
                    SharedProxyLink.share_id == token,
                    SharedProxyLink.is_active == True
                ).first()
                
                if shared_link:
                    proxy_connector = shared_link.proxy_connector
                else:
                    # Log available connectors for debugging
                    available_connectors = db.query(ProxyConnector).filter(
                        ProxyConnector.is_active == True
                    ).all()
                    connector_names = [c.name for c in available_connectors]
                    logger.error(f"API '{decoded_db_name}' not found. Available connectors: {connector_names}")
                    raise HTTPException(status_code=404, detail=f"API '{decoded_db_name}' not found. Available: {connector_names}")
            
            # Prepare operation data based on request
            if request.method == "GET":
                operation_data = {
                    "query": request.query_params.get("query", "SELECT 1"),
                    "operation": "select",
                    "method": "GET",
                    "params": dict(request.query_params)
                }
                # Only add endpoint if explicitly provided in query params
                if "endpoint" in request.query_params:
                    operation_data["endpoint"] = request.query_params.get("endpoint")
            else:
                try:
                    body = await request.json()
                    operation_data = body
                except:
                    operation_data = {
                        "query": "SELECT 1",
                        "operation": "select"
                    }
            
            # Route to appropriate handler based on proxy type and connector type
            if proxy_connector.connector_type == "api" or proxy_type == "api":
                result = await self._handle_api_proxy(proxy_connector, request, operation_data, db)
            elif proxy_type == "mysql":
                result = await self._handle_mysql_proxy(proxy_connector, operation_data, db)
            elif proxy_type == "postgresql":
                result = await self._handle_postgresql_proxy(proxy_connector, operation_data, db)
            elif proxy_type == "clickhouse":
                result = await self._handle_clickhouse_proxy(proxy_connector, operation_data, db)
            elif proxy_type == "mongodb":
                result = await self._handle_mongodb_proxy(proxy_connector, operation_data, db)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported proxy type: {proxy_type}")
            
            return result
            
        except Exception as e:
            logger.error(f"Proxy operation failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def handle_share_access(
        self,
        share_id: str,
        request: Request,
        db: Session
    ) -> Dict[str, Any]:
        """Handle shared link access"""
        
        try:
            shared_link = db.query(SharedProxyLink).filter(
                SharedProxyLink.share_id == share_id,
                SharedProxyLink.is_active == True
            ).first()
            
            if not shared_link:
                raise HTTPException(status_code=404, detail="Shared link not found")
            
            # Check expiration
            if shared_link.expires_at and shared_link.expires_at < datetime.utcnow():
                raise HTTPException(status_code=403, detail="Shared link expired")
            
            # Increment usage
            shared_link.current_uses += 1
            db.commit()
            
            proxy_connector = shared_link.proxy_connector
            
            # Prepare operation data
            if request.method == "GET":
                operation_data = {
                    "method": "GET",
                    "endpoint": request.query_params.get("endpoint", "/"),
                    "params": dict(request.query_params),
                    "query": request.query_params.get("query", "SELECT 1")
                }
            else:
                try:
                    body = await request.json()
                    operation_data = body
                except:
                    operation_data = {"query": "SELECT 1"}
            
            # Execute based on connector type
            if proxy_connector.connector_type == "api":
                result = await self._handle_api_proxy(proxy_connector, request, operation_data, db)
            else:
                # Default to database query
                result = await self._handle_mysql_proxy(proxy_connector, operation_data, db)
            
            return {
                "message": "Shared link accessed successfully",
                "database_name": proxy_connector.name,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Shared link access failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _handle_api_proxy(self, proxy_connector: ProxyConnector, request: Request, operation_data: Dict, db: Session) -> Dict:
        """Handle API proxy operations"""
        
        try:
            # Get connection configuration
            if isinstance(proxy_connector.real_connection_config, str):
                connection_config = json.loads(proxy_connector.real_connection_config)
            else:
                connection_config = proxy_connector.real_connection_config
            
            # Get the external API URL
            external_url = connection_config.get('base_url') or connection_config.get('url')
            if not external_url:
                raise HTTPException(status_code=400, detail="API URL not configured")
            
            # Prepare headers
            headers = {
                'User-Agent': 'AI-Share-Platform/1.0',
                'Accept': 'application/json'
            }
            
            # Add authentication if available
            if proxy_connector.real_credentials:
                if isinstance(proxy_connector.real_credentials, str):
                    credentials = json.loads(proxy_connector.real_credentials)
                else:
                    credentials = proxy_connector.real_credentials
                    
                api_key = credentials.get('api_key')
                if api_key:
                    auth_header = credentials.get('auth_header', 'Authorization')
                    auth_prefix = credentials.get('auth_prefix', 'Bearer ')
                    headers[auth_header] = f"{auth_prefix}{api_key}"
            
            # Build endpoint URL
            # Use endpoint from connector config as default, allow request to override
            default_endpoint = connection_config.get('endpoint', '/')
            
            # Auto-detect endpoint if not provided or is root
            if default_endpoint == '/' or not default_endpoint:
                # First, try to get from the stored dataset_endpoint
                dataset_endpoint = connection_config.get('dataset_endpoint', '')
                if dataset_endpoint and dataset_endpoint != '/':
                    default_endpoint = dataset_endpoint
                    logger.info(f"Using stored dataset endpoint: {default_endpoint}")
                
                # If no dataset_endpoint, try to extract from source_url
                elif connection_config.get('source_url'):
                    source_url = connection_config.get('source_url', '')
                    if source_url and source_url.count('/') > 2:
                        # Extract path from URL (e.g., https://api.example.com/comments -> /comments)
                        url_parts = source_url.split('/', 3)
                        if len(url_parts) > 3:
                            default_endpoint = '/' + url_parts[3]
                            logger.info(f"Auto-detected endpoint from source_url: {default_endpoint}")
            
            endpoint = operation_data.get('endpoint', default_endpoint)
            # Remove leading slash for proper URL construction but keep the endpoint
            if endpoint and endpoint.startswith('/'):
                endpoint = endpoint[1:]
            
            # Build the full URL - if we have an endpoint, append it
            if endpoint and endpoint != '':
                full_url = f"{external_url.rstrip('/')}/{endpoint}"
            else:
                full_url = external_url
            
            logger.info(f"API Proxy: external_url={external_url}, default_endpoint={default_endpoint}, final_endpoint={endpoint}, full_url={full_url}")
            
            # Make HTTP request to external API
            async with httpx.AsyncClient(timeout=30.0) as client:
                method = operation_data.get('method', request.method)
                
                if method.upper() == "GET":
                    # Forward query parameters
                    params = operation_data.get('params', {})
                    # Remove internal parameters
                    params.pop('token', None)
                    params.pop('endpoint', None)
                    
                    response = await client.get(full_url, headers=headers, params=params)
                else:
                    # Forward POST body
                    data = operation_data.get('data')
                    if data:
                        response = await client.post(full_url, headers=headers, json=data)
                    else:
                        response = await client.post(full_url, headers=headers)
            
            # Return response data
            try:
                if response.headers.get('content-type', '').startswith('application/json'):
                    data = response.json()
                else:
                    data = response.text
            except:
                data = response.text
            
            return {
                "status": "success",
                "data": data,
                "status_code": response.status_code,
                "headers": dict(response.headers)
            }
            
        except httpx.TimeoutException:
            logger.error(f"API proxy timeout for {proxy_connector.name}")
            return {
                "status": "error",
                "error": "API request timeout"
            }
        except Exception as e:
            logger.error(f"API proxy operation failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def _handle_mysql_proxy(self, proxy_connector: ProxyConnector, operation_data: Dict, db: Session) -> Dict:
        """Handle MySQL proxy operations"""
        
        try:
            # Decrypt connection details
            real_config = json.loads(proxy_connector.real_connection_config)
            real_credentials = json.loads(proxy_connector.real_credentials)
            
            # Apply SSL configuration for development
            from app.core.config import settings
            
            host = real_config.get('host', 'localhost')
            port = real_config.get('port', 3306)
            
            # Get SSL-aware configuration
            ssl_config = settings.get_ssl_config_for_connector(
                'mysql', host, port, real_config
            )
            
            # Create MySQL connection
            config = {
                'host': host,
                'port': port,
                'user': real_credentials.get('username'),
                'password': real_credentials.get('password'),
                'database': real_config.get('database'),
                'connect_timeout': self.app_config.integrations.CONNECTOR_CONNECTION_TIMEOUT,
                'ssl_disabled': ssl_config.get('ssl_disabled', False)
            }
            
            connection = mysql.connector.connect(**config)
            cursor = connection.cursor(dictionary=True)
            
            # Execute query
            query = operation_data.get('query', 'SELECT 1')
            cursor.execute(query)
            
            if query.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
            else:
                results = []
                columns = []
                connection.commit()
            
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "data": results,
                "columns": columns,
                "row_count": len(results)
            }
            
        except Exception as e:
            logger.error(f"MySQL proxy operation failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _handle_postgresql_proxy(self, proxy_connector: ProxyConnector, operation_data: Dict, db: Session) -> Dict:
        """Handle PostgreSQL proxy operations"""
        
        try:
            # Decrypt connection details
            real_config = json.loads(proxy_connector.real_connection_config)
            real_credentials = json.loads(proxy_connector.real_credentials)
            
            # Apply SSL configuration for development
            from app.core.config import settings
            
            host = real_config.get('host', 'localhost')
            port = real_config.get('port', 5432)
            
            # Get SSL-aware configuration
            ssl_config = settings.get_ssl_config_for_connector(
                'postgresql', host, port, real_config
            )
            
            # Create PostgreSQL connection
            connection = psycopg2.connect(
                host=host,
                port=port,
                user=real_credentials.get('username'),
                password=real_credentials.get('password'),
                database=real_config.get('database'),
                sslmode=ssl_config.get('sslmode', 'prefer')
            )
            
            cursor = connection.cursor()
            
            # Execute query
            query = operation_data.get('query', 'SELECT 1')
            cursor.execute(query)
            
            if query.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
            else:
                results = []
                columns = []
                connection.commit()
            
            cursor.close()
            connection.close()
            
            return {
                "status": "success",
                "data": results,
                "columns": columns,
                "row_count": len(results)
            }
            
        except Exception as e:
            logger.error(f"PostgreSQL proxy operation failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _handle_clickhouse_proxy(self, proxy_connector: ProxyConnector, operation_data: Dict, db: Session) -> Dict:
        """Handle ClickHouse proxy operations"""
        
        try:
            # Decrypt connection details
            real_config = json.loads(proxy_connector.real_connection_config)
            real_credentials = json.loads(proxy_connector.real_credentials)
            
            # Create ClickHouse connection
            client = ClickHouseClient(
                host=real_config.get('host', 'localhost'),
                port=real_config.get('port', 9000),
                user=real_credentials.get('username'),
                password=real_credentials.get('password'),
                database=real_config.get('database')
            )
            
            # Execute query
            query = operation_data.get('query', 'SELECT 1')
            results = client.execute(query)
            
            return {
                "status": "success",
                "data": results,
                "row_count": len(results)
            }
            
        except Exception as e:
            logger.error(f"ClickHouse proxy operation failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _handle_mongodb_proxy(self, proxy_connector: ProxyConnector, operation_data: Dict, db: Session) -> Dict:
        """Handle MongoDB proxy operations"""
        
        try:
            # Decrypt connection details
            real_config = json.loads(proxy_connector.real_connection_config)
            real_credentials = json.loads(proxy_connector.real_credentials)
            
            # Create MongoDB connection
            connection_string = f"mongodb://{real_credentials.get('username')}:{real_credentials.get('password')}@{real_config.get('host', 'localhost')}:{real_config.get('port', 27017)}/{real_config.get('database')}"
            
            client = pymongo.MongoClient(connection_string)
            db_conn = client[real_config.get('database')]
            
            # Execute operation
            collection_name = operation_data.get('collection', 'default')
            operation = operation_data.get('operation', 'find')
            query = operation_data.get('query', {})
            
            collection = db_conn[collection_name]
            
            if operation == 'find':
                results = list(collection.find(query))
            elif operation == 'insert':
                results = collection.insert_one(query)
            elif operation == 'update':
                results = collection.update_one(query.get('filter', {}), query.get('update', {}))
            else:
                results = []
            
            client.close()
            
            return {
                "status": "success",
                "data": results,
                "row_count": len(results) if isinstance(results, list) else 1
            }
            
        except Exception as e:
            logger.error(f"MongoDB proxy operation failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_proxy_info(self) -> Dict[str, Any]:
        """Get proxy service information"""
        # Unified proxy endpoints - all accessible via main API port
        proxy_types = ["mysql", "postgresql", "api", "clickhouse", "mongodb", "s3", "shared"]
        
        return {
            "enabled": self.proxy_enabled,
            "running": self.proxy_running,
            "architecture": "unified_single_port",
            "main_port": 8000,
            "endpoints": {
                f"{proxy_type}": f"http://localhost:8000/api/proxy/{proxy_type}/{{database_name}}"
                for proxy_type in proxy_types
            }
        }

# Global instance
integrated_proxy = IntegratedProxyService()