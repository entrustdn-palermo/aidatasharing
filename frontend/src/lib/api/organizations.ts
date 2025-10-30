import { apiClient } from './client';

export const organizationsAPI = {
  getOptions: async () => {
    const response = await apiClient.get('/api/organizations/options');
    return response.data;
  },

  create: async (orgData: {
    name: string;
    description?: string;
    type?: string;
    website?: string;
    contact_email?: string;
  }) => {
    const response = await apiClient.post('/api/organizations', orgData);
    return response.data;
  },

  getMy: async () => {
    const response = await apiClient.get('/api/organizations/my');
    return response.data;
  },

  getMembers: async (organizationId: number) => {
    const response = await apiClient.get(`/api/organizations/${organizationId}/members`);
    return response.data;
  },
};
