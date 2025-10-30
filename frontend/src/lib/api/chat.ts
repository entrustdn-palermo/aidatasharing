import { apiClient } from './client';

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
