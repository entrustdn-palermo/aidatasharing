import { apiClient } from './client';

export const mindsdbAPI = {
  getStatus: async () => {
    const response = await apiClient.get('/api/mindsdb/status');
    return response.data;
  },

  getModels: async () => {
    const response = await apiClient.get('/api/mindsdb/models');
    return response.data;
  },

  createModel: async (modelData: { name: string; query: string; engine?: string }) => {
    const response = await apiClient.post('/api/mindsdb/models', modelData);
    return response.data;
  },

  getModelInfo: async (modelName: string) => {
    const response = await apiClient.get(`/api/mindsdb/models/${modelName}`);
    return response.data;
  },

  predict: async (modelName: string, data: Record<string, any>) => {
    const response = await apiClient.post(`/api/mindsdb/models/${modelName}/predict`, data);
    return response.data;
  },

  deleteModel: async (modelName: string) => {
    const response = await apiClient.delete(`/api/mindsdb/models/${modelName}`);
    return response.data;
  },

  getDatabases: async () => {
    const response = await apiClient.get('/api/mindsdb/databases');
    return response.data;
  },

  createDatabase: async (dbData: { name: string; engine: string; parameters: Record<string, any> }) => {
    const response = await apiClient.post('/api/mindsdb/databases', dbData);
    return response.data;
  },

  executeSQL: async (query: string) => {
    const response = await apiClient.post('/api/mindsdb/sql', { query });
    return response.data;
  },

  // Gemini Flash 2 Integration
  initializeGemini: async () => {
    const response = await apiClient.post('/api/mindsdb/gemini/initialize');
    return response.data;
  },

  geminiChat: async (prompt: string) => {
    const response = await apiClient.post('/api/mindsdb/gemini/chat', { prompt });
    return response.data;
  },

  naturalLanguageToSQL: async (query: string, context?: string) => {
    const response = await apiClient.post('/api/mindsdb/gemini/nl-to-sql', { query, context });
    return response.data;
  },

  createGeminiModel: async (modelData: {
    name: string;
    model_type?: string;
    prompt_template?: string;
    mode?: string;
  }) => {
    const response = await apiClient.post('/api/mindsdb/gemini/models', modelData);
    return response.data;
  },

  queryGeminiModel: async (modelName: string, inputData: Record<string, any>) => {
    const response = await apiClient.post(`/api/mindsdb/gemini/models/${modelName}/query`, { input_data: inputData });
    return response.data;
  },

  getGeminiEngineStatus: async () => {
    const response = await apiClient.get('/api/mindsdb/gemini/engine/status');
    return response.data;
  },

  createGeminiVisionModel: async (modelData: {
    name: string;
    img_url_column?: string;
    context_column?: string;
  }) => {
    const response = await apiClient.post('/api/mindsdb/gemini/vision/model', modelData);
    return response.data;
  },

  createGeminiEmbeddingModel: async (modelData: {
    name: string;
    question_column?: string;
    context_column?: string;
  }) => {
    const response = await apiClient.post('/api/mindsdb/gemini/embedding/model', modelData);
    return response.data;
  },
};
