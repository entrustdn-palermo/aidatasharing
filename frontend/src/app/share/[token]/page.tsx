'use client';

import { useState, useEffect, useRef } from 'react';
import { useParams } from 'next/navigation';
import { datasetsAPI, dataSharingAPI } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import Link from 'next/link';

export default function SharedDatasetPage() {
  const params = useParams();
  const token = params.token as string;
  
  const [dataset, setDataset] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<any[]>([]);
  const [isLoadingData, setIsLoadingData] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const itemsPerPage = 10;

  // Chat functionality
  const [showChat, setShowChat] = useState(false);
  const [chatMessages, setChatMessages] = useState<Array<{
    id: string;
    message: string;
    response: string;
    timestamp: Date;
  }>>([]);
  const [currentMessage, setCurrentMessage] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (token) {
      fetchSharedDataset();
    }
  }, [token]);

  useEffect(() => {
    // Scroll to bottom of chat when new messages are added
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages]);

  const fetchSharedDataset = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await dataSharingAPI.getSharedDataset(token);
      setDataset(response);
      
      // Also fetch the data
      await fetchSharedData(1);
    } catch (error: any) {
      console.error('Failed to fetch shared dataset:', error);
      setError(error.response?.data?.detail || 'Failed to access shared dataset');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchSharedData = async (page: number) => {
    try {
      setIsLoadingData(true);
      const response = await dataSharingAPI.getSharedDatasetData(token, page, itemsPerPage);
      setData(response.data || []);
      setTotalPages(Math.ceil((response.total || 0) / itemsPerPage));
      setCurrentPage(page);
    } catch (error: any) {
      console.error('Failed to fetch shared data:', error);
      setError(error.response?.data?.detail || 'Failed to load dataset data');
    } finally {
      setIsLoadingData(false);
    }
  };

  const handlePageChange = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      fetchSharedData(page);
    }
  };

  const handleSendMessage = async () => {
    if (!currentMessage.trim() || isChatLoading) return;

    const messageId = Date.now().toString();
    const userMessage = currentMessage.trim();
    setCurrentMessage('');
    setIsChatLoading(true);

    try {
      const response = await dataSharingAPI.chatWithSharedDataset(
        token,
        userMessage,
        sessionToken || undefined
      );

      // If this is the first message and we get a session token, store it
      if (response.session_token && !sessionToken) {
        setSessionToken(response.session_token);
      }

      // Add the message and response to chat history
      setChatMessages(prev => [...prev, {
        id: messageId,
        message: userMessage,
        response: response.response || 'No response received',
        timestamp: new Date()
      }]);

    } catch (error: any) {
      console.error('Chat error:', error);
      setChatMessages(prev => [...prev, {
        id: messageId,
        message: userMessage,
        response: `Error: ${error.response?.data?.detail || 'Failed to send message'}`,
        timestamp: new Date()
      }]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
        <div className="flex items-center justify-center h-screen">
          <div className="flex flex-col items-center space-y-4">
            <div className="h-16 w-16 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600"></div>
            <p className="text-gray-600 text-lg">Loading shared dataset...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
        <div className="flex items-center justify-center h-screen">
          <div className="max-w-md w-full mx-4">
            <Card variant="elevated" className="bg-white shadow-xl">
              <CardContent className="p-8 text-center">
                <div className="w-20 h-20 mx-auto mb-6 bg-red-100 rounded-full flex items-center justify-center">
                  <span className="text-4xl">❌</span>
                </div>
                <h1 className="text-xl font-bold text-gray-900 mb-2">Access Denied</h1>
                <p className="text-gray-600 mb-6">{error}</p>
                <div className="space-y-3">
                  <p className="text-sm text-gray-500">
                    This link may have expired or been revoked.
                  </p>
                  <Link href="/">
                    <Button variant="gradient" className="w-full">
                      Go to Entrust MCP Platform
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  if (!dataset) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
        <div className="flex items-center justify-center h-screen">
          <div className="max-w-md w-full mx-4">
            <Card variant="elevated" className="bg-white shadow-xl">
              <CardContent className="p-8 text-center">
                <div className="w-20 h-20 mx-auto mb-6 bg-gray-100 rounded-full flex items-center justify-center">
                  <span className="text-4xl">❓</span>
                </div>
                <h1 className="text-xl font-bold text-gray-900 mb-2">Dataset Not Found</h1>
                <p className="text-gray-600 mb-6">
                  The shared dataset you're looking for doesn't exist or is no longer available.
                </p>
                <Link href="/">
                  <Button variant="gradient" className="w-full">
                    Go to Entrust MCP Platform
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-3">
              <div className="flex-shrink-0">
                <div className="w-8 h-8 bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                  <span className="text-white font-bold text-sm">AI</span>
                </div>
              </div>
              <div>
                <h1 className="text-lg font-semibold text-gray-900">Entrust MCP Platform</h1>
                <p className="text-xs text-gray-500">Shared Dataset View</p>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                🔗 Shared Access
              </span>
              {dataset.ai_chat_enabled && (
                <Button
                  variant={showChat ? "secondary" : "gradient"}
                  size="sm"
                  onClick={() => setShowChat(!showChat)}
                >
                  <span className="mr-1">💬</span>
                  {showChat ? 'Hide Chat' : 'Chat with Data'}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="py-8 animate-fade-in">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className={`grid gap-8 ${showChat ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'}`}>
            {/* Main Content */}
            <div className="space-y-8">
              {/* Dataset Info */}
              <Card variant="elevated" className="bg-white shadow-lg">
                <CardHeader className="bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-t-lg">
                  <CardTitle className="text-2xl flex items-center">
                    <span className="mr-3">📊</span>
                    {dataset.name}
                  </CardTitle>
                  <CardDescription className="text-blue-100">
                    {dataset.description || 'No description provided'}
                  </CardDescription>
                </CardHeader>
                
                <CardContent className="p-6">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="flex items-center space-x-3">
                      <div className="flex-shrink-0">
                        <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                          <span className="text-blue-600">👤</span>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">Owner</p>
                        <p className="text-sm text-gray-600">{dataset.owner?.username || 'Unknown'}</p>
                      </div>
                    </div>
                    
                    <div className="flex items-center space-x-3">
                      <div className="flex-shrink-0">
                        <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                          <span className="text-green-600">📅</span>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">Created</p>
                        <p className="text-sm text-gray-600">
                          {new Date(dataset.created_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    
                    <div className="flex items-center space-x-3">
                      <div className="flex-shrink-0">
                        <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                          <span className="text-purple-600">🔢</span>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">Records</p>
                        <p className="text-sm text-gray-600">{dataset.record_count || 0}</p>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Data Table */}
              <Card variant="elevated" className="bg-white shadow-lg">
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span className="flex items-center">
                      <span className="mr-2">📋</span>
                      Dataset Preview
                    </span>
                    {isLoadingData && (
                      <div className="flex items-center space-x-2">
                        <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-600 border-t-transparent"></div>
                        <span className="text-sm text-gray-600">Loading...</span>
                      </div>
                    )}
                  </CardTitle>
                  <CardDescription>
                    Viewing page {currentPage} of {totalPages} ({dataset.record_count || 0} total records)
                  </CardDescription>
                </CardHeader>
                
                <CardContent>
                  {data.length === 0 ? (
                    <div className="text-center py-12">
                      <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 rounded-full flex items-center justify-center">
                        <span className="text-2xl">📭</span>
                      </div>
                      <h3 className="text-lg font-medium text-gray-900 mb-2">No data available</h3>
                      <p className="text-gray-600">
                        This dataset doesn't contain any records yet.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {/* Table */}
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                          <thead className="bg-gray-50">
                            <tr>
                              {Object.keys(data[0] || {}).map((key) => (
                                <th
                                  key={key}
                                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                                >
                                  {key}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="bg-white divide-y divide-gray-200">
                            {data.map((row, index) => (
                              <tr key={index} className="hover:bg-gray-50">
                                {Object.values(row).map((value: any, cellIndex) => (
                                  <td
                                    key={cellIndex}
                                    className="px-6 py-4 whitespace-nowrap text-sm text-gray-900"
                                  >
                                    {value !== null && value !== undefined ? String(value) : '-'}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Pagination */}
                      {totalPages > 1 && (
                        <div className="flex items-center justify-between border-t border-gray-200 pt-4">
                          <div className="flex items-center space-x-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handlePageChange(currentPage - 1)}
                              disabled={currentPage === 1 || isLoadingData}
                            >
                              ← Previous
                            </Button>
                            <span className="text-sm text-gray-600">
                              Page {currentPage} of {totalPages}
                            </span>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handlePageChange(currentPage + 1)}
                              disabled={currentPage === totalPages || isLoadingData}
                            >
                              Next →
                            </Button>
                          </div>
                          <div className="text-sm text-gray-500">
                            Showing {((currentPage - 1) * itemsPerPage) + 1} to {Math.min(currentPage * itemsPerPage, dataset.record_count || 0)} of {dataset.record_count || 0} results
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Chat Panel */}
            {showChat && dataset.ai_chat_enabled && (
              <div className="space-y-4">
                <Card variant="elevated" className="bg-white shadow-lg h-[600px] flex flex-col">
                  <CardHeader className="bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-t-lg flex-shrink-0">
                    <CardTitle className="text-lg flex items-center">
                      <span className="mr-2">💬</span>
                      Chat with Dataset
                    </CardTitle>
                    <CardDescription className="text-purple-100">
                      Ask questions about the data and get AI-powered insights
                    </CardDescription>
                  </CardHeader>
                  
                  <CardContent className="flex-1 flex flex-col p-0">
                    {/* Chat Messages */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-4">
                      {chatMessages.length === 0 ? (
                        <div className="text-center py-8">
                          <div className="w-16 h-16 mx-auto mb-4 bg-purple-100 rounded-full flex items-center justify-center">
                            <span className="text-2xl">🤖</span>
                          </div>
                          <h3 className="text-lg font-medium text-gray-900 mb-2">Start a conversation</h3>
                          <p className="text-gray-600 text-sm">
                            Ask questions about the dataset and I'll help you analyze the data.
                          </p>
                          <div className="mt-4 text-xs text-gray-500">
                            <p>Try asking:</p>
                            <p>"What are the main trends in this data?"</p>
                            <p>"Can you summarize the key insights?"</p>
                          </div>
                        </div>
                      ) : (
                        chatMessages.map((chat) => (
                          <div key={chat.id} className="space-y-3">
                            {/* User Message */}
                            <div className="flex justify-end">
                              <div className="max-w-xs lg:max-w-md px-4 py-2 bg-blue-600 text-white rounded-lg rounded-br-none">
                                <p className="text-sm">{chat.message}</p>
                              </div>
                            </div>
                            
                            {/* AI Response */}
                            <div className="flex justify-start">
                              <div className="max-w-xs lg:max-w-md px-4 py-2 bg-gray-100 text-gray-900 rounded-lg rounded-bl-none">
                                <p className="text-sm whitespace-pre-wrap">{chat.response}</p>
                                <p className="text-xs text-gray-500 mt-1">
                                  {chat.timestamp.toLocaleTimeString()}
                                </p>
                              </div>
                            </div>
                          </div>
                        ))
                      )}
                      
                      {isChatLoading && (
                        <div className="flex justify-start">
                          <div className="max-w-xs lg:max-w-md px-4 py-2 bg-gray-100 text-gray-900 rounded-lg rounded-bl-none">
                            <div className="flex items-center space-x-2">
                              <div className="animate-spin rounded-full h-4 w-4 border-2 border-gray-400 border-t-transparent"></div>
                              <span className="text-sm text-gray-600">AI is thinking...</span>
                            </div>
                          </div>
                        </div>
                      )}
                      
                      <div ref={chatEndRef} />
                    </div>
                    
                    {/* Chat Input */}
                    <div className="border-t border-gray-200 p-4 flex-shrink-0">
                      <div className="flex space-x-2">
                        <textarea
                          value={currentMessage}
                          onChange={(e) => setCurrentMessage(e.target.value)}
                          onKeyPress={handleKeyPress}
                          placeholder="Ask a question about the dataset..."
                          className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                          rows={2}
                          disabled={isChatLoading}
                        />
                        <Button
                          onClick={handleSendMessage}
                          disabled={!currentMessage.trim() || isChatLoading}
                          variant="gradient"
                          size="sm"
                          className="self-end"
                        >
                          <span className="mr-1">📤</span>
                          Send
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>

          {/* Footer Info */}
          <div className="mt-8 text-center">
            <Card variant="outlined" className="bg-gray-50 border-gray-200">
              <CardContent className="p-6">
                <div className="flex items-center justify-center space-x-2 text-sm text-gray-600">
                  <span>🔒</span>
                  <span>This is a read-only view of a shared dataset.</span>
                  <span>•</span>
                  <Link href="/" className="text-blue-600 hover:text-blue-700">
                    Create your own account
                  </Link>
                  <span>to upload and share your own datasets.</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}