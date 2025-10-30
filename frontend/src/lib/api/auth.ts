/**
 * Authentication API
 * Handles user login, registration, and profile
 */

import { apiClient } from './client';

export const authAPI = {
  login: async (email: string, password: string) => {
    const formData = new FormData();
    formData.append('username', email);
    formData.append('password', password);

    const response = await apiClient.post('/api/auth/login', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    return response.data;
  },

  register: async (userData: {
    email: string;
    password: string;
    full_name: string;
    organization_id?: number;
    create_organization?: boolean;
    organization_name?: string;
  }) => {
    const response = await apiClient.post('/api/auth/register', userData);
    return response.data;
  },

  getMe: async () => {
    const response = await apiClient.get('/api/auth/me');
    return response.data;
  },
};
