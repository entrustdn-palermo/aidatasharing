import { apiClient } from './client';

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
