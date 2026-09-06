'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { dataSharingAPI } from '@/lib/api';
import { Eye, Download, MessageSquare, Lock, User, Database, Shield, Copy, BarChart3 } from 'lucide-react';
import { DataVisualization } from '@/components/DataVisualization';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import apiConfig from '@/config/api.config';

interface SharedDataset {
  dataset_id: number;
  dataset_name: string;
  description?: string;
  file_type?: string;
  size_bytes?: number;
  row_count?: number;
  column_count?: number;
  owner_name?: string;
  organization_name?: string;
  shared_at?: string;
  access_allowed: boolean;
  requires_password: boolean;
  enable_chat: boolean;
  preview_data?: any;
  is_uploaded_file?: boolean;
  has_proxy_connection?: boolean;
  proxy_connection_info?: {
    connection_type: string;
    proxy_url: string;
    access_token: string;
    database_name: string;
    supports_sql: boolean;
  };
}

export default function SharedDatasetPage() {
  const params = useParams();
  const token = params.token as string;
  
  const [dataset, setDataset] = useState<SharedDataset | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [showChat, setShowChat] = useState(false);
  const [chatMessage, setChatMessage] = useState('');
  const [chatHistory, setChatHistory] = useState<any[]>([]);
  const [chatSessionToken, setChatSessionToken] = useState<string | undefined>();
  const [isChatting, setIsChatting] = useState(false);
  const [antonAnalysis, setAntonAnalysis] = useState<any>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // File manager state
  const [files, setFiles] = useState<any[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<Set<number>>(new Set());
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isDownloadingFiles, setIsDownloadingFiles] = useState(false);

  const fetchSharedDataset = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const info = await dataSharingAPI.getSharedDatasetInfo(token);
      if (info.password_protected) {
        setDataset({
          dataset_id: 0,
          dataset_name: info.name,
          description: info.description,
          file_type: info.type,
          size_bytes: info.size_bytes,
          row_count: info.row_count,
          column_count: info.column_count,
          access_allowed: false,
          requires_password: true,
          enable_chat: info.chat_enabled
        });
        setShowPasswordForm(true);
        return;
      }

      const response = await dataSharingAPI.getPublicSharedDataset(token);
      setDataset(response);
      setShowPasswordForm(false);
      const session = await dataSharingAPI.createChatSession(token, password || undefined);
      setChatSessionToken(session.session_token);
    } catch (error: any) {
      console.error('Failed to fetch shared dataset:', error);
      if (error.response?.status === 404) {
        setError('Shared dataset not found or no longer available');
      } else {
        setError(error.response?.data?.detail || 'Failed to access shared dataset');
      }
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      fetchSharedDataset();
    }
  }, [token, fetchSharedDataset]);

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      setIsAuthenticating(true);
      setError(null);
      
      const response = await dataSharingAPI.getPublicSharedDataset(token, password);
      setDataset(response);
      setShowPasswordForm(false);
      const session = await dataSharingAPI.createChatSession(token, password || undefined);
      setChatSessionToken(session.session_token);
      setError(null);
    } catch (error: any) {
      console.error('Password authentication failed:', error);
      setError(error.response?.data?.detail || 'Invalid password');
    } finally {
      setIsAuthenticating(false);
    }
  };

  const handleDownload = async () => {
    try {
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      
      // Build download URL with password if needed
      let downloadUrl = `${API_BASE_URL}/api/data-sharing/public/shared/${token}/download`;
      
      // Add password as query parameter if dataset requires it
      if (dataset?.requires_password && password) {
        downloadUrl += `?password=${encodeURIComponent(password)}`;
      }
      
      // Create a fetch request to handle proper file extension from response headers
      const response = await fetch(downloadUrl, {
        method: 'GET'
      });
      
      if (!response.ok) {
        throw new Error(`Download failed: ${response.status}`);
      }
      
      // Extract filename from Content-Disposition header or use dataset info
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = dataset?.dataset_name || 'dataset';
      
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
        if (filenameMatch && filenameMatch[1]) {
          filename = filenameMatch[1].replace(/['"]/g, '');
        }
      } else if (dataset?.file_type) {
        // Add file extension based on file type if not already present
        const extension = dataset.file_type.toLowerCase();
        if (!filename.toLowerCase().endsWith(`.${extension}`)) {
          filename += `.${extension}`;
        }
      }
      
      // Download the file with proper filename
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      
    } catch (error) {
      console.error('Download failed:', error);
      setError('Download failed. Please try again.');
    }
  };

  const formatFileSize = (bytes?: number): string => {
    if (!bytes) return 'Unknown size';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (dateString?: string): string => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    // Simple toast notification - can be enhanced with proper toast library
    const originalTitle = document.title;
    document.title = '✓ Copied to clipboard!';
    setTimeout(() => {
      document.title = originalTitle;
    }, 2000);
  };

  const handleChat = async () => {
    if (!chatMessage.trim() || !token) return;

    const userMessage = chatMessage.trim();
    setChatMessage('');

    // Add user message to history
    const newUserMessage = {
      id: Date.now(),
      type: 'user',
      message: userMessage,
      timestamp: new Date().toISOString()
    };
    setChatHistory(prev => [...prev, newUserMessage]);

    try {
      setIsChatting(true);
      let sessionToken = chatSessionToken;
      if (!sessionToken) {
        const session = await dataSharingAPI.createChatSession(token, password || undefined);
        sessionToken = session.session_token;
        setChatSessionToken(sessionToken);
      }
      const response = await dataSharingAPI.chatWithSharedDataset(token, userMessage, sessionToken, password || undefined);

      // Parse MindsDB agent response if present
      let answerText = response.answer || response.response || 'No response received';

      // Handle AgentCompletion format from MindsDB
      if (typeof answerText === 'string' && answerText.includes('AgentCompletion')) {
        // Extract content from AgentCompletion(content: "...", ...)
        const contentMatch = answerText.match(/content:\s*["`'](.+?)["`']/) ||
                            answerText.match(/content:\s*(.+?)(?:,|\))/);
        if (contentMatch) {
          answerText = contentMatch[1].trim();
        } else {
          // Fallback: try to extract text between quotes
          const simpleMatch = answerText.match(/["'](.+?)["']/);
          if (simpleMatch) {
            answerText = simpleMatch[1];
          }
        }
      }

      // Add AI response to history
      const aiMessage = {
        id: Date.now() + 1,
        type: 'ai',
        message: answerText,
        timestamp: new Date().toISOString(),
        model: response.model,
        source: response.source, // Track if using agent or fallback
        agent_name: response.agent_name, // Track agent name
        tokens_used: response.tokens_used,
        visualizations: response.visualizations,
        dataAnalysis: response.data_analysis,
        hasVisualizations: response.has_visualizations || false,
        error: false
      };
      setChatHistory(prev => [...prev, aiMessage]);

    } catch (error: any) {
      console.error('Chat failed:', error);

      // Add error message to history
      const errorMessage = {
        id: Date.now() + 1,
        type: 'ai',
        message: error.response?.data?.detail || 'Failed to connect to chat service. Please try again.',
        timestamp: new Date().toISOString(),
        error: true
      };
      setChatHistory(prev => [...prev, errorMessage]);
    } finally {
      setIsChatting(false);
    }
  };

  const clearChat = () => {
    setChatHistory([]);
  };

  const handleAntonAnalyze = async (query?: string) => {
    if (!token) return;

    try {
      setIsAnalyzing(true);
      setAnalysisError(null);
      const response = await dataSharingAPI.analyzeSharedDataset(token, {
        query,
        password: password || undefined,
        max_visualizations: 3
      });
      setAntonAnalysis(response);
    } catch (error: any) {
      console.error('Anton analysis failed:', error);
      setAnalysisError(error.response?.data?.detail || 'Anton could not analyze this shared dataset. Please try again.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Fetch files list for multi-file datasets
  const fetchFiles = useCallback(async () => {
    if (!dataset?.preview_data?.type || dataset.preview_data.type !== 'multi_file') return;
    
    try {
      setIsLoadingFiles(true);
      const response = await dataSharingAPI.getSharedDatasetFiles(token, password);
      setFiles(response.files || []);
    } catch (error: any) {
      console.error('Failed to fetch files:', error);
      // Don't show error here as it might be expected for non-multi-file datasets
    } finally {
      setIsLoadingFiles(false);
    }
  }, [token, password, dataset?.preview_data?.type]);
  
  useEffect(() => {
    if (dataset?.preview_data?.type === 'multi_file') {
      fetchFiles();
    }
  }, [dataset?.preview_data?.type, fetchFiles]);
  
  const handleFileSelect = (fileId: number) => {
    const newSelected = new Set(selectedFiles);
    if (newSelected.has(fileId)) {
      newSelected.delete(fileId);
    } else {
      newSelected.add(fileId);
    }
    setSelectedFiles(newSelected);
  };
  
  const handleSelectAll = () => {
    if (selectedFiles.size === files.length) {
      setSelectedFiles(new Set());
    } else {
      setSelectedFiles(new Set(files.map(f => f.id)));
    }
  };
  
  const handleDownloadIndividualFile = async (fileId: number) => {
    try {
      await dataSharingAPI.downloadIndividualFile(token, fileId, password);
    } catch (error) {
      console.error('Individual file download failed:', error);
      setError('File download failed. Please try again.');
    }
  };
  
  const handleDownloadSelectedFiles = async () => {
    if (selectedFiles.size === 0) return;
    
    try {
      setIsDownloadingFiles(true);
      const fileIds = Array.from(selectedFiles);
      await dataSharingAPI.downloadSelectedFiles(token, fileIds, password);
    } catch (error) {
      console.error('Selected files download failed:', error);
      setError('Download failed. Please try again.');
    } finally {
      setIsDownloadingFiles(false);
    }
  };

  const generateConnectionString = (dataset: SharedDataset, token: string): string => {
    // Use the centralized API configuration for consistent URL generation
    return apiConfig.helpers.getConnectionString(
      dataset.file_type || 'api',
      dataset.dataset_name,
      token
    );
  };


  const getSupportedOperations = (fileType?: string): string[] => {
    switch (fileType?.toLowerCase()) {
      case 'mysql':
      case 'postgresql':
      case 'clickhouse':
        return ['SELECT', 'SHOW', 'DESCRIBE'];
      case 's3':
        return ['GET', 'LIST'];
      case 'api':
        return ['GET'];
      case 'mongodb':
        return ['find', 'aggregate'];
      default:
        return ['READ'];
    }
  };

  const antonPrompts = [
    'Give me an executive summary',
    'Find data quality issues',
    'Show key distributions and outliers',
    'Find correlations or relationships',
    'Create charts for important patterns'
  ];

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading shared dataset...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-6">
          <div className="text-center">
            <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-red-100">
              <Lock className="h-6 w-6 text-red-600" />
            </div>
            <h3 className="mt-2 text-lg font-medium text-gray-900">Access Denied</h3>
            <p className="mt-1 text-sm text-gray-500">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (showPasswordForm) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-6">
          <div className="text-center mb-6">
            <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-blue-100">
              <Lock className="h-6 w-6 text-blue-600" />
            </div>
            <h3 className="mt-2 text-lg font-medium text-gray-900">Password Required</h3>
            <p className="mt-1 text-sm text-gray-500">This shared dataset is password protected</p>
          </div>

          <form onSubmit={handlePasswordSubmit}>
            <div className="mb-4">
              <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                Password
              </label>
              <input
                type="password"
                id="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="Enter password"
                required
              />
            </div>

            {error && (
              <div className="mb-4 bg-red-50 border border-red-200 rounded-md p-3">
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={isAuthenticating}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {isAuthenticating ? 'Verifying...' : 'Access Dataset'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  if (!dataset || !dataset.access_allowed) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-6">
          <div className="text-center">
            <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-red-100">
              <Lock className="h-6 w-6 text-red-600" />
            </div>
            <h3 className="mt-2 text-lg font-medium text-gray-900">Access Not Allowed</h3>
            <p className="mt-1 text-sm text-gray-500">You don't have permission to access this dataset</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="bg-white shadow rounded-lg mb-6">
          <div className="px-6 py-4 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">{dataset.dataset_name}</h1>
                {dataset.description && (
                  <p className="mt-1 text-sm text-gray-600">{dataset.description}</p>
                )}
              </div>
              <div className="flex space-x-3">
                {/* Show download for uploaded files or any dataset without proxy connection */}
                {(dataset.is_uploaded_file || !dataset.has_proxy_connection) && (
                  <button
                    onClick={handleDownload}
                    className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </button>
                )}
                {dataset.enable_chat && (
                  <>
                    <button
                      onClick={() => handleAntonAnalyze()}
                      disabled={isAnalyzing}
                      className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50"
                    >
                      <BarChart3 className="h-4 w-4 mr-2" />
                      {isAnalyzing ? 'Analyzing...' : 'Ask Anton to visualize'}
                    </button>
                    <button
                      onClick={() => setShowChat(!showChat)}
                      className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                    >
                      <MessageSquare className="h-4 w-4 mr-2" />
                      {showChat ? 'Hide Anton Chat' : 'Chat with Anton'}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Dataset Info */}
          <div className="px-6 py-4">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div className="flex items-center">
                <Database className="h-5 w-5 text-gray-400 mr-2" />
                <div>
                  <div className="text-sm font-medium text-gray-900">Type</div>
                  <div className="text-sm text-gray-600">{dataset.file_type?.toUpperCase() || 'Unknown'}</div>
                </div>
              </div>
              <div className="flex items-center">
                <Eye className="h-5 w-5 text-gray-400 mr-2" />
                <div>
                  <div className="text-sm font-medium text-gray-900">Size</div>
                  <div className="text-sm text-gray-600">{formatFileSize(dataset.size_bytes)}</div>
                </div>
              </div>
              <div className="flex items-center">
                <User className="h-5 w-5 text-gray-400 mr-2" />
                <div>
                  <div className="text-sm font-medium text-gray-900">Shared by</div>
                  <div className="text-sm text-gray-600">{dataset.owner_name || 'Unknown'}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {dataset.enable_chat && (
          <div className="bg-white shadow rounded-lg mb-6">
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center">
                  <BarChart3 className="h-5 w-5 text-purple-600 mr-2" />
                  <div>
                    <h2 className="text-lg font-medium text-gray-900">Ask Anton to analyze or visualize</h2>
                    <p className="mt-1 text-sm text-gray-600">
                      Use the MindsDB Anton chat flow to ask for summaries, patterns, and charts from this shared data.
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleAntonAnalyze()}
                  disabled={isAnalyzing}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50"
                >
                  {isAnalyzing ? 'Asking Anton...' : 'Ask Anton now'}
                </button>
              </div>
            </div>
            <div className="px-6 py-4 space-y-4">
              <div className="flex flex-wrap gap-2">
                {antonPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => handleAntonAnalyze(prompt)}
                    disabled={isAnalyzing}
                    className="px-3 py-2 text-sm rounded-md border border-purple-200 text-purple-700 bg-purple-50 hover:bg-purple-100 disabled:opacity-50"
                  >
                    {prompt}
                  </button>
                ))}
              </div>

              {analysisError && (
                <div className="bg-red-50 border border-red-200 rounded-md p-3">
                  <p className="text-sm text-red-800">{analysisError}</p>
                </div>
              )}

              {antonAnalysis && (
                <div className="space-y-4">
                  <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-medium text-gray-900">
                        {antonAnalysis.agent_name || 'Anton'} analysis
                      </span>
                      {antonAnalysis.visualization_count > 0 && (
                        <span className="text-xs bg-purple-100 text-purple-800 px-2 py-1 rounded-full">
                          {antonAnalysis.visualization_count} chart{antonAnalysis.visualization_count === 1 ? '' : 's'}
                        </span>
                      )}
                    </div>
                    <MarkdownRenderer content={antonAnalysis.answer || 'No analysis returned.'} />
                  </div>

                  {(antonAnalysis.has_visualizations || antonAnalysis.visualizations || antonAnalysis.data_analysis) && (
                    <DataVisualization
                      visualizations={antonAnalysis.visualizations}
                      dataAnalysis={antonAnalysis.data_analysis}
                    />
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* File Information - Show for uploaded files or datasets without proxy connection */}
        {(dataset.is_uploaded_file || !dataset.has_proxy_connection) && (
          <div className="bg-white shadow rounded-lg mb-6">
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center">
                <Database className="h-5 w-5 text-green-600 mr-2" />
                <h2 className="text-lg font-medium text-gray-900">File Information</h2>
              </div>
              <p className="mt-1 text-sm text-gray-600">
                This is a shared file. You can ask Anton to analyze or visualize it, and download it if permitted.
              </p>
            </div>
            <div className="px-6 py-4">
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center">
                    <Database className="h-5 w-5 text-green-600 mr-2" />
                    <span className="font-medium text-green-900">
                      {dataset.file_type?.toUpperCase() || 'FILE'} File
                    </span>
                  </div>
                  <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded-full">
                    Shared File
                  </span>
                </div>
                
                <div className="text-sm text-green-800">
                  <p className="mb-2">
                    {dataset.preview_data?.type === 'multi_file' 
                      ? `This dataset contains ${dataset.preview_data.total_files} files with various data formats. You can download the files to analyze them locally with your preferred tools.`
                      : `This dataset is a shared file that contains ${dataset.file_type} data. You can download the file to analyze it locally with your preferred tools.`
                    }
                  </p>
                  
                  {/* Multi-file details */}
                  {dataset.preview_data?.type === 'multi_file' && dataset.preview_data.files_list && (
                    <div className="mt-3 mb-3">
                      <h5 className="font-medium text-green-900 mb-2">Files in this dataset:</h5>
                      <div className="space-y-1">
                        {dataset.preview_data.files_list.map((file: any, index: number) => (
                          <div key={index} className="flex items-center text-sm text-green-700">
                            <span className="mr-2">{file.is_primary ? '🔹' : '▫️'}</span>
                            <span className="font-medium">{file.filename}</span>
                            <span className="ml-2 text-green-600">({file.file_type?.toUpperCase()})</span>
                            {file.file_size && (
                              <span className="ml-2 text-green-600">- {formatFileSize(file.file_size)}</span>
                            )}
                            {file.is_primary && (
                              <span className="ml-2 px-2 py-1 bg-green-200 text-green-800 rounded-full text-xs">
                                Primary
                              </span>
                            )}
                          </div>
                        ))}
                        {dataset.preview_data.total_files > dataset.preview_data.files_list.length && (
                          <div className="text-sm text-green-600 italic">
                            ... and {dataset.preview_data.total_files - dataset.preview_data.files_list.length} more files
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  
                  {/* Data statistics */}
                  <div className="flex flex-wrap items-center gap-4 text-sm">
                    {dataset.preview_data?.type === 'multi_file' && (
                      <span>
                        <strong>Files:</strong> {dataset.preview_data.total_files}
                      </span>
                    )}
                    {dataset.row_count && dataset.column_count && (
                      <>
                        <span>
                          <strong>Rows:</strong> {dataset.row_count.toLocaleString()}
                        </span>
                        <span>
                          <strong>Columns:</strong> {dataset.column_count.toLocaleString()}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {/* Download Instructions */}
                <div className="mt-3 pt-3 border-t border-green-200">
                  <h4 className="font-medium text-green-900 mb-2">
                    {dataset.preview_data?.type === 'multi_file' ? 'How to Access These Files' : 'How to Access This File'}
                  </h4>
                  <div className="text-sm text-green-700 space-y-1">
                    {dataset.enable_chat && <p>• Ask Anton to summarize, analyze, or visualize this shared data directly in chat</p>}
                    <p>• Download is optional and only needed if you want to inspect the raw {dataset.preview_data?.type === 'multi_file' ? 'files' : 'file'} locally</p>
                    {dataset.preview_data?.type === 'multi_file' && (
                      <p className="text-green-600 italic">• Anton uses the dataset context and primary tabular file for chart generation when available</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Proxy Connection Details - Only show for connector datasets with proxy connection */}
        {dataset.has_proxy_connection && (
          <div className="bg-white shadow rounded-lg mb-6">
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center">
                <Shield className="h-5 w-5 text-blue-600 mr-2" />
                <h2 className="text-lg font-medium text-gray-900">Third-Party Database Access</h2>
              </div>
              <p className="mt-1 text-sm text-gray-600">
                Ask Anton questions in chat, or connect through this secure proxy from a database client or BI tool
              </p>
            </div>
          <div className="px-6 py-4">
            <div className="grid gap-4">
              {/* Connection Details */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center">
                    <Database className="h-5 w-5 text-blue-600 mr-2" />
                    <span className="font-medium text-blue-900">
                      {dataset.file_type?.toUpperCase() || 'DATABASE'} Connection
                    </span>
                  </div>
                  <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded-full">
                    Secure Proxy
                  </span>
                </div>
                
                {/* Connection String */}
                <div className="mb-3">
                  <label className="block text-sm font-medium text-blue-900 mb-1">
                    Connection String
                  </label>
                  <div className="flex items-center space-x-2">
                    <code className="flex-1 text-sm bg-white border border-blue-200 rounded px-3 py-2 font-mono">
                      {generateConnectionString(dataset, token)}
                    </code>
                    <button
                      onClick={() => copyToClipboard(generateConnectionString(dataset, token))}
                      className="p-2 text-blue-600 hover:bg-blue-100 rounded"
                      title="Copy connection string"
                    >
                      <Copy className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Credentials */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-blue-900 mb-1">
                      Username
                    </label>
                    <div className="flex items-center space-x-2">
                      <code className="flex-1 text-sm bg-white border border-blue-200 rounded px-3 py-2">
                        proxy_user
                      </code>
                      <button
                        onClick={() => copyToClipboard('proxy_user')}
                        className="p-2 text-blue-600 hover:bg-blue-100 rounded"
                        title="Copy username"
                      >
                        <Copy className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-blue-900 mb-1">
                      Password/Token
                    </label>
                    <div className="flex items-center space-x-2">
                      <code className="flex-1 text-sm bg-white border border-blue-200 rounded px-3 py-2 font-mono">
                        {token}
                      </code>
                      <button
                        onClick={() => copyToClipboard(token)}
                        className="p-2 text-blue-600 hover:bg-blue-100 rounded"
                        title="Copy token"
                      >
                        <Copy className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>

                {/* Additional Connection Info */}
                <div className="mt-3 pt-3 border-t border-blue-200">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div>
                      <span className="font-medium text-blue-900">Host:</span>
                      <span className="ml-1 text-blue-700">{typeof window !== 'undefined' ? window.location.hostname : 'localhost'}</span>
                    </div>
                    <div>
                      <span className="font-medium text-blue-900">Port:</span>
                      <span className="ml-1 text-blue-700">8000 (unified)</span>
                    </div>
                    <div>
                      <span className="font-medium text-blue-900">Database:</span>
                      <span className="ml-1 text-blue-700">{dataset.dataset_name}</span>
                    </div>
                    <div>
                      <span className="font-medium text-blue-900">SSL:</span>
                      <span className="ml-1 text-blue-700">Required</span>
                    </div>
                  </div>
                </div>

                {/* Supported Operations */}
                <div className="mt-3 pt-3 border-t border-blue-200">
                  <span className="text-sm font-medium text-blue-900">Supported Operations: </span>
                  <span className="text-sm text-blue-700">
                    {getSupportedOperations(dataset.file_type).join(', ')}
                  </span>
                </div>
              </div>

              {/* Usage Instructions */}
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 mb-2">How to Connect</h4>
                <div className="text-sm text-gray-700 space-y-2">
                  <p>1. Copy the connection string above</p>
                  <p>2. Use it in your preferred database client (DBeaver, TablePlus, etc.)</p>
                  <p>3. Or use the individual credentials for manual configuration</p>
                  <p className="text-xs text-gray-500 mt-2">
                    Note: This is a secure proxy connection that provides read-only access to the shared dataset.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
        )}

        {/* Preview Section */}
        {dataset.preview_data && (
          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-medium text-gray-900">
                {dataset.preview_data.type === 'multi_file' ? 'Dataset Overview & Primary File Preview' : 'Data Preview'}
              </h2>
              {dataset.preview_data.type === 'multi_file' && (
                <p className="text-sm text-gray-600 mt-1">
                  Showing preview of primary file: <strong>{dataset.preview_data.primary_file?.filename}</strong>
                </p>
              )}
            </div>
            <div className="px-6 py-4">
              {/* Multi-file overview */}
              {dataset.preview_data.type === 'multi_file' && (
                <div className="mb-6">
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <div className="flex items-center mb-2">
                      <span className="text-blue-600 text-lg mr-2">📁</span>
                      <h3 className="font-medium text-blue-900">Multi-File Dataset</h3>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm text-blue-800">
                      <div>
                        <span className="font-medium">Total Files:</span>
                        <span className="ml-1">{dataset.preview_data.total_files}</span>
                      </div>
                      <div>
                        <span className="font-medium">Primary File:</span>
                        <span className="ml-1">{dataset.preview_data.primary_file?.filename}</span>
                      </div>
                      <div>
                        <span className="font-medium">File Type:</span>
                        <span className="ml-1">{dataset.preview_data.primary_file?.file_type?.toUpperCase()}</span>
                      </div>
                      <div>
                        <span className="font-medium">Preview Source:</span>
                        <span className="ml-1">Primary File</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
              
              {/* Data table preview */}
              {dataset.preview_data.headers && dataset.preview_data.rows && (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        {dataset.preview_data.headers.map((header: string, index: number) => (
                          <th
                            key={index}
                            scope="col"
                            className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                          >
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {dataset.preview_data.rows.slice(0, 10).map((row: any[], rowIndex: number) => (
                        <tr key={rowIndex} className={rowIndex % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                          {row.map((cell: any, cellIndex: number) => (
                            <td key={cellIndex} className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                              {cell !== null && cell !== undefined ? String(cell) : (
                                <span className="text-gray-400 italic">null</span>
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {dataset.preview_data.total_rows > 10 && (
                    <div className="mt-3 text-sm text-gray-500 text-center">
                      Showing first 10 rows of {dataset.preview_data.total_rows} total rows in {dataset.preview_data.type === 'multi_file' ? 'primary file' : 'dataset'}
                    </div>
                  )}
                </div>
              )}
              
              {/* No preview available message */}
              {(!dataset.preview_data.headers || !dataset.preview_data.rows) && dataset.preview_data.type === 'multi_file' && (
                <div className="text-center py-8">
                  <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 rounded-full flex items-center justify-center">
                    <span className="text-2xl">📁</span>
                  </div>
                  <h3 className="text-lg font-medium text-gray-900 mb-2">Multi-File Dataset</h3>
                  <p className="text-gray-600">
                    This dataset contains {dataset.preview_data.total_files} files. Download the dataset to access all files.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Chat Interface */}
        {showChat && dataset.enable_chat && (
          <div className="bg-white shadow rounded-lg mb-6">
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <MessageSquare className="h-5 w-5 text-blue-600 mr-2" />
                  <h2 className="text-lg font-medium text-gray-900">Anton Data Analyst</h2>
                </div>
                {chatHistory.length > 0 && (
                  <button
                    onClick={clearChat}
                    className="text-sm text-gray-500 hover:text-gray-700"
                  >
                    Clear Chat
                  </button>
                )}
              </div>
              <p className="mt-1 text-sm text-gray-600">
                Ask Anton to analyze, visualize, build a dashboard outline, or answer follow-up questions about this shared dataset
              </p>
            </div>
            
            <div className="px-6 py-4">
              {/* Chat History */}
              {chatHistory.length > 0 && (
                <div className="mb-6 space-y-4 max-h-[600px] overflow-y-auto">
                  {chatHistory.map((message) => (
                    <div key={message.id}>
                      {message.type === 'user' ? (
                        <div className="flex justify-end">
                          <div className="max-w-xs lg:max-w-md px-4 py-2 rounded-lg bg-blue-600 text-white">
                            <div className="text-sm whitespace-pre-wrap">
                              {message.message}
                            </div>
                            <p className="text-xs mt-1 opacity-75">
                              {new Date(message.timestamp).toLocaleTimeString()}
                            </p>
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <div className="flex justify-start">
                            <div className={`max-w-2xl px-4 py-2 rounded-lg ${
                              message.error
                                ? 'bg-red-50 border border-red-200 text-red-700'
                                : 'bg-white border border-gray-200 shadow-sm'
                            }`}>
                              <div className="text-sm">
                                {message.error ? (
                                  <div className="text-red-700 whitespace-pre-wrap">{message.message}</div>
                                ) : (
                                  <MarkdownRenderer content={message.message} />
                                )}
                              </div>
                              <p className="text-xs mt-3 pt-3 border-t border-gray-100 opacity-60">
                                {new Date(message.timestamp).toLocaleTimeString()}
                              </p>
                            </div>
                          </div>
                          
                          {/* Show visualizations if available */}
                          {message.hasVisualizations && (message.visualizations || message.dataAnalysis) && (
                            <div className="ml-0">
                              <DataVisualization
                                visualizations={message.visualizations}
                                dataAnalysis={message.dataAnalysis}
                              />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                  {isChatting && (
                    <div className="flex justify-start">
                      <div className="bg-gray-100 text-gray-900 px-4 py-2 rounded-lg">
                        <div className="flex items-center space-x-2">
                          <div className="animate-spin rounded-full h-4 w-4 border-2 border-gray-300 border-t-blue-600"></div>
                          <span className="text-sm">Anton is thinking...</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Chat Input */}
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Ask a question about the data
                  </label>
                  <div className="flex space-x-3">
                    <input
                      type="text"
                      value={chatMessage}
                      onChange={(e) => setChatMessage(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleChat()}
                      placeholder="Ask Anton to summarize, visualize trends, or draft a dashboard..."
                      className="flex-1 border border-gray-300 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      disabled={isChatting}
                    />
                    <button
                      onClick={handleChat}
                      disabled={!chatMessage.trim() || isChatting}
                      className="px-6 py-3 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isChatting ? (
                        <div className="flex items-center">
                          <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent mr-2"></div>
                          Asking...
                        </div>
                      ) : (
                        <>
                          Ask Anton
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Suggestions */}
                {chatHistory.length === 0 && (
                  <div className="bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-gray-900 mb-3">
                      Try these Anton prompts to get started:
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {antonPrompts.map((suggestion) => (
                        <button
                          key={suggestion}
                          onClick={() => setChatMessage(suggestion)}
                          className="text-left text-sm text-gray-700 hover:text-gray-900 p-3 rounded-lg hover:bg-white hover:shadow-sm transition-all border border-transparent hover:border-blue-200"
                        >
                          "{suggestion}"
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Information */}
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <span className="text-gray-500 text-lg">ℹ️</span>
                    </div>
                    <div className="ml-3">
                      <h4 className="text-sm font-medium text-gray-800">Anton Information</h4>
                      <div className="mt-1 text-sm text-gray-600">
                        <p>
                          Anton uses MindsDB with dataset memory, semantic context, and canonical definitions when available.
                          Ask for summaries, dashboards, charts, caveats, or follow-up analysis in the same chat.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}