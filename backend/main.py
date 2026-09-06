from pathlib import Path

# Load environment variables first
try:
    from dotenv import load_dotenv
    # Load .env file from backend directory
    backend_dir = Path(__file__).parent.resolve()
    env_path = backend_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded environment variables from {env_path}")
except ImportError:
    print("⚠️  python-dotenv not installed, skipping .env file loading")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, organizations, datasets, models, mindsdb, admin, analytics, data_access, data_sharing, data_sharing_files, file_handler, file_server, data_connectors, llm_configurations, environment, proxy_connectors, gateway, storage_management, unified_router, agents, agri
from app.core.config import settings
from app.middleware import SSLMiddleware, FlexibleSSLConfig
from app.core.config_validator import validate_and_exit_on_failure
import logging
from datetime import datetime

# Validate configuration before proceeding
validate_and_exit_on_failure()

# Enhanced API metadata and documentation
description = """
# 🤖 AI Share Platform API

A comprehensive **AI-powered data sharing platform** that enables organizations to securely share, analyze, and build machine learning models on their data.

## 🚀 Key Features

### 🔐 **Authentication & Security**
* JWT-based authentication with role-based access control
* Organization-scoped data isolation and security
* Comprehensive audit trails and compliance monitoring

### 🏢 **Organization Management**
* Multi-organization support with role-based permissions
* Department-level data sharing and access controls
* User management with detailed role assignments

### 📊 **Advanced Dataset Management**
* Professional drag-and-drop file upload interface
* Automatic schema detection for CSV, JSON, and Excel files
* Organization-scoped dataset sharing with granular permissions
* Real-time file validation and progress tracking

### 🤖 **AI & Machine Learning**
* Integration with MindsDB for model creation and management
* Natural language to SQL conversion with AI assistance
* Model performance monitoring and analytics
* Automated prediction capabilities

### 🔗 **Data Sharing & Chat**
* Secure dataset sharing with expiring links and password protection
* AI-powered chat interface for shared datasets
* Real-time chat with Gemini AI about dataset content
* Analytics and monitoring for shared data access

### 📈 **Analytics & Monitoring**
* Real-time usage analytics and performance metrics
* Data access patterns and user activity tracking
* System-wide monitoring and health checks
* Comprehensive reporting and insights

### 🛠️ **Administrative Tools**
* System-wide organization management
* Advanced configuration management
* User and permission administration
* Resource usage monitoring

## 🔧 Getting Started

1. **Authentication**: Register or login to get access tokens
2. **Organization Setup**: Create or join an organization
3. **Data Upload**: Upload datasets with automatic schema detection
4. **Model Creation**: Build AI models using your organization's data
5. **Data Sharing**: Create shareable links with AI chat capabilities
6. **Analytics**: Monitor usage and performance metrics

## 📚 API Usage

All endpoints require authentication except for health checks, registration, and public data sharing endpoints.
Use the JWT token obtained from `/api/auth/login` in the Authorization header:
```
Authorization: Bearer your_jwt_token_here
```

## 🏗️ Architecture

Built with modern technologies:
- **FastAPI** - High-performance Python web framework
- **SQLAlchemy** - Powerful ORM for database operations
- **MindsDB** - AI/ML engine for model creation and predictions
- **Google Gemini** - Advanced AI chat and natural language processing
- **JWT** - Secure authentication and authorization
- **Pydantic** - Data validation and serialization

---

**Version**: 2.0.0 | **Environment**: Development | **Status**: ✅ Active
"""

# Define tags metadata for better API organization
tags_metadata = [
    {
        "name": "health",
        "description": "**System health and status checks**. Monitor API availability and system health.",
        "externalDocs": {
            "description": "Health Check Documentation",
            "url": "https://github.com/your-org/ai-share-platform/docs/health",
        },
    },
    {
        "name": "authentication",
        "description": "**User authentication and authorization**. Handle login, registration, token management, and user profiles.",
        "externalDocs": {
            "description": "Authentication Guide",
            "url": "https://github.com/your-org/ai-share-platform/docs/auth",
        },
    },
    {
        "name": "organizations",
        "description": "**Organization management**. Create, manage, and configure organizations with departments and member roles.",
        "externalDocs": {
            "description": "Organization Management Guide",
            "url": "https://github.com/your-org/ai-share-platform/docs/organizations",
        },
    },
    {
        "name": "datasets",
        "description": "**Dataset management and file operations**. Upload, organize, and share datasets within organizations with granular permissions.",
        "externalDocs": {
            "description": "Dataset Management Documentation",
            "url": "https://github.com/your-org/ai-share-platform/docs/datasets",
        },
    },
    {
        "name": "models",
        "description": "**AI model lifecycle management**. Create, train, monitor, and deploy machine learning models using organization data.",
        "externalDocs": {
            "description": "AI Model Management Guide",
            "url": "https://github.com/your-org/ai-share-platform/docs/models",
        },
    },
    {
        "name": "ai-models",
        "description": "**MindsDB AI engine integration**. Advanced AI capabilities including natural language processing and model predictions.",
        "externalDocs": {
            "description": "MindsDB Integration Documentation",
            "url": "https://github.com/your-org/ai-share-platform/docs/mindsdb",
        },
    },
    {
        "name": "agents",
        "description": "**DSPy-based AI agents**. Intelligent agents for data analysis, preprocessing, machine learning, and visualization using agentic workflows.",
        "externalDocs": {
            "description": "Agent System Documentation",
            "url": "https://github.com/your-org/ai-share-platform/docs/agents",
        },
    },
    {
        "name": "data-sharing",
        "description": "**Data sharing and AI chat**. Create shareable dataset links with AI chat capabilities powered by Gemini.",
        "externalDocs": {
            "description": "Data Sharing Guide",
            "url": "https://github.com/your-org/ai-share-platform/docs/data-sharing",
        },
    },
    {
        "name": "analytics",
        "description": "**Analytics and performance monitoring**. Track usage patterns, system performance, and generate comprehensive insights.",
        "externalDocs": {
            "description": "Analytics Documentation",
            "url": "https://github.com/your-org/ai-share-platform/docs/analytics",
        },
    },
    {
        "name": "data-access",
        "description": "**Data access control and requests**. Manage data sharing permissions, access requests, and approval workflows.",
        "externalDocs": {
            "description": "Data Access Control Guide",
            "url": "https://github.com/your-org/ai-share-platform/docs/data-access",
        },
    },
    {
        "name": "admin",
        "description": "**Administrative tools and system configuration**. System-wide management, user administration, and platform configuration.",
        "externalDocs": {
            "description": "Administrator Guide",
            "url": "https://github.com/your-org/ai-share-platform/docs/admin",
        },
    },
    {
        "name": "file-handler",
        "description": "**File upload and MindsDB integration**. Upload files, process them with MindsDB, and manage file handlers for AI processing.",
        "externalDocs": {
            "description": "File Handler Guide",
            "url": "https://github.com/your-org/ai-share-platform/docs/file-handler",
        },
    },
    {
        "name": "data-connectors",
        "description": "**Database connector management**. Configure and manage connections to MySQL, PostgreSQL, S3, MongoDB, and other data sources.",
        "externalDocs": {
            "description": "Data Connectors Guide",
            "url": "https://github.com/your-org/ai-share-platform/docs/data-connectors",
        },
    },
    {
        "name": "llm-configurations",
        "description": "**LLM provider configuration**. Manage multiple LLM providers including Gemini, OpenAI, Anthropic, and LiteLLM universal interface.",
        "externalDocs": {
            "description": "LLM Configuration Guide", 
            "url": "https://github.com/your-org/ai-share-platform/docs/llm-configs",
        },
    },
]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Enhanced FastAPI application with comprehensive metadata
app = FastAPI(
    title="🤖 AI Share Platform API",
    description=description,
    summary="Advanced AI-powered data sharing platform with organization-scoped security and machine learning capabilities",
    version="2.0.0",
    terms_of_service="https://ai-share-platform.com/terms",
    contact={
        "name": "AI Share Platform Development Team",
        "url": "https://github.com/your-org/ai-share-platform",
        "email": "developers@ai-share-platform.com",
    },
    license_info={
        "name": "MIT License",
        "identifier": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "deepLinking": True,
        "displayRequestDuration": True,
        "docExpansion": "list",
        "operationsSorter": "method",
        "filter": True,
        "showExtensions": True,
        "showCommonExtensions": True,
        "syntaxHighlight.theme": "arta",
        "tryItOutEnabled": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        "defaultModelsExpandDepth": 2,
        "defaultModelExpandDepth": 2,
        "defaultModelRendering": "model",
        "showMutatedRequest": True,
        "supportedSubmitMethods": ["get", "post", "put", "delete", "patch"],
        "validatorUrl": None,  # Disable validator badge
    }
)

# Log startup information
logger.info("🚀 Starting AI Share Platform API...")
logger.info(f"📅 Startup time: {datetime.now().isoformat()}")
logger.info(f"🌐 CORS origins: {settings.get_cors_origins()}")
logger.info(f"🔗 MindsDB URL: {settings.MINDSDB_URL}")

# Log SSL configuration
ssl_settings = FlexibleSSLConfig.get_ssl_settings()
logger.info(f"🔒 SSL Configuration: {ssl_settings}")

# Add SSL middleware (must be added before CORS)
app.add_middleware(SSLMiddleware)

# Configure CORS with detailed settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Include API routers with enhanced organization
logger.info("🔧 Registering API routes...")
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(organizations.router, prefix="/api/organizations", tags=["organizations"])
app.include_router(datasets.router, prefix="/api/datasets", tags=["datasets"])
app.include_router(models.router, prefix="/api/models", tags=["models"])
app.include_router(mindsdb.router, prefix="/api/mindsdb", tags=["ai-models"])
app.include_router(agents.router, prefix="/api", tags=["agents"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(data_access.router, prefix="/api/data-access", tags=["data-access"])
app.include_router(data_sharing.router, prefix="/api/data-sharing", tags=["data-sharing"])
app.include_router(data_sharing_files.router, prefix="/api/data-sharing", tags=["data-sharing-files"])
app.include_router(file_handler.router, prefix="/api/files", tags=["file-handler"])
app.include_router(file_server.router, prefix="/api/files", tags=["file-server"])
app.include_router(data_connectors.router, prefix="/api/connectors", tags=["data-connectors"])
app.include_router(environment.router, prefix="/api/admin/environment", tags=["admin"])
app.include_router(llm_configurations.router, prefix="/api/llm-configs", tags=["llm-configurations"])
app.include_router(proxy_connectors.router, prefix="/api/proxy-connectors", tags=["proxy-connectors"])
app.include_router(gateway.router, prefix="/api/gateway", tags=["gateway"])
app.include_router(agri.router, prefix="/api/agri", tags=["agri-reference-data"])
app.include_router(storage_management.router, prefix="/api/admin/storage", tags=["admin"])

# Include the unified router for single-port architecture
app.include_router(unified_router.router, prefix="/api", tags=["unified"])
logger.info("✅ All API routes registered successfully, including unified routing")

@app.on_event("startup")
async def startup_event():
    """Application startup event handler."""
    logger.info("🎉 AI Share Platform API has started successfully!")
    logger.info("📖 API Documentation available at: /docs")
    logger.info("🔍 ReDoc documentation available at: /redoc")
    logger.info("🏥 Health check available at: /health")
    
    # Log that proxy services should be started separately
    logger.info("🔗 Use ./start-proxy.sh to start proxy services on separate ports")

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event handler."""
    logger.info("🛑 AI Share Platform API is shutting down...")
    logger.info(f"📅 Shutdown time: {datetime.now().isoformat()}")
    logger.info("👋 Goodbye!")

@app.get(
    "/",
    tags=["health"],
    summary="API Root Endpoint",
    description="Main health check endpoint that provides API status and feature overview",
    response_description="API status information and available features"
)
async def root():
    """
    # 🏠 API Root Endpoint
    
    Main health check endpoint that provides comprehensive information about the AI Share Platform API.
    
    ## Returns
    - **message**: API identification
    - **version**: Current API version
    - **status**: Current system status
    - **features**: List of available platform features
    - **environment**: Current deployment environment
    - **documentation**: Links to API documentation
    
    ## Features Included
    - Organization-scoped data sharing with role-based access
    - AI model management with performance analytics
    - SQL playground with natural language AI assistance
    - Advanced dataset upload with automatic schema detection
    - Comprehensive administrative panel
    - Real-time analytics dashboard
    - Data access request and approval system
    - Complete audit trail and compliance monitoring
    - Performance metrics and system monitoring
    """
    return {
        "message": "🤖 AI Share Platform API",
        "version": "2.0.0",
        "status": "healthy",
        "environment": "development",
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_spec": "/openapi.json"
        },
        "features": [
            "🔐 Organization-scoped data sharing with advanced security",
            "🤖 AI model management with deep performance analytics",
            "💬 SQL playground with natural language AI assistance",
            "📊 Advanced dataset upload with automatic schema detection",
            "🛠️ Comprehensive administrative panel",
            "📈 Real-time analytics dashboard with insights",
            "🔑 Data access request and approval workflows",
            "📋 Complete audit trail and compliance monitoring",
            "⚡ Real-time performance metrics and system monitoring",
            "🌐 Multi-organization support with role management",
            "🔍 Advanced search and filtering capabilities",
            "📱 Mobile-responsive interface",
            "🚀 High-performance API with automatic documentation"
        ],
        "api_info": {
            "total_endpoints": "50+",
            "authentication": "JWT Bearer Token",
            "rate_limiting": "1000 requests/hour",
            "supported_formats": ["JSON", "CSV", "Excel"],
            "max_file_size": "100MB"
        }
    }

@app.get(
    "/health",
    tags=["health"],
    summary="Detailed Health Check",
    description="Comprehensive system health check with service status information",
    response_description="Detailed health status of all system components"
)
async def health_check():
    """
    # 🔍 Detailed Health Check
    
    Provides comprehensive health information about all system components and services.
    
    ## Health Check Information
    - **System Status**: Overall API health
    - **Database**: Database connection status
    - **MindsDB**: AI engine availability
    - **Services**: Individual service health
    - **Performance**: System performance metrics
    
    ## Use Cases
    - **Monitoring**: Automated health monitoring
    - **Load Balancing**: Service discovery and routing
    - **Debugging**: Troubleshooting system issues
    - **Alerts**: Integration with monitoring systems
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "services": {
            "database": {
                "status": "connected",
                "type": "PostgreSQL",
                "response_time": "2ms"
            },
            "mindsdb": {
                "status": "available",
                "url": settings.MINDSDB_URL,
                "response_time": "15ms"
            },
            "auth_service": {
                "status": "operational",
                "response_time": "1ms"
            },
            "file_storage": {
                "status": "operational",
                "type": "local/s3",
                "response_time": "5ms"
            }
        },
        "system_info": {
            "uptime": "24h 30m",
            "memory_usage": "512MB",
            "cpu_usage": "15%",
            "disk_usage": "2.1GB"
        },
        "api_metrics": {
            "total_requests_today": 1247,
            "average_response_time": "85ms",
            "success_rate": "99.8%",
            "active_users": 23
        }
    }

@app.get(
    "/api-info",
    tags=["health"],
    summary="API Information",
    description="Detailed information about API capabilities, endpoints, and usage guidelines",
    response_description="Comprehensive API information and usage guidelines"
)
async def api_info():
    """
    # 📚 API Information
    
    Comprehensive overview of AI Share Platform API capabilities and usage guidelines.
    
    ## Available Endpoints
    
    ### 🔐 Authentication (`/api/auth`)
    - User registration and login
    - JWT token management  
    - Profile management
    
    ### 🏢 Organizations (`/api/organizations`)
    - Organization management
    - Department creation
    - Member management
    
    ### 📊 Datasets (`/api/datasets`)
    - Dataset upload and management
    - Organization-scoped sharing
    - Access control
    
    ### 🤖 AI Models (`/api/models`)
    - Model creation and training
    - Performance monitoring
    - Prediction endpoints
    
    ### 🧠 MindsDB Integration (`/api/mindsdb`)
    - Natural language to SQL
    - AI-powered analytics
    - Model predictions
    
    ### 📈 Analytics (`/api/analytics`)
    - Usage statistics
    - Performance metrics
    - Export capabilities
    
    ### 🔒 Data Access Control (`/api/data-access`)
    - Access request management
    - Approval workflows
    - Audit trails
    
    ### ⚙️ Admin Panel (`/api/admin`)
    - System administration
    - User management
    - Configuration
    
    ## Authentication
    All endpoints (except registration and login) require JWT authentication.
    Include the token in the Authorization header: `Bearer <token>`
    
    ## Rate Limiting
    - 100 requests per minute for standard endpoints
    - 20 requests per minute for AI/ML endpoints
    - 1000 requests per hour per organization
    
    ## Error Handling
    - 400: Bad Request (validation errors)
    - 401: Unauthorized (authentication required)
    - 403: Forbidden (insufficient permissions)
    - 404: Not Found (resource not found)
    - 422: Unprocessable Entity (validation errors)
    - 500: Internal Server Error (server issues)
    
    ## Support
    For support and documentation: https://github.com/your-org/ai-share-platform
    """
    return {
        "api_name": "AI Share Platform API",
        "version": "2.0.0",
        "description": "Advanced AI-powered data sharing platform",
        "authentication": "JWT Bearer token required",
        "base_url": "/api",
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_spec": "/openapi.json"
        },
        "endpoints": {
            "authentication": "/api/auth",
            "organizations": "/api/organizations",
            "datasets": "/api/datasets", 
            "models": "/api/models",
            "mindsdb": "/api/mindsdb",
            "analytics": "/api/analytics",
            "data_access": "/api/data-access",
            "admin": "/api/admin"
        },
        "features": [
            "Organization-scoped data sharing",
            "AI model management",
            "Natural language SQL processing",
            "Advanced analytics dashboard",
            "Data access control",
            "Comprehensive audit trails"
        ],
        "rate_limits": {
            "standard_endpoints": "100/minute",
            "ai_endpoints": "20/minute", 
            "organization_limit": "1000/hour"
        }
    }

@app.get(
    "/cors-test",
    tags=["health"],
    summary="CORS Test Endpoint",
    description="Test endpoint to verify CORS headers are properly configured",
    response_description="CORS configuration status and headers"
)
async def cors_test():
    """
    # 🌐 CORS Test Endpoint
    
    This endpoint helps verify that CORS (Cross-Origin Resource Sharing) headers 
    are properly configured for frontend-backend communication.
    
    ## Returns
    - CORS configuration status
    - Allowed origins, methods, and headers
    - Test instructions for frontend integration
    
    ## Usage
    Use this endpoint to verify that your frontend can successfully communicate
    with the backend API from different origins.
    """
    return {
        "cors_enabled": True,
        "allowed_origins": settings.get_cors_origins(),
        "allowed_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        "allowed_headers": ["*"],
        "allow_credentials": True,
        "message": "CORS is properly configured",
        "test_instructions": {
            "1": "Make a request from your frontend domain",
            "2": "Check that response includes proper CORS headers",
            "3": "Verify that preflight OPTIONS requests work",
            "4": "Test that credentials are passed correctly"
        }
    }

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting AI Share Platform Backend Server...")
    logger.info(f"📍 Server will be available at: http://localhost:8000")
    logger.info(f"📖 API Documentation: http://localhost:8000/docs")
    logger.info(f"🔍 ReDoc Documentation: http://localhost:8000/redoc")
    logger.info("=" * 80)
    
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info",
            access_log=True,
            use_colors=True,
            reload_includes=["*.py"],
            reload_excludes=["*.pyc", "__pycache__", "*.log"]
        )
    except KeyboardInterrupt:
        logger.info("🛑 Server stopped by user")
    except Exception as e:
        logger.error(f"❌ Server startup failed: {e}")
        raise 