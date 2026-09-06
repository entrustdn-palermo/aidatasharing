# Database Migrations

This directory contains database migration scripts for the AI Share Platform.

## Essential Files

### Core Migrations
- **`current_schema_migration.py`** - Complete current schema migration (recommended)
- **`consolidated_migration_postgresql.py`** - Legacy consolidated migration (older version)

### Management Scripts
- **`rls_manager.py`** - Row Level Security management
- **`clean_migrations.py`** - Migration cleanup utility

## Usage

### Initial Setup (New Database)
```bash
# Run the current schema migration
python migrations/current_schema_migration.py
```

### RLS Management
```bash
# Enable RLS on all tables
python migrations/rls_manager.py enable

# Verify RLS status
python migrations/rls_manager.py verify
```

### Cleanup
```bash
# Clean up old migration files
python migrations/clean_migrations.py
```

## Database Schema Overview

### Core Tables
- **organizations** - Organization/tenant management
- **users** - User accounts and authentication
- **datasets** - Dataset metadata and management
- **dataset_files** - File management for datasets

### Analytics & Monitoring
- **activity_logs** - User activity tracking
- **usage_metrics** - Resource usage metrics
- **usage_stats** - Aggregated usage statistics
- **api_usage** - API call tracking
- **system_metrics** - System performance metrics

### AI & Chat Features
- **chat_interactions** - AI chat conversations
- **dataset_chat_sessions** - Chat session management
- **llm_configurations** - AI model configurations

### Data Access & Sharing
- **dataset_access_logs** - Dataset access tracking
- **dataset_downloads** - Download history
- **dataset_share_accesses** - Sharing access logs
- **share_access_sessions** - Share session management

### System Management
- **configurations** - Application configuration
- **audit_logs** - System audit trail
- **notifications** - User notifications
- **access_requests** - Access request management

### Proxy & Connectors (Optional)
- **proxy_connectors** - External service connectors
- **proxy_credential_vault** - Secure credential storage
- **shared_proxy_links** - Shared connector access
- **proxy_access_logs** - Proxy usage logs

## Security

All tables have Row Level Security (RLS) enabled with appropriate policies:
- **User data**: Users can only access their own data
- **Dataset data**: Access based on ownership and sharing levels
- **System data**: Admin-only access
- **Configuration data**: Read-only for most users

## Archive

Old and redundant migration files have been moved to the `archive/` directory to keep the migrations folder clean and organized.

## Environment Variables

Required environment variables:
- `DATABASE_URL` - PostgreSQL connection string

## Notes

- All migrations are idempotent (safe to run multiple times)
- RLS policies can be customized based on specific security requirements
- The current schema supports multi-tenant architecture with organizations
- All timestamps use UTC timezone