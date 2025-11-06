# SSL and URL Configuration Guide

## 🔒 Flexible SSL Methodology

The Simple AI Sharing platform now supports **flexible SSL configuration** that adapts to different deployment environments automatically, while still allowing manual overrides when needed.

## ✨ Key Features

✅ **Auto-Detection**: HTTP in development, HTTPS in production  
✅ **Manual Override**: Force SSL on/off with environment variables  
✅ **Proxy-Aware**: Handles reverse proxy headers correctly  
✅ **Cloud Platform Ready**: Works with Railway, Render, Heroku, Vercel  
✅ **Development Friendly**: Always HTTP for localhost  
✅ **Dynamic URLs**: Auto-detects backend URL from requests  

## 🚀 Quick Configuration

### For Development (Default)
```bash
# .env (development)
ENVIRONMENT=development
REQUIRE_SSL=auto          # Results in HTTP for localhost
API_BASE_URL=             # Auto-detect from request
```

### For Production (Recommended)
```bash
# .env.production
ENVIRONMENT=production
REQUIRE_SSL=auto          # Results in HTTPS for production domains  
SSL_REDIRECT=auto         # Auto-redirect HTTP to HTTPS in production
API_BASE_URL=             # Auto-detect from request headers
```

## 📋 Environment Variables

| Variable | Options | Default | Description |
|----------|---------|---------|-------------|
| `REQUIRE_SSL` | `auto`, `true`, `false` | `auto` | SSL enforcement policy |
| `SSL_REDIRECT` | `auto`, `true`, `false` | `auto` | HTTP to HTTPS redirect |
| `FORCE_HTTPS_URLS` | `auto`, `true`, `false` | `auto` | Force HTTPS in generated URLs |
| `API_BASE_URL` | URL or empty | (empty) | Fixed base URL or auto-detect |
| `ENVIRONMENT` | `development`, `production` | `development` | Deployment environment |

## 🔧 SSL Configuration Modes

### Auto Mode (Recommended)
```bash
REQUIRE_SSL=auto
```
- **Development**: Uses HTTP for localhost, 127.0.0.1, 192.168.x.x
- **Production**: Uses HTTPS for all other domains
- **Smart Detection**: Respects proxy headers

### Force Enable
```bash
REQUIRE_SSL=true
```
- Always requires HTTPS
- Redirects HTTP to HTTPS
- Adds security headers

### Force Disable  
```bash
REQUIRE_SSL=false
```
- Always uses HTTP
- No redirects
- Useful for internal networks

## 🌐 Dynamic URL Detection

Instead of hardcoding backend URLs, the system can auto-detect them:

### How It Works
1. **Check Environment**: If `API_BASE_URL` is set, use it
2. **Read Headers**: Get host and protocol from request headers
3. **Detect Protocol**: Use X-Forwarded-Proto, X-Forwarded-SSL, or environment
4. **Build URL**: Combine protocol + host

### Header Detection Priority
1. `X-Forwarded-Proto: https/http` (from load balancer)
2. `X-Forwarded-SSL: on` (from SSL terminator)
3. Environment-based default (HTTP dev, HTTPS prod)
4. Host-based detection (HTTP for localhost)

## 🏗️ Cloud Platform Integration

### Railway
```bash
# Railway automatically sets:
# X-Forwarded-Proto: https
# Host: your-app.railway.app

ENVIRONMENT=production
REQUIRE_SSL=auto          # Results in HTTPS
API_BASE_URL=             # Auto-detects: https://your-app.railway.app
```

### Render
```bash  
# Render automatically sets:
# X-Forwarded-Proto: https
# Host: your-app.onrender.com

ENVIRONMENT=production  
REQUIRE_SSL=auto          # Results in HTTPS
API_BASE_URL=             # Auto-detects: https://your-app.onrender.com
```

### Heroku
```bash
# Heroku automatically sets:
# X-Forwarded-Proto: https
# Host: your-app.herokuapp.com

ENVIRONMENT=production
REQUIRE_SSL=auto          # Results in HTTPS  
API_BASE_URL=             # Auto-detects: https://your-app.herokuapp.com
```

### Docker/Kubernetes
```bash
# Configure based on your reverse proxy setup
ENVIRONMENT=production
REQUIRE_SSL=auto
API_BASE_URL=https://your-domain.com  # Or leave empty for auto-detection
```

## 🔍 Frontend Integration

### Vercel Environment Variables
```bash
# Frontend will connect to auto-detected backend URL
NEXT_PUBLIC_API_URL=https://your-backend.railway.app/api
NEXT_PUBLIC_FORCE_HTTPS=true
NEXT_PUBLIC_ALLOW_HTTP_LOCALHOST=true
```

### API Client Configuration
```typescript
// Frontend API client automatically handles protocol
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL;

// The backend will auto-detect its own URLs for shared links
const response = await fetch(`${API_BASE_URL}/shared/create`, {
  method: 'POST',
  body: JSON.stringify(shareData)
});
```

## 🛠️ Development vs Production

### Development Environment
```bash
# Local development - always HTTP
curl http://localhost:8000/api/health
curl http://127.0.0.1:8000/api/shared/abc123
```

### Production Environment  
```bash  
# Production - auto HTTPS
curl https://your-app.railway.app/api/health
curl https://your-app.railway.app/api/shared/abc123

# HTTP requests automatically redirect to HTTPS
curl http://your-app.railway.app/api/health
# → 301 Redirect to https://your-app.railway.app/api/health
```

## 🚨 Security Features

### Automatic Security Headers (HTTPS only)
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`

### SSL Redirect Middleware
- Automatically redirects HTTP to HTTPS in production
- Preserves query parameters and path
- Configurable per environment

## 🧪 Testing

### Test SSL Configuration
```bash
# Check current SSL settings
curl http://localhost:8000/api/health
# Should show SSL configuration in logs

# Test redirect behavior
curl -I http://your-app.railway.app/api/health
# Should return 301 redirect to HTTPS in production
```

### Verify URL Detection
```bash
# Backend logs will show detected URLs
grep "detected_base_url" backend.log

# Check generated shared links
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/shared/create \
  -d '{"connector_id": 1, "name": "test"}'
# Should return correct full_url
```

## 📝 Migration from Hardcoded URLs

### Before (Hardcoded)
```bash
# Had to set specific URLs
API_BASE_URL=https://my-specific-app.railway.app
BACKEND_CORS_ORIGINS=https://my-frontend.vercel.app
```

### After (Auto-Detection)
```bash
# Works with any deployment URL
API_BASE_URL=                    # Empty = auto-detect
BACKEND_CORS_ORIGINS=*           # Or specific domains
```

## 🆘 Troubleshooting

### Common Issues

**🔥 Mixed Content Warnings**
```bash
# Solution: Ensure frontend uses HTTPS
NEXT_PUBLIC_FORCE_HTTPS=true
```

**🔥 SSL Redirects Not Working**
```bash
# Check environment configuration
ENVIRONMENT=production
SSL_REDIRECT=auto
```

**🔥 Wrong URLs in Generated Links**
```bash
# Check proxy headers are being forwarded
X-Forwarded-Proto: https
X-Forwarded-Host: your-domain.com
```

**🔥 Localhost SSL Issues**
```bash
# Development should always use HTTP
ENVIRONMENT=development
# or force HTTP
REQUIRE_SSL=false
```

### Debug Headers
Add logging to see what headers are being received:
```bash
# Check application logs for:
# "🔒 SSL Configuration: {...}"
# "🌐 Detected URL: https://..."
```

## 📈 Benefits

1. **Zero Configuration**: Works out of the box with cloud platforms
2. **Security by Default**: HTTPS in production, HTTP in development
3. **Flexible Override**: Can still set explicit URLs when needed
4. **Platform Agnostic**: Works with any deployment platform
5. **Future Proof**: Handles random deployment URLs automatically

## 🎯 Best Practices

1. **Use Auto-Detection**: Leave `API_BASE_URL` empty unless you need specific control
2. **Environment-Based Config**: Use `ENVIRONMENT=production` for production deployments
3. **Proxy Headers**: Ensure your reverse proxy forwards `X-Forwarded-Proto`
4. **Security Headers**: Let the middleware handle security headers automatically
5. **Testing**: Test with both HTTP (dev) and HTTPS (prod) environments

This flexible SSL and URL configuration makes deployments much simpler while maintaining security and compatibility across all environments! 🚀