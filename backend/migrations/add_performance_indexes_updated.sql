-- Database Performance Optimization Migration (Updated for Actual Schema)
-- Add indexes for common query patterns
-- Expected Performance Improvement: 10-100x on indexed queries

-- ============================================================
-- DATASET INDEXES (High Priority - Most Queried Table)
-- ============================================================

-- Composite index for organization filtering with status
-- Used in: List datasets by org, exclude deleted datasets
CREATE INDEX IF NOT EXISTS idx_dataset_org_status
ON datasets(organization_id, is_deleted, is_active);

-- Index on created_at for sorting and time-based queries
CREATE INDEX IF NOT EXISTS idx_dataset_created
ON datasets(created_at DESC);

-- Unique index on share_token for public access lookups (already exists, but ensuring)
-- CREATE INDEX IF NOT EXISTS idx_dataset_share_token
-- ON datasets(share_token)
-- WHERE share_token IS NOT NULL;

-- Index on owner_id for user's datasets queries
CREATE INDEX IF NOT EXISTS idx_dataset_owner
ON datasets(owner_id);

-- Index on type for filtering by dataset type
CREATE INDEX IF NOT EXISTS idx_dataset_type
ON datasets(type);

-- Index on status for filtering active/processing datasets
CREATE INDEX IF NOT EXISTS idx_dataset_status
ON datasets(status);

-- ============================================================
-- DATASET ACCESS LOG INDEXES (High Priority - Rapidly Growing)
-- ============================================================

-- Composite index for dataset access history queries
-- Used in: Get access logs for a dataset, analytics queries
CREATE INDEX IF NOT EXISTS idx_access_dataset_time
ON dataset_access_logs(dataset_id, created_at DESC);

-- Index on user_id for user activity queries
CREATE INDEX IF NOT EXISTS idx_access_user
ON dataset_access_logs(user_id)
WHERE user_id IS NOT NULL;

-- Index on access_type for filtering by action type
CREATE INDEX IF NOT EXISTS idx_access_type
ON dataset_access_logs(access_type);

-- Index on share_token for public access analytics
CREATE INDEX IF NOT EXISTS idx_access_share_token
ON dataset_access_logs(share_token)
WHERE share_token IS NOT NULL;

-- Composite index for session tracking
CREATE INDEX IF NOT EXISTS idx_access_session
ON dataset_access_logs(session_id, created_at DESC)
WHERE session_id IS NOT NULL;

-- ============================================================
-- USER INDEXES (Medium Priority - Auth & Org Queries)
-- ============================================================

-- Index on organization_id for org member queries
CREATE INDEX IF NOT EXISTS idx_user_org
ON users(organization_id)
WHERE organization_id IS NOT NULL;

-- Index on is_active for filtering active users
CREATE INDEX IF NOT EXISTS idx_user_active
ON users(is_active);

-- Index on role for role-based queries
CREATE INDEX IF NOT EXISTS idx_user_role
ON users(role);

-- Composite index for org + active users
CREATE INDEX IF NOT EXISTS idx_user_org_active
ON users(organization_id, is_active)
WHERE organization_id IS NOT NULL;

-- ============================================================
-- ACTIVITY LOG INDEXES (High Priority - Analytics)
-- ============================================================

-- Index on created_at (not timestamp) for time-based queries
CREATE INDEX IF NOT EXISTS idx_activity_time
ON activity_logs(created_at DESC);

-- Composite index for user activity queries
CREATE INDEX IF NOT EXISTS idx_activity_user_time
ON activity_logs(user_id, created_at DESC);

-- Index on activity_type for filtering by action
CREATE INDEX IF NOT EXISTS idx_activity_type
ON activity_logs(activity_type);

-- Composite index for organization activity
CREATE INDEX IF NOT EXISTS idx_activity_org_time
ON activity_logs(organization_id, created_at DESC)
WHERE organization_id IS NOT NULL;

-- ============================================================
-- USAGE METRICS INDEXES (Medium Priority - Analytics)
-- ============================================================

-- Index on created_at for metrics queries
CREATE INDEX IF NOT EXISTS idx_usage_created
ON usage_metrics(created_at DESC);

-- Composite index for organization metrics
CREATE INDEX IF NOT EXISTS idx_usage_org_created
ON usage_metrics(organization_id, created_at DESC)
WHERE organization_id IS NOT NULL;

-- Index on metric_type for filtering
CREATE INDEX IF NOT EXISTS idx_usage_type
ON usage_metrics(metric_type);

-- Index on period_start for time-series queries
CREATE INDEX IF NOT EXISTS idx_usage_period
ON usage_metrics(period_start DESC, period_end DESC);

-- ============================================================
-- CHAT MESSAGE INDEXES (Medium Priority - Chat History)
-- ============================================================

-- Index on session_id for chat history retrieval
CREATE INDEX IF NOT EXISTS idx_chat_session
ON chat_messages(session_id, created_at DESC);

-- ============================================================
-- DATASET DOWNLOAD INDEXES (Medium Priority - Download Tracking)
-- ============================================================

-- Index on download_token is already unique (ix_dataset_downloads_download_token)
-- Composite index for dataset download history (idx_dataset_downloads_dataset already exists)
-- Index on user downloads
CREATE INDEX IF NOT EXISTS idx_download_user
ON dataset_downloads(user_id, created_at DESC)
WHERE user_id IS NOT NULL;

-- Index on download_status for active downloads
CREATE INDEX IF NOT EXISTS idx_download_status
ON dataset_downloads(download_status);

-- ============================================================
-- DATASET MODEL INDEXES (Low Priority - ML Operations)
-- ============================================================

-- Index on dataset_id for dataset models (already exists: ix_dataset_models_*)
-- Index on status for model training queries (already exists)

-- ============================================================
-- ORGANIZATION INDEXES (Low Priority - Admin Queries)
-- ============================================================

-- Organization indexes already exist (idx_organizations_*)

-- ============================================================
-- DATABASE CONNECTOR INDEXES (Low Priority - Data Connections)
-- ============================================================

-- Index on organization_id for org connectors
CREATE INDEX IF NOT EXISTS idx_connector_org
ON database_connectors(organization_id);

-- Index on is_active for active connectors
CREATE INDEX IF NOT EXISTS idx_connector_active
ON database_connectors(is_active);

-- Index on connector_type for filtering
CREATE INDEX IF NOT EXISTS idx_connector_type
ON database_connectors(connector_type);

-- ============================================================
-- ACCESS REQUEST INDEXES (Medium Priority - Data Access)
-- ============================================================

-- Composite index for user's pending requests
CREATE INDEX IF NOT EXISTS idx_request_user_status
ON access_requests(requester_id, status);

-- Composite index for dataset pending requests
CREATE INDEX IF NOT EXISTS idx_request_dataset_status
ON access_requests(dataset_id, status);

-- Index on created_at for sorting
CREATE INDEX IF NOT EXISTS idx_request_created
ON access_requests(created_at DESC);

-- ============================================================
-- NOTIFICATION INDEXES (Medium Priority - User Notifications)
-- ============================================================

-- Composite index for user's unread notifications
CREATE INDEX IF NOT EXISTS idx_notif_user_read
ON notifications(recipient_id, is_read, created_at DESC);

-- Index on notification_type for filtering
CREATE INDEX IF NOT EXISTS idx_notif_type
ON notifications(notification_type);

-- ============================================================
-- DATASET ACCESS INDEXES (for dataset_access table)
-- ============================================================

-- Most indexes already exist (idx_dataset_access_*)

-- ============================================================
-- CHAT INTERACTIONS INDEXES
-- ============================================================

-- Index on dataset for chat history
CREATE INDEX IF NOT EXISTS idx_chat_interactions_dataset
ON chat_interactions(dataset_id, timestamp DESC);

-- Index on user for user chat history
CREATE INDEX IF NOT EXISTS idx_chat_interactions_user
ON chat_interactions(user_id, timestamp DESC)
WHERE user_id IS NOT NULL;

-- Index on session for session history
CREATE INDEX IF NOT EXISTS idx_chat_interactions_session
ON chat_interactions(session_id, timestamp DESC)
WHERE session_id IS NOT NULL;

-- ============================================================
-- FILE UPLOADS INDEXES
-- ============================================================

-- Index on user uploads
CREATE INDEX IF NOT EXISTS idx_file_uploads_user
ON file_uploads(user_id, created_at DESC);

-- Index on dataset files
CREATE INDEX IF NOT EXISTS idx_file_uploads_dataset
ON file_uploads(dataset_id, created_at DESC);

-- Index on organization files
CREATE INDEX IF NOT EXISTS idx_file_uploads_org
ON file_uploads(organization_id, created_at DESC);

-- Index on upload status
CREATE INDEX IF NOT EXISTS idx_file_uploads_status
ON file_uploads(upload_status);

-- ============================================================
-- API USAGE INDEXES
-- ============================================================

-- Index on timestamp for time-series queries
CREATE INDEX IF NOT EXISTS idx_api_usage_time
ON api_usage(timestamp DESC);

-- Index on user for user API usage
CREATE INDEX IF NOT EXISTS idx_api_usage_user
ON api_usage(user_id, timestamp DESC)
WHERE user_id IS NOT NULL;

-- Index on organization API usage
CREATE INDEX IF NOT EXISTS idx_api_usage_org
ON api_usage(organization_id, timestamp DESC)
WHERE organization_id IS NOT NULL;

-- Index on endpoint for endpoint analytics
CREATE INDEX IF NOT EXISTS idx_api_usage_endpoint
ON api_usage(endpoint, timestamp DESC);

-- ============================================================
-- DATASET CHAT SESSIONS INDEXES
-- ============================================================

-- Index on dataset sessions
CREATE INDEX IF NOT EXISTS idx_chat_sessions_dataset
ON dataset_chat_sessions(dataset_id, created_at DESC);

-- Index on active sessions
CREATE INDEX IF NOT EXISTS idx_chat_sessions_active
ON dataset_chat_sessions(is_active, created_at DESC)
WHERE is_active = true;

-- ============================================================
-- AUDIT LOGS INDEXES
-- ============================================================

-- Index on timestamp for audit queries
CREATE INDEX IF NOT EXISTS idx_audit_time
ON audit_logs(timestamp DESC);

-- Index on user audit logs
CREATE INDEX IF NOT EXISTS idx_audit_user
ON audit_logs(user_id, timestamp DESC);

-- Index on dataset audit logs
CREATE INDEX IF NOT EXISTS idx_audit_dataset
ON audit_logs(dataset_id, timestamp DESC);

-- Index on action type
CREATE INDEX IF NOT EXISTS idx_audit_action
ON audit_logs(action);

-- ============================================================
-- SYSTEM METRICS INDEXES
-- ============================================================

-- Index on timestamp for metrics time-series
CREATE INDEX IF NOT EXISTS idx_system_metrics_time
ON system_metrics(timestamp DESC);

-- ============================================================
-- END OF MIGRATION
-- ============================================================
