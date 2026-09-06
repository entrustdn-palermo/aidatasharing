# Quick Start Guide - AI Share Platform

## 🚀 Get Started in 3 Steps

### 1. Prerequisites

```bash
# Clone or navigate to the project
cd simpleaisharing

# Install backend dependencies
cd backend
pip install -r requirements.txt

# Install frontend dependencies (optional)
cd ../frontend
npm install
```

### 2. Start the Services

#### Option A: Backend Only (Recommended for API testing)

```bash
# Start MindsDB (required for AI features)
./start-mindsdb.sh

# Start the backend with integrated proxy
cd backend
python start.py
```

#### Option B: Full Stack (Backend + Frontend)

```bash
# Start all services
./start-dev.sh
```

### 3. Verify Everything is Running

```bash
# Check main API
curl http://localhost:8000/health

# Check integrated proxy
curl http://localhost:8000/api/proxy/health

# Access API documentation
open http://localhost:8000/docs
```

## 📋 Available Services

| Service | URL | Purpose |
|---------|-----|---------|
| **Backend API** | http://localhost:8000 | Main API server |
| **API Docs** | http://localhost:8000/docs | Interactive API documentation |
| **Frontend** | http://localhost:3000 | Web interface (if started) |
| **MindsDB** | http://localhost:47334 | AI/ML engine |

## 🔐 Demo Accounts

| Role | Email | Password |
|------|-------|----------|
| **Admin** | admin@example.com | SuperAdmin123! |
| **TechCorp User** | alice@techcorp.com | Password123! |
| **DataAnalytics User** | bob@dataanalytics.com | Password123! |

## 🎯 Test the Platform

### 1. Login and Get Token

```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "SuperAdmin123!"
  }'
```

### 2. Upload Data (Upload Mode)

```bash
# Upload a CSV file
curl -X POST "http://localhost:8000/api/datasets/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@sample.csv" \
  -F "name=Sample Dataset"
```

### 3. Create Proxy Connector (Connector Mode)

```bash
# Create an API connector
curl -X POST "http://localhost:8000/api/proxy-connectors" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "JSONPlaceholder API",
    "connector_type": "api",
    "description": "Demo REST API",
    "real_connection_config": {
      "base_url": "https://jsonplaceholder.typicode.com"
    },
    "real_credentials": {},
    "is_public": true,
    "allowed_operations": ["GET"]
  }'
```

### 4. Test Proxy Access

```bash
# Access API through proxy
curl "http://localhost:8000/api/proxy/api/JSONPlaceholder_API?endpoint=/posts/1"
```

## 🔧 Configuration

### Key Environment Variables (backend/.env)

```bash
# API Keys
GOOGLE_API_KEY=your_google_api_key_here

# Database
DATABASE_URL=sqlite:///../storage/aishare_platform.db

# Services
MINDSDB_URL=http://localhost:47334
ENABLE_PROXY_SERVICE=true

# CORS for frontend
BACKEND_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## 🔄 Data Sharing Modes

### Upload Mode (Traditional)
1. Upload files via API or web interface
2. Files are stored locally/cloud
3. Share via download links or AI chat

### Connector Mode (Proxy-based)
1. Create secure connectors to external databases/APIs
2. Real credentials are encrypted
3. Share via proxy endpoints with tokens
4. Real-time data access without duplication

## 📚 Next Steps

- **Read the full guides**: [Backend Startup Guide](./BACKEND_STARTUP_GUIDE.md) | [Proxy Mode Guide](./PROXY_MODE_GUIDE.md)
- **Explore API docs**: http://localhost:8000/docs
- **Test with sample data**: Use the demo accounts to create datasets and connectors
- **Set up your own connectors**: Connect to your real databases and APIs

## 🚨 Troubleshooting

### Port Already in Use
```bash
# Kill processes on common ports
lsof -ti:8000 | xargs kill -9  # Backend
lsof -ti:3000 | xargs kill -9  # Frontend
lsof -ti:47334 | xargs kill -9  # MindsDB
```

### Services Not Starting
```bash
# Check if all dependencies are installed
pip check

# Verify environment file exists
ls backend/.env

# Check logs
tail -f logs/backend_test.log
```

### Database Issues
```bash
# Reset database (WARNING: Deletes all data)
rm storage/aishare_platform.db

# Restart backend to recreate
cd backend && python start.py
```

## 💡 Tips

1. **API First**: Start with the API endpoints before building UI
2. **Use Demo Data**: The platform comes with sample datasets
3. **Check Logs**: Most issues can be diagnosed from log output
4. **Test Incrementally**: Start with simple API calls, then build complexity
5. **Security**: Never commit real API keys or credentials to the repository