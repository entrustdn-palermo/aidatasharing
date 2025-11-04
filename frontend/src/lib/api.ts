import axios from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Create axios instance
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor to include auth token and handle trailing slashes
apiClient.interceptors.request.use(
  (config) => {
    // Check for both token names for backward compatibility
    const token = localStorage.getItem('access_token') || localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Add trailing slash to avoid 307 redirects (FastAPI requirement)
    if (config.url && !config.url.endsWith('/') && !config.url.includes('?')) {
      config.url = config.url + '/';
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor to handle auth errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear both possible token names
      localStorage.removeItem('access_token');
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  login: async (email: string, password: string) => {
    // Use URLSearchParams for proper application/x-www-form-urlencoded encoding
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);

    const response = await apiClient.post('/api/auth/login', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    return response.data;
  },
  
  register: async (userData: {
    email: string;
    password: string;
    full_name: string;
    organization_id?: number;
    create_organization?: boolean;
    organization_name?: string;
  }) => {
    const response = await apiClient.post('/api/auth/register', userData);
    return response.data;
  },
  
  getMe: async () => {
    const response = await apiClient.get('/api/auth/me');
    return response.data;
  },
};

// Admin API
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
    console.log('🔧 Admin datasets API response:', response.data);
    // The backend returns { datasets: [...], total: X, ... }
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
    try {
      console.log('🔄 Calling reload environment variables API...');
      const response = await apiClient.post('/api/admin/environment/environment-variables/reload');
      console.log('✅ Reload API response:', response.data);
      return response.data;
    } catch (error) {
      console.error('❌ Reload API error:', error);
      throw error;
    }
  },

  // Organization management
  getOrganizations: async () => {
    const response = await apiClient.get('/api/admin/organizations');
    return response.data.organizations || response.data; // Handle both response formats
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
    return response.data.users || response.data; // Handle both response formats
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

// Organizations API
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

// Datasets API
export const datasetsAPI = {
  getDatasets: async (params?: {
    skip?: number;
    limit?: number;
    sharing_level?: string;
    dataset_type?: string;
  }) => {
    const response = await apiClient.get('/api/datasets/', { params });
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
    const response = await apiClient.post('/api/datasets/', datasetData);
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

  // Alias for uploadFile to match frontend expectations
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
  
  // Upload multiple files as a single dataset
  uploadMultipleDatasets: async (files: File[], metadata: {
    name: string;
    description?: string;
    sharing_level?: string;
  }) => {
    const formData = new FormData();
    
    // Append all files to the 'files' field
    files.forEach((file) => {
      formData.append('files', file);
    });
    
    // Append metadata
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

  // Download functionality
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

  // Ownership transfer functionality
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

// Data Sharing API
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

  // Chat with shared dataset (public endpoint)
  chatWithSharedDataset: async (shareToken: string, message: string, sessionToken?: string) => {
    const response = await apiClient.post(`/api/data-sharing/public/shared/${shareToken}/chat`, {
      message,
      session_token: sessionToken
    });
    return response.data;
  },
  
  // File management for shared datasets
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
    
    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    
    // Extract filename from content-disposition header
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
    
    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    
    // Extract filename from content-disposition header
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

// Chat API
export const chatAPI = {
  createChatSession: async (shareToken: string) => {
    const response = await apiClient.post('/api/data-sharing/chat/create-session', {
      share_token: shareToken
    });
    return response.data;
  },

  sendMessage: async (sessionToken: string, message: string) => {
    const response = await apiClient.post('/api/data-sharing/chat/message', {
      session_token: sessionToken,
      message
    });
    return response.data;
  },

  getChatHistory: async (sessionToken: string) => {
    const response = await apiClient.get(`/api/data-sharing/chat/${sessionToken}/history`);
    return response.data;
  },

  endChatSession: async (sessionToken: string) => {
    const response = await apiClient.delete(`/api/data-sharing/chat/${sessionToken}`);
    return response.data;
  },
};

// MindsDB API
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

// Models API
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

// Data Access API
export const dataAccessAPI = {
  getAccessibleDatasets: async (params?: {
    search?: string;
    sharing_level?: string;
    department?: string;
  }) => {
    const response = await apiClient.get('/api/data-access/datasets', { params });
    return response.data;
  },

  createAccessRequest: async (requestData: {
    dataset_id: number;
    request_type: 'access' | 'download' | 'share';
    requested_level: 'read' | 'write' | 'admin';
    purpose: string;
    justification: string;
    urgency?: 'low' | 'medium' | 'high';
    category?: 'research' | 'analysis' | 'compliance' | 'reporting' | 'development';
    expiry_date?: string;
  }) => {
    const response = await apiClient.post('/api/data-access/requests', requestData);
    return response.data;
  },

  getAccessRequests: async (params?: {
    status?: string;
    urgency?: string;
    my_requests?: boolean;
  }) => {
    const response = await apiClient.get('/api/data-access/requests', { params });
    return response.data;
  },

  approveAccessRequest: async (requestId: number, approvalData: {
    decision: 'approve' | 'reject';
    reason?: string;
    expiry_date?: string;
  }) => {
    const response = await apiClient.put(`/api/data-access/requests/${requestId}/approve`, approvalData);
    return response.data;
  },

  getAccessRequestDetails: async (requestId: number) => {
    const response = await apiClient.get(`/api/data-access/requests/${requestId}`);
    return response.data;
  },

  cancelAccessRequest: async (requestId: number) => {
    const response = await apiClient.delete(`/api/data-access/requests/${requestId}`);
    return response.data;
  },

  // Notification endpoints
  getNotifications: async (params?: { unread_only?: boolean; limit?: number }) => {
    const response = await apiClient.get('/api/data-access/notifications', { params });
    return response.data;
  },

  markNotificationAsRead: async (notificationId: number) => {
    const response = await apiClient.patch(`/api/data-access/notifications/${notificationId}/read`);
    return response.data;
  },

  markAllNotificationsAsRead: async () => {
    const response = await apiClient.patch('/api/data-access/notifications/mark-all-read');
    return response.data;
  },

  deleteNotification: async (notificationId: number) => {
    const response = await apiClient.delete(`/api/data-access/notifications/${notificationId}`);
    return response.data;
  },

  getAuditTrail: async (params?: {
    start_date?: string;
    end_date?: string;
    action?: string;
    dataset_id?: number;
  }) => {
    const response = await apiClient.get('/api/data-access/audit', { params });
    return response.data;
  },

  sendNotification: async (data: {
    recipient_email: string;
    subject: string;
    message: string;
    notification_type?: string;
  }) => {
    const response = await apiClient.post('/api/data-access/notify', data);
    return response.data;
  },
};

// Analytics API
export const analyticsAPI = {
  getOrganizationAnalytics: async () => {
    const response = await apiClient.get('/api/analytics/organization');
    return response.data;
  },

  getUserActivity: async (params?: {
    start_date?: string;
    end_date?: string;
    user_id?: number;
  }) => {
    const response = await apiClient.get('/api/analytics/user-activity', { params });
    return response.data;
  },

  getDatasetUsage: async (params?: {
    start_date?: string;
    end_date?: string;
    dataset_id?: number;
  }) => {
    const response = await apiClient.get('/api/analytics/dataset-usage', { params });
    return response.data;
  },

  getModelPerformance: async (params?: {
    start_date?: string;
    end_date?: string;
    model_id?: number;
  }) => {
    const response = await apiClient.get('/api/analytics/model-performance', { params });
    return response.data;
  },
};

// Data Connectors API
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

// Proxy Connectors API
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

// Shared Links API
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

// Agents API
export const agentsAPI = {
  // Get available agents
  getAvailableAgents: async () => {
    const response = await apiClient.get('/api/agents/');
    return response.data;
  },

  // Chat with dataset using agents
  chatWithDatasetAgents: async (datasetId: number, message: string, agentName?: string) => {
    const response = await apiClient.post(`/api/agents/datasets/${datasetId}/chat`, {
      message,
      agent_name: agentName
    });
    return response.data;
  },

  // Execute code generated by agents
  executeAgentCode: async (datasetId: number, code: string) => {
    const response = await apiClient.post(`/api/agents/datasets/${datasetId}/execute`, {
      code
    });
    return response.data;
  },

  // Get agent templates
  getAgentTemplates: async () => {
    const response = await apiClient.get('/api/agents/templates');
    return response.data;
  },

  // Get chat history for dataset with agents
  getDatasetChatHistory: async (datasetId: number, limit: number = 50, offset: number = 0) => {
    const response = await apiClient.get(`/api/agents/datasets/${datasetId}/chat/history`, {
      params: { limit, offset }
    });
    return response.data;
  },

  // Health check for agent system
  healthCheck: async () => {
    const response = await apiClient.get('/api/agents/health');
    return response.data;
  }
};

export default apiClient;