# Simple AI Sharing Platform - Documentation

## 📖 Documentation Overview

This directory contains documentation for the Simple AI Sharing platform with **unified single-port architecture** optimized for modern cloud deployment.

## 📚 Key Documentation

### 🚀 [DEPLOYMENT.md](./DEPLOYMENT.md)
**Complete Production Deployment Guide**
- Docker deployment with single port architecture
- Railway, Render, and Vercel configuration
- Environment variables and security setup
- Frontend-backend integration

### 🔍 [FRONTEND_PATHS_VERIFICATION.md](./FRONTEND_PATHS_VERIFICATION.md) 
**Frontend Integration & API Verification**
- Single-port API architecture verification
- Frontend code examples and configuration
- API client setup for React/Next.js
- Production deployment steps

### ⚡ [QUICK_START.md](./QUICK_START.md)
**Local Development Setup**
- Quick setup for development
- Basic usage examples
- Demo accounts and testing

### 🔒 [SSL_AND_URL_CONFIGURATION.md](./SSL_AND_URL_CONFIGURATION.md)
**Flexible SSL and URL Configuration**
- Auto-detection of HTTPS/HTTP based on environment
- Dynamic backend URL detection for any deployment platform
- SSL middleware and security headers
- Cloud platform integration (Railway, Render, Vercel)

## 🏗️ Unified Single-Port Architecture

```
┌─────────────────────────────────────────────────────────┐
│                Simple AI Sharing Platform               │
├─────────────────────────────────────────────────────────┤
│                    🌐 Single Port 8000                  │
├─────────────────────────────────────────────────────────┤
│ /api/auth/        │ Authentication & JWT               │
│ /api/datasets/    │ Dataset management & AI chat       │
│ /api/files/       │ File upload/download               │
│ /api/connectors/  │ Data connectors (MySQL, API, S3)  │
│ /api/shared/      │ Public sharing & access            │
│ /api/proxy/       │ Proxy operations                   │
│ /api/organizations/ │ Organization management          │
│ /docs             │ API documentation                  │
│ /health           │ Health check                       │
├─────────────────────────────────────────────────────────┤
│                    🔧 Backend Services                  │
│ • FastAPI unified server                               │
│ • PostgreSQL database                                  │ 
│ • Google Gemini AI                                     │
│ • Encrypted credential storage                         │
│ • JWT authentication                                   │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Quick Reference

### Starting the Backend

```bash
# Local development (single command)
cd backend && python start.py

# Docker development
docker-compose up -d

# Production deployment
# See DEPLOYMENT.md for Railway/Render/Vercel setup
```

### Health Check

```bash
# Unified API health check
curl http://localhost:8000/api/health
# Should return: {"status": "healthy", "endpoints": {...}}
```

### Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `http://localhost:8000/docs` | Interactive API Documentation |
| `http://localhost:8000/api/auth/login` | Authentication |
| `http://localhost:8000/api/datasets` | Dataset management |
| `http://localhost:8000/api/files/upload-file` | File uploads |
| `http://localhost:8000/api/connectors` | Data connectors |
| `http://localhost:8000/api/data-sharing/*` | Sharing & AI chat |

## 🔐 Authentication

Demo accounts available for testing:

```bash
# Login with demo account
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice@techcorp.com&password=Password123!"

# Use returned JWT token in requests
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/datasets"
```

## ✨ Key Features

✅ **Single Port**: All services through port 8000  
✅ **Docker Ready**: Simple containerization  
✅ **Cloud Deploy**: Railway/Render/Vercel configs  
✅ **File Management**: Upload, share, manage datasets  
✅ **Data Connectors**: MySQL, PostgreSQL, S3, APIs  
✅ **AI Chat**: Interactive analysis with Gemini  
✅ **Public Sharing**: Secure sharing with expiration  
✅ **JWT Auth**: Secure authentication system  

## 🎯 Getting Started

1. **Quick Setup**: See [QUICK_START.md](./QUICK_START.md)
2. **Production Deploy**: See [DEPLOYMENT.md](./DEPLOYMENT.md)
3. **Frontend Integration**: See [FRONTEND_PATHS_VERIFICATION.md](./FRONTEND_PATHS_VERIFICATION.md)

## 📞 Support

- **API Docs**: http://localhost:8000/docs (when running)
- **Health Check**: http://localhost:8000/api/health
- **Issues**: Check logs and verify environment configuration