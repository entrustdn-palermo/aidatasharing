import { apiClient } from './client';

export const proxyConnectorsAPI = {
  getProxyConnectors: async () => {
    const response = await apiClient.get('/api/proxy-connectors');
    return response.data;
  },

  createProxyConnector: async (connectorData: {
    name: string;
    connector_type: string;
    description?: string;
    real_connection_config: Record<string, any>;
    real_credentials: Record<string, any>;
    is_public?: boolean;
    allowed_operations?: string[];
  }) => {
    const response = await apiClient.post('/api/proxy-connectors', connectorData);
    return response.data;
  },

  getProxyConnector: async (connectorId: number) => {
    const response = await apiClient.get(`/api/proxy-connectors/${connectorId}`);
    return response.data;
  },

  deleteProxyConnector: async (connectorId: number) => {
    const response = await apiClient.delete(`/api/proxy-connectors/${connectorId}`);
    return response.data;
  },

  executeProxyOperation: async (proxyId: string, operationData: {
    operation_type: string;
    operation_data: Record<string, any>;
  }) => {
    const response = await apiClient.post(`/api/proxy/${proxyId}/execute`, operationData);
    return response.data;
  },

  getProxyAnalytics: async (connectorId: number) => {
    const response = await apiClient.get(`/api/proxy-connectors/${connectorId}/analytics`);
    return response.data;
  },
};
