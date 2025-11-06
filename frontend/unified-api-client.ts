/**
 * Unified API Client for Entrust Data Sharing MCP Platform
 * Provides a simplified interface for API interactions
 */

import axios, { AxiosInstance, AxiosRequestConfig } from 'axios'
import apiConfig from './src/config/api.config'

export interface ApiClientConfig {
  baseURL: string
  timeout?: number
  token?: string
}

export interface ApiResponse<T = any> {
  data: T
  success: boolean
  message?: string
  status: number
}

export class UnifiedApiClient {
  private client: AxiosInstance

  constructor(config: ApiClientConfig) {
    this.client = axios.create({
      baseURL: config.baseURL,
      timeout: config.timeout || 30000,
      headers: {
        'Content-Type': 'application/json',
        ...(config.token && { Authorization: `Bearer ${config.token}` })
      }
    })

    // Request interceptor
    this.client.interceptors.request.use(
      (config) => {
        return config
      },
      (error) => {
        return Promise.reject(error)
      }
    )

    // Response interceptor
    this.client.interceptors.response.use(
      (response) => {
        return response
      },
      (error) => {
        const errorResponse = {
          data: null,
          success: false,
          message: error.response?.data?.detail || error.message || 'An error occurred',
          status: error.response?.status || 500
        }
        return Promise.reject(errorResponse)
      }
    )
  }

  // GET request
  async get<T = any>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    return this.client.get(url, config)
  }

  // POST request
  async post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    return this.client.post(url, data, config)
  }

  // PUT request
  async put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    return this.client.put(url, data, config)
  }

  // DELETE request
  async delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    return this.client.delete(url, config)
  }

  // PATCH request
  async patch<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    return this.client.patch(url, data, config)
  }

  // Update authentication token
  setToken(token: string | null) {
    if (token) {
      this.client.defaults.headers.common['Authorization'] = `Bearer ${token}`
    } else {
      delete this.client.defaults.headers.common['Authorization']
    }
  }

  // Upload files
  async upload<T = any>(
    url: string, 
    file: File, 
    additionalData?: Record<string, any>,
    onProgress?: (progress: number) => void
  ): Promise<ApiResponse<T>> {
    const formData = new FormData()
    formData.append('file', file)
    
    if (additionalData) {
      Object.keys(additionalData).forEach(key => {
        formData.append(key, additionalData[key])
      })
    }

    return this.client.post(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          onProgress(progress)
        }
      }
    })
  }

  // Download files
  async download(url: string, filename?: string): Promise<void> {
    const response = await this.client.get(url, {
      responseType: 'blob'
    })

    const blob = new Blob([response.data])
    const downloadUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = filename || 'download'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(downloadUrl)
  }
}

// Factory function to create API client instances
export function createApiClient(config: ApiClientConfig): UnifiedApiClient {
  return new UnifiedApiClient(config)
}

// Default client instance
export const defaultApiClient = createApiClient({
  baseURL: apiConfig.baseUrl,
  timeout: 30000
})

// Specialized client methods
export const apiClient = {
  // Authentication
  auth: {
    login: (email: string, password: string) => 
      defaultApiClient.post('/api/auth/login', { email, password }),
    
    register: (userData: any) => 
      defaultApiClient.post('/api/auth/register', userData),
    
    logout: () => 
      defaultApiClient.post('/api/auth/logout'),
    
    refresh: () => 
      defaultApiClient.post('/api/auth/refresh'),
    
    profile: () => 
      defaultApiClient.get('/api/auth/me')
  },

  // Datasets
  datasets: {
    list: () => 
      defaultApiClient.get('/api/datasets'),
    
    get: (id: string) => 
      defaultApiClient.get(`/api/datasets/${id}`),
    
    upload: (file: File, metadata: any, onProgress?: (progress: number) => void) => 
      defaultApiClient.upload('/api/datasets/upload', file, metadata, onProgress),
    
    delete: (id: string) => 
      defaultApiClient.delete(`/api/datasets/${id}`),
    
    share: (id: string, shareConfig: any) => 
      defaultApiClient.post(`/api/datasets/${id}/share`, shareConfig),
    
    download: (id: string, filename?: string) => 
      defaultApiClient.download(`/api/datasets/${id}/download`, filename)
  },

  // Organizations
  organizations: {
    list: () => 
      defaultApiClient.get('/api/organizations'),
    
    get: (id: string) => 
      defaultApiClient.get(`/api/organizations/${id}`),
    
    create: (orgData: any) => 
      defaultApiClient.post('/api/organizations', orgData),
    
    update: (id: string, orgData: any) => 
      defaultApiClient.put(`/api/organizations/${id}`, orgData),
    
    delete: (id: string) => 
      defaultApiClient.delete(`/api/organizations/${id}`)
  },

  // Proxy Connectors
  proxy: {
    connectors: {
      list: () => 
        defaultApiClient.get('/api/proxy-connectors'),
      
      create: (connectorData: any) => 
        defaultApiClient.post('/api/proxy-connectors', connectorData),
      
      get: (id: string) => 
        defaultApiClient.get(`/api/proxy-connectors/${id}`),
      
      update: (id: string, connectorData: any) => 
        defaultApiClient.put(`/api/proxy-connectors/${id}`, connectorData),
      
      delete: (id: string) => 
        defaultApiClient.delete(`/api/proxy-connectors/${id}`),
      
      test: (id: string) => 
        defaultApiClient.post(`/api/proxy-connectors/${id}/test`)
    },

    access: {
      mysql: (databaseName: string, token: string, query?: string) => 
        fetch(`${apiConfig.urls.proxy.mysql(databaseName, token)}&query=${encodeURIComponent(query || 'SELECT 1')}`).then(r => r.json()),
      
      postgresql: (databaseName: string, token: string, query?: string) => 
        fetch(`${apiConfig.urls.proxy.postgresql(databaseName, token)}&query=${encodeURIComponent(query || 'SELECT 1')}`).then(r => r.json()),
      
      api: (apiName: string, token: string, endpoint?: string) => 
        fetch(`${apiConfig.urls.proxy.api(apiName, token)}&endpoint=${encodeURIComponent(endpoint || '/posts')}`).then(r => r.json()),
      
      shared: (shareId: string, query?: string) => 
        fetch(`${apiConfig.urls.sharing.public(shareId)}?query=${encodeURIComponent(query || 'SELECT 1')}`).then(r => r.json())
    },

    info: () => 
      defaultApiClient.get('/api/proxy/info'),
    
    health: () => 
      defaultApiClient.get('/api/proxy/health')
  },

  // Data Sharing
  sharing: {
    createLink: (datasetId: string, shareConfig: any) => 
      defaultApiClient.post(`/api/data-sharing/${datasetId}/links`, shareConfig),
    
    getLink: (shareId: string) => 
      defaultApiClient.get(`/api/data-sharing/links/${shareId}`),
    
    accessShared: (shareId: string) => 
      defaultApiClient.get(`/api/data-sharing/shared/${shareId}`),
    
    chat: (shareId: string, message: string) => 
      defaultApiClient.post(`/api/data-sharing/shared/${shareId}/chat`, { message })
  },

  // Analytics
  analytics: {
    overview: () => 
      defaultApiClient.get('/api/analytics/overview'),
    
    usage: (period?: string) => 
      defaultApiClient.get(`/api/analytics/usage${period ? `?period=${period}` : ''}`),
    
    datasets: () => 
      defaultApiClient.get('/api/analytics/datasets'),
    
    organizations: () => 
      defaultApiClient.get('/api/analytics/organizations')
  }
}

export default apiClient