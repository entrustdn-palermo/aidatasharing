import { apiClient } from './client';

export const dataSharingAPI = {
  createShareLink: async (data: {
    dataset_id: number;
    password?: string;
    enable_chat?: boolean;
  }) => {
    const response = await apiClient.post('/api/data-sharing/create-share-link', data);
    return response.data;
  },

  getSharedDataset: async (shareToken: string, password?: string) => {
    const params = password ? { password } : {};
    const response = await apiClient.get(`/api/data-sharing/shared/${shareToken}`, { params });
    return response.data;
  },

  getSharedDatasetData: async (shareToken: string, page: number = 1, limit: number = 50) => {
    const response = await apiClient.get(`/api/data-sharing/shared/${shareToken}/data`, {
      params: { page, limit }
    });
    return response.data;
  },

  accessSharedDatasetWithPassword: async (shareToken: string, password: string) => {
    const response = await apiClient.post(`/api/data-sharing/shared/${shareToken}/access`, {
      password
    });
    return response.data;
  },

  getMySharedDatasets: async (includeInvalid: boolean = true) => {
    const response = await apiClient.get(`/api/data-sharing/my-shared-datasets?include_invalid=${includeInvalid}`);
    return response.data;
  },

  disableSharing: async (datasetId: number) => {
    const response = await apiClient.delete(`/api/data-sharing/shared/${datasetId}/disable`);
    return response.data;
  },

  getDatasetAnalytics: async (datasetId: number) => {
    const response = await apiClient.get(`/api/data-sharing/analytics/${datasetId}`);
    return response.data;
  },

  // Public endpoints (no auth required)
  getSharedDatasetInfo: async (shareToken: string) => {
    const response = await apiClient.get(`/api/data-sharing/public/shared/${shareToken}/info`);
    return response.data;
  },

  getPublicSharedDataset: async (shareToken: string, password?: string) => {
    const params = password ? { password } : {};
    const response = await apiClient.get(`/api/data-sharing/public/shared/${shareToken}`, { params });
    return response.data;
  },

  accessPublicSharedDatasetWithPassword: async (shareToken: string, password: string) => {
    const response = await apiClient.get(`/api/data-sharing/public/shared/${shareToken}`, {
      params: { password }
    });
    return response.data;
  },

  chatWithSharedDataset: async (shareToken: string, message: string, sessionToken?: string) => {
    const response = await apiClient.post(`/api/data-sharing/public/shared/${shareToken}/chat`, {
      message,
      session_token: sessionToken
    });
    return response.data;
  },

  getSharedDatasetFiles: async (shareToken: string, password?: string) => {
    const params = password ? { password } : {};
    const response = await apiClient.get(`/api/data-sharing/public/shared/${shareToken}/files`, { params });
    return response.data;
  },

  downloadIndividualFile: async (shareToken: string, fileId: number, password?: string) => {
    const params = password ? { password } : {};
    const response = await apiClient.get(`/api/data-sharing/public/shared/${shareToken}/files/${fileId}/download`, {
      params,
      responseType: 'blob'
    });

    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;

    const contentDisposition = response.headers['content-disposition'];
    const filename = contentDisposition
      ? contentDisposition.split('filename="')[1]?.split('"')[0]
      : `file_${fileId}`;

    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);

    return { success: true, filename };
  },

  downloadSelectedFiles: async (shareToken: string, fileIds: number[], password?: string) => {
    const data = { file_ids: fileIds };
    const params = password ? { password } : {};

    const response = await apiClient.post(`/api/data-sharing/public/shared/${shareToken}/files/download-selected`, data, {
      params,
      responseType: 'blob'
    });

    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;

    const contentDisposition = response.headers['content-disposition'];
    const filename = contentDisposition
      ? contentDisposition.split('filename="')[1]?.split('"')[0]
      : `selected_files.zip`;

    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);

    return { success: true, filename, fileCount: fileIds.length };
  },
};
