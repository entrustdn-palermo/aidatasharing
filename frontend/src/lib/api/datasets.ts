import { apiClient } from './client';

export const datasetsAPI = {
  getDatasets: async (params?: {
    skip?: number;
    limit?: number;
    sharing_level?: string;
    dataset_type?: string;
  }) => {
    const response = await apiClient.get('/api/datasets', { params });
    return response.data;
  },

  createDataset: async (datasetData: {
    name: string;
    description?: string;
    type: string;
    sharing_level?: string;
    source_url?: string;
    connection_params?: Record<string, any>;
    schema_info?: Record<string, any>;
    allow_download?: boolean;
    allow_api_access?: boolean;
  }) => {
    const response = await apiClient.post('/api/datasets', datasetData);
    return response.data;
  },

  getDataset: async (datasetId: number) => {
    const response = await apiClient.get(`/api/datasets/${datasetId}`);
    return response.data;
  },

  getDatasetMetadata: async (datasetId: number) => {
    const response = await apiClient.get(`/api/datasets/${datasetId}/metadata/detailed`);
    return response.data;
  },

  getDatasetPreview: async (datasetId: number) => {
    const response = await apiClient.get(`/api/datasets/${datasetId}/preview`);
    return response.data;
  },

  editDataset: async (datasetId: number, editData: {
    name?: string;
    description?: string;
    content?: string;
  }) => {
    const response = await apiClient.put(`/api/datasets/${datasetId}/edit`, editData);
    return response.data;
  },

  reuploadDataset: async (datasetId: number, file: File, metadata: {
    name?: string;
    description?: string;
  }) => {
    const formData = new FormData();
    formData.append('file', file);
    Object.entries(metadata).forEach(([key, value]) => {
      if (value !== undefined) {
        formData.append(key, value.toString());
      }
    });

    const response = await apiClient.put(`/api/datasets/${datasetId}/reupload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  updateDataset: async (datasetId: number, updateData: {
    name?: string;
    description?: string;
    sharing_level?: string;
    allow_download?: boolean;
    allow_api_access?: boolean;
    schema_info?: Record<string, any>;
  }) => {
    const response = await apiClient.put(`/api/datasets/${datasetId}`, updateData);
    return response.data;
  },

  deleteDataset: async (datasetId: number) => {
    const response = await apiClient.delete(`/api/datasets/${datasetId}`);
    return response.data;
  },

  uploadFile: async (file: File, metadata: {
    name: string;
    description?: string;
    sharing_level?: string;
  }) => {
    const formData = new FormData();
    formData.append('file', file);
    Object.entries(metadata).forEach(([key, value]) => {
      if (value !== undefined) {
        formData.append(key, value.toString());
      }
    });

    const response = await apiClient.post('/api/datasets/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  uploadDataset: async (file: File, metadata: {
    name: string;
    description?: string;
    sharing_level?: string;
  }) => {
    const formData = new FormData();
    formData.append('file', file);
    Object.entries(metadata).forEach(([key, value]) => {
      if (value !== undefined) {
        formData.append(key, value.toString());
      }
    });

    const response = await apiClient.post('/api/datasets/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  uploadMultipleDatasets: async (files: File[], metadata: {
    name: string;
    description?: string;
    sharing_level?: string;
  }) => {
    const formData = new FormData();

    files.forEach((file) => {
      formData.append('files', file);
    });

    Object.entries(metadata).forEach(([key, value]) => {
      if (value !== undefined) {
        formData.append(key, value.toString());
      }
    });

    const response = await apiClient.post('/api/datasets/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  chatWithDataset: async (datasetId: number, message: string, agentName?: string, useAgents: boolean = true) => {
    const response = await apiClient.post(`/api/datasets/${datasetId}/chat`, {
      message,
      agent_name: agentName,
      use_agents: useAgents
    });
    return response.data;
  },

  visualizeDataset: async (datasetId: number, visualizationType?: string, maxVisualizations: number = 4) => {
    const params: any = { max_visualizations: maxVisualizations };
    if (visualizationType) {
      params.visualization_type = visualizationType;
    }
    const response = await apiClient.get(`/api/datasets/${datasetId}/visualize`, { params });
    return response.data;
  },

  getDatasetModels: async (datasetId: number) => {
    const response = await apiClient.get(`/api/datasets/${datasetId}/models`);
    return response.data;
  },

  recreateDatasetModels: async (datasetId: number) => {
    const response = await apiClient.post(`/api/datasets/${datasetId}/recreate-models`);
    return response.data;
  },

  initiateDownload: async (datasetId: number) => {
    const response = await apiClient.get(`/api/datasets/${datasetId}/download`);
    return response.data;
  },

  getDownloadProgress: async (downloadToken: string) => {
    const response = await apiClient.get(`/api/datasets/download/${downloadToken}/progress`);
    return response.data;
  },

  retryDownload: async (downloadToken: string) => {
    const response = await apiClient.post(`/api/datasets/download/${downloadToken}/retry`);
    return response.data;
  },

  transferOwnership: async (datasetId: number, newOwnerId: number) => {
    const response = await apiClient.post(`/api/datasets/${datasetId}/transfer-ownership`, {
      new_owner_id: newOwnerId
    });
    return response.data;
  },

  getDatasetStats: async (datasetId: number, includeDownloads: boolean = true, includeAccessLogs: boolean = false) => {
    const params = {
      include_downloads: includeDownloads,
      include_access_logs: includeAccessLogs
    };
    const response = await apiClient.get(`/api/datasets/${datasetId}/stats`, { params });
    return response.data;
  },

  getShareTokens: async (datasetId: number) => {
    const response = await apiClient.get(`/api/datasets/${datasetId}/share-tokens`);
    return response.data;
  },

  generateShareToken: async (datasetId: number) => {
    const response = await apiClient.post(`/api/datasets/${datasetId}/generate-share-token`);
    return response.data;
  },

  revokeShareToken: async (datasetId: number, tokenId: number | string) => {
    const response = await apiClient.delete(`/api/datasets/${datasetId}/share-tokens/${tokenId}`);
    return response.data;
  },
};
