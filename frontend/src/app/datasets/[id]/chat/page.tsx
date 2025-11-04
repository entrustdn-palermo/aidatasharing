'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { datasetsAPI } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { DataVisualization } from '@/components/DataVisualization';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import Link from 'next/link';

export default function DatasetChatPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <DatasetChatContent />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function DatasetChatContent() {
  const params = useParams();
  const datasetId = parseInt(params.id as string);
  
  const [dataset, setDataset] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chatMessage, setChatMessage] = useState('');
  const [chatHistory, setChatHistory] = useState<any[]>([]);
  const [isChatting, setIsChatting] = useState(false);

  useEffect(() => {
    fetchDataset();
  }, [datasetId]);

  const fetchDataset = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await datasetsAPI.getDataset(datasetId);
      setDataset(response);
    } catch (error: any) {
      console.error('Failed to fetch dataset:', error);
      setError(error.response?.data?.detail || 'Failed to fetch dataset');
    } finally {
      setIsLoading(false);
    }
  };

  const handleChat = async () => {
    if (!chatMessage.trim()) return;
    
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

      // Always use MindsDB agent-based chat (no agent selection needed)
      const response = await datasetsAPI.chatWithDataset(datasetId, userMessage, undefined, true);

      // Add AI response to history
      const aiMessage = {
        id: Date.now() + 1,
        type: 'ai',
        message: response.answer || response.response || 'No response received',
        timestamp: new Date().toISOString(),
        model: response.model,
        tokens_used: response.tokens_used,
        visualizations: response.visualizations || [], // New combined visualizations array
        plotly_figures: response.plotly_figures || [], // Plotly-specific figures
        matplotlib_figures: response.matplotlib_figures || [], // Matplotlib-specific figures
        dataAnalysis: response.data_analysis,
        hasVisualizations: response.has_visualizations || (response.visualizations && response.visualizations.length > 0) || false,
        agent_used: response.agent_used,
        agent_system: response.agent_system,
        planner: response.planner,
        code: response.code,
        execution_output: response.execution_output,
        error: false
      };
      setChatHistory(prev => [...prev, aiMessage]);
      
    } catch (error: any) {
      console.error('Chat failed:', error);
      
      // Add error message to history
      const errorMessage = {
        id: Date.now() + 1,
        type: 'ai',
        message: error.response?.data?.detail || 'Failed to connect to chat service. Please ensure MindsDB is running and properly configured.',
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center space-y-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600"></div>
          <p className="text-gray-600">Loading dataset...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-6">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 md:px-8">
          <Card variant="outlined" className="bg-red-50 border-red-200">
            <CardContent className="p-6">
              <div className="flex">
                <div className="flex-shrink-0">
                  <span className="text-red-400 text-xl">❌</span>
                </div>
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-red-800">Error Loading Dataset</h3>
                  <div className="mt-2 text-sm text-red-700">
                    <p>{error}</p>
                  </div>
                  <div className="mt-3">
                    <Link href="/datasets">
                      <Button variant="outline" size="sm">
                        ← Back to datasets
                      </Button>
                    </Link>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  if (!dataset) {
    return (
      <div className="py-6">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 md:px-8">
          <Card variant="elevated">
            <CardContent className="p-12 text-center">
              <div className="w-24 h-24 mx-auto mb-4 bg-gray-100 rounded-full flex items-center justify-center">
                <span className="text-4xl">❓</span>
              </div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">Dataset not found</h3>
              <p className="text-gray-600 mb-6">
                The dataset you're looking for doesn't exist or you don't have access to it.
              </p>
              <Link href="/datasets">
                <Button variant="gradient">
                  ← Back to datasets
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="py-6 animate-fade-in">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 md:px-8">
        {/* Header */}
        <div className="mb-8">
          <Link
            href={`/datasets/${datasetId}`}
            className="text-sm text-gray-500 hover:text-gray-700 mb-2 inline-block"
          >
            ← Back to dataset
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">
            Chat with "{dataset.name}"
          </h1>
          <div className="flex items-center gap-2 mt-2">
            <p className="text-sm text-gray-600">
              Ask questions about your dataset and get AI-powered insights using MindsDB Agents
            </p>
            {dataset.is_multi_file && (
              <Badge variant="secondary" className="text-xs">
                Multi-file ({dataset.total_files_count} files)
              </Badge>
            )}
          </div>
        </div>

        {/* Chat Interface */}
        <Card variant="elevated">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center">
                  <span className="mr-2">🤖</span>
                  AI Agent Chat
                </CardTitle>
                <CardDescription>
                  {dataset.agent_name ? (
                    <span className="text-blue-600 font-medium">
                      Using MindsDB Agent: {dataset.agent_name}
                    </span>
                  ) : (
                    "Agent will be created on first chat"
                  )}
                </CardDescription>
              </div>
              {chatHistory.length > 0 && (
                <Button variant="outline" size="sm" onClick={clearChat}>
                  Clear Chat
                </Button>
              )}
            </div>
          </CardHeader>
          
          <CardContent>
            {/* Chat History */}
            {chatHistory.length > 0 && (
              <div className="mb-6 space-y-4 max-h-[600px] overflow-y-auto">
                {chatHistory.map((message) => (
                  <div key={message.id}>
                    {message.type === 'user' ? (
                      <div className="flex justify-end">
                        <div className="max-w-xs lg:max-w-md px-4 py-2 rounded-lg bg-blue-600 text-white">
                          <p className="text-sm whitespace-pre-wrap">{message.message}</p>
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

                            <div className="text-xs mt-3 pt-3 border-t border-gray-100 space-y-1">
                              <p className="opacity-60">
                                {new Date(message.timestamp).toLocaleTimeString()}
                              </p>
                              {message.agent_used && (
                                <div className="flex items-center gap-2 text-blue-600">
                                  <span>🤖</span>
                                  <span>Agent: {message.agent_used}</span>
                                </div>
                              )}
                              {message.model && (
                                <p className="opacity-50">
                                  Model: {message.model}
                                </p>
                              )}
                            </div>
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
                        <span className="text-sm">AI is thinking...</span>
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
                  Ask a question about your data
                </label>
                <div className="flex space-x-3">
                  <input
                    type="text"
                    value={chatMessage}
                    onChange={(e) => setChatMessage(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleChat()}
                    placeholder="What insights can you provide about this dataset?"
                    className="flex-1 border border-gray-300 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    disabled={isChatting}
                  />
                  <Button
                    onClick={handleChat}
                    disabled={!chatMessage.trim() || isChatting}
                    variant="gradient"
                    className="px-6"
                  >
                    {isChatting ? (
                      <div className="flex items-center">
                        <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent mr-2"></div>
                        Asking...
                      </div>
                    ) : (
                      <>
                        <span className="mr-1">🚀</span>
                        Ask AI
                      </>
                    )}
                  </Button>
                </div>
              </div>

              {/* Suggestions */}
              {chatHistory.length === 0 && (
                <div className="bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-gray-900 mb-3 flex items-center">
                    <span className="text-xl mr-2">💡</span>
                    Try these examples to get started:
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {(dataset.is_multi_file ? [
                      "📊 What data is in each file?",
                      "🔗 Show me relationships between the files",
                      "📈 Analyze patterns across all files",
                      "💾 Summarize the entire dataset structure",
                      "🔍 What insights can you find across the data?",
                      "📋 Show statistics for all tables",
                      "🎯 How are the files related?",
                      "📊 Create a comprehensive analysis"
                    ] : [
                      "📊 Show visualizations of this dataset",
                      "📈 Analyze the data distribution with charts",
                      "🔍 What are the key patterns and correlations?",
                      "📉 Create statistical analysis with graphs",
                      "💾 Summarize the dataset structure",
                      "📋 Show me data quality issues",
                      "🎯 What insights can you find?",
                      "📊 Create a comprehensive data report"
                    ]).map((suggestion, index) => (
                      <button
                        key={index}
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
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-4">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <span className="text-blue-500 text-lg">🤖</span>
                  </div>
                  <div className="ml-3">
                    <h4 className="text-sm font-medium text-gray-800">MindsDB Agent-Based Chat</h4>
                    <p className="mt-1 text-sm text-gray-600">
                      Ask questions in natural language and get AI-powered insights using MindsDB agents.
                      {dataset.is_multi_file && (
                        <span className="font-medium text-blue-700">
                          {' '}This multi-file dataset uses a single agent with access to all {dataset.total_files_count} files -
                          you can ask questions that span across multiple files!
                        </span>
                      )}
                      {' '}The agent can query your data using SQL, create visualizations, and provide detailed analysis.
                    </p>
                    {!dataset.agent_name && (
                      <p className="mt-2 text-xs text-blue-600 bg-blue-100 px-2 py-1 rounded inline-block">
                        💡 The MindsDB agent will be created automatically when you send your first message
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}