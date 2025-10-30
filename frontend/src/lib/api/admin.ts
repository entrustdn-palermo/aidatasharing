import { apiClient } from './client';

export const adminAPI = {
  getConfigurations: async () => {
    const response = await apiClient.get('/api/admin/config');
    return response.data;
  },

  createConfiguration: async (config: { key: string; value?: string; description?: string }) => {
    const response = await apiClient.post('/api/admin/config', config);
    return response.data;
  },

  updateConfiguration: async (key: string, config: { value?: string; description?: string }) => {
    const response = await apiClient.put(`/api/admin/config/${key}`, config);
    return response.data;
  },

  deleteConfiguration: async (key: string) => {
    const response = await apiClient.delete(`/api/admin/config/${key}`);
    return response.data;
  },

  setGoogleApiKey: async (apiKey: string) => {
    const response = await apiClient.post('/api/admin/google-api-key', {
      api_key: apiKey,
    });
    return response.data;
  },

  getGoogleApiKeyStatus: async () => {
    const response = await apiClient.get('/api/admin/google-api-key');
    return response.data;
  },

  // Admin dataset management
  getAdminDatasets: async (params?: {
    skip?: number;
    limit?: number;
    include_deleted?: boolean;
    include_inactive?: boolean;
    organization_id?: number;
  }) => {
    const response = await apiClient.get('/api/admin/datasets', { params });
    return response.data;
  },

  deleteAdminDataset: async (datasetId: number, forceDelete: boolean = false) => {
    const response = await apiClient.delete(`/api/admin/datasets/${datasetId}`, {
      params: { force_delete: forceDelete }
    });
    return response.data;
  },

  restoreDataset: async (datasetId: number) => {
    const response = await apiClient.patch(`/api/admin/datasets/${datasetId}/restore`);
    return response.data;
  },

  getAdminDatasetStats: async () => {
    const response = await apiClient.get('/api/admin/datasets/stats');
    return response.data;
  },

  getAdminStats: async () => {
    const response = await apiClient.get('/api/admin/stats');
    return response.data;
  },

  // Environment management
  getEnvironmentVariables: async () => {
    const response = await apiClient.get('/api/admin/environment/environment-variables');
    return response.data;
  },

  updateEnvironmentVariable: async (name: string, value: string) => {
    const response = await apiClient.put(`/api/admin/environment/environment-variables/${name}`, { value });
    return response.data;
  },

  createEnvironmentVariable: async (name: string, value: string) => {
    const response = await apiClient.post('/api/admin/environment/environment-variables', { name, value });
    return response.data;
  },

  deleteEnvironmentVariable: async (name: string) => {
    const response = await apiClient.delete(`/api/admin/environment/environment-variables/${name}`);
    return response.data;
  },

  bulkUpdateEnvironmentVariables: async (updates: Record<string, string>) => {
    const response = await apiClient.post('/api/admin/environment/environment-variables/bulk-update', updates);
    return response.data;
  },

  reloadEnvironmentVariables: async () => {
    const response = await apiClient.post('/api/admin/environment/environment-variables/reload');
    return response.data;
  },

  // Organization management
  getOrganizations: async () => {
    const response = await apiClient.get('/api/admin/organizations');
    return response.data.organizations || response.data;
  },

  createOrganization: async (orgData: {
    name: string;
    description?: string;
    type?: string;
    slug?: string;
    is_active?: boolean;
  }) => {
    const response = await apiClient.post('/api/admin/organizations', orgData);
    return response.data;
  },

  updateOrganization: async (orgId: number, orgData: {
    name?: string;
    description?: string;
    type?: string;
    is_active?: boolean;
  }) => {
    const response = await apiClient.put(`/api/admin/organizations/${orgId}`, orgData);
    return response.data;
  },

  deleteOrganization: async (orgId: number, force: boolean = false) => {
    const response = await apiClient.delete(`/api/admin/organizations/${orgId}`, {
      params: { force }
    });
    return response.data;
  },

  // User management
  getUsers: async (params?: {
    skip?: number;
    limit?: number;
    organization_id?: number;
  }) => {
    const response = await apiClient.get('/api/admin/users', { params });
    return response.data.users || response.data;
  },

  createUser: async (userData: {
    email: string;
    password: string;
    full_name: string;
    role?: string;
    is_active?: boolean;
    is_superuser?: boolean;
    organization_id?: number;
  }) => {
    const response = await apiClient.post('/api/admin/users', userData);
    return response.data;
  },

  updateUser: async (userId: number, userData: {
    full_name?: string;
    role?: string;
    is_active?: boolean;
    is_superuser?: boolean;
    organization_id?: number;
    password?: string;
  }) => {
    const response = await apiClient.put(`/api/admin/users/${userId}`, userData);
    return response.data;
  },

  deleteUser: async (userId: number, force: boolean = true, transferToAdmin: boolean = true) => {
    const response = await apiClient.delete(`/api/admin/users/${userId}`, {
      params: { force, transfer_to_admin: transferToAdmin }
    });
    return response.data;
  },

  // Database cleanup endpoints
  getCleanupStats: async () => {
    const response = await apiClient.get('/api/admin/cleanup/stats');
    return response.data;
  },

  cleanupOrphanedDatasets: async (confirm: boolean = false) => {
    const response = await apiClient.post('/api/admin/cleanup/orphaned-datasets', null, {
      params: { confirm }
    });
    return response.data;
  },

  cleanupEmptyOrganizations: async (confirm: boolean = false) => {
    const response = await apiClient.post('/api/admin/cleanup/empty-organizations', null, {
      params: { confirm }
    });
    return response.data;
  },

  cleanupAllOrphanedData: async (confirm: boolean = false) => {
    const response = await apiClient.post('/api/admin/cleanup/all', null, {
      params: { confirm }
    });
    return response.data;
  },
};
