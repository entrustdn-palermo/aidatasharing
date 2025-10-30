import { apiClient } from './client';

export const modelsAPI = {
  getModels: async (params?: {
    skip?: number;
    limit?: number;
    status?: string;
  }) => {
    const response = await apiClient.get('/api/models', { params });
    return response.data;
  },

  createModel: async (modelData: {
    name: string;
    dataset_id: number;
    target_column: string;
    feature_columns?: string[];
    model_type: string;
    engine?: string;
    model_params?: Record<string, any>;
  }) => {
    const response = await apiClient.post('/api/models', modelData);
    return response.data;
  },

  getModel: async (modelId: number) => {
    const response = await apiClient.get(`/api/models/${modelId}`);
    return response.data;
  },

  deleteModel: async (modelId: number) => {
    const response = await apiClient.delete(`/api/models/${modelId}`);
    return response.data;
  },

  predict: async (modelId: number, data: Record<string, any>) => {
    const response = await apiClient.post(`/api/models/${modelId}/predict`, data);
    return response.data;
  },

  retrainModel: async (modelId: number) => {
    const response = await apiClient.post(`/api/models/${modelId}/retrain`);
    return response.data;
  },
};
