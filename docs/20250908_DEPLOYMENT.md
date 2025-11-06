# Deployment Guide - Single Port Architecture

This guide explains how to deploy the Simple AI Sharing platform with a unified single-port architecture that's optimized for cloud platforms.

## Architecture Overview

The refactored architecture uses a **single port (8000)** with path-based routing for all services:

- `/api/files/*` - File upload and management
- `/api/connectors/*` - Data connector operations  
- `/api/shared/*` - Public shared links
- `/api/proxy/*` - Proxy operations
- `/api/datasets/*` - Dataset management
- All other existing API endpoints

This eliminates the complexity of managing multiple ports and makes deployment much simpler.

## Backend Deployment

### Option 1: Deploy to Railway

1. **Prerequisites**
   - Railway account
   - GitHub repository connected

2. **Configuration**
   ```bash
   # In Railway dashboard, set these environment variables:
   DATABASE_URL=<Railway PostgreSQL URL>
   SECRET_KEY=<generate-secure-key>
   API_BASE_URL=https://your-app.railway.app
   BACKEND_CORS_ORIGINS=https://your-frontend.vercel.app
   FIRST_SUPERUSER=admin@example.com
   FIRST_SUPERUSER_PASSWORD=<secure-password>
   GOOGLE_API_KEY=<optional>
   ```

3. **Deploy**
   - Railway will auto-detect the `railway.json` configuration
   - The app will be available at `https://your-app.railway.app`

### Option 2: Deploy to Render

1. **Prerequisites**
   - Render account
   - GitHub repository connected

2. **Configuration**
   - Use the `render.yaml` blueprint
   - Or create a new Web Service with Docker runtime

3. **Environment Variables**
   ```bash
   DATABASE_URL=<Render PostgreSQL URL>
   SECRET_KEY=<generate-secure-key>
   API_BASE_URL=https://your-app.onrender.com
   BACKEND_CORS_ORIGINS=https://your-frontend.vercel.app
   FIRST_SUPERUSER=admin@example.com
   FIRST_SUPERUSER_PASSWORD=<secure-password>
   ```

### Option 3: Deploy with Docker

1. **Build and Run**
   ```bash
   cd backend
   
   # Build the image
   docker build -t simpleaisharing-backend .
   
   # Run with environment variables
   docker run -d \
     -p 8000:8000 \
     -e DATABASE_URL=postgresql://user:pass@host/db \
     -e SECRET_KEY=your-secret-key \
     -e API_BASE_URL=https://your-domain.com \
     -e BACKEND_CORS_ORIGINS=https://frontend.com \
     --name simpleaisharing \
     simpleaisharing-backend
   ```

2. **Using Docker Compose**
   ```bash
   # Copy .env.production to .env and fill in values
   cp .env.production .env
   
   # Start services
   docker-compose up -d
   
   # With MindsDB (optional)
   docker-compose --profile with-mindsdb up -d
   ```

## Frontend Deployment (Vercel)

1. **Prerequisites**
   - Vercel account
   - GitHub repository connected

2. **Configuration**
   - The `vercel.json` is already configured
   - Set environment variables in Vercel dashboard:

   ```bash
   NEXT_PUBLIC_API_URL=https://your-backend.railway.app/api
   NEXT_PUBLIC_WS_URL=wss://your-backend.railway.app/ws
   NEXT_PUBLIC_APP_NAME=AI Share Platform
   ```

3. **Deploy**
   ```bash
   # Install Vercel CLI
   npm i -g vercel
   
   # Deploy
   cd frontend
   vercel --prod
   ```

## API Endpoints Structure

All services now use unified routing through a single port:

### File Management
```bash
# Upload file
POST https://api.example.com/api/files/upload

# Get file
GET https://api.example.com/api/files/{file_id}

# Delete file
DELETE https://api.example.com/api/files/{file_id}
```

### Connectors
```bash
# Create connector
POST https://api.example.com/api/connectors/create

# Execute connector
POST https://api.example.com/api/connectors/{connector_id}/execute
GET https://api.example.com/api/connectors/{connector_id}/data
```

### Shared Links
```bash
# Create shared link
POST https://api.example.com/api/shared/create

# Access shared link (public, no auth)
GET https://api.example.com/api/shared/{share_id}
POST https://api.example.com/api/shared/{share_id}/query
```

## Testing the Deployment

1. **Health Check**
   ```bash
   curl https://your-backend.com/api/health
   ```

2. **Create a Connector**
   ```bash
   curl -X POST https://your-backend.com/api/connectors/create \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Test API",
       "connector_type": "api",
       "connection_config": {
         "base_url": "https://jsonplaceholder.typicode.com"
       },
       "credentials": {},
       "allowed_operations": ["GET", "POST"]
     }'
   ```

3. **Upload a File**
   ```bash
   curl -X POST https://your-backend.com/api/files/upload \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -F "file=@test.csv" \
     -F "description=Test file"
   ```

## Environment Variables Reference

### Backend (Required)
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - JWT secret key
- `API_BASE_URL` - Public URL of your backend
- `BACKEND_CORS_ORIGINS` - Comma-separated list of allowed origins
- `FIRST_SUPERUSER` - Admin email
- `FIRST_SUPERUSER_PASSWORD` - Admin password

### Backend (Optional)
- `GOOGLE_API_KEY` - For AI features
- `MINDSDB_URL` - MindsDB instance URL
- `MAX_FILE_SIZE_MB` - Maximum file upload size
- `ENVIRONMENT` - Set to "production" for production

### Frontend
- `NEXT_PUBLIC_API_URL` - Backend API URL
- `NEXT_PUBLIC_APP_NAME` - Application name
- `NEXT_PUBLIC_ENABLE_*` - Feature flags

## Security Considerations

1. **HTTPS Only** - Always use HTTPS in production
2. **CORS** - Configure `BACKEND_CORS_ORIGINS` to only allow your frontend domain
3. **Secrets** - Never commit secrets to version control
4. **Database** - Use connection pooling and SSL for database connections
5. **File Storage** - Consider using cloud storage (S3) for production file uploads

## Monitoring

1. **Health Checks**
   - Backend: `/api/health`
   - Use uptime monitoring services

2. **Logs**
   - Railway: Check logs in dashboard
   - Render: Check logs in dashboard
   - Docker: `docker logs simpleaisharing`

3. **Performance**
   - Monitor response times
   - Set up alerts for errors

## Troubleshooting

### CORS Issues
- Ensure `BACKEND_CORS_ORIGINS` includes your frontend URL
- Check that URLs don't have trailing slashes

### Database Connection
- Verify `DATABASE_URL` is correct
- Check if database allows connections from your backend IP

### File Uploads
- Ensure storage directories have write permissions
- Check `MAX_FILE_SIZE_MB` setting

### Port Issues
- The app now uses only port 8000
- No need for multiple port mappings

## Scaling

1. **Horizontal Scaling**
   - Railway: Increase replicas in dashboard
   - Render: Configure auto-scaling in settings
   - Docker: Use Kubernetes or Docker Swarm

2. **Database**
   - Use connection pooling
   - Consider read replicas for heavy read loads

3. **File Storage**
   - Migrate to S3 or similar cloud storage
   - Use CDN for static files

## Support

For issues or questions:
1. Check application logs
2. Review environment variables
3. Ensure all services are running
4. Check network connectivity between services