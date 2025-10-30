import { apiClient } from './client';

export const agentsAPI = {
  getAvailableAgents: async () => {
    const response = await apiClient.get('/api/agents/');
    return response.data;
  },

  chatWithDatasetAgents: async (datasetId: number, message: string, agentName?: string) => {
    const response = await apiClient.post(`/api/agents/datasets/${datasetId}/chat`, {
      message,
      agent_name: agentName
    });
    return response.data;
  },

  executeAgentCode: async (datasetId: number, code: string) => {
    const response = await apiClient.post(`/api/agents/datasets/${datasetId}/execute`, {
      code
    });
    return response.data;
  },

  getAgentTemplates: async () => {
    const response = await apiClient.get('/api/agents/templates');
    return response.data;
  },

  getDatasetChatHistory: async (datasetId: number, limit: number = 50, offset: number = 0) => {
    const response = await apiClient.get(`/api/agents/datasets/${datasetId}/chat/history`, {
      params: { limit, offset }
    });
    return response.data;
  },

  healthCheck: async () => {
    const response = await apiClient.get('/api/agents/health');
    return response.data;
  }
};
