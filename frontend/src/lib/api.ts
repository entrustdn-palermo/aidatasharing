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
export const adminAPI = {updateConfiguration: async (key: string, config: { value?: string; description?: string }) => {
    const response = await apiClient.put(`/api/admin/config/${key}`, config);
    return response.data;
  },setGoogleApiKey: async (apiKey: string) => {
    const response = await apiClient.post('/api/admin/google-api-key', {
      api_key: apiKey,
    });
    return response.data;
  },// Admin dataset management
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
  },deleteEnvironmentVariable: async (name: string) => {
    const response = await apiClient.delete(`/api/admin/environment/environment-variables/${name}`);
    return response.data;
  },reloadEnvironmentVariables: async () => {
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
  },updateOrganization: async (orgId: number, orgData: {
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
  },updateUser: async (userId: number, userData: {
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

  getMySharedDatasets: async (includeInvalid: boolean = true) => {
    const response = await apiClient.get(`/api/data-sharing/my-shared-datasets?include_invalid=${includeInvalid}`);
    return response.data;
  },

  disableSharing: async (datasetId: number) => {
    const response = await apiClient.delete(`/api/data-sharing/shared/${datasetId}/disable`);
    return response.data;
  },

  createChatSession: async (shareToken: string, password?: string) => {
    const response = await apiClient.post('/api/data-sharing/chat/create-session', {
      share_token: shareToken,
      password
    });
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

  // Chat with shared dataset (public endpoint)
  chatWithSharedDataset: async (shareToken: string, message: string, sessionToken?: string, password?: string) => {
    const response = await apiClient.post(`/api/data-sharing/public/shared/${shareToken}/chat`, {
      message,
      session_token: sessionToken,
      password
    });
    return response.data;
  },

  analyzeSharedDataset: async (shareToken: string, options: {
    query?: string;
    password?: string;
    max_visualizations?: number;
  } = {}) => {
    const response = await apiClient.post(`/api/data-sharing/public/shared/${shareToken}/analyze`, options);
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

// Chat API;

// MindsDB API
export const mindsdbAPI = {
  getStatus: async () => {
    const response = await apiClient.get('/api/mindsdb/status');
    return response.data;
  },
};;

// Models API;

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
;

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
;
;
;

export default apiClient;