/**
 * Dataset Types
 */

export interface Dataset {
  id: number;
  name: string;
  description?: string;
  type: DatasetType;
  status: DatasetStatus;
  owner_id: number;
  organization_id: number;
  sharing_level: SharingLevel;
  size_bytes?: number;
  row_count?: number;
  column_count?: number;
  file_path?: string;
  created_at: string;
  updated_at: string;
  last_accessed?: string;

  // Soft delete
  is_active: boolean;
  is_deleted: boolean;
  deleted_at?: string;

  // AI features
  ai_processing_status: AIProcessingStatus;
  ai_chat_enabled: boolean;

  // Sharing
  public_share_enabled: boolean;
  share_token?: string;
  share_view_count: number;

  // Access control
  allow_download: boolean;
  allow_api_access: boolean;
  allow_ai_chat: boolean;

  // Download tracking
  download_count: number;
  last_downloaded_at?: string;
}

export enum DatasetType {
  CSV = "csv",
  JSON = "json",
  EXCEL = "excel",
  PARQUET = "parquet",
  DATABASE = "database",
  API = "api",
  PDF = "pdf",
  DOCX = "docx",
  TXT = "txt",
  IMAGE = "image",
}

export enum DatasetStatus {
  ACTIVE = "active",
  INACTIVE = "inactive",
  PROCESSING = "processing",
  ERROR = "error",
  ARCHIVED = "archived",
  DELETED = "deleted",
}

export enum SharingLevel {
  PRIVATE = "private",
  ORGANIZATION = "organization",
  PUBLIC = "public",
}

export enum AIProcessingStatus {
  NOT_PROCESSED = "not_processed",
  PROCESSING = "processing",
  READY = "ready",
  ERROR = "error",
}

export interface DatasetListParams {
  skip?: number;
  limit?: number;
  sharing_level?: SharingLevel;
  dataset_type?: DatasetType;
  status?: DatasetStatus;
}

export interface DatasetListResponse {
  datasets: Dataset[];
  total: number;
  skip: number;
  limit: number;
}

export interface CreateDatasetRequest {
  name: string;
  description?: string;
  type: DatasetType;
  sharing_level?: SharingLevel;
  source_url?: string;
  connection_params?: Record<string, any>;
  schema_info?: Record<string, any>;
  allow_download?: boolean;
  allow_api_access?: boolean;
}

export interface UpdateDatasetRequest {
  name?: string;
  description?: string;
  sharing_level?: SharingLevel;
  allow_download?: boolean;
  allow_api_access?: boolean;
  schema_info?: Record<string, any>;
}

export interface UploadDatasetMetadata {
  name: string;
  description?: string;
  sharing_level?: SharingLevel;
}

export interface DatasetMetadata {
  row_count: number;
  column_count: number;
  file_size: number;
  columns: ColumnInfo[];
  preview: any[][];
  schema_info: Record<string, any>;
}

export interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  unique?: boolean;
  examples?: any[];
}

export interface DatasetPreview {
  columns: string[];
  rows: any[][];
  total_rows: number;
}

export interface DatasetStats {
  total_downloads: number;
  total_views: number;
  unique_users: number;
  recent_activity: ActivityLog[];
}

export interface ActivityLog {
  timestamp: string;
  action: string;
  user_id?: number;
  user_email?: string;
}

export interface ShareToken {
  id: number;
  token: string;
  created_at: string;
  expires_at?: string;
  view_count: number;
}
