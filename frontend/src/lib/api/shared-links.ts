import { apiClient } from './client';

export const sharedLinksAPI = {
  getSharedLinks: async () => {
    const response = await apiClient.get('/api/shared-links');
    return response.data;
  },

  createSharedLink: async (linkData: {
    proxy_connector_id: number;
    name: string;
    description?: string;
    is_public?: boolean;
    requires_authentication?: boolean;
    allowed_users?: string[];
    max_uses?: number;
  }) => {
    const response = await apiClient.post('/api/shared-links', linkData);
    return response.data;
  },

  accessSharedLink: async (shareId: string) => {
    const response = await apiClient.get(`/api/share/${shareId}`);
    return response.data;
  },
};
