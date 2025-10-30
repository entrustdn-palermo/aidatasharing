import { apiClient } from './client';

export const analyticsAPI = {
  getOrganizationAnalytics: async () => {
    const response = await apiClient.get('/api/analytics/organization');
    return response.data;
  },

  getUserActivity: async (params?: {
    start_date?: string;
    end_date?: string;
    user_id?: number;
  }) => {
    const response = await apiClient.get('/api/analytics/user-activity', { params });
    return response.data;
  },

  getDatasetUsage: async (params?: {
    start_date?: string;
    end_date?: string;
    dataset_id?: number;
  }) => {
    const response = await apiClient.get('/api/analytics/dataset-usage', { params });
    return response.data;
  },

  getModelPerformance: async (params?: {
    start_date?: string;
    end_date?: string;
    model_id?: number;
  }) => {
    const response = await apiClient.get('/api/analytics/model-performance', { params });
    return response.data;
  },
};
