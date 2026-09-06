/**
 * Common API Types
 * Shared types used across all API modules
 */

export interface ApiResponse<T = any> {
  data?: T;
  error?: string;
  message?: string;
  status: "success" | "error";
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  skip?: number;
  has_more: boolean;
}

export interface ErrorResponse {
  detail: string;
  status_code: number;
}

export type AsyncResult<T> = Promise<T>;

export interface TimeRange {
  start_date?: string;
  end_date?: string;
}

export interface ListParams {
  skip?: number;
  limit?: number;
  search?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}
