'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { SharingLevelSelector, SharingLevelBadge } from '@/components/datasets/SharingLevelSelector';
import { useAuth } from '@/components/auth/AuthProvider';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { datasetsAPI } from '@/lib/api';
import { API_BASE_URL } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export default function DatasetsPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <DatasetsContent />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function DatasetsContent() {
  const { user } = useAuth();
  const [datasets, setDatasets] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');

  useEffect(() => {
    fetchDatasets();
  }, []);

  const fetchDatasets = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await datasetsAPI.getDatasets();
      setDatasets(response);
    } catch (error: any) {
      console.error('Failed to fetch datasets:', error);
      setError(error.response?.data?.detail || 'Failed to fetch datasets');
      setDatasets([]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteDataset = async (datasetId: number, datasetName: string) => {
    if (!confirm(`Are you sure you want to delete the dataset "${datasetName}"? This action cannot be undone.`)) {
      return;
    }

    try {
      await datasetsAPI.deleteDataset(datasetId);
      setDatasets(datasets.filter(dataset => dataset.id !== datasetId));
    } catch (error: any) {
      console.error('Failed to delete dataset:', error);
      alert(error.response?.data?.detail || 'Failed to delete dataset');
    }
  };

  const handleSharingLevelChange = async (datasetId: number, newLevel: 'private' | 'organization' | 'public') => {
    try {
      await datasetsAPI.updateDataset(datasetId, { sharing_level: newLevel });
      setDatasets(datasets.map(dataset => 
        dataset.id === datasetId 
          ? { ...dataset, sharing_level: newLevel }
          : dataset
      ));
    } catch (error: any) {
      console.error('Error updating sharing level:', error);
      alert(error.response?.data?.detail || 'Failed to update sharing level');
    }
  };

  const handleDownloadDataset = async (datasetId: number, datasetName: string, datasetType: string) => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        alert('Authentication required. Please log in again.');
        return;
      }
      
      // Step 1: Get download token from the backend
      const tokenResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/datasets/${datasetId}/download`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!tokenResponse.ok) {
        const errorData = await tokenResponse.json().catch(() => null);
        throw new Error(errorData?.detail?.message || `Failed to initiate download: ${tokenResponse.status}`);
      }
      
      const downloadInfo = await tokenResponse.json();
      
      if (!downloadInfo.download_token) {
        throw new Error('No download token received from server');
      }
      
      const downloadUrl = `${API_BASE_URL}/api/datasets/download/${downloadInfo.download_token}`;
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = downloadUrl;
      a.download = `${datasetName}.${datasetType || 'csv'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      
    } catch (error: any) {
      console.error('Failed to download dataset:', error);
      alert(error.message || 'Failed to download dataset');
    }
  };

  // Filter datasets based on search and type
  const filteredDatasets = datasets.filter(dataset => {
    const matchesSearch = dataset.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         (dataset.description && dataset.description.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesType = filterType === 'all' || dataset.type === filterType;
    return matchesSearch && matchesType;
  });

  const datasetTypes = ['all', ...Array.from(new Set(datasets.map(d => d.type).filter(Boolean)))];

  if (isLoading && datasets.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center space-y-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600"></div>
          <p className="text-gray-600">Loading your datasets...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="py-6 animate-fade-in">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-8">
        {/* Header Section */}
        <div className="mb-8">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between">
            <div className="mb-6 lg:mb-0">
              <h1 className="text-3xl font-bold text-gray-900">Data Management Hub</h1>
              <p className="text-gray-600 mt-2">
                Upload, connect, and manage your data sources with ease
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
              <Link href="/datasets/upload">
                <Button variant="gradient" size="lg" className="w-full sm:w-auto">
                  <span className="mr-2">📤</span>
                  Upload Dataset
                </Button>
              </Link>
              <Link href="/connections">
                <Button variant="outline" size="lg" className="w-full sm:w-auto">
                  <span className="mr-2">🔗</span>
                  Connect Data Source
                </Button>
              </Link>
            </div>
          </div>
        </div>

        {/* Quick Actions Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card variant="elevated" interactive className="hover-lift">
            <CardHeader className="pb-4">
              <div className="flex items-center">
                <div className="w-12 h-12 bg-gradient-to-r from-blue-500 to-blue-600 rounded-lg flex items-center justify-center mr-4">
                  <span className="text-2xl">📊</span>
                </div>
                <div>
                  <CardTitle className="text-lg">File Upload</CardTitle>
                  <CardDescription>CSV, Excel, JSON files</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <Link href="/datasets/upload">
                <Button variant="outline" className="w-full">
                  Upload Files
                </Button>
              </Link>
            </CardContent>
          </Card>

          <Card variant="elevated" interactive className="hover-lift">
            <CardHeader className="pb-4">
              <div className="flex items-center">
                <div className="w-12 h-12 bg-gradient-to-r from-green-500 to-green-600 rounded-lg flex items-center justify-center mr-4">
                  <span className="text-2xl">🗄️</span>
                </div>
                <div>
                  <CardTitle className="text-lg">Database Connector</CardTitle>
                  <CardDescription>MySQL, PostgreSQL, MongoDB</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <Link href="/connections">
                <Button variant="outline" className="w-full">
                  Connect Database
                </Button>
              </Link>
            </CardContent>
          </Card>

          <Card variant="elevated" interactive className="hover-lift">
            <CardHeader className="pb-4">
              <div className="flex items-center">
                <div className="w-12 h-12 bg-gradient-to-r from-purple-500 to-purple-600 rounded-lg flex items-center justify-center mr-4">
                  <span className="text-2xl">🤝</span>
                </div>
                <div>
                  <CardTitle className="text-lg">Shared Data</CardTitle>
                  <CardDescription>Access shared datasets</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <Link href="/datasets/shared">
                <Button variant="outline" className="w-full">
                  View Shared
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>

        {/* Datasets Section */}
        <Card variant="elevated">
          <CardHeader>
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle className="text-xl">Your Datasets</CardTitle>
                <CardDescription>
                  Manage and organize your data collections
                </CardDescription>
              </div>
              <div className="flex flex-col sm:flex-row gap-3 mt-4 lg:mt-0">
                <Link href="/datasets/sharing">
                  <Button variant="secondary" size="sm" className="w-full sm:w-auto">
                    <span className="mr-2">⚙️</span>
                    Manage Sharing
                  </Button>
                </Link>
              </div>
            </div>
          </CardHeader>
          
          <CardContent>
            {/* Search and Filter */}
            <div className="flex flex-col sm:flex-row gap-4 mb-6">
              <div className="flex-1">
                <input
                  type="text"
                  placeholder="Search datasets..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <select
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                {datasetTypes.map(type => (
                  <option key={type} value={type}>
                    {type === 'all' ? 'All Types' : type.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>

            {error && (
              <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.5 0L4.268 18.5c-.77.833.192 2.5 1.732 2.5z" />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <h3 className="text-sm font-medium text-red-800">Error loading datasets</h3>
                    <div className="mt-2 text-sm text-red-700">
                      <p>{error}</p>
                    </div>
                    <div className="mt-3">
                      <Button
                        onClick={fetchDatasets}
                        variant="outline"
                        size="sm"
                      >
                        Try again
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {filteredDatasets.length === 0 && !error && !isLoading ? (
              <div className="text-center py-12">
                <div className="w-24 h-24 mx-auto mb-4 bg-gray-100 rounded-full flex items-center justify-center">
                  <span className="text-4xl">📊</span>
                </div>
                <h3 className="text-lg font-medium text-gray-900 mb-2">
                  {searchTerm || filterType !== 'all' ? 'No matching datasets' : 'No datasets found'}
                </h3>
                <p className="text-gray-600 mb-6">
                  {searchTerm || filterType !== 'all' 
                    ? 'Try adjusting your search or filter criteria.'
                    : 'Get started by uploading your first dataset.'
                  }
                </p>
                {!searchTerm && filterType === 'all' && (
                  <Link href="/datasets/upload">
                    <Button variant="gradient">
                      <span className="mr-2">📤</span>
                      Upload Your First Dataset
                    </Button>
                  </Link>
                )}
              </div>
            ) : filteredDatasets.length > 0 ? (
              <div className="grid gap-4">
                {filteredDatasets.map((dataset) => (
                  <Card key={dataset.id} variant="outlined" interactive className="hover-lift">
                    <CardContent className="p-6">
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center mb-2">
                            <h3 className="text-lg font-semibold text-gray-900 mr-3">
                              {dataset.name}
                            </h3>
                            <SharingLevelBadge level={(dataset.sharing_level?.toLowerCase() || 'private') as 'private' | 'organization' | 'public'} />
                          </div>
                          <p className="text-gray-600 mb-3">
                            {dataset.description || 'No description provided'}
                          </p>
                          <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500">
                            <span className="flex items-center">
                              <span className="mr-1">{dataset.is_multi_file_dataset ? '📁' : '📄'}</span>
                              {dataset.type?.toUpperCase() || 'Unknown'}
                              {dataset.is_multi_file_dataset && (
                                <span className="ml-1 px-2 py-1 bg-blue-100 text-blue-800 rounded-full text-xs">
                                  {dataset.total_files_count || 'Multi'} files
                                </span>
                              )}
                            </span>
                            {dataset.size_bytes && (
                              <span className="flex items-center">
                                <span className="mr-1">💾</span>
                                {formatFileSize(dataset.size_bytes)}
                              </span>
                            )}
                            <span className="flex items-center">
                              <span className="mr-1">📅</span>
                              {new Date(dataset.created_at).toLocaleDateString()}
                            </span>
                          </div>
                        </div>
                        <div className="flex flex-col items-end space-y-3 ml-4">
                          <SharingLevelSelector
                            currentLevel={(dataset.sharing_level?.toLowerCase() || 'private') as 'private' | 'organization' | 'public'}
                            onLevelChange={(level) => handleSharingLevelChange(dataset.id, level)}
                            size="sm"
                          />
                          <div className="flex items-center space-x-2">
                            <Link href={`/datasets/${dataset.id}`}>
                              <Button variant="outline" size="sm">
                                <span className="mr-1">👁️</span>
                                View
                              </Button>
                            </Link>
                            {/* Only show download for uploaded file datasets, not connector datasets */}
                            {dataset.source_url && !dataset.connector_id && (
                              <Button 
                                onClick={() => handleDownloadDataset(dataset.id, dataset.name, dataset.type)}
                                variant="secondary"
                                size="sm"
                                title="Download dataset file"
                              >
                                <span className="mr-1">💾</span>
                                Download
                              </Button>
                            )}
                            <Button 
                              onClick={() => window.open(`/datasets/${dataset.id}/chat`, '_blank')}
                              variant="secondary"
                              size="sm"
                            >
                              <span className="mr-1">💬</span>
                              Chat
                            </Button>
                            <Button 
                              onClick={() => handleDeleteDataset(dataset.id, dataset.name)}
                              variant="destructive"
                              size="sm"
                            >
                              <span className="mr-1">🗑️</span>
                              Delete
                            </Button>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : null}

            {isLoading && datasets.length > 0 && (
              <div className="text-center py-4">
                <div className="inline-flex items-center">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600 mr-2"></div>
                  <span className="text-gray-600">Updating datasets...</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}