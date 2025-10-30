import { apiClient } from './client';

export const dataConnectorsAPI = {
  getConnectors: async (params?: {
    connector_type?: string;
    active_only?: boolean;
    include_datasets?: boolean;
  }) => {
    const response = await apiClient.get('/api/connectors', { params });
    return response.data;
  },

  createConnector: async (connectorData: {
    name: string;
    connector_type: string;
    description?: string;
    connection_config: Record<string, any>;
    credentials?: Record<string, any>;
  }) => {
    const response = await apiClient.post('/api/connectors', connectorData);
    return response.data;
  },

  createSimplifiedConnector: async (connectorData: {
    name: string;
    connector_type: string;
    description?: string;
    connection_url: string;
  }) => {
    const response = await apiClient.post('/api/connectors/simplified', connectorData);
    return response.data;
  },

  getConnector: async (connectorId: number) => {
    const response = await apiClient.get(`/api/connectors/${connectorId}`);
    return response.data;
  },

  updateConnector: async (connectorId: number, updateData: {
    name?: string;
    description?: string;
    connection_config?: Record<string, any>;
    credentials?: Record<string, any>;
    is_active?: boolean;
  }) => {
    const response = await apiClient.put(`/api/connectors/${connectorId}`, updateData);
    return response.data;
  },

  deleteConnector: async (connectorId: number) => {
    const response = await apiClient.delete(`/api/connectors/${connectorId}`);
    return response.data;
  },

  testConnector: async (connectorId: number) => {
    const response = await apiClient.post(`/api/connectors/${connectorId}/test`);
    return response.data;
  },

  syncWithMindsDB: async (connectorId: number) => {
    const response = await apiClient.post(`/api/connectors/${connectorId}/sync-mindsdb`);
    return response.data;
  },

  createDatasetFromConnector: async (connectorId: number, datasetData: {
    dataset_name: string;
    description?: string;
    table_or_endpoint?: string;
    sharing_level?: string;
  }) => {
    const response = await apiClient.post(`/api/connectors/${connectorId}/create-dataset`, datasetData);
    return response.data;
  },
};
