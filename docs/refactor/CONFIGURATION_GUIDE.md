# Configuration Guide

**AI Share Platform - Environment Configuration**
**Last Updated:** 2025-10-28

---

## Quick Start

### For Local Development:

1. **Backend:**
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env with your settings
   ```

2. **Frontend:**
   ```bash
   cd frontend
   cp .env.local.example .env.local
   # Usually defaults work for local dev
   ```

3. **Generate Encryption Key:**
   ```bash
   cd backend
   python scripts/migrate_encrypt_credentials.py --generate-key
   # Add output to backend/.env
   ```

---

## Configuration Files

### Backend Configuration

**File:** `backend/.env`

**Template:** `backend/.env.example`

**Required Variables:**
```bash
# Security (REQUIRED)
JWT_SECRET_KEY=your-jwt-secret-key-at-least-32-characters-long
ENCRYPTION_KEY=your-encryption-key-here  # Phase 1

# Database (REQUIRED)
DATABASE_URL=postgresql://user:pass@localhost:5432/aishare

# Admin (REQUIRED for first setup)
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_PASSWORD=your_admin_password
```

**Optional Variables:**
```bash
# AI Integration
GOOGLE_API_KEY=your_google_api_key

# MindsDB
MINDSDB_URL=http://localhost:47334

# Storage (if using S3)
S3_ENDPOINT_URL=your_s3_endpoint
S3_BUCKET_NAME=your_bucket
S3_ACCESS_KEY_ID=your_key
S3_SECRET_ACCESS_KEY=your_secret
```

---

### Frontend Configuration

**File:** `frontend/.env.local`

**Template:** `frontend/.env.local.example`

**Required Variables:**
```bash
# Backend API (REQUIRED)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Optional Variables:**
```bash
# Feature Flags
NEXT_PUBLIC_ENABLE_DATA_SHARING=true
NEXT_PUBLIC_ENABLE_AI_CHAT=true
NEXT_PUBLIC_ENABLE_DATABASE_CONNECTORS=true

# API Configuration
NEXT_PUBLIC_API_TIMEOUT=30000
NEXT_PUBLIC_MAX_FILE_SIZE_MB=100

# Development
NEXT_PUBLIC_DEBUG=true
NEXT_PUBLIC_ENVIRONMENT=development
```

---

## Configuration Hierarchy

```
Root (.env.template - DEPRECATED, DO NOT USE)
  │
  ├── Backend (backend/.env.example → backend/.env)
  │   ├── Security settings
  │   ├── Database connection
  │   ├── Storage configuration
  │   └── Service integrations
  │
  └── Frontend (frontend/.env.local.example → frontend/.env.local)
      ├── API endpoint
      ├── Feature flags
      └── UI settings
```

---

## Variable Naming Convention

### Backend Variables:
- Direct use: `DATABASE_URL`, `JWT_SECRET_KEY`
- Service-specific: `MINDSDB_URL`, `GOOGLE_API_KEY`
- Storage: `S3_BUCKET_NAME`, `STORAGE_TYPE`

### Frontend Variables:
- **Always prefix with `NEXT_PUBLIC_`** for client-side access
- Example: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_DEBUG`

---

## Environment-Specific Settings

### Development
```bash
# Backend
DATABASE_URL=postgresql://dev:dev@localhost:5432/aishare_dev
DEBUG=true
SSL_DEVELOPMENT_MODE=true

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_DEBUG=true
NEXT_PUBLIC_ENVIRONMENT=development
```

### Staging
```bash
# Backend
DATABASE_URL=postgresql://staging_user:pass@staging-db:5432/aishare_staging
DEBUG=false
FORCE_SSL_IN_PRODUCTION=true

# Frontend
NEXT_PUBLIC_API_URL=https://api-staging.yourdomain.com
NEXT_PUBLIC_DEBUG=false
NEXT_PUBLIC_ENVIRONMENT=staging
```

### Production
```bash
# Backend
DATABASE_URL=postgresql://prod_user:secure_pass@prod-db:5432/aishare
DEBUG=false
FORCE_SSL_IN_PRODUCTION=true
ENCRYPTION_KEY=your-production-encryption-key

# Frontend
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_DEBUG=false
NEXT_PUBLIC_ENVIRONMENT=production
```

---

## Security Best Practices

### 1. Never Commit .env Files
```bash
# .gitignore already includes:
.env
.env.local
.env*.local
```

### 2. Rotate Keys Regularly
```bash
# Generate new encryption key
python scripts/migrate_encrypt_credentials.py --generate-key

# Update .env
ENCRYPTION_KEY=new-key-here

# Re-encrypt credentials
python scripts/migrate_encrypt_credentials.py
```

### 3. Use Environment-Specific Keys
- Different `JWT_SECRET_KEY` per environment
- Different `ENCRYPTION_KEY` per environment
- Different database credentials per environment

### 4. Secure Key Storage
- Use secret management service (AWS Secrets Manager, Azure Key Vault, etc.)
- Never share keys via email/chat
- Store backups encrypted

---

## Common Issues & Solutions

### Issue: "ENCRYPTION_KEY not found"
**Solution:**
```bash
cd backend
python scripts/migrate_encrypt_credentials.py --generate-key
# Copy output to .env
```

### Issue: "Database connection failed"
**Solution:**
```bash
# Check DATABASE_URL format:
postgresql://username:password@host:port/database

# Test connection:
psql $DATABASE_URL
```

### Issue: "Frontend can't reach backend"
**Solution:**
```bash
# Check NEXT_PUBLIC_API_URL in frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000

# Verify backend is running:
curl http://localhost:8000/api/health
```

### Issue: "MindsDB connection failed"
**Solution:**
```bash
# Check MindsDB is running:
curl http://localhost:47334

# Update backend/.env:
MINDSDB_URL=http://localhost:47334
```

---

## Deprecated Configuration Files

The following files are **DEPRECATED** and should **NOT** be used:

- ❌ `/.env.template` (root) - Use backend/.env.example instead
- ❌ `references/Auto-Analyst/.env*` - Legacy reference code

---

## Configuration Validation

### Validate Backend Configuration:
```bash
cd backend
python -c "
from app.core.config import settings
print('✅ Configuration loaded successfully')
print(f'Database: {settings.DATABASE_URL}')
print(f'Encryption: {"✅ Set" if settings.ENCRYPTION_KEY else "❌ Missing"}')
"
```

### Validate Frontend Configuration:
```bash
cd frontend
npm run dev
# Check console for "API URL: http://localhost:8000"
```

---

## Migration from Old Configuration

If you have old configuration files:

```bash
# 1. Backup old files
mkdir -p backup/config_$(date +%Y%m%d)
cp .env backup/config_$(date +%Y%m%d)/ 2>/dev/null || true

# 2. Create new backend config
cd backend
cp .env.example .env

# 3. Migrate important values manually
# Copy: DATABASE_URL, JWT_SECRET_KEY, GOOGLE_API_KEY, etc.

# 4. Add new encryption key
python scripts/migrate_encrypt_credentials.py --generate-key
# Add to .env: ENCRYPTION_KEY=...

# 5. Create new frontend config
cd ../frontend
cp .env.local.example .env.local

# 6. Update API URL if needed
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Environment Variables Reference

### Backend - Complete List

#### Security
```bash
JWT_SECRET_KEY=                    # JWT signing key (REQUIRED)
JWT_ALGORITHM=HS256               # JWT algorithm
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30 # Token expiry
ENCRYPTION_KEY=                    # Data encryption key (REQUIRED Phase 1+)
PASSWORD_MIN_LENGTH=8             # Min password length
```

#### Database
```bash
DATABASE_URL=                      # Database connection (REQUIRED)
DB_POOL_SIZE=10                   # Connection pool size
DB_MAX_OVERFLOW=20                # Max overflow connections
DB_POOL_PRE_PING=true             # Enable connection pre-ping
DB_POOL_RECYCLE=3600              # Connection recycle time (seconds)
DB_CONNECTION_TIMEOUT=30          # Connection timeout (seconds)
```

#### Admin
```bash
FIRST_SUPERUSER=                   # First admin email (REQUIRED)
FIRST_SUPERUSER_PASSWORD=          # First admin password (REQUIRED)
```

#### AI Integration
```bash
GOOGLE_API_KEY=                    # Google AI API key
OPENAI_API_KEY=                    # OpenAI API key (optional)
ANTHROPIC_API_KEY=                 # Anthropic API key (optional)
DEFAULT_GEMINI_MODEL=gemini-2.0-flash # Default Gemini model
```

#### MindsDB
```bash
MINDSDB_URL=http://localhost:47334 # MindsDB URL
MINDSDB_DATABASE=mindsdb           # MindsDB database name
MINDSDB_USERNAME=                   # MindsDB username (optional)
MINDSDB_PASSWORD=                   # MindsDB password (optional)
```

#### Storage
```bash
STORAGE_TYPE=local                 # Storage type: local or s3
STORAGE_BASE_PATH=../storage       # Base storage path
UPLOAD_PATH=../storage/uploads     # Upload directory
DATASET_STORAGE_PATH=../storage/datasets # Dataset storage

# S3 Configuration (if STORAGE_TYPE=s3)
S3_ENDPOINT_URL=                   # S3 endpoint URL
S3_BUCKET_NAME=                    # S3 bucket name
S3_ACCESS_KEY_ID=                  # S3 access key
S3_SECRET_ACCESS_KEY=              # S3 secret key
S3_REGION=us-east-1               # S3 region
S3_USE_SSL=true                    # Use SSL
```

#### Features
```bash
ENABLE_DATA_SHARING=true           # Enable data sharing
ENABLE_AI_CHAT=true                # Enable AI chat
ENABLE_DATABASE_CONNECTORS=true    # Enable DB connectors
SHARE_LINK_EXPIRY_HOURS=24        # Share link expiry
MAX_CHAT_SESSIONS_PER_DATASET=10  # Max chat sessions
```

#### Development
```bash
DEBUG=false                        # Debug mode
NODE_ENV=development               # Environment
SSL_DEVELOPMENT_MODE=true          # SSL dev mode
DISABLE_SSL_FOR_LOCALHOST=true     # Disable SSL for localhost
```

---

### Frontend - Complete List

```bash
# API
NEXT_PUBLIC_API_URL=http://localhost:8000 # Backend API URL (REQUIRED)

# Feature Flags
NEXT_PUBLIC_ENABLE_DATA_SHARING=true      # Enable data sharing
NEXT_PUBLIC_ENABLE_AI_CHAT=true           # Enable AI chat
NEXT_PUBLIC_ENABLE_DATABASE_CONNECTORS=true # Enable DB connectors

# API Configuration
NEXT_PUBLIC_API_TIMEOUT=30000             # API timeout (ms)
NEXT_PUBLIC_MAX_FILE_SIZE_MB=100          # Max file size (MB)

# Development
NEXT_PUBLIC_DEBUG=true                    # Debug mode
NEXT_PUBLIC_ENVIRONMENT=development       # Environment
```

---

## Summary

### Minimum Required Configuration:

**Backend (.env):**
```bash
JWT_SECRET_KEY=your-secret-key
ENCRYPTION_KEY=your-encryption-key
DATABASE_URL=postgresql://user:pass@localhost:5432/db
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_PASSWORD=your-password
```

**Frontend (.env.local):**
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

That's it! You're ready to run the application.

---

**For more information:**
- Phase 1 Setup: See [PHASE1_QUICK_START.md](PHASE1_QUICK_START.md)
- Security Configuration: See [PHASE1_REFACTORING_COMPLETE.md](PHASE1_REFACTORING_COMPLETE.md)
- Full Documentation: See [REFACTORING_INDEX.md](REFACTORING_INDEX.md)
