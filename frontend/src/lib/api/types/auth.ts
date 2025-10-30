/**
 * Authentication & Authorization Types
 */

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  organization_id?: number;
  create_organization?: boolean;
  organization_name?: string;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  organization_id: number | null;
  role: UserRole;
  created_at: string;
  updated_at?: string;
  last_login?: string;
}

export enum UserRole {
  ADMIN = "admin",
  MEMBER = "member",
  VIEWER = "viewer",
}

export interface Organization {
  id: number;
  name: string;
  slug: string;
  type: string;
  description?: string;
  is_active: boolean;
  created_at: string;
  website?: string;
  contact_email?: string;
}
